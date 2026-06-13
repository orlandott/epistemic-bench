"""Thin judge-model call wrapper (SPEC §7.5, §10) — STUB.

The judge model is pinned + versioned and must not share a maker with the model
under test (OPEN in SPEC §10; cross-maker/ensemble recommended).
"""

from __future__ import annotations

from typing import Any, Mapping


async def judge(prompt: str, rubric: str, params: Mapping[str, Any]) -> str:
    raise NotImplementedError("judge client is a stub (SPEC §10)")
