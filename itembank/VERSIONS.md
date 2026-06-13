# Item bank versions & rotation log

The item bank is versioned; the version (`v<N>`) is embedded in every item `id`
(e.g. `calibration/v1/cal-0007`) and stamped onto every published number. See
SPEC.md §8 for the public/private split and rotation policy.

## v1 (2026-06-13) — initial public release

| Metric | File | Items | Rotation group | Notes |
|---|---|---|---|---|
| calibration | `public/calibration.v1.jsonl` | 30 | `cal-v1a` | 10 easy / 10 medium / 10 hard, MCQ + numeric confidence |

Private split (held out, separate access-controlled repo): not yet populated.

### Changelog
- **v1 initial:** 30 calibration items minted for the milestone (SPEC §11). No
  items retired/burned yet. Rotation cadence and budget: see
  `methodology/rotation.md` (OPEN — quarterly recommended).
