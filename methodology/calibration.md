# Methodology: Calibration (v1)

Auditability requirement (SPEC §9): this document is the reproducible record of
how the calibration number is produced. If the implementation and this document
disagree, that is a bug.

## What it measures

Whether a model's stated confidence matches its actual accuracy. A model that
says "80% confident" should be right about 80% of the time across such answers.

## Item format

- Source: `itembank/public/calibration.v1.jsonl` (rotation group `cal-v1a`),
  30 multiple-choice factual questions over 3 difficulty tiers (easy/medium/hard).
  The items are deliberately **recall-heavy and precise** (specific atomic
  numbers, dates, units, and named results) so that a strong model has genuine
  uncertainty to report; calibration is only exercised when answers are not
  uniformly certain. Even the "easy" tier avoids trivia a frontier model is
  effectively 100% on.
- Each item has one condition, `base`, a known correct option
  (`reference.kind == "answer"`), and `response_format.type == "mcq"` with
  `require_confidence: true`.

## Elicitation

The model is asked to reply on a single line:

```
ANSWER: <A|B|C|D>  CONFIDENCE: <a number from 0 to 1 saying how sure you are that your answer is correct, for example 0.7 means about 70% sure>
```

The confidence is phrased as "how sure you are" (with a percentage example) but is
still a probability in `[0, 1]`; the parser reads the first numeric token and
clamps to `[0, 1]` (see Parsing), so the value range is unchanged from earlier
revisions; only the wording was made more explicit.

> **OPEN (SPEC §3.1):** MCQ + numeric confidence is the v1 default. It has a
> guessing floor (≈0.25 accuracy at chance) which bounds achievable ECE; note
> this when interpreting scores. Alternatives (verbalized buckets, full
> per-option distributions, short-answer) are future operationalizations.

## Parsing (`runner.parse_output`)

- `ANSWER:` → first letter token, upper-cased.
- `CONFIDENCE:` → first numeric token, clamped to `[0, 1]` at scoring time.
- If `ANSWER:` is absent the completion is marked invalid and excluded.

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
pipeline demonstration only, not real model performance.
