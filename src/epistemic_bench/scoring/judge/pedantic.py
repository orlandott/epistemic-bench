"""Pedantic-mode precision scorer (SPEC §3, v2) — STUB.

Extracts the full set of claims a careful reader could attribute to the output,
scores each against ``item.sources`` via the judge + ``rubric.PEDANTIC_V1``, and
penalizes ambiguity. Gated behind validation (SPEC §10); not registered.
"""

from __future__ import annotations

from typing import Mapping

from ...types import Completion, ConditionId, Item, MetricScore, ScoringContext


def score_pedantic(
    item: Item,
    completions: Mapping[ConditionId, Completion],
    ctx: ScoringContext,
) -> MetricScore:
    raise NotImplementedError("pedantic scorer is a v2 stub, gated by validation (SPEC §3, §10)")
