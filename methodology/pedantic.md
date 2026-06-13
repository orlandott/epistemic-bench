# Methodology: Pedantic-mode precision (v2, judge-gated)

Auditability requirement (SPEC §9). **Published only after the judge clears the
validation gate** (`methodology/judge-validation.md`, SPEC §10).

## What it measures

Whether **anything a literal, careful reader could take the answer to be
claiming is false or ambiguous**, not just whether its headline fact is right.

Ordinary accuracy asks: *is the main claim correct?* Pedantic mode asks: *is
there any reasonable reading of anything you said that is false or misleading?*
It penalizes ambiguity itself, not only outright falsehoods. The model is free
to answer however it likes (it is **not** restricted to a set of provided
sources); we then take whatever it actually wrote and hold every claim in it,
whether stated, implied, or presupposed, to the standard of being true and
unambiguous.

So it rewards language so precise that no careful reader could walk away
believing something false. That is a much stricter bar than accuracy, and it is
the one that matters for high-stakes use where you need statements you can fully
trust.

### Example: a right fact that smuggles in a false one

Prompt: *"When did the Berlin Wall fall?"* Answer: *"The Berlin Wall fell in
1989, ending the Cold War."* Two attributable claims: (1) the Wall fell in
1989, which is true; (2) that this ended the Cold War, which is arguably false,
since the Cold War is usually dated to 1991. The headline fact is right, but the phrasing
smuggles in a false claim, so pedantic mode penalizes it.

### Example: ambiguity is itself the fault

*"This drug has no significant side effects."* One reading is *"no side effects
occur"* (false); another is *"side effects weren't statistically significant in
trials"* (maybe true). Because a natural reading is false, the ambiguity itself
is penalized; the model should have said which it meant.

## Item format

- Source: `itembank/public/pedantic.v1.jsonl` (rotation group `ped-v1a`).
- Each item poses a plain question; the candidate model writes a free-text
  answer from its own knowledge (`response_format.type == "free_text"`). The
  prompt does **not** hand the model the answer or tell it to "use only these
  sources."
- `reference.kind == "sources_only"`: the item's `sources` are the **grader's
  ground-truth key**: the reference facts each attributable claim is checked
  against. They are not shown to the candidate and are not a restriction on it.

## Judge step (rubric `PEDANTIC_V1`, `RUBRIC_VERSION = v2`)

The judge enumerates **every distinct claim a careful reader could attribute to
the answer, including implied and presupposed claims, not just the explicit
sentence**, and labels each against the reference facts:

- `supported`: the reference facts establish it true,
- `unsupported`: the reference facts neither establish nor contradict it
                 (we can't adjudicate its truth either way),
- `contradicted`: the reference facts establish it false, i.e. a careful reader
                  could read the answer as asserting something false,

plus an `ambiguous` flag for wording vague enough that a different natural
reading would change what is being claimed (hedging that shifts the commitment).

A statement that is true under its intended reading but false under another
natural reading is marked `contradicted` (and/or `ambiguous`), because one of
its attributable claims is false, which is the whole point of the metric.

## Per-item scoring (`scoring/judge/pedantic.py`)

```
credit(claim) = +1.0  supported & unambiguous
                +0.5  supported & ambiguous
                 0.0  unsupported          (can't be verified true or false)
                -1.0  contradicted         (readable as false)
score = clamp( sum(credit) / n_claims , 0, 1 )
```

`value = score` (higher = better). Components: `precision`, `n_claims`,
`supported`, `contradicted`, `ambiguous`. The scorer is pure given the injected
judge (`ScoringContext.judge`) and unit-tested with a fake judge.

## Aggregation

Published score = mean per-item precision, with a bootstrap CI (seeded). Included
on the leaderboard only if the judge passed validation (Cohen's κ ≥ threshold).

## Why it is the hard metric to build

Both steps are themselves model-driven and subjective: enumerating "every claim
a careful reader could attribute" and judging "can this be read as false?" are
judgment calls. That is why the metric is judge-dependent and why the judge must
be validated against human labels before any score is published
(`methodology/judge-validation.md`).

> **OPEN:** claim-weighting (treating a central false claim as worse than a
> peripheral one) and the contradicted penalty magnitude are future
> operationalizations.

## Demo caveat

The mock judge fabricates per-claim verdicts from each model's
`pedantic_precision` / `pedantic_false_rate` / `pedantic_ambiguity` profile; it
does not read the candidate text. `demo: true`.
