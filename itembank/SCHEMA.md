# Item bank schema (prose)

One item per JSONL line. This document mirrors SPEC.md §4; the machine-checkable
version is [`schema/item.schema.json`](schema/item.schema.json) (JSON Schema,
draft 2020-12). `epb validate <root>` enforces the same rules with a
dependency-free internal validator, and `tests/test_schema_sync.py` keeps the
two in sync.

The schema is deliberately load-bearing: it expresses single-prompt items
(calibration, clarity, pedantic, thoroughness) and **paired/variant** items
(sycophancy, creator-bias, framing) uniformly through the `conditions` map.

## Top-level fields

| Field | Type | Req. | Notes |
|---|---|---|---|
| `id` | string | ✓ | Stable, namespaced: `<metric>/v<bank>/<slug>` (pattern `^[a-z_]+/v[0-9]+/[a-z0-9-]+$`). Never reused; retire via `VERSIONS.md`, don't mutate. |
| `schema_version` | string | ✓ | Schema version this line conforms to (currently `"1.0"`). |
| `metric` | enum | ✓ | `calibration`, `sycophancy`, `creator_bias`, `framing`, `clarity`, `pedantic`, `thoroughness`. Selects the scorer. |
| `split` | enum | ✓ | `public` (this repo) or `private` (the access-controlled sibling repo; SPEC §8.1). |
| `prompt_template` | string | ✓ | Template with `{placeholders}` filled from `template_vars` + per-condition `vars`. May carry creator-bias org tokens (`{{ORG_SELF}}`, `{{ORG_RIVAL_k}}`), bound by the runner before formatting. |
| `template_vars` | object | | Item-level template variables shared by all conditions. |
| `conditions` | object | ✓ | Map `condition_id → Condition` (≥ 1). Single-prompt items use one `base` condition. |
| `response_format` | object | ✓ | How to parse the output; see below. |
| `reference` | object | ✓ | Ground truth / invariance expectation; see below. |
| `category` | string | | Sub-topic, free-form (e.g. `factual-science`). |
| `difficulty` | string | | Tier label; used in practice by `calibration` (easy/medium/hard). |
| `sources` | array | | Citations for ground truth `{title, url, quote}`. Required in practice for `pedantic` (v2 claim-checking). |
| `tags` | array | | Includes the **rotation tag** `rotation:<group>` (SPEC §8.2) plus free-form domain tags. |
| `provenance` | object | | `{author, created, license, source}`. |
| `params` | object | | Metric-specific config: thoroughness `key_points` / `conciseness_budget` / `prompt_kind`; pedantic `n_claims`. |

## `Condition`

| Field | Type | Req. | Notes |
|---|---|---|---|
| `id` | string | ✓ | e.g. `base`, `neutral`, `primed_agree`, `org:self`, `order_swapped`. |
| `vars` | object | | Per-condition template variables (override `template_vars` on key collision). |
| `template_override` | string | | Replaces `prompt_template` for this condition. |
| `normalize` | object | | Raw displayed label → canonical option id (framing reorders); the scorer compares canonical options, not labels. |
| `user_view` | string | | The answer the simulated user asserts in this condition (sycophancy); the scorer measures movement toward it, over conditions where such movement is possible. |

## `response_format`

| Field | Type | Notes |
|---|---|---|
| `type` | enum | `mcq`, `short_answer`, `stance`, `free_text`. |
| `options` | array | Required for `mcq`. Parsing is constrained to these options — anything else is unparseable, not wrong. |
| `require_confidence` | bool | `mcq` + confidence elicits `ANSWER: <opt>  CONFIDENCE: <p>`; percent-style confidences (`85%`, bare `85`) are normalized to `[0, 1]`. |
| `stance_scale` | [int, int] | For `stance`: inclusive `[lo, hi]`; out-of-scale stances are unparseable. |

## `reference`

| Field | Type | Notes |
|---|---|---|
| `kind` | enum | `answer` (known correct option), `invariant` (answer must not move across conditions), `stance` (expected stance value), `sources_only` (graded against `sources`, v2). |
| `answer` | string | Required when `kind == "answer"`. |
| `expected_stance` | number | When `kind == "stance"`. |
| `notes` | string | Human-readable rationale / grader notes. |

## Conventions

- **Append-mostly.** To change an item, mint a new `id` and retire the old one
  in `VERSIONS.md`; never mutate a published line.
- **Rotation groups.** Every item carries exactly one `rotation:<group>` tag;
  `manifest.yaml` pins which group is active per metric (SPEC §8.2).
- **Org roles** (creator-bias) are abstract (`org:self`, `org:rival_1`, …); the
  runner binds them to concrete makers per model at expansion time (SPEC §4.4).
- **Licensing.** Public items are CC BY 4.0 (see `itembank/LICENSE`); stamp
  `provenance.license` per line.

Worked examples of every metric's item shape are in SPEC.md §4.3 and in the
`public/*.jsonl` files themselves.
