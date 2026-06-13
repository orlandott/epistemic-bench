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

Private split (held out, separate access-controlled repo): not yet populated.

### Changelog
- **v1 initial:** 30 calibration items minted for the milestone (SPEC §11).
- **v1 + sycophancy:** 20 sycophancy items added (`syc-v1a`); introduced the
  `Condition.user_view` field (the answer the simulated user asserts).
- **v1 + creator_bias:** 14 creator-bias items added (`cb-v1a`); role-keyed
  conditions resolved per model from the runner's `org_pool`.
- **v1 + framing:** 10 framing items added (`fr-v1a`); uses the
  `Condition.normalize` label→canonical map so option reordering is not counted
  as an answer change. No items retired/burned yet. Rotation cadence and budget:
  see `methodology/rotation.md` (OPEN — quarterly recommended).
