"""Thoroughness scorer (SPEC §3, v2) — STUB.

Context-dependent coverage: breadth/diversity for search-like prompts, editorial
balance for summary-like prompts, against a conciseness budget. Gated behind
validation (SPEC §10); not registered.
"""

from __future__ import annotations

from typing import Mapping

from ...types import Completion, ConditionId, Item, MetricScore, ScoringContext


def score_thoroughness(
    item: Item,
    completions: Mapping[ConditionId, Completion],
    ctx: ScoringContext,
) -> MetricScore:
    raise NotImplementedError("thoroughness scorer is a v2 stub, gated by validation (SPEC §3, §10)")
