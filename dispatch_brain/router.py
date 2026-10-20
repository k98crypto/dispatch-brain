"""Layer 2 — routing policy: classification + routing table -> decision.

Design credit: the strong/weak model split with an explicit cost/quality
trade-off per request follows RouteLLM (LMSYS,
https://github.com/lm-sys/RouteLLM, Apache-2.0). RouteLLM itself is
unmaintained since 2024-08 and is NOT a dependency of this project;
only the design idea is adopted, implemented here as a plain YAML table
so the "brain" stays inspectable and hand-editable.

The cascade order (cheap first, escalate on failure) follows the
FrugalGPT paper (Chen et al., 2023) — a paper, no code involved.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .classifier import Classification


@dataclass
class RouteDecision:
    scene: str
    difficulty: str
    executor: str                 # script | llm | gui
    model_alias: str | None       # key into models.yaml; None for script executor
    fallbacks: list[str] = field(default_factory=list)
    reasoning: str = "medium"     # off | low | medium | high
    max_tokens: int = 8000
    max_steps: int = 40
    max_seconds: int = 900
    needs_human_confirm: bool = False   # True when risk == high
    needs_vision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class Router:
    def __init__(self, routes: dict, models: dict):
        self.routes = routes or {}
        self.models = models or {}
        self.defaults = self.routes.get("defaults", {}) or {}
        self.scenes = self.routes.get("scenes", {}) or {}
        self.pins = self.routes.get("pins", {}) or {}

    # -- pinned virtual models: auto-cheap / auto-strong / auto-vision ----
    def pinned(self, pin_name: str) -> RouteDecision | None:
        pin = self.pins.get(pin_name)
        if not pin:
            return None
        return RouteDecision(
            scene="pinned",
            difficulty=pin.get("difficulty", "standard"),
            executor="llm",
            model_alias=pin.get("model"),
            fallbacks=pin.get("fallbacks", []),
            reasoning=pin.get("reasoning", "medium"),
            max_tokens=int(pin.get("max_tokens", self.defaults.get("max_tokens", 8000))),
            max_steps=int(self.defaults.get("max_steps", 40)),
            max_seconds=int(self.defaults.get("max_seconds", 900)),
            needs_vision=bool(pin.get("vision", False)),
        )

    def decide(self, c: Classification) -> RouteDecision:
        scene_cfg = self.scenes.get(c.scene) or self.scenes.get("chat") or {}
        tier = scene_cfg.get(c.difficulty) or scene_cfg.get("standard") or {}

        max_tokens = int(tier.get("max_tokens", self.defaults.get("max_tokens", 8000)))
        return RouteDecision(
            scene=c.scene,
            difficulty=c.difficulty,
            executor=tier.get("executor", c.executor),
            model_alias=tier.get("model"),
            fallbacks=list(tier.get("fallbacks", [])),
            reasoning=tier.get("reasoning", "medium"),
            max_tokens=max_tokens,
            max_steps=int(tier.get("max_steps", self.defaults.get("max_steps", 40))),
            max_seconds=int(tier.get("max_seconds", self.defaults.get("max_seconds", 900))),
            needs_human_confirm=(c.risk == "high"),
            needs_vision=c.needs_vision,
        )
