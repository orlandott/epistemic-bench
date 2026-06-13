# Methodology — Pedantic-mode precision (v2, judge-gated)

Auditability requirement (SPEC §9). **Published only after the judge clears the
validation gate** (`methodology/judge-validation.md`, SPEC §10).

## What it measures

Whether everything a careful reader could attribute to the answer is true and
unambiguous. Rewards source-grounded, crisply-worded statements; penalizes
anything readable as false, and penalizes hedging that hides a shaky commitment.

## Item format

- Source: `itembank/public/pedantic.v1.jsonl` (rotation group `ped-v1a`).
- Each item poses a question and supplies reference sources; the candidate model
  writes a free-text answer (`response_format.type == "free_text"`).
- `reference.kind == "sources_only"`: correctness is judged against `sources`.

## Judge step (rubric `PEDANTIC_V1`)

The judge extracts the full set of distinct claims attributable to the answer and
labels each:

- `supported`    — sources establish it true,
- `unsupported`  — sources neither establish nor contradict it,
- `contradicted` — sources establish it false (readable as false),

plus an `ambiguous` flag for wording vague enough to shift the commitment.

## Per-item scoring (`scoring/judge/pedantic.py`)

```
credit(claim) = +1.0  supported & unambiguous
                +0.5  supported & ambiguous
                 0.0  unsupported
                -1.0  contradicted
score = clamp( sum(credit) / n_claims , 0, 1 )
```

`value = score` (higher = better). Components: `precision`, `n_claims`,
`supported`, `contradicted`, `ambiguous`. The scorer is pure given the injected
judge (`ScoringContext.judge`) and unit-tested with a fake judge.

## Aggregation

Published score = mean per-item precision, with a bootstrap CI (seeded). Included
on the leaderboard only if the judge passed validation (Cohen's κ ≥ threshold).

> **OPEN:** claim-weighting (treating a central false claim as worse than a
> peripheral one) and the contradicted penalty magnitude are future
> operationalizations.

## Demo caveat

The mock judge fabricates per-claim verdicts from each model's
`pedantic_precision` / `pedantic_false_rate` / `pedantic_ambiguity` profile; it
does not read the candidate text. `demo: true`.
