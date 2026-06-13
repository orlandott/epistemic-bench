"""Core data model (SPEC.md §7.1).

Frozen dataclasses are the contract between modules. Items, completions, scores,
and run artifacts all round-trip through plain dicts (JSONL on disk).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path  # noqa: F401  (referenced in type hints elsewhere)
from typing import Any, Literal, Mapping, Optional, Sequence

ItemId = str  # "calibration/v1/cal-0007"
ConditionId = str  # "base", "neutral", "org:self"
ModelId = str  # registry key, e.g. "claude-demo"
Metric = Literal[
    "calibration", "sycophancy", "creator_bias", "framing", "clarity", "pedantic", "thoroughness"
]
Split = Literal["public", "private"]


@dataclass(frozen=True)
class ResponseFormat:
    type: Literal["mcq", "short_answer", "stance", "free_text"]
    options: Optional[Sequence[str]] = None
    require_confidence: bool = False
    stance_scale: Optional[Sequence[int]] = None


@dataclass(frozen=True)
class Condition:
    id: ConditionId
    vars: Mapping[str, str] = field(default_factory=dict)
    template_override: Optional[str] = None
    normalize: Optional[Mapping[str, str]] = None  # raw label -> canonical id (framing)
    user_view: Optional[str] = None  # answer the simulated user asserts (sycophancy)


@dataclass(frozen=True)
class Reference:
    kind: Literal["answer", "invariant", "stance", "sources_only"]
    answer: Optional[str] = None
    expected_stance: Optional[float] = None
    notes: str = ""


@dataclass(frozen=True)
class Item:
    id: ItemId
    schema_version: str
    metric: Metric
    split: Split
    prompt_template: str
    conditions: Mapping[ConditionId, Condition]
    response_format: ResponseFormat
    reference: Reference
    template_vars: Mapping[str, str] = field(default_factory=dict)
    category: Optional[str] = None
    difficulty: Optional[str] = None
    sources: Sequence[Mapping[str, str]] = field(default_factory=tuple)
    tags: Sequence[str] = field(default_factory=tuple)
    provenance: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelInfo:
    id: ModelId
    provider: Literal["anthropic", "openai", "google", "openweights", "mock"]
    maker: str  # org that built it; binds {{ORG_SELF}} for creator_bias
    display_name: str
    version: str = ""  # exact pinned version/date, recorded in provenance


@dataclass(frozen=True)
class RunUnit:
    item_id: ItemId
    condition_id: ConditionId
    model_id: ModelId
    prompt: str  # fully rendered
    response_format: ResponseFormat
    org_binding: Mapping[str, str] = field(default_factory=dict)  # role token -> concrete org


@dataclass(frozen=True)
class Completion:
    item_id: ItemId
    condition_id: ConditionId
    model_id: ModelId
    raw_text: str
    parsed: Optional[Mapping[str, Any]] = None  # {answer, confidence, stance, ...}
    usage: Mapping[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass(frozen=True)
class ScoringContext:
    model: ModelInfo
    rng_seed: int = 0
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MetricScore:
    item_id: ItemId
    metric: Metric
    model_id: ModelId
    value: float  # per-item scalar; direction documented per metric (SPEC §3)
    components: Mapping[str, float] = field(default_factory=dict)
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    n_conditions: int = 0
    valid: bool = True


# ---- dict <-> dataclass helpers (JSONL round-tripping) --------------------


def completion_to_dict(c: Completion) -> dict:
    return {
        "item_id": c.item_id,
        "condition_id": c.condition_id,
        "model_id": c.model_id,
        "raw_text": c.raw_text,
        "parsed": dict(c.parsed) if c.parsed is not None else None,
        "usage": dict(c.usage),
        "error": c.error,
    }


def completion_from_dict(d: Mapping[str, Any]) -> Completion:
    return Completion(
        item_id=d["item_id"],
        condition_id=d["condition_id"],
        model_id=d["model_id"],
        raw_text=d.get("raw_text", ""),
        parsed=d.get("parsed"),
        usage=d.get("usage", {}) or {},
        error=d.get("error"),
    )


def metricscore_to_dict(s: MetricScore) -> dict:
    return {
        "item_id": s.item_id,
        "metric": s.metric,
        "model_id": s.model_id,
        "value": s.value,
        "components": dict(s.components),
        "diagnostics": dict(s.diagnostics),
        "n_conditions": s.n_conditions,
        "valid": s.valid,
    }


def metricscore_from_dict(d: Mapping[str, Any]) -> MetricScore:
    return MetricScore(
        item_id=d["item_id"],
        metric=d["metric"],
        model_id=d["model_id"],
        value=float(d["value"]),
        components=d.get("components", {}) or {},
        diagnostics=d.get("diagnostics", {}) or {},
        n_conditions=int(d.get("n_conditions", 0)),
        valid=bool(d.get("valid", True)),
    )


def modelinfo_from_dict(d: Mapping[str, Any]) -> ModelInfo:
    return ModelInfo(
        id=d["id"],
        provider=d["provider"],
        maker=d.get("maker", ""),
        display_name=d.get("display_name", d["id"]),
        version=d.get("version", ""),
    )
