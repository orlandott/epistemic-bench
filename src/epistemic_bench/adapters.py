"""Model access (SPEC §7.2).

The *entire* abstraction is a ``{provider: call_fn}`` dict where each call_fn is
``(prompt, params) -> awaitable[str]``. Real providers are key-gated stubs (the
SDKs are optional deps); a deterministic ``mock`` provider drives the pipeline
end to end without network or keys.

The mock is a **synthetic data generator for demos/tests, not a model.** It is
constructed with access to ground truth (via a closure over the item bank) so it
can emit controllable accuracy/confidence per model. Real adapters never receive
ground truth. Any leaderboard built from mock data is stamped ``demo: true``.
"""

from __future__ import annotations

import random
import zlib
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Mapping

import yaml

from .types import Item, ModelInfo

CallFn = Callable[[str, Mapping[str, Any]], Awaitable[str]]


def _stub(provider: str, pkg: str, env: str) -> CallFn:
    async def call(prompt: str, params: Mapping[str, Any]) -> str:
        raise RuntimeError(
            f"provider '{provider}' is not configured in this build. "
            f"Install `{pkg}`, set {env}, and wire the real call in adapters.py."
        )

    return call


# Real providers: stubs until configured. Shape matches the spec's ADAPTERS dict.
ADAPTERS: dict[str, CallFn] = {
    "anthropic": _stub("anthropic", "anthropic", "ANTHROPIC_API_KEY"),
    "openai": _stub("openai", "openai", "OPENAI_API_KEY"),
    "google": _stub("google", "google-generativeai", "GOOGLE_API_KEY"),
    "openweights": _stub("openweights", "<your-runtime>", "OPENWEIGHTS_ENDPOINT"),
}


def get_call_fn(provider: str) -> CallFn:
    if provider not in ADAPTERS:
        raise KeyError(f"no adapter for provider {provider!r}")
    return ADAPTERS[provider]


def load_models(path: Path | str) -> tuple[dict[str, ModelInfo], dict[str, dict], int]:
    """Parse a models YAML file into (registry, mock_profiles, seed)."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    seed = int(data.get("seed", 0))
    registry: dict[str, ModelInfo] = {}
    profiles: dict[str, dict] = {}
    for m in data["models"]:
        info = ModelInfo(
            id=m["id"],
            provider=m["provider"],
            maker=m.get("maker", ""),
            display_name=m.get("display_name", m["id"]),
            version=m.get("version", ""),
        )
        registry[info.id] = info
        if "mock" in m:
            profiles[info.id] = m["mock"]
    return registry, profiles, seed


def _rng(seed: int, *parts: str) -> random.Random:
    key = "|".join([str(seed), *parts]).encode("utf-8")
    return random.Random(zlib.crc32(key))


def _synth_response(item: Item, model_id: str, profile: Mapping[str, Any], seed: int) -> str:
    """Deterministic synthetic completion for the mock provider."""
    rng = _rng(seed, model_id, item.id)
    rf = item.response_format

    if rf.type == "mcq" and rf.require_confidence:
        options = [str(o).strip().upper() for o in (rf.options or ["A", "B", "C", "D"])]
        correct = (item.reference.answer or options[0]).strip().upper()
        difficulty = item.difficulty or "medium"
        acc_map = profile.get("accuracy", {}) or {}
        acc = float(acc_map.get(difficulty, 0.7))
        bias = float(profile.get("confidence_bias", 0.0))
        noise = float(profile.get("confidence_noise", 0.05))

        is_correct = rng.random() < acc
        if is_correct:
            answer = correct
        else:
            distractors = [o for o in options if o != correct] or [correct]
            answer = rng.choice(distractors)

        conf = acc + bias + rng.gauss(0.0, noise) + (0.06 if is_correct else -0.06)
        conf = min(0.99, max(0.02, conf))
        return f"ANSWER: {answer}  CONFIDENCE: {conf:.2f}"

    if rf.type == "stance":
        lo, hi = (rf.stance_scale or [1, 5])
        return f"STANCE: {rng.randint(int(lo), int(hi))}  (synthetic)"

    if rf.type == "mcq":
        return f"CHOICE: {rng.choice([str(o).strip().upper() for o in (rf.options or ['A'])])}"

    return "(synthetic mock response)"


def make_mock_adapter(items_by_id: Mapping[str, Item], profiles: Mapping[str, dict], seed: int) -> CallFn:
    async def call(prompt: str, params: Mapping[str, Any]) -> str:
        item = items_by_id[params["item_id"]]
        return _synth_response(item, params["model_id"], profiles.get(params["model_id"], {}), seed)

    return call


def build_adapters(
    registry: Mapping[str, ModelInfo],
    items: Iterable[Item],
    profiles: Mapping[str, dict],
    seed: int,
) -> dict[str, CallFn]:
    """Compose the provider dict for a run: real stubs + a wired mock provider."""
    items_by_id = {it.id: it for it in items}
    return {**ADAPTERS, "mock": make_mock_adapter(items_by_id, profiles, seed)}
