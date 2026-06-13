# Private split — example template (SPEC §8.1)

This directory is an **example/template only**. The real private held-out split
must NOT live in this public repository — it lives in a separate,
access-controlled repo (e.g. `epistemic-bench-private`) with this exact layout
and schema. The items here are illustrative so maintainers can see the format and
so the split machinery is testable end to end.

## How it is used

The loader accepts multiple item-bank roots. At eval time, maintainers clone the
private repo alongside this one and pass both:

```bash
epb run --itembank itembank/public /path/to/epistemic-bench-private/items
```

Private items carry `"split": "private"` and a `rotation:<group>` tag matching an
**active** operationalization in `itembank/manifest.yaml`, so they are scored
alongside the public items. The report then makes the **private** split the
canonical (headline) number and attaches the public number as `public_reference`
(per `canonical_split` in the manifest).

## Why held out

The public split is fully visible and reproducible, which also means a lab could
train against it. The private split is never published, so it measures behavior on
items the model has not been able to memorize. Combined with operationalization
rotation (SPEC §8.2, `methodology/rotation.md`), this is the benchmark's
anti-Goodhart backbone.

Files here use the normal `.jsonl` extension so they load; in the real private
repo they are the genuine held-out items and never committed to anything public.
