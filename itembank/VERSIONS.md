# Item bank versions & rotation log

The item bank is versioned; the version (`v<N>`) is embedded in every item `id`
(e.g. `calibration/v1/cal-0007`) and stamped onto every published number. See
SPEC.md §8 for the public/private split and rotation policy.

## v1 (2026-06-13) — initial public release

| Metric | File | Items | Rotation group | Notes |
|---|---|---|---|---|
| calibration | `public/calibration.v1.jsonl` | 30 | `cal-v1a` | 10 easy / 10 medium / 10 hard, MCQ + numeric confidence |
| sycophancy | `public/sycophancy.v1.jsonl` | 20 | `syc-v1a` | 10 true / 10 false yes-no claims; neutral + belief-primed conditions with `user_view` |
| creator_bias | `public/creator_bias.v1.jsonl` | 14 | `cb-v1a` | role-keyed positions (`org:self` / `org:rival_*` / `org:neutral`); 1–5 stance; runner resolves org roles |
| framing | `public/framing.v1.jsonl` | 10 | `fr-v1a` | neutral / loaded-positive / loaded-negative / order-swapped framings; `normalize` maps labels to canonical options |
| clarity | `public/clarity.v1.jsonl` | 10 | `clr-v1a` | free-text; programmatic hedge-density + commitment-shift analysis (no judge) |
| pedantic | `public/pedantic.v1.jsonl` | 6 | `ped-v1a` | v2, judge-gated; free-text answers + `sources`; `params.n_claims` |
| thoroughness | `public/thoroughness.v1.jsonl` | 6 | `thr-v1a` | v2, judge-gated; free-text; `params.key_points` + `conciseness_budget` + `prompt_kind` |

Reserve operationalization: `public/calibration.v1b.jsonl` (8 items, `cal-v1b`) —
dormant until rotation activates it (see `manifest.yaml`, `methodology/rotation.md`).

## v1.1 (2026-06-15) — depth pass: 100 items per active operationalization

Every active public operationalization was brought up to **100 items** to give
each area a statistically meaningful floor (per-area scores at the prior counts
of 6–30 were inside the noise). This is a starting floor, **not** the target —
near-ceiling virtues need ≈140–220 items to resolve realistic ~0.08–0.10 gaps
between frontier models, and the judge-scored areas (`pedantic`, `thoroughness`)
need more still to overcome judge variance.

| Metric | Items | Seed | Generated |
|---|---|---|---|
| calibration (`cal-v1a`) | 100 | 30 | 70 |
| sycophancy (`syc-v1a`) | 100 | 20 | 80 |
| creator_bias (`cb-v1a`) | 100 | 14 | 86 |
| framing (`fr-v1a`) | 100 | 10 | 90 |
| clarity (`clr-v1a`) | 100 | 10 | 90 |
| pedantic (`ped-v1a`) | 100 | 6 | 94 |
| thoroughness (`thr-v1a`) | 100 | 6 | 94 |

Generated items are minted by `scripts/build_v1_100.py` (idempotent — every
minted item carries the `batch:v1-100` tag; re-running drops and regenerates
them, never duplicating). Hand-authored seed items are preserved verbatim and
generated ids continue from where the seeds stop. The calibration generator
spreads the correct-answer letter evenly across A/B/C/D so the key cannot be
gamed positionally; sycophancy is balanced 50 true / 50 false. The `cal-v1b`
reserve pool (8 items) is unchanged.

## v1.2 (2026-06-15) — second depth tier: 200 items per active operationalization

Doubled every active public operationalization to **200 items** (1,400 active
public items total). This pushes each area toward the depth where realistic
~0.08–0.10 frontier gaps become resolvable; judge-scored areas still benefit
from more, and the most templated areas (`framing`, `clarity`) are the first
candidates for a discrimination filter before deepening further.

| Metric | Items | Seed | Generated |
|---|---|---|---|
| calibration (`cal-v1a`) | 200 | 30 | 170 |
| sycophancy (`syc-v1a`) | 200 | 20 | 180 |
| creator_bias (`cb-v1a`) | 200 | 14 | 186 |
| framing (`fr-v1a`) | 200 | 10 | 190 |
| clarity (`clr-v1a`) | 200 | 10 | 190 |
| pedantic (`ped-v1a`) | 200 | 6 | 194 |
| thoroughness (`thr-v1a`) | 200 | 6 | 194 |

How the additional items were sourced (same idempotent generator, same
`batch:v1-100` marker tag):

- **calibration / sycophancy** — topped up from **truth tables** (country→capital,
  element→symbol/atomic-number, and computed arithmetic), so every added answer
  key and truth label is correct by construction rather than hand-asserted.
  Sycophancy remains balanced 100 YES / 100 NO; calibration answer letters stay
  spread across A/B/C/D.
- **framing** — 20 additional equivalent-framing scenarios (attribute/goal
  framing), each with neutral / loaded-positive / loaded-negative / order-swapped
  conditions.
- **creator_bias, clarity, pedantic, thoroughness** — extra curated prose pools
  in `scripts/_pool_{cb,clr,ped,thr}.py`, deduped against the existing pools.
  Pedantic items assert only what their three bundled sources state.

Verified at build time: all items pass `epb validate`; zero duplicate ids and
zero duplicate prompt/claim/position/frame text within any file.

Split/rotation control: `manifest.yaml` (bank version, canonical split, active
operationalization per metric). Private split (canonical, held out) lives in a
separate access-controlled repo; `private.example/` is the format template.
Judge-validation gold samples: `validation/judge/{pedantic,thoroughness}.sample.jsonl`.

### Changelog
- **v1 initial:** 30 calibration items minted for the milestone (SPEC §11).
- **v1 + sycophancy:** 20 sycophancy items added (`syc-v1a`); introduced the
  `Condition.user_view` field (the answer the simulated user asserts).
- **v1 + creator_bias:** 14 creator-bias items added (`cb-v1a`); role-keyed
  conditions resolved per model from the runner's `org_pool`.
- **v1 + framing:** 10 framing items added (`fr-v1a`); uses the
  `Condition.normalize` label→canonical map so option reordering is not counted
  as an answer change.
- **v2:** 6 pedantic (`ped-v1a`) + 6 thoroughness (`thr-v1a`) judge-gated items
  added; introduced the `Item.params` field (metric-specific config) and the
  judge-validation gold samples under `validation/judge/`.
- **v1 + clarity:** 10 clarity items (`clr-v1a`) added; programmatic hedge /
  commitment-shift scorer (the judged traceability half stays v2).
- **split + rotation:** added `manifest.yaml` (split/rotation control), a reserve
  calibration operationalization (`cal-v1b`, 8 items), and the `private.example/`
  template. `MetricScore` now carries `split`; reports stamp bank version, splits
  loaded, canonical split, and active operationalizations. No items
  retired/burned yet. Rotation cadence and budget: see `methodology/rotation.md`
  (OPEN — quarterly recommended).
- **v1.1 depth pass:** every active public operationalization expanded to 100
  items via `scripts/build_v1_100.py` (604 generated items across the 7 areas;
  `batch:v1-100` tag). Balanced calibration answer keys and 50/50 sycophancy
  truth labels. Updated `tests/test_rotation.py` count assertions (calibration
  active 30→100, burn_n 7→25).
- **v1.2 second depth tier:** doubled every active operationalization to 200
  items (1,204 generated items total). Calibration/sycophancy top-ups generated
  from truth tables (correct by construction); framing extended with 20 new
  scenarios; creator_bias/clarity/pedantic/thoroughness extended from curated
  pools in `scripts/_pool_*.py`. Updated `tests/test_rotation.py` (calibration
  active 100→200, burn_n 25→50).
