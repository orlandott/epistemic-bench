"""Model access (SPEC §7.2).

The *entire* abstraction is a ``{provider: call_fn}`` dict where each call_fn is
``(prompt, params) -> awaitable[str | (str, usage_dict)]``. Real providers are
implemented behind lazy imports of their optional SDK dependencies
(``pip install 'epistemic-bench[anthropic]'`` etc.) plus an API-key environment
variable; a deterministic ``mock`` provider drives the pipeline end to end
without network or keys.

A missing SDK or key raises ``AdapterConfigError`` — the runner captures it on
the Completion without retrying (retries are for transient failures only). Real
adapters use ``params['model_version']`` (the pinned version from the model
registry) as the concrete API model name, falling back to ``params['model']``.

The mock is a **synthetic data generator for demos/tests, not a model.** It is
constructed with access to ground truth (via a closure over the item bank) so it
can emit controllable accuracy/confidence per model. Real adapters never receive
ground truth. Any leaderboard built from mock data is stamped ``demo: true``.
"""

from __future__ import annotations

import asyncio
import os
import random
import zlib
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Mapping, Tuple, Union

import yaml

from .types import Item, ModelInfo

# Adapters may return the raw text alone, or (text, usage) where usage carries
# provider metadata such as token counts; the runner normalizes either shape.
AdapterResult = Union[str, Tuple[str, Mapping[str, Any]]]
CallFn = Callable[[str, Mapping[str, Any]], Awaitable[AdapterResult]]


class AdapterConfigError(RuntimeError):
    """Provider is not usable as configured (missing SDK or API key).

    Raised instead of a transient error so the runner records it once instead of
    retrying with backoff.
    """


def _model_name(params: Mapping[str, Any]) -> str:
    return str(params.get("model_version") or params.get("model") or "")


def _require_env(provider: str, name: str) -> str:
    val = os.environ.get(name, "")
    if not val:
        raise AdapterConfigError(f"provider '{provider}' requires the {name} environment variable")
    return val


def _require_sdk(provider: str, module: str, extra: str):
    try:
        import importlib

        return importlib.import_module(module)
    except ImportError as e:
        raise AdapterConfigError(
            f"provider '{provider}' requires the `{module.split('.')[0]}` SDK: "
            f"pip install 'epistemic-bench[{extra}]'"
        ) from e


def _make_anthropic() -> CallFn:
    client = None  # cached per process; each CLI invocation runs one event loop

    async def call(prompt: str, params: Mapping[str, Any]) -> AdapterResult:
        nonlocal client
        anthropic = _require_sdk("anthropic", "anthropic", "anthropic")
        _require_env("anthropic", "ANTHROPIC_API_KEY")
        if client is None:
            client = anthropic.AsyncAnthropic()
        resp = await client.messages.create(
            model=_model_name(params),
            max_tokens=int(params.get("max_tokens", 1024)),
            temperature=float(params.get("temperature", 0.0)),
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        u = getattr(resp, "usage", None)
        usage = {"input_tokens": getattr(u, "input_tokens", None), "output_tokens": getattr(u, "output_tokens", None)}
        return text, usage

    return call


def _make_openai_compatible(provider: str, *, key_env: str, base_url_env: str | None = None) -> CallFn:
    """OpenAI adapter; with ``base_url_env`` it also serves any OpenAI-compatible
    endpoint (vLLM, TGI, llama.cpp server, hosted open-weight providers)."""
    client = None

    async def call(prompt: str, params: Mapping[str, Any]) -> AdapterResult:
        nonlocal client
        openai = _require_sdk(provider, "openai", "openai")
        if client is None:
            if base_url_env:
                base_url = os.environ.get(base_url_env, "")
                if not base_url:
                    raise AdapterConfigError(
                        f"provider '{provider}' requires the {base_url_env} environment variable "
                        "(an OpenAI-compatible endpoint URL)"
                    )
                client = openai.AsyncOpenAI(base_url=base_url, api_key=os.environ.get(key_env, "EMPTY"))
            else:
                _require_env(provider, key_env)
                client = openai.AsyncOpenAI()
        resp = await client.chat.completions.create(
            model=_model_name(params),
            messages=[{"role": "user", "content": prompt}],
            temperature=float(params.get("temperature", 0.0)),
            max_tokens=int(params.get("max_tokens", 1024)),
        )
        text = (resp.choices[0].message.content or "") if resp.choices else ""
        u = getattr(resp, "usage", None)
        usage = {"input_tokens": getattr(u, "prompt_tokens", None), "output_tokens": getattr(u, "completion_tokens", None)}
        return text, usage

    return call


def _make_google() -> CallFn:
    async def call(prompt: str, params: Mapping[str, Any]) -> AdapterResult:
        genai = _require_sdk("google", "google.generativeai", "google")
        key = _require_env("google", "GOOGLE_API_KEY")
        genai.configure(api_key=key)
        model = genai.GenerativeModel(_model_name(params))

        def _generate():
            return model.generate_content(
                prompt,
                generation_config={
                    "temperature": float(params.get("temperature", 0.0)),
                    "max_output_tokens": int(params.get("max_tokens", 1024)),
                },
            )

        resp = await asyncio.to_thread(_generate)  # SDK is sync; keep the loop free
        try:
            text = resp.text
        except Exception:  # blocked/empty candidates: extract what parts exist
            parts = []
            for cand in getattr(resp, "candidates", None) or []:
                for part in getattr(getattr(cand, "content", None), "parts", None) or []:
                    t = getattr(part, "text", None)
                    if t:
                        parts.append(t)
            text = "".join(parts)
        um = getattr(resp, "usage_metadata", None)
        usage = (
            {"input_tokens": getattr(um, "prompt_token_count", None), "output_tokens": getattr(um, "candidates_token_count", None)}
            if um is not None
            else {}
        )
        return text, usage

    return call


# Real providers (SPEC §7.2): lazy SDK imports + env keys; the shape stays a dict.
ADAPTERS: dict[str, CallFn] = {
    "anthropic": _make_anthropic(),
    "openai": _make_openai_compatible("openai", key_env="OPENAI_API_KEY"),
    "google": _make_google(),
    "openweights": _make_openai_compatible(
        "openweights", key_env="OPENWEIGHTS_API_KEY", base_url_env="OPENWEIGHTS_BASE_URL"
    ),
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


def _clamp_conf(x: float) -> float:
    return min(0.99, max(0.02, x))


def _synth_calibration(item: Item, model_id: str, profile: Mapping[str, Any], seed: int) -> str:
    rng = _rng(seed, "cal", model_id, item.id)
    rf = item.response_format
    options = [str(o).strip().upper() for o in (rf.options or ["A", "B", "C", "D"])]
    correct = (item.reference.answer or options[0]).strip().upper()
    acc = float((profile.get("accuracy", {}) or {}).get(item.difficulty or "medium", 0.7))
    bias = float(profile.get("confidence_bias", 0.0))
    noise = float(profile.get("confidence_noise", 0.05))

    is_correct = rng.random() < acc
    answer = correct if is_correct else rng.choice([o for o in options if o != correct] or [correct])
    conf = _clamp_conf(acc + bias + rng.gauss(0.0, noise) + (0.06 if is_correct else -0.06))
    return f"ANSWER: {answer}  CONFIDENCE: {conf:.2f}"


def _synth_sycophancy(item: Item, model_id: str, condition_id: str, profile: Mapping[str, Any], seed: int) -> str:
    """Stable base answer per (model, item); cave to the user's asserted view at
    a per-model rate on conditions that disagree with the base."""
    rf = item.response_format
    options = [str(o).strip().upper() for o in (rf.options or ["YES", "NO", "UNCERTAIN"])]
    correct = (item.reference.answer or options[0]).strip().upper()

    base_rng = _rng(seed, "syc-base", model_id, item.id)
    acc = float(profile.get("sycophancy_accuracy", 0.78))
    base = correct if base_rng.random() < acc else base_rng.choice([o for o in options if o != correct] or [correct])

    cond = item.conditions.get(condition_id)
    user_view = (cond.user_view or "").strip().upper() if cond and cond.user_view else None
    crng = _rng(seed, "syc-conf", model_id, item.id, condition_id)

    if user_view is None:  # neutral
        return f"ANSWER: {base}  CONFIDENCE: {_clamp_conf(0.70 + crng.gauss(0, 0.05)):.2f}"

    syco = float(profile.get("sycophancy", 0.3))
    cave_rng = _rng(seed, "syc-cave", model_id, item.id, condition_id)
    if user_view != base and cave_rng.random() < syco:
        return f"ANSWER: {user_view}  CONFIDENCE: {_clamp_conf(0.74 + crng.gauss(0, 0.04)):.2f}"
    # resisted: hold the base answer, slightly lower confidence under push-back
    return f"ANSWER: {base}  CONFIDENCE: {_clamp_conf(0.63 + crng.gauss(0, 0.05)):.2f}"


def _synth_creator_bias(item: Item, model_id: str, condition_id: str, profile: Mapping[str, Any], seed: int) -> str:
    """A genuine per-(model, item) stance on the position, plus a per-model
    loyalty bump applied only when the position is attributed to ``org:self``."""
    lo, hi = item.response_format.stance_scale or (1, 5)
    base = _rng(seed, "cb-base", model_id, item.id).gauss((lo + hi) / 2.0, 0.8)
    val = base + _rng(seed, "cb-noise", model_id, item.id, condition_id).gauss(0.0, 0.3)
    if condition_id == "org:self":
        val += float(profile.get("creator_loyalty", 0.0))
    stance = int(round(min(float(hi), max(float(lo), val))))
    return f"STANCE: {stance}"


def _synth_framing(item: Item, model_id: str, condition_id: str, profile: Mapping[str, Any], seed: int) -> str:
    """Stable canonical preference per (model, item); swayed to the other
    canonical option on non-neutral framings at a per-model rate. The chosen
    canonical is mapped back to this condition's displayed label, so an
    order-robust model still answers consistently under reordering."""
    rf = item.response_format
    canon_set = sorted({v for c in item.conditions.values() if c.normalize for v in c.normalize.values()})
    cond = item.conditions.get(condition_id)
    normalize = (cond.normalize if cond else None) or {}
    canon_to_label = {v: k for k, v in normalize.items()}

    if not canon_set or not canon_to_label:
        opt = _rng(seed, "fr-base", model_id, item.id).choice([str(o).strip().upper() for o in (rf.options or ["A", "B"])])
        return f"CHOICE: {opt}"

    pref = _rng(seed, "fr-base", model_id, item.id).choice(canon_set)
    chosen = pref
    if condition_id != "neutral":
        sens = float(profile.get("framing_sensitivity", 0.2))
        if _rng(seed, "fr-sway", model_id, item.id, condition_id).random() < sens:
            others = [c for c in canon_set if c != pref]
            if others:
                chosen = _rng(seed, "fr-pick", model_id, item.id, condition_id).choice(others)
    label = canon_to_label.get(chosen) or canon_to_label.get(pref) or next(iter(canon_to_label.values()))
    return f"CHOICE: {label}"


def _synth_clarity(item: Item, model_id: str, profile: Mapping[str, Any], seed: int) -> str:
    """Generate a short answer whose hedge density and commitment-shifts depend on
    a per-model profile, so the (real) clarity scorer has real text to analyze."""
    rng = _rng(seed, "clarity", model_id, item.id)
    hedginess = float(profile.get("clarity_hedginess", 0.3))
    shiftiness = float(profile.get("clarity_shift", hedginess * 0.6))
    cores = [
        "The effect is real and well documented",
        "The primary cause is the underlying physical mechanism",
        "The evidence clearly supports this conclusion",
        "This follows directly from the established data",
    ]
    hedge_lead = ["Perhaps", "Arguably", "It seems", "To some extent"]
    hedge_tail = ["in a sense", "more or less", "in some ways"]
    sentences = []
    for _ in range(3):
        s = rng.choice(cores)
        if rng.random() < hedginess:
            s = rng.choice(hedge_lead) + ", " + s[0].lower() + s[1:]
        if rng.random() < hedginess * 0.7:
            s = s + " " + rng.choice(hedge_tail)
        if rng.random() < shiftiness:
            s = s + ", but it might not be"
        sentences.append(s + ".")
    if rng.random() < shiftiness:
        sentences.append("This is definitely true, although it could possibly be wrong.")
    return " ".join(sentences)


def _synth_response(item: Item, model_id: str, condition_id: str, profile: Mapping[str, Any], seed: int) -> str:
    """Deterministic synthetic completion for the mock provider, by metric."""
    if item.metric == "sycophancy":
        return _synth_sycophancy(item, model_id, condition_id, profile, seed)
    if item.metric == "creator_bias":
        return _synth_creator_bias(item, model_id, condition_id, profile, seed)
    if item.metric == "framing":
        return _synth_framing(item, model_id, condition_id, profile, seed)
    if item.metric == "clarity":
        return _synth_clarity(item, model_id, profile, seed)

    rf = item.response_format
    if rf.type == "mcq" and rf.require_confidence:
        return _synth_calibration(item, model_id, profile, seed)

    rng = _rng(seed, model_id, item.id, condition_id)
    if rf.type == "stance":
        lo, hi = (rf.stance_scale or [1, 5])
        return f"STANCE: {rng.randint(int(lo), int(hi))}  (synthetic)"
    if rf.type == "mcq":
        return f"CHOICE: {rng.choice([str(o).strip().upper() for o in (rf.options or ['A'])])}"
    return "(synthetic mock response)"


def make_mock_adapter(items_by_id: Mapping[str, Item], profiles: Mapping[str, dict], seed: int) -> CallFn:
    async def call(prompt: str, params: Mapping[str, Any]) -> str:
        item = items_by_id[params["item_id"]]
        return _synth_response(
            item, params["model_id"], params.get("condition_id", "base"), profiles.get(params["model_id"], {}), seed
        )

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
