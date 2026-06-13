"""Report writer (SPEC §7.7). The static site is built in ``site_build.py``."""

from __future__ import annotations

from pathlib import Path

from .jsonlio import write_json


def write_report(report: dict, out_dir: Path | str) -> Path:
    return write_json(Path(out_dir) / "report.json", report)
