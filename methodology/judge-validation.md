# Methodology: Judge validation gate (v2)

This is the credibility backbone for every judge-dependent metric. **No judged
score is published until the judge clears this gate** (SPEC §10). Auditability
requirement (SPEC §9): this document is the reproducible record of the gate.

## Why a gate

v2 metrics (pedantic-mode precision, thoroughness) depend on an LLM judge. A
judge is only trustworthy to the extent it agrees with careful humans. So before
a judged metric appears on the leaderboard, we measure judge↔human agreement on a
human-labeled sample and require it to meet a threshold.

## What is pinned

- **Judge model**: pinned and versioned (`run_meta.judge.id`). It **must not
  share a maker** with any model under test, which is acute given the creator-bias metric
  (OPEN, SPEC §10: a cross-maker or ensemble judge is recommended).
- **Rubric**: a fixed, versioned constant (`scoring/judge/rubric.py`,
  `RUBRIC_VERSION`). Changing the rubric or the judge **re-triggers the gate**.

## The validation artifact

For each judged metric, a human-labeled sample lives at
`validation/judge/<metric>.sample.jsonl`. Each record contains the inputs, the
**human label**, and the **judge's output** (produced by running the pinned judge
over the human-labeled inputs). Shipping both columns makes the comparison
auditable and reproducible.

- **pedantic** (`pedantic.sample.jsonl`): per-claim records with
  `human_verdict` and `judge_verdict` in `{supported, unsupported, contradicted}`.
- **thoroughness** (`thoroughness.sample.jsonl`): per-item records with
  `human_score` and `judge_score` in `[0, 1]`.

## Agreement statistic and threshold

- **pedantic** → **Cohen's κ** over the categorical verdicts.
- **thoroughness** → **Pearson r** between judge and human item scores.

A metric passes iff the statistic ≥ its threshold (default **0.6**, configurable
in `config/run.example.yaml` under `judge.thresholds`).

> **OPEN (SPEC §10):** the agreement statistic and threshold per metric. κ ≥ 0.6
> and r ≥ 0.6 are reasonable defaults but should be set with domain input;
> consider Krippendorff's α for >2 raters and a higher bar for high-stakes claims.

## Running the gate

```
epb validate-judge --metric pedantic       # -> validation/judge/pedantic.result.json
epb validate-judge --metric thoroughness
```

Each writes a `<metric>.result.json` with the statistic, n, threshold, and
`passed`. At report time, `aggregate.to_report` reads these results:

- **passed** → the metric is included under `report.virtues` with a `judge`
  block recording the agreement evidence.
- **failed or missing** → the metric is moved to `report.withheld` with the
  reason; it never reaches the leaderboard.

`result.json` files are regenerated (gitignored); the human-labeled `sample.jsonl`
files are the committed source of truth.

## Demo caveat

In demo mode the judge is a deterministic **mock** that simulates verdicts from
per-model quality profiles; the `*.sample.jsonl` gold files ship with both human
and (notional) judge columns so the gate computes a real κ / r. This exercises
the gate mechanics end to end, but the judge is synthetic (`demo: true`). Real
validation uses a real, pinned judge and genuinely human labels.
