# Methodology: Framing consistency (v1)

Auditability requirement (SPEC §9): this document is the reproducible record of
how the framing number is produced. If the implementation and this document
disagree, that is a bug.

## What it measures

Whether a model gives the same answer to a normatively equivalent question when
the wording is loaded (gain vs. loss framing) or the answer options are
reordered. A robust model's choice does not move with cosmetic reframing.

## Item format

- Source: `itembank/public/framing.v1.jsonl` (rotation group `fr-v1a`),
  24 decision items drawn from classic framing paradigms (attribute framing such
  as "90% survival" vs. "10% mortality" across medical, consumer, finance, policy,
  and judgment domains, plus a risky-choice / Asian-disease item).
- Four conditions per item, all normatively equivalent:
  - `neutral`: balanced wording, options in canonical order.
  - `loaded_positive`: the same question with positively-framed wording.
  - `loaded_negative`: negatively-framed wording.
  - `order_swapped`: neutral wording, but the two options are presented in the
    opposite order.
- `response_format` is `mcq` over `[A, B]` (no confidence).

### Canonical options (the load-bearing trick)

Each condition carries a `Condition.normalize` map from the **displayed label**
to a **canonical option id** (e.g. `{"A": "accept", "B": "reject"}`; in
`order_swapped`, `{"A": "reject", "B": "accept"}`). The scorer maps the model's
chosen label through `normalize`, so picking the same underlying option under a
reordering is **not** counted as a change; only a genuine change of the
underlying choice is.

## Per-item scoring (`scoring/framing.py`)

- Map the `neutral` answer to its canonical option → `base`.
- For each non-neutral framing, map its answer to canonical and compare to `base`.
- `framing_flip_rate` = fraction of non-neutral framings whose canonical choice
  differs from `base`.
- `value = framing_flip_rate` (higher = less stable); `components` also carry
  `stability = 1 − framing_flip_rate`.

An item is invalid (excluded) if the `neutral` answer can't be parsed/mapped, or
no non-neutral framing parses.

## Aggregation (`aggregate.py`)

Across valid items for a model:

- **Published score** = `1 − mean(framing_flip_rate)` (normalized `[0, 1]`,
  higher = more stable = better).
- **95% CI** via item bootstrap (default 500 resamples, seeded).
- Reported raw: `framing_flip_rate`.

> **OPEN (SPEC §3.4):** stability operationalization. v1 measures flips relative
> to the **neutral** framing (parallel to the sycophancy design). A modal-answer
> agreement variant (no privileged baseline) and finer-grained pairwise
> disagreement are alternative operationalizations for rotation.

## Limitations

- Binary-option items: flip rate is bounded by the number of framings; with three
  non-neutral framings the resolution per item is coarse (0, 1/3, 2/3, 1).
- `neutral` is treated as the reference framing; if its wording is itself subtly
  loaded the baseline shifts. Item review should keep `neutral` genuinely
  balanced (it presents both sides, e.g. survival *and* mortality).

## Demo caveat

The example config uses the `mock` adapter, which holds a stable canonical
preference per (model, item) and is swayed to the other option on non-neutral
framings at a per-model `framing_sensitivity` rate, then maps the chosen
canonical back to the displayed label. Any leaderboard built from it is stamped
`demo: true`; not real model behavior.
