"""Framing-consistency scorer (SPEC §3.4) — STUB.

Maps each condition's raw choice through ``Condition.normalize`` to a canonical
option, then measures answer stability across loaded/neutral wording and option
reorderings. Not yet implemented.
"""

from __future__ import annotations

from typing import Mapping

from ..types import Completion, ConditionId, Item, MetricScore, ScoringContext
from .base import register


@register("framing")
def score_framing(
    item: Item,
    completions: Mapping[ConditionId, Completion],
    ctx: ScoringContext,
) -> MetricScore:
    raise NotImplementedError("framing scorer is a stub (SPEC §3.4)")
