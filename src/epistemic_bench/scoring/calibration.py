"""Calibration scorer (SPEC §3.1, §7.5) — IMPLEMENTED for the v1 milestone.

Pointwise: reads the single ``base`` condition, returns correctness + stated
confidence and the per-item Brier score. ECE and the reliability diagram are
computed across items at aggregation time (``aggregate.py``), because binning is
inherently cross-item.
"""

from __future__ import annotations

from typing import Mapping

from ..types import Completion, ConditionId, Item, MetricScore, ScoringContext
from .base import register


@register("calibration")
def score_calibration(
    item: Item,
    completions: Mapping[ConditionId, Completion],
    ctx: ScoringContext,
) -> MetricScore:
    comp = completions.get("base")
    model_id = comp.model_id if comp is not None else ctx.model.id

    def invalid(components: dict | None = None) -> MetricScore:
        return MetricScore(
            item_id=item.id,
            metric="calibration",
            model_id=model_id,
            value=0.0,
            components=components or {},
            n_conditions=len(completions),
            valid=False,
        )

    if comp is None or comp.error or not comp.parsed or "answer" not in comp.parsed:
        return invalid()

    answer = str(comp.parsed.get("answer", "")).strip().upper()
    correct_opt = (item.reference.answer or "").strip().upper()
    correct = 1.0 if answer == correct_opt else 0.0

    raw_conf = comp.parsed.get("confidence")
    if raw_conf is None:
        return invalid({"correct": correct})

    conf = min(1.0, max(0.0, float(raw_conf)))
    brier = (conf - correct) ** 2
    return MetricScore(
        item_id=item.id,
        metric="calibration",
        model_id=model_id,
        value=brier,
        components={"correct": correct, "confidence": conf},
        diagnostics={"answer": answer, "reference": correct_opt},
        n_conditions=1,
        valid=True,
    )
