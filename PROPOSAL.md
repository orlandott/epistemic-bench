# epistemic-bench — Proposal for Feedback

**To:** Justin Shenk (mentor) · **From:** Orlando · **Date:** 2026-06-24
**Repo:** `orlandott/epistemic-bench` · **Status:** v1 implemented end-to-end; seeking feedback before scaling the item bank

---

## Where the idea came from

The project is a direct build-out of **Forethought's "epistemic virtue evals"
sketch**. In their *AI for Epistemics* agenda, Forethought proposes benchmark
suites that score frontier models on **epistemic virtues** — calibration,
clarity, precision, non-bias, non-sycophancy, non-manipulation — including a
"pedantic mode" where individual statements must avoid being even ambiguously
misleading. Their argument is that public, per-virtue evals change the
*incentive landscape*: if labs know models are compared on these virtues, they
feel pressure to improve them at the development stage.

That sketch is a paragraph of motivation. **epistemic-bench is the concrete,
reproducible benchmark that implements it** — a real item bank, real scorers, a
published per-virtue leaderboard, and anti-gaming machinery.

> Source: Forethought, *Project ideas: Epistemics* / *What's important in "AI
> for Epistemics"* — https://www.forethought.org/research/project-ideas-epistemics

## What it is

An open benchmark that scores LLMs on epistemic *behavior* (not raw capability)
and publishes a **journalist-friendly, per-virtue leaderboard** backed by a
documented, reproducible methodology. Built in two tiers:

| Tier | Metrics | Scoring |
|---|---|---|
| **v1** (built) | Calibration · Sycophancy resistance · Creator/loyalty bias · Framing consistency · Clarity (programmatic) | Pure functions, no judge |
| **v2** (built, gated) | Pedantic precision · Thoroughness | LLM judge, **withheld until it clears human-labeled agreement (Cohen's κ / Pearson r)** |

Deliberate design choices: **no single composite score** (a per-virtue profile
resists Goodharting and journalist oversimplification), and **flat files only**
(versioned JSONL + a static site, no backend).

## The ask: scale the item bank to **100 private questions per category**

The methodology, scorers, and pipeline are done. The current item bank is a
**proof-of-scale seed** (30 calibration, 20 sycophancy, 14 creator-bias, 10
framing/clarity, 6 each pedantic/thoroughness). The next step is **statistical
credibility**, which means minting real items at volume:

- **Target: ~100 *private* questions per category**, held out in a separate
  access-controlled repo (`epistemic-bench-private`).
- **Public/private split ≈ 30/70** per category. The **private split is the
  canonical published number**; the public split (~40+ items) is the
  reproducible reference shown alongside.
- This is the **anti-Goodhart backbone**: labs cannot train to a test they
  cannot see. It's reinforced by **operationalization rotation** — each metric
  has interchangeable scored variants, and each quarterly release burns exposed
  public items, promotes fresh ones, and rotates which variant counts.

Every published number is **stamped** with bank version, split, and active
operationalization, so a score is never ambiguous about what it measured.

## What already works (so feedback lands on substance, not vaporware)

- Full pipeline runs offline with a mock adapter: `python -m epistemic_bench demo`
  → run → score → aggregate → render leaderboard.
- All seven scorers implemented + tested; v2 judge-validation gate enforced.
- Public/private split + rotation driven by `itembank/manifest.yaml`
  (`epb manifest`, `epb rotate`).
- One methodology doc per metric under `methodology/` for auditability.

## Questions I'd love your feedback on

1. **Is 100 private / category the right target** for credible per-virtue
   numbers, or should it vary by metric (e.g. calibration needs more for stable
   ECE bins than creator-bias)?
2. **Is 30/70 public/private the right ratio**, and is *private-as-canonical*
   the right call for journalist-facing numbers?
3. **Item sourcing at scale** — how do we mint 700+ private items per release
   without quality drift or annotator bias? (Expert-authored vs. templated vs.
   model-assisted-then-human-vetted?)
4. **v2 judge validation** — what κ / r threshold would you trust before
   publishing pedantic precision and thoroughness?
5. **Rotation cadence** — is quarterly burn/promote/mint realistic to sustain,
   or should the first few releases be slower?

---

*Full design in [SPEC.md](SPEC.md); per-metric methodology in [`methodology/`](methodology/).*
