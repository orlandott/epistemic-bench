"""Tiny JSONL read/write helpers. Flat files, no DB (SPEC §1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator


def write_jsonl(path: Path | str, records: Iterable[dict]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False))
            fh.write("\n")
    return path


def read_jsonl(path: Path | str) -> Iterator[dict]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def write_json(path: Path | str, obj: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def read_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
