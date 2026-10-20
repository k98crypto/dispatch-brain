"""Layer 3 — OpenAI-compatible gateway.

Any OpenAI-compatible client (DeepSeek Harness custom provider, Cua,
OpenAI SDK, curl...) points at this endpoint with model "auto":

    POST /v1/chat/completions   {"model": "auto", "messages": [...]}

The gateway classifies the last user message, picks the target model
from routes.yaml, enforces the per-route max_tokens cap, forwards to
the provider, walks the fallback chain on 5xx/network errors, and logs
the outcome to SQLite.

Streaming (SSE) is supported: chunks are relayed verbatim as they
arrive, and the final chunk's `usage` (when the provider sends one) is
what gets logged. One inherent limit of all streaming proxies: the
fallback chain can only engage *before the first byte is sent* — once
a stream has started it cannot be restarted on another model without
duplicating output, so a mid-stream failure ends the response and is
logged as a failure.

Also exposed: "auto-cheap" / "auto-strong" / "auto-vision" pins, and
every alias from models.yaml passed through directly.

The forwarder is plain httpx — LiteLLM (BerriAI, MIT,
https://github.com/BerriAI/litellm) remains an optional alternative
engine, see config/litellm_config.yaml. No LiteLLM code is vendored here.
"""

from __future__ import annotations

import json
import os
import time

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .classifier import classify
from .config import load_models, load_routes, resolve_api_key, resolve_base_url
from .logstore import LogStore
from .router import Router

app = FastAPI(title="DispatchBrain Gateway", version="0.1.1")

_models = load_models()
_router = Router(load_routes(), _models)
_store: LogStore | None = None


def store() -> LogStore:
    global _store
    if _store is None:
        _store = LogStore()
    return _store


def _check_auth(authorization: str | None) -> None:
    expected = os.environ.get("DISPATCH_BRAIN_API_KEY")
    if expected and authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid gateway api key")


def _last_user_text(messages: list) -> tuple[str, bool]:
    text, has_image = "", False
    for msg in reversed(messages or []):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
                if part.get("type") in ("image_url", "image"):
                    has_image = True
            text = " ".join(parts)
        break
    return text, has_image


def _usage_from_sse_line(line: bytes) -> int:
    """Extract usage.total_tokens from one SSE line; 0 when absent.

    Providers that support `stream_options: {"include_usage": true}`
    send a final chunk carrying usage before `data: [DONE]`.
    """
    s = line.strip()
    if not s.startswith(b"data:"):
        return 0
    data = s[5:].strip()
    if not data or data == b"[DONE]":
        return 0
    try:
        obj = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return 0
    if isinstance(obj, dict):
        usage = obj.get("usage") or {}
        if isinstance(usage, dict):
            return int(usage.get("total_tokens") or 0)
    return 0


def _resolve_chain(payload: dict):
    """Return (chain, scene, difficulty, max_tokens_cap) or a ready
    JSONResponse for the deterministic short-circuit."""
    requested = payload.get("model", "auto")
    messages = payload.get("messages", [])

    if requested in _models:
        return [requested], "direct", "", None

    text, has_image = _last_user_text(messages)
    if requested == "auto":
        c = classify(text, has_image=has_image)
        decision = _router.decide(c)
        if decision.executor == "script":
            return JSONResponse({
                "id": "dispatch-brain",
                "object": "chat.completion",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": (
                            "[DispatchBrain] This looks like a deterministic operation "
                            f"(scene={decision.scene}). Run it as a script instead of "
                            "spending LLM tokens."
                        ),
                    },
                    "finish_reason": "stop",
                }],
                "dispatch_brain": decision.to_dict(),
            })
        if decision.model_alias is None:
            raise HTTPException(status_code=500, detail=f"no model routed for scene {decision.scene}")
        return [decision.model_alias, *decision.fallbacks], decision.scene, decision.difficulty, decision.max_tokens

    if requested in _router.pins:
        decision = _router.pinned(requested)
        return [decision.model_alias, *decision.fallbacks], "pinned", decision.difficulty, decision.max_tokens

    raise HTTPException(status_code=400, detail=f"unknown model: {requested}")


def _upstream_headers(entry: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    key = resolve_api_key(entry)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _forward(alias: str, payload: dict) -> httpx.Response:
    entry = _models[alias]
    base = resolve_base_url(entry)
    body = dict(payload)
    body["model"] = entry["model"]
    with httpx.Client(timeout=300.0, trust_env=False) as client:
        return client.post(f"{base}/chat/completions", json=body,
                           headers=_upstream_headers(entry))


async def _stream_response(chain, payload, scene, difficulty, started):
    """Probe the chain, open the first viable upstream stream, relay it.

    5xx / network failure before the first byte -> next alias.
    A non-200, non-5xx status is passed through with its body.
    """
    last_error = ""
    for alias in chain:
        entry = _models.get(alias)
        if entry is None:
            continue
        base = resolve_base_url(entry)
        body = dict(payload)
        body["model"] = entry["model"]
        body["stream"] = True
        client = httpx.AsyncClient(timeout=300.0, trust_env=False)
        try:
            req = client.build_request("POST", f"{base}/chat/completions",
                                       json=body, headers=_upstream_headers(entry))
            resp = await client.send(req, stream=True)
        except httpx.HTTPError as e:
            last_error = f"{alias}: {e}"
            await client.aclose()
            continue
        if resp.status_code >= 500:
            last_error = f"{alias}: HTTP {resp.status_code}"
            await resp.aclose()
            await client.aclose()
            continue

        async def relay(resp=resp, client=client, alias=alias):
            tokens = 0
            buffer = b""
            ok = resp.status_code == 200
            try:
                async for chunk in resp.aiter_bytes():
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        t = _usage_from_sse_line(line)
                        if t:
                            tokens = t
                    yield chunk
            except httpx.HTTPError:
                ok = False  # mid-stream failure: cannot restart, just end
            finally:
                latency_ms = int((time.monotonic() - started) * 1000)
                store().record(scene=scene, model_alias=alias, success=ok,
                               tokens=tokens, latency_ms=latency_ms,
                               difficulty=difficulty)
                await resp.aclose()
                await client.aclose()

        return StreamingResponse(relay(), status_code=resp.status_code,
                                 media_type="text/event-stream")

    store().record(scene=scene, model_alias=chain[0] if chain else None,
                   success=False, difficulty=difficulty, note=last_error)
    raise HTTPException(status_code=502, detail=f"all upstreams failed: {last_error}")


@app.get("/healthz")
def healthz():
    return {"ok": True, "models": sorted(_models.keys())}


@app.get("/v1/models")
def list_models():
    ids = ["auto", *_router.pins.keys(), *_models.keys()]
    return {"object": "list", "data": [{"id": i, "object": "model"} for i in ids]}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    payload = await request.json()

    resolved = _resolve_chain(payload)
    if isinstance(resolved, JSONResponse):
        return resolved
    chain, scene, difficulty, max_tokens_cap = resolved

    if max_tokens_cap:
        payload["max_tokens"] = min(int(payload.get("max_tokens") or max_tokens_cap), max_tokens_cap)

    started = time.monotonic()
    if payload.get("stream"):
        return await _stream_response(chain, payload, scene, difficulty, started)

    last_error = ""
    for alias in chain:
        if alias not in _models:
            continue
        try:
            resp = _forward(alias, payload)
        except httpx.HTTPError as e:
            last_error = f"{alias}: {e}"
            continue
        if resp.status_code >= 500:
            last_error = f"{alias}: HTTP {resp.status_code}"
            continue
        latency_ms = int((time.monotonic() - started) * 1000)
        data = resp.json()
        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        store().record(
            scene=scene,
            model_alias=alias,
            success=resp.status_code == 200,
            tokens=int(usage.get("total_tokens", 0) or 0),
            latency_ms=latency_ms,
            difficulty=difficulty,
        )
        if isinstance(data, dict):
            data.setdefault("dispatch_brain", {"routed_to": alias, "scene": scene})
        return JSONResponse(content=data, status_code=resp.status_code)

    store().record(scene=scene, model_alias=chain[0] if chain else None,
                   success=False, difficulty=difficulty, note=last_error)
    raise HTTPException(status_code=502, detail=f"all upstreams failed: {last_error}")


def run(host: str = "127.0.0.1", port: int = 8787) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
