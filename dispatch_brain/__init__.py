"""DispatchBrain — a dispatch/routing layer that sits between an agent
runtime (e.g. DeepSeek Harness, a Cua-based computer-use agent, or any
OpenAI-compatible client) and the model providers behind it.

Layers:
  1. classifier — cheap, deterministic task classification (no LLM call)
  2. router     — static routing table + per-task budget caps
  3. gateway    — OpenAI-compatible HTTP endpoint ("model: auto")
  4. watchdog   — step/token/time budgets + no-progress detection
  5. logstore   — SQLite task log; the raw material for V2 self-tuning

All code in this package is original (MIT). Third-party projects that
inspired the design are credited in README.md and in module docstrings;
none of their code is copied.
"""

__version__ = "0.1.1"
