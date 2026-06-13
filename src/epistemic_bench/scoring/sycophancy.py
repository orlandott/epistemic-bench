"""Sycophancy-resistance scorer (SPEC §3.2) — STUB.

Compares ``primed_agree`` / ``primed_disagree`` against ``neutral``:
answer-flip rate and confidence shift, with directional flip toward the user's
asserted view as the headline scalar. Not yet implemented.
"""

from __future__ import annotations

from typing import Mapping

from ..types import Completion, ConditionId, Item, MetricScore, ScoringContext
from .base import register


@register("sycophancy")
def score_sycophancy(
    item: Item,
    completions: Mapping[ConditionId, Completion],
    ctx: ScoringContext,
) -> MetricScore:
    raise NotImplementedError("sycophancy scorer is a stub (SPEC §3.2)")
