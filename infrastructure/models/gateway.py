"""Model gateway: capability-based routing to LLMs (architecture §24).

Agents request capabilities (planning/classification/extraction/reasoning);
the gateway picks the model, tracks usage and cost. Phase 1 ships a
deterministic fake + optional real adapter; routing stays in one place.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelReply:
    text: str
    model_id: str
    cost_cents: int = 0
    tokens: int = 0


class ModelAdapter(Protocol):
    def complete(self, capability: str, prompt: str, params: dict[str, Any]) -> ModelReply: ...


class FakeModel:
    """Deterministic reply for tests/dev; records every call."""

    def __init__(self, model_id: str = "fake-model-v1", replies: dict[str, str] | None = None):
        self.model_id = model_id
        self._replies = replies or {}
        self.calls: list[tuple[str, str]] = []

    def complete(self, capability: str, prompt: str, params: dict[str, Any]) -> ModelReply:
        self.calls.append((capability, prompt))
        text = self._replies.get(capability, f"[{capability}] ok")
        return ModelReply(text=text, model_id=self.model_id, cost_cents=1, tokens=len(prompt) // 4)


class ModelGateway:
    def __init__(self):
        self._adapters: dict[str, list[tuple[int, ModelAdapter]]] = {}

    def register(self, capability: str, adapter: ModelAdapter, priority: int = 100) -> None:
        self._adapters.setdefault(capability, []).append((priority, adapter))
        self._adapters[capability].sort(key=lambda p: p[0])

    def complete(self, capability: str, prompt: str,
                 params: dict[str, Any] | None = None) -> ModelReply:
        last_error = "no adapter registered"
        for _, adapter in self._adapters.get(capability, []):
            try:
                return adapter.complete(capability, prompt, params or {})
            except Exception as exc:  # noqa: BLE001 — fallback to next model
                last_error = f"{type(exc).__name__}: {exc}"
        raise RuntimeError(f"model gateway: capability {capability} failed: {last_error}")
