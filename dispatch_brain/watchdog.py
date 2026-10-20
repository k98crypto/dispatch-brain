"""Layer 4 — watchdog for agent loops.

Built for the two failure modes users actually hit with long agent runs:
  1. token burn — a runaway loop quietly eats the API balance;
  2. self-stuck — the agent repeats the same action (or actions that
     change nothing) and never notices.

The watchdog is a small state machine fed by the agent runtime after
every step. It returns one of:
  "ok"               — keep going
  "replan_escalate"  — no progress detected: interrupt once, compress
                       context, re-plan with the stronger fallback model
  "stop"             — hard budget exhausted, or stuck again after the
                       one allowed re-plan: stop and report to the human

Original implementation; no third-party code.
"""

from __future__ import annotations

import hashlib
import time


def signature(tool_name: str, args: str, state_hash: str) -> str:
    """Hash one step: (what was tried) + (what the world looked like)."""
    h = hashlib.sha256()
    h.update(tool_name.encode("utf-8", "ignore"))
    h.update(b"\x00")
    h.update((args or "").encode("utf-8", "ignore"))
    h.update(b"\x00")
    h.update((state_hash or "").encode("utf-8", "ignore"))
    return h.hexdigest()[:16]


class Watchdog:
    def __init__(
        self,
        max_steps: int = 40,
        max_tokens: int = 60000,
        max_seconds: int = 900,
        repeat_limit: int = 3,
    ):
        self.max_steps = max_steps
        self.max_tokens = max_tokens
        self.max_seconds = max_seconds
        self.repeat_limit = repeat_limit

        self.steps = 0
        self.tokens = 0
        self.started = time.monotonic()
        self._seen: dict[str, int] = {}
        self._last_state: str | None = None
        self._no_change_streak = 0
        self._replanned = False

    def observe(
        self,
        tool_name: str,
        args: str = "",
        state_hash: str = "",
        tokens_used: int = 0,
    ) -> str:
        """Call after every agent step. Returns the verdict string."""
        self.steps += 1
        self.tokens += max(0, int(tokens_used))

        # hard budgets first — these never negotiate
        if self.steps > self.max_steps:
            return "stop"
        if self.tokens > self.max_tokens:
            return "stop"
        if time.monotonic() - self.started > self.max_seconds:
            return "stop"

        sig = signature(tool_name, args, state_hash)
        self._seen[sig] = self._seen.get(sig, 0) + 1

        if state_hash and state_hash == self._last_state:
            self._no_change_streak += 1
        else:
            self._no_change_streak = 0
        if state_hash:
            self._last_state = state_hash

        repeated = self._seen[sig] >= self.repeat_limit
        frozen = self._no_change_streak >= self.repeat_limit
        if repeated or frozen:
            if not self._replanned:
                self._replanned = True
                # give the re-plan a clean slate on loop detection
                self._seen.clear()
                self._no_change_streak = 0
                return "replan_escalate"
            return "stop"

        return "ok"

    def status(self) -> dict:
        return {
            "steps": self.steps,
            "tokens": self.tokens,
            "elapsed_seconds": round(time.monotonic() - self.started, 1),
            "replanned": self._replanned,
        }
