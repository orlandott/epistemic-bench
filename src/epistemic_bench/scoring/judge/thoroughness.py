"""Thoroughness scorer (SPEC §3, v2). Implemented, judge-gated.

Context-dependent coverage against a conciseness budget. The judge reports which
of the item's key points the candidate substantively covers, an editorial
balance/diversity score, and the response word count. The scorer combines them:

    coverage    = covered_key_points / total_key_points
    conciseness = clamp(1 - max(0, word_count - budget) / budget, 0, 1)
    score       = 0.5*coverage + 0.3*balance + 0.2*conciseness            (in [0,1])

Pure given ``ctx.judge``. Registered, but **published only if** a passing
judge-validation record exists (gate in ``aggregate.to_report``, SPEC §10).
"""

from __future__ import annotations

import json
from typing import Mapping

from ...types import Completion, ConditionId, Item, MetricScore, ScoringContext
from ..base import register
from .judge_client import JudgeRequest
from .rubric import THOROUGHNESS_V1


@register("thoroughness")
def score_thoroughness(
    item: Item,
    completions: Mapping[ConditionId, Completion],
    ctx: ScoringContext,
) -> MetricScore:
    if ctx.judge is None:
        raise RuntimeError("thoroughness scorer requires a judge in ScoringContext (SPEC §10)")

    comp = completions.get("base")
    model_id = comp.model_id if comp is not None else ctx.model.id
    if comp is None or comp.error:
        return MetricScore(item.id, "thoroughness", model_id, 0.0, n_conditions=len(completions), valid=False)

    key_points = list(item.params.get("key_points", []))
    budget = int(item.params.get("conciseness_budget", 150))
    req = JudgeRequest(
        prompt=f"PROMPT:\n{item.prompt_template}\n\nCANDIDATE RESPONSE:\n{comp.raw_text}\n",
        rubric=THOROUGHNESS_V1,
        metric="thoroughness",
        item_id=item.id,
        model_id=model_id,
        payload={"key_points": key_points, "budget": budget, "prompt_kind": item.params.get("prompt_kind", "summary")},
    )
    try:
        data = json.loads(ctx.judge(req))
    except (json.JSONDecodeError, TypeError):
        return MetricScore(item.id, "thoroughness", model_id, 0.0, n_conditions=len(completions), valid=False)

    coverage = (len(data.get("covered_points", [])) / len(key_points)) if key_points else 0.0
    balance = max(0.0, min(1.0, float(data.get("balance", 0.0))))
    word_count = int(data.get("word_count", budget))
    conciseness = max(0.0, min(1.0, 1.0 - max(0, word_count - budget) / budget)) if budget else 1.0
    score = 0.5 * coverage + 0.3 * balance + 0.2 * conciseness

    return MetricScore(
        item_id=item.id,
        metric="thoroughness",
        model_id=model_id,
        value=score,
        components={
            "coverage": round(coverage, 4),
            "balance": round(balance, 4),
            "conciseness": round(conciseness, 4),
            "word_count": float(word_count),
        },
        n_conditions=len(completions),
        valid=True,
    )
