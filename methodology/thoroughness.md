# Methodology — Thoroughness (v2, judge-gated)

Auditability requirement (SPEC §9). **Published only after the judge clears the
validation gate** (`methodology/judge-validation.md`, SPEC §10).

## What it measures

Context-dependent coverage against a conciseness budget: breadth/diversity for
search-like prompts, editorial balance for summary-like prompts — without
rewarding padding.

## Item format

- Source: `itembank/public/thoroughness.v1.jsonl` (rotation group `thr-v1a`).
- Free-text prompt (`response_format.type == "free_text"`).
- `params`:
  - `key_points`: the points a thorough answer should address,
  - `conciseness_budget`: target length in words,
  - `prompt_kind`: `summary` or `search`.

## Judge step (rubric `THOROUGHNESS_V1`)

The judge returns which key points the answer substantively covers, an editorial
balance/diversity score in `[0,1]`, and the answer's word count.

## Per-item scoring (`scoring/judge/thoroughness.py`)

```
coverage    = covered_key_points / total_key_points
conciseness = clamp(1 - max(0, word_count - budget) / budget, 0, 1)
score       = 0.5*coverage + 0.3*balance + 0.2*conciseness          (in [0,1])
```

`value = score` (higher = better). Components: `coverage`, `balance`,
`conciseness`, `word_count`. Pure given the injected judge; unit-tested with a
fake judge.

## Aggregation

Published score = mean per-item thoroughness, with a bootstrap CI (seeded).
Included on the leaderboard only if the judge passed validation (Pearson r ≥
threshold).

> **OPEN (SPEC §3):** the 0.5/0.3/0.2 weighting of coverage/balance/conciseness,
> and whether `prompt_kind` should switch the balance criterion (diversity for
> search vs even-handedness for summary) more sharply, are operationalizations to
> fix with judge-validation evidence.

## Demo caveat

The mock judge fabricates coverage/balance/word-count from each model's
`thoroughness_coverage` / `thoroughness_balance` / `thoroughness_verbosity`
profile; it does not read the candidate text. `demo: true`.
