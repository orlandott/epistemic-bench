"""Item bank: load + validate + iterate versioned JSONL (SPEC §4, §7.3).

We ship a JSON Schema at ``itembank/schema/item.schema.json`` for external
tooling, but validation here is a dependency-free internal validator so
``epb validate`` runs anywhere (the ``jsonschema`` package is optional).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Iterator

from .jsonlio import read_jsonl
from .types import (
    Condition,
    Item,
    Metric,
    Reference,
    ResponseFormat,
    Split,
)

_METRICS = {"calibration", "sycophancy", "creator_bias", "framing", "clarity", "pedantic", "thoroughness"}
_SPLITS = {"public", "private"}
_RESP_TYPES = {"mcq", "short_answer", "stance", "free_text"}
_REF_KINDS = {"answer", "invariant", "stance", "sources_only"}
_ID_RE = re.compile(r"^[a-z_]+/v[0-9]+/[a-z0-9-]+$")


def validate_item(d: dict) -> list[str]:
    """Return a list of human-readable validation errors ([] means valid)."""
    errs: list[str] = []
    iid = d.get("id", "<no-id>")

    def need(field: str) -> bool:
        if field not in d:
            errs.append(f"{iid}: missing required field '{field}'")
            return False
        return True

    for f in ("id", "schema_version", "metric", "split", "prompt_template",
              "conditions", "response_format", "reference"):
        need(f)

    if "id" in d and not _ID_RE.match(str(d["id"])):
        errs.append(f"{iid}: id must match '<metric>/v<N>/<slug>' (got {d['id']!r})")
    if "metric" in d and d["metric"] not in _METRICS:
        errs.append(f"{iid}: unknown metric {d['metric']!r}")
    if "split" in d and d["split"] not in _SPLITS:
        errs.append(f"{iid}: split must be one of {sorted(_SPLITS)}")

    conds = d.get("conditions")
    if isinstance(conds, dict):
        if not conds:
            errs.append(f"{iid}: 'conditions' must have at least one condition")
        for cid, cond in conds.items():
            if not isinstance(cond, dict) or "id" not in cond:
                errs.append(f"{iid}: condition {cid!r} missing 'id'")
    elif conds is not None:
        errs.append(f"{iid}: 'conditions' must be an object")

    rf = d.get("response_format")
    if isinstance(rf, dict):
        if rf.get("type") not in _RESP_TYPES:
            errs.append(f"{iid}: response_format.type must be one of {sorted(_RESP_TYPES)}")
        if rf.get("type") == "mcq" and not rf.get("options"):
            errs.append(f"{iid}: mcq response_format requires 'options'")
    elif rf is not None:
        errs.append(f"{iid}: 'response_format' must be an object")

    ref = d.get("reference")
    if isinstance(ref, dict):
        if ref.get("kind") not in _REF_KINDS:
            errs.append(f"{iid}: reference.kind must be one of {sorted(_REF_KINDS)}")
        if ref.get("kind") == "answer" and not ref.get("answer"):
            errs.append(f"{iid}: reference.kind=='answer' requires 'answer'")
    elif ref is not None:
        errs.append(f"{iid}: 'reference' must be an object")

    return errs


def item_from_dict(d: dict) -> Item:
    """Build an Item dataclass from a parsed JSONL object (assumes validated)."""
    conditions = {
        cid: Condition(
            id=c.get("id", cid),
            vars=c.get("vars", {}) or {},
            template_override=c.get("template_override"),
            normalize=c.get("normalize"),
        )
        for cid, c in d["conditions"].items()
    }
    rf = d["response_format"]
    ref = d["reference"]
    return Item(
        id=d["id"],
        schema_version=str(d["schema_version"]),
        metric=d["metric"],
        split=d["split"],
        prompt_template=d["prompt_template"],
        conditions=conditions,
        response_format=ResponseFormat(
            type=rf["type"],
            options=tuple(rf["options"]) if rf.get("options") else None,
            require_confidence=bool(rf.get("require_confidence", False)),
            stance_scale=tuple(rf["stance_scale"]) if rf.get("stance_scale") else None,
        ),
        reference=Reference(
            kind=ref["kind"],
            answer=ref.get("answer"),
            expected_stance=ref.get("expected_stance"),
            notes=ref.get("notes", ""),
        ),
        template_vars=d.get("template_vars", {}) or {},
        category=d.get("category"),
        difficulty=d.get("difficulty"),
        sources=tuple(d.get("sources", []) or []),
        tags=tuple(d.get("tags", []) or []),
        provenance=d.get("provenance", {}) or {},
    )


def _iter_jsonl_files(root: Path) -> Iterator[Path]:
    if root.is_file():
        yield root
    elif root.is_dir():
        yield from sorted(root.rglob("*.jsonl"))


def validate_file(path: Path | str) -> list[str]:
    """Validate every line of one JSONL file. Backs ``epb validate``."""
    errs: list[str] = []
    for i, d in enumerate(read_jsonl(path), start=1):
        for e in validate_item(d):
            errs.append(f"{Path(path).name}:{i}: {e}")
    return errs


def load_items(*roots: Path | str, splits: tuple[Split, ...] = ("public",)) -> list[Item]:
    """Load + validate items from one or more roots (dir or file).

    At eval time pass both the public dir and the private repo's dir; filter by
    ``splits`` to control which lines are included.
    """
    items: list[Item] = []
    seen: set[str] = set()
    for root in roots:
        for path in _iter_jsonl_files(Path(root)):
            for i, d in enumerate(read_jsonl(path), start=1):
                errs = validate_item(d)
                if errs:
                    raise ValueError(f"{path}:{i}: invalid item:\n  " + "\n  ".join(errs))
                if d["split"] not in splits:
                    continue
                if d["id"] in seen:
                    raise ValueError(f"{path}:{i}: duplicate item id {d['id']!r}")
                seen.add(d["id"])
                items.append(item_from_dict(d))
    return items


def iter_items(items: Iterable[Item], metric: Metric | None = None) -> Iterator[Item]:
    for it in items:
        if metric is None or it.metric == metric:
            yield it
