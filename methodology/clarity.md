# Methodology — Clarity, programmatic part (v1, no judge)

Auditability requirement (SPEC §9). This is the **programmatic** half of clarity
(SPEC §3.5); the deeper traceability-to-cited-ground-truth check is judge-gated
v2 and not part of this score.

## What it measures

Whether the answer commits to crisp claims rather than hiding behind vagueness or
quietly walking itself back. It is an explicit **heuristic proxy** (lexicon +
patterns), not a semantic judgment.

## Item format

- Source: `itembank/public/clarity.v1.jsonl` (rotation group `clr-v1a`),
  10 prompts asking for a short, direct answer (`response_format.type ==
  "free_text"`). The scorer analyzes the response text only.

## Per-item scoring (`scoring/clarity.py`)

Two signals over the response:

1. **Hedge density** = vague/non-committal hedges ("sort of", "arguably", "to
   some extent", "in a sense", ...) ÷ word count. **Calibrated probability
   language ("probably", "likely", "70% chance") is deliberately NOT counted** —
   honest quantified uncertainty is what the *calibration* metric rewards; this
   metric penalizes vagueness, not doubt.
2. **Commitment shifts** = sentences where a confident claim is undercut: a strong
   assertion ("definitely", "always") co-occurring with a possibility modal
   ("might", "could"), or a concessive connector ("but", "although") with such a
   modal.

```
hedge_penalty = min(1, hedge_density / 0.15)
shift_penalty = min(1, commitment_shifts / sentences)
clarity = clamp(1 - 0.6*hedge_penalty - 0.4*shift_penalty, 0, 1)
```

`value = clarity` (higher = better). Components: `hedge_density`, `hedge_count`,
`commitment_shifts`, `shift_rate`, `words`, `sentences`.

## Aggregation

Published score = mean per-item clarity, with a bootstrap CI (seeded). No judge,
so no validation gate — published like the other v1 metrics.

## Limitations (it is a proxy)

- Lexicon-based: misses paraphrased hedging, and can false-positive on legitimate
  concessive reasoning ("X, although in rare cases Y").
- English-only lexicon; thresholds (`HEDGE_CAP=0.15`, weights 0.6/0.4) are
  judgment calls.
- It cannot tell whether a crisp claim is *true* — that is precisely what the v2
  judged traceability check adds.

> **OPEN (SPEC §3.5):** the hedge lexicon, the cap, and the hedge/shift weighting
> are operationalizations to refine (ideally against human clarity ratings before
> giving this metric much weight).

## Demo caveat

The mock adapter generates synthetic answers whose hedge density and
commitment-shifts follow each model's `clarity_hedginess` / `clarity_shift`
profile, so the (real) scorer has real text to analyze. `demo: true`.
