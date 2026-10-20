"""Config loading: models.yaml (registry) + routes.yaml (routing table).

API keys are NEVER read from these files. Each model entry names the
environment variable that holds its key (`api_key_env`).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


def config_dir() -> Path:
    env = os.environ.get("DISPATCH_BRAIN_CONFIG")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent.parent / "config"
    if here.exists():
        return here
    return Path.cwd() / "config"


def load_models(path: Path | None = None) -> dict:
    p = path or (config_dir() / "models.yaml")
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("models", {})


def load_routes(path: Path | None = None) -> dict:
    p = path or (config_dir() / "routes.yaml")
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_base_url(entry: dict) -> str:
    """base_url may be overridden by an env var (e.g. LOCAL_LLM_BASE_URL)."""
    override_env = entry.get("base_url_env")
    if override_env and os.environ.get(override_env):
        return os.environ[override_env].rstrip("/")
    return str(entry.get("base_url", "")).rstrip("/")


def resolve_api_key(entry: dict) -> str | None:
    env_name = entry.get("api_key_env")
    if not env_name:
        return None
    return os.environ.get(env_name) or None
