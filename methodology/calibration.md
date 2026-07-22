# Methodology — Calibration (v1)

Auditability requirement (SPEC §9): this document is the reproducible record of
how the calibration number is produced. If the implementation and this document
disagree, that is a bug.

## What it measures

Whether a model's stated confidence matches its actual accuracy. A model that
says "80% confident" should be right about 80% of the time across such answers.

## Item format

- Source: `itembank/public/calibration.v1.jsonl` (rotation group `cal-v1a`),
  30 multiple-choice factual questions over 3 difficulty tiers (easy/medium/hard).
- Each item has one condition, `base`, a known correct option
  (`reference.kind == "answer"`), and `response_format.type == "mcq"` with
  `require_confidence: true`.

## Elicitation

The model is asked to reply on a single line:

```
ANSWER: <A|B|C|D>  CONFIDENCE: <a probability between 0 and 1 that your answer is correct>
```

> **OPEN (SPEC §3.1):** MCQ + numeric confidence is the v1 default. It has a
> guessing floor (≈0.25 accuracy at chance) which bounds achievable ECE; note
> this when interpreting scores. Alternatives (verbalized buckets, full
> per-option distributions, short-answer) are future operationalizations.

## Parsing (`runner.parse_output`)

- `ANSWER:` → matched **against the item's option set only** (case-insensitive;
  longest option first). Text that is not one of the options — prose like
  "ANSWER: The answer is unclear", or an out-of-set letter — is *unparseable*,
  not an incorrect answer.
- `CONFIDENCE:` → first numeric token, read as a probability. **Percent-style
  answers are normalized**: a trailing `%`, or any bare value in `(1, 100]`
  (models frequently answer `CONFIDENCE: 85`), is divided by 100. Values above
  100 are unparseable. The result is clamped to `[0, 1]` at scoring time.
- If `ANSWER:` can't be matched, or a required confidence can't be parsed, the
  completion is marked invalid and excluded — and the **count of exclusions is
  published** as `n_invalid` in the metric's raw block, so dropped items are
  visible rather than silently flattering (aggregation section below).

## Per-item scoring (`scoring/calibration.py`)

- `correct = 1.0` iff parsed answer equals `reference.answer`, else `0.0`.
- `value = Brier = (confidence − correct)²`.
- `components = {correct, confidence}` (consumed by aggregation).

## Aggregation (`aggregate.py`)

Across all valid items for a model:

- **Accuracy** = mean(correct).
- **Brier** = mean of per-item Brier.
- **ECE** (Expected Calibration Error), 10 equal-width confidence bins:
  `ECE = Σ_b (n_b / N) · |acc_b − conf_b|`, where `acc_b` and `conf_b` are the
  bin's mean accuracy and mean confidence.
- **Reliability diagram** = per-bin `(mean_conf, accuracy, n)` (the plot data).
- **Published score** = `1 − ECE` (normalized to `[0, 1]`, higher is better).
- **95% CI** on the score via item bootstrap (default 500 resamples, seeded).
- **Exclusion accounting**: `n_invalid` (unparseable or errored completions,
  excluded from all of the above) is reported in the raw block next to
  `n_items`.

Number of bins (10) and bootstrap resamples (500) are fixed parameters recorded
in `run_meta.json` via the run seed; change them only with a methodology bump.

## Limitations

- MCQ guessing floor (above) bounds ECE.
- 10 fixed-width bins; sparsely populated bins are noisy with small item sets.
- Single-correct-answer items only; no partial credit.
- ECE is a **biased estimator** (it is minimized on the full sample and tends to
  be larger on bootstrap resamples, which redistribute items across bins). For a
  very well-calibrated model at small `n`, the percentile bootstrap interval on
  `1 − ECE` can therefore fall *below* the full-sample point estimate, and is
  bounded above by the `1.0` ceiling. Read the interval as a **spread indicator**,
  not a frequentist coverage guarantee; a larger item bank (and/or adaptive
  binning) is the fix and is tracked for a later operationalization.

## Demo caveat

The example config (`config/models.example.yaml`) uses the `mock` adapter, which
**fabricates** answers/confidences with controllable per-model accuracy and
confidence bias. Any leaderboard built from it is stamped `demo: true` and is for
pipeline demonstration only — not real model performance.
