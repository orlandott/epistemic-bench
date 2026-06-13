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
