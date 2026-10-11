"""Public/private split + operationalization rotation (SPEC §8).

The anti-Goodhart machinery. Two ideas:

1. **Split**: every item is `public` or `private`. The public split is fully
   reproducible; the private split (a separate access-controlled repo) is the
   canonical anti-train-to-test surface. Scores are stamped with their split.

2. **Operationalization rotation**: each metric has one or more interchangeable
   operationalizations, tagged `rotation:<group>` on items. A versioned
   **manifest** pins which group is *active* (canonical) for the current release.
   Even if the public split leaks, next release activates a different
   operationalization, so training on leaked items does not transfer.

This module loads the manifest, selects the active operationalization, and
produces a rotation **plan** (a dry-run of what to burn / promote / mint for the
next release). Actually moving items into the private repo is a maintainer step;
see `methodology/rotation.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Optional

import yaml

from .types import Item


@dataclass(frozen=True)
class Manifest:
    bank_version: str
    canonical_split: str  # "private" | "public"; which split is the headline number
    active: Mapping[str, str]  # metric -> active rotation group
    operationalizations: Mapping[str, list]  # metric -> [groups]
    burned: frozenset  # rotation groups retired from scoring (exposed/contaminated)
    cadence: str = "quarterly"
    release: str = ""


def load_manifest(path: Path | str) -> Manifest:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    metrics = data.get("rotation", {}).get("metrics", {})
    return Manifest(
        bank_version=str(data.get("bank_version", "v?")),
        canonical_split=str(data.get("canonical_split", "public")),
        active={m: cfg["active"] for m, cfg in metrics.items()},
        operationalizations={m: list(cfg.get("operationalizations", [cfg["active"]])) for m, cfg in metrics.items()},
        burned=frozenset(data.get("burned", []) or []),
        cadence=str(data.get("rotation", {}).get("cadence", "quarterly")),
        release=str(data.get("rotation", {}).get("release", data.get("bank_version", ""))),
    )


def rotation_group_of(item: Item) -> Optional[str]:
    """Extract the `rotation:<group>` tag from an item, if present."""
    for tag in item.tags:
        if tag.startswith("rotation:"):
            return tag.split(":", 1)[1]
    return None


def select_active(items: Iterable[Item], manifest: Manifest) -> list[Item]:
    """Keep only items in the active operationalization for their metric.

    Items whose metric is unmanaged by the manifest pass through. Items in a
    burned group are always dropped. Items whose metric IS managed but whose
    group is not the active one are dropped (they are reserve/retired).
    """
    out = []
    for it in items:
        group = rotation_group_of(it)
        if group is not None and group in manifest.burned:
            continue
        active = manifest.active.get(it.metric)
        if active is None:
            out.append(it)  # unmanaged metric
        elif group == active:
            out.append(it)
    return out


def rotation_plan(items: Iterable[Item], manifest: Manifest, *, burn_fraction: float = 0.25) -> dict:
    """Dry-run plan for the next release: per metric, which public items in the
    active group would be burned, and the public/private balance. Reporting only;
    minting new private items is a maintainer step."""
    items = list(items)
    plan = {"release_from": manifest.release, "burn_fraction": burn_fraction, "metrics": {}}
    for metric, active in manifest.active.items():
        in_group = [it for it in items if rotation_group_of(it) == active]
        public = [it for it in in_group if it.split == "public"]
        private = [it for it in in_group if it.split == "private"]
        reserves = [g for g in manifest.operationalizations.get(metric, []) if g != active and g not in manifest.burned]
        plan["metrics"][metric] = {
            "active": active,
            "n_public": len(public),
            "n_private": len(private),
            "burn_n": int(len(public) * burn_fraction),
            "burn_ids": [it.id for it in public[: int(len(public) * burn_fraction)]],
            "reserve_operationalizations": reserves,
            "next_active": reserves[0] if reserves else active,
        }
    return plan


def split_counts(items: Iterable[Item]) -> dict:
    counts = {"public": 0, "private": 0}
    for it in items:
        counts[it.split] = counts.get(it.split, 0) + 1
    return counts
