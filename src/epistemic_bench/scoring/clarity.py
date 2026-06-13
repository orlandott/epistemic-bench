"""Clarity scorer, programmatic part (SPEC §3.5) — STUB.

Penalizes hedges that shift commitments and detectable commitment-shifts over the
``base`` condition. The traceability-to-sources judgment is judge-gated (v2).
Not yet implemented.
"""

from __future__ import annotations

from typing import Mapping

from ..types import Completion, ConditionId, Item, MetricScore, ScoringContext
from .base import register


@register("clarity")
def score_clarity(
    item: Item,
    completions: Mapping[ConditionId, Completion],
    ctx: ScoringContext,
) -> MetricScore:
    raise NotImplementedError("clarity scorer is a stub (SPEC §3.5)")
