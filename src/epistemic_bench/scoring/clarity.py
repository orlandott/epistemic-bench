"""Clarity scorer, programmatic part (SPEC §3.5). Implemented, no judge.

Pure text analysis of the candidate answer on two programmatic signals:

1. **Hedge density**: the fraction of vague, non-committal hedges ("sort of",
   "arguably", "to some extent", ...). Calibrated probability language
   ("probably", "70% likely") is deliberately NOT penalized here, since
   expressing honest uncertainty is what the *calibration* metric rewards. We
   penalize vagueness, not quantified doubt.
2. **Commitment shifts**: a confident claim that is then quietly walked back:
   a strong assertion ("definitely", "always") co-occurring with a possibility
   modal ("might", "could"), or a concessive connector ("but", "although")
   followed by such a modal.

    hedge_penalty = min(1, hedge_density / HEDGE_CAP)
    shift_penalty = min(1, commitment_shifts / sentences)
    clarity = clamp(1 - 0.6*hedge_penalty - 0.4*shift_penalty, 0, 1)

This is an explicit **heuristic proxy** (lexicon + patterns); the deeper
traceability-to-cited-ground-truth check is judge-gated v2 (SPEC §3, §3.5). The
scorer is pure and unit-testable.
"""

from __future__ import annotations

import re
from typing import Mapping

from ..types import Completion, ConditionId, Item, MetricScore, ScoringContext
from .base import register

# Vague / non-committal hedges (NOT calibrated probability terms) -> hedge density.
HEDGES = [
    "perhaps", "maybe", "possibly", "arguably", "presumably", "sort of", "kind of", "somewhat",
    "more or less", "to some extent", "in a sense", "in some ways", "i guess", "i suppose",
    "it seems", "it appears", "supposedly", "ostensibly", "conceivably", "if anything",
]
# Strong commitments and possibility modals -> commitment-shift detection.
STRONG = ["definitely", "certainly", "clearly", "obviously", "always", "never", "undoubtedly",
          "absolutely", "guaranteed", "unquestionably"]
CONCESSIVE = ["but", "however", "although", "though", "yet", "that said", "then again", "on the other hand"]
WALKBACK = ["might", "may", "could", "perhaps", "possibly", "maybe", "arguably"]

HEDGE_CAP = 0.15  # hedge fraction at/above which the hedge axis is fully penalized
W_HEDGE = 0.6
W_SHIFT = 0.4


def _count_terms(text_lower: str, terms) -> int:
    return sum(len(re.findall(r"\b" + re.escape(t) + r"\b", text_lower)) for t in terms)


def _has_any(sentence_lower: str, terms) -> bool:
    return any(re.search(r"\b" + re.escape(t) + r"\b", sentence_lower) for t in terms)


@register("clarity")
def score_clarity(
    item: Item,
    completions: Mapping[ConditionId, Completion],
    ctx: ScoringContext,
) -> MetricScore:
    comp = completions.get("base")
    model_id = comp.model_id if comp is not None else ctx.model.id
    text = (comp.raw_text if (comp is not None and not comp.error) else "") or ""

    words = re.findall(r"[a-zA-Z']+", text.lower())
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    n_words = len(words)
    if n_words == 0:
        return MetricScore(item.id, "clarity", model_id, 0.0, n_conditions=len(completions), valid=False)

    text_lower = text.lower()
    hedge_count = _count_terms(text_lower, HEDGES)
    hedge_density = hedge_count / n_words

    shifts = 0
    for s in sentences:
        sl = s.lower()
        has_walkback = _has_any(sl, WALKBACK)
        if has_walkback and (_has_any(sl, STRONG) or _has_any(sl, CONCESSIVE)):
            shifts += 1
    n_sentences = max(1, len(sentences))
    shift_rate = shifts / n_sentences

    hedge_penalty = min(1.0, hedge_density / HEDGE_CAP)
    shift_penalty = min(1.0, shift_rate)
    clarity = max(0.0, min(1.0, 1.0 - W_HEDGE * hedge_penalty - W_SHIFT * shift_penalty))

    return MetricScore(
        item_id=item.id,
        metric="clarity",
        model_id=model_id,
        value=clarity,  # higher = crisper; aggregator publishes the mean
        components={
            "clarity": round(clarity, 4),
            "hedge_density": round(hedge_density, 4),
            "hedge_count": float(hedge_count),
            "commitment_shifts": float(shifts),
            "shift_rate": round(shift_rate, 4),
            "words": float(n_words),
            "sentences": float(len(sentences)),
        },
        n_conditions=len(completions),
        valid=True,
    )
