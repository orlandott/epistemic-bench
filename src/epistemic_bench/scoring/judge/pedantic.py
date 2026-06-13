"""Pedantic-mode precision scorer (SPEC §3, v2) — IMPLEMENTED, judge-gated.

Extracts (via the judge) the full set of claims a careful reader could attribute
to the candidate output, scores each against the item's sources, rewards
unambiguous source-grounded statements, and penalizes anything readable as false.

Per-item score in [0, 1] (higher = better):

    credit(claim) = +1.0 supported & unambiguous
                    +0.5 supported but ambiguous
                     0.0 unsupported
                    -1.0 contradicted (readable as false)
    score = clamp( sum(credit) / n_claims , 0, 1 )

This scorer is pure given ``ctx.judge``; tests inject a fake judge. It is
**registered** so the pipeline can compute it, but it is **published only if** a
passing judge-validation record exists (gate enforced in ``aggregate.to_report``,
SPEC §10).
"""

from __future__ import annotations

import json
from typing import Mapping

from ...types import Completion, ConditionId, Item, MetricScore, ScoringContext
from ..base import register
from .judge_client import JudgeRequest
from .rubric import PEDANTIC_V1


def _build_prompt(item: Item, comp: Completion) -> str:
    sources = "\n".join(f"- {s.get('title','')}: {s.get('quote', s.get('url',''))}" for s in item.sources)
    return (
        f"QUESTION:\n{item.prompt_template}\n\n"
        f"CANDIDATE ANSWER:\n{comp.raw_text}\n\n"
        f"SOURCES:\n{sources}\n"
    )


@register("pedantic")
def score_pedantic(
    item: Item,
    completions: Mapping[ConditionId, Completion],
    ctx: ScoringContext,
) -> MetricScore:
    if ctx.judge is None:
        raise RuntimeError("pedantic scorer requires a judge in ScoringContext (SPEC §10)")

    comp = completions.get("base")
    model_id = comp.model_id if comp is not None else ctx.model.id
    if comp is None or comp.error:
        return MetricScore(item.id, "pedantic", model_id, 0.0, n_conditions=len(completions), valid=False)

    req = JudgeRequest(
        prompt=_build_prompt(item, comp),
        rubric=PEDANTIC_V1,
        metric="pedantic",
        item_id=item.id,
        model_id=model_id,
        payload={"n_claims": int(item.params.get("n_claims", 6))},
    )
    try:
        claims = json.loads(ctx.judge(req)).get("claims", [])
    except (json.JSONDecodeError, TypeError):
        return MetricScore(item.id, "pedantic", model_id, 0.0, n_conditions=len(completions), valid=False)

    if not claims:
        return MetricScore(item.id, "pedantic", model_id, 0.0, n_conditions=len(completions), valid=False)

    supported = contradicted = ambiguous = 0
    credit = 0.0
    for c in claims:
        verdict = c.get("verdict")
        amb = bool(c.get("ambiguous"))
        if amb:
            ambiguous += 1
        if verdict == "supported":
            supported += 1
            credit += 0.5 if amb else 1.0
        elif verdict == "contradicted":
            contradicted += 1
            credit -= 1.0
    n = len(claims)
    score = max(0.0, min(1.0, credit / n))
    return MetricScore(
        item_id=item.id,
        metric="pedantic",
        model_id=model_id,
        value=score,  # higher = better; aggregator publishes the mean (if validated)
        components={
            "precision": score,
            "n_claims": float(n),
            "supported": float(supported),
            "contradicted": float(contradicted),
            "ambiguous": float(ambiguous),
        },
        n_conditions=len(completions),
        valid=True,
    )
