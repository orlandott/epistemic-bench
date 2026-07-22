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

Reserve operationalizations (dormant until rotation activates them — see
`manifest.yaml`, `methodology/rotation.md`):

| Metric | File | Items | Rotation group |
|---|---|---|---|
| calibration | `public/calibration.v1b.jsonl` | 30 | `cal-v1b` (10 easy / 10 medium / 10 hard) |
| sycophancy | `public/sycophancy.v1b.jsonl` | 10 | `syc-v1b` (5 true / 5 false claims) |
| creator_bias | `public/creator_bias.v1b.jsonl` | 6 | `cb-v1b` |
| framing | `public/framing.v1b.jsonl` | 6 | `fr-v1b` |
| clarity | `public/clarity.v1b.jsonl` | 6 | `clr-v1b` |
| pedantic | `public/pedantic.v1b.jsonl` | 4 | `ped-v1b` |
| thoroughness | `public/thoroughness.v1b.jsonl` | 4 | `thr-v1b` |

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
- **v1 reserve fill (2026-07-22):** `cal-v1b` grown 8 → 30 items
  (`cal-1009`…`cal-1030`, balanced 10/10/10 across difficulty tiers), meeting the
  SPEC §11 ~60-public-calibration-item target across both operationalizations.
  Minted a reserve operationalization for every other metric — `syc-v1b` (10),
  `cb-v1b` (6), `fr-v1b` (6), `clr-v1b` (6), `ped-v1b` (4), `thr-v1b` (4) — so
  `epb rotate` now has a real next-active group per metric. Active groups
  unchanged; no items retired/burned. Data license notice added at
  `itembank/LICENSE` (CC BY 4.0); prose schema doc added at `itembank/SCHEMA.md`.
