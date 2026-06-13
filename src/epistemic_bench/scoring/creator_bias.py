"""Creator-bias / loyalty scorer (SPEC §3.3) — STUB.

Compares endorsement on the runner-resolved ``org:self`` condition against the
``org:rival_*`` / ``org:neutral`` conditions; reports skew toward the model's own
maker. Not yet implemented.
"""

from __future__ import annotations

from typing import Mapping

from ..types import Completion, ConditionId, Item, MetricScore, ScoringContext
from .base import register


@register("creator_bias")
def score_creator_bias(
    item: Item,
    completions: Mapping[ConditionId, Completion],
    ctx: ScoringContext,
) -> MetricScore:
    raise NotImplementedError("creator_bias scorer is a stub (SPEC §3.3)")
