# Methodology — Public/private split & rotation (SPEC §8)

The anti-Goodhart backbone. A public leaderboard that scores only public items can
be trained against; this document defines how the held-out split and
operationalization rotation prevent that, and how every number is stamped so the
protection is auditable (SPEC §9).

The control point is **`itembank/manifest.yaml`** (machine-readable): bank
version, canonical split, and the active operationalization per metric.

## 1. The split

Every item carries `split: "public" | "private"`.

- **Public split** (`itembank/public/`) — fully visible and reproducible by
  anyone. It is the transparency surface and the `public_reference` number.
- **Private split** — lives in a **separate, access-controlled repo** (e.g.
  `epistemic-bench-private`), never in this public repo. It is the **canonical**
  (headline) number: items a model could not have memorized.

The loader takes multiple roots; maintainers pass both at eval time:

```bash
epb run --itembank itembank/public /path/to/epistemic-bench-private/items
```

The report makes the canonical split (manifest `canonical_split: private`) the
headline and attaches the public number as `public_reference`. If no private
split is loaded, the report falls back to public and **labels it as
reproducible-but-not-held-out** (a visible warning), so a public-only number is
never mistaken for the canonical one. See `itembank/private.example/` for the
exact format.

> **OPEN (SPEC §8.1):** target ratio ≈ **30% public / 70% private** per metric;
> the private split is canonical. Confirm the ratio and which split journalists
> see as primary.

## 2. Operationalization rotation

Each metric has one or more interchangeable **operationalizations**, tagged
`rotation:<group>` on items (e.g. `cal-v1a`, and the reserve `cal-v1b`). The
manifest pins which group is **active** (scored) for the current release; the
others are reserve. `epb run` scores only the active group (`--no-rotate` scores
all). Inspect and plan with:

```bash
epb manifest      # active vs reserve groups + public/private counts
epb rotate        # dry-run: what to burn / which group activates next
```

### Per-release procedure (cadence: quarterly — OPEN, SPEC §8.2)

On each release `v<N>`:

1. **Burn** a fraction (default 25%) of the active public items — exposure may
   have contaminated them. `epb rotate` lists the ids; record them in the
   manifest's `burned` and in `itembank/VERSIONS.md`.
2. **Promote** fresh private items into the public split to refill it (keeps the
   public split representative without re-exposing burned items).
3. **Mint** new private items to refill the held-out pool.
4. **Activate** the next operationalization (`active:` bump) so even a fully
   leaked public split maps to a different scored operationalization next cycle.

Because the canonical score uses the private split **and** rotates which
operationalization counts, training on the visible public split of release `v<N>`
does not transfer to the canonical score of `v<N+1>`.

## 3. What gets stamped

Every `report.json` records `bank_version`, `canonical_split` (policy),
`splits_loaded`, `private_loaded`, and `active_operationalizations`; each virtue
records the split actually used and `splits_available`; each per-model entry
carries its `split` and (when canonical is private) the `public_reference`. The
leaderboard therefore always states exactly what was measured, on which split, at
which operationalization and bank version.
