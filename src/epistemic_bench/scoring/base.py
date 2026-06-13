"""Scorer protocol + registry (SPEC §7.5).

One uniform shape covers pointwise and paired/variant metrics:

    (item, {condition_id: completion}, ctx) -> MetricScore

Pointwise metrics (calibration) just receive a single ``base`` key.
"""

from __future__ import annotations

from typing import Callable, Dict, Mapping, Protocol, runtime_checkable

from ..types import Completion, ConditionId, Item, Metric, MetricScore, ScoringContext


@runtime_checkable
class Scorer(Protocol):
    metric: Metric

    def __call__(
        self,
        item: Item,
        completions: Mapping[ConditionId, Completion],
        ctx: ScoringContext,
    ) -> MetricScore: ...


# metric -> scorer callable
SCORERS: Dict[str, Callable[..., MetricScore]] = {}

# Judge-dependent metrics (v2): computed like any other, but withheld from the
# published leaderboard unless a passing judge-validation record exists (SPEC §10).
JUDGED_METRICS = frozenset({"pedantic", "thoroughness"})


def register(metric: str) -> Callable[[Callable[..., MetricScore]], Callable[..., MetricScore]]:
    """Decorator: register a scorer under a metric key and tag it with ``.metric``."""

    def deco(fn: Callable[..., MetricScore]) -> Callable[..., MetricScore]:
        fn.metric = metric  # type: ignore[attr-defined]
        SCORERS[metric] = fn
        return fn

    return deco


def get_scorer(metric: str) -> Callable[..., MetricScore]:
    if metric not in SCORERS:
        raise KeyError(f"no scorer registered for metric {metric!r}")
    return SCORERS[metric]
