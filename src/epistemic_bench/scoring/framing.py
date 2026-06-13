"""Framing-consistency scorer (SPEC §3.4) — IMPLEMENTED.

The same underlying question is asked under loaded vs. neutral wording and with
reordered options. Each condition's raw choice label is mapped through
``Condition.normalize`` to a **canonical option**, so reordering labels (A↔B)
does not count as a change — only a genuine change of the underlying choice does.

Per-item signal: ``value = framing_flip_rate`` = fraction of non-neutral
framings whose canonical choice differs from the ``neutral`` framing (higher =
less stable). The aggregator publishes ``1 − mean(framing_flip_rate)`` so the
leaderboard score is higher = better (more stable across framings).
"""

from __future__ import annotations

from typing import Mapping, Optional

from ..types import Completion, Condition, ConditionId, Item, MetricScore, ScoringContext
from .base import register


def _canonical(comp: Optional[Completion], cond: Optional[Condition]) -> Optional[str]:
    if comp is None or comp.error or not comp.parsed or "answer" not in comp.parsed:
        return None
    label = str(comp.parsed["answer"]).strip().upper()
    if cond is not None and cond.normalize:
        nm = {str(k).strip().upper(): v for k, v in cond.normalize.items()}
        return nm.get(label, label)
    return label


@register("framing")
def score_framing(
    item: Item,
    completions: Mapping[ConditionId, Completion],
    ctx: ScoringContext,
) -> MetricScore:
    neutral = completions.get("neutral")
    model_id = neutral.model_id if neutral is not None else ctx.model.id

    def invalid() -> MetricScore:
        return MetricScore(
            item_id=item.id,
            metric="framing",
            model_id=model_id,
            value=0.0,
            n_conditions=len(completions),
            valid=False,
        )

    base = _canonical(neutral, item.conditions.get("neutral"))
    if base is None:
        return invalid()

    n = flips = 0
    for cid, comp in completions.items():
        if cid == "neutral":
            continue
        choice = _canonical(comp, item.conditions.get(cid))
        if choice is None:
            continue
        n += 1
        if choice != base:
            flips += 1

    if n == 0:
        return invalid()

    flip_rate = flips / n
    return MetricScore(
        item_id=item.id,
        metric="framing",
        model_id=model_id,
        value=flip_rate,  # higher = less stable; aggregator publishes 1 - mean
        components={"framing_flip_rate": flip_rate, "stability": 1.0 - flip_rate},
        diagnostics={"neutral_choice": base, "n_framings": n},
        n_conditions=len(completions),
        valid=True,
    )
