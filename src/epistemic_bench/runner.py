"""Runner (SPEC §7.4): expand conditions, call models async+batched, dump raw.

Errors are captured on the Completion (never raised) so one failing call can't
sink a whole run.
"""

from __future__ import annotations

import asyncio
import random
import re
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .adapters import CallFn
from .jsonlio import write_jsonl
from .types import Completion, Item, ModelInfo, ResponseFormat, RunUnit, completion_to_dict


@dataclass(frozen=True)
class RunConfig:
    models: Sequence[ModelInfo]
    out_dir: Path
    concurrency: int = 16
    batch_size: int = 32
    temperature: float = 0.0
    max_tokens: int = 1024
    seed: int = 0
    org_pool: Sequence[str] = ()  # candidate maker names for creator_bias roles


class _Default(dict):
    """format_map helper that leaves unknown placeholders intact."""

    def __missing__(self, key: str) -> str:  # pragma: no cover - trivial
        return "{" + key + "}"


def _org_binding(item: Item, model: ModelInfo, cfg: RunConfig) -> dict[str, str]:
    """Resolve creator-bias org roles to concrete orgs, deterministically."""
    if item.metric != "creator_bias":
        return {}
    rng = random.Random(zlib.crc32(f"{cfg.seed}|{model.id}|{item.id}".encode("utf-8")))
    self_org = model.maker or "the model's maker"
    pool = [o for o in cfg.org_pool if o != self_org]
    rng.shuffle(pool)
    binding = {"{{ORG_SELF}}": self_org}
    n_rivals = sum(1 for cid in item.conditions if cid.startswith("org:rival"))
    for i in range(1, n_rivals + 1):
        binding[f"{{{{ORG_RIVAL_{i}}}}}"] = pool[(i - 1) % len(pool)] if pool else "a competing organization"
    return binding


def _render(item: Item, condition_id: str, cfg: RunConfig, model: ModelInfo, binding: Mapping[str, str]):
    cond = item.conditions[condition_id]
    template = cond.template_override or item.prompt_template
    merged = {**dict(item.template_vars), **dict(cond.vars or {})}
    prompt = template.format_map(_Default(merged))
    used: dict[str, str] = {}
    for token, concrete in binding.items():
        if token in prompt:
            prompt = prompt.replace(token, concrete)
            used[token] = concrete
    return prompt, used


def expand(items: Sequence[Item], cfg: RunConfig) -> list[RunUnit]:
    """Cartesian product item × condition × model, with prompts rendered and
    creator-bias org roles resolved (SPEC §4.4)."""
    units: list[RunUnit] = []
    for item in items:
        for model in cfg.models:
            binding = _org_binding(item, model, cfg)
            for cid in item.conditions:
                prompt, used = _render(item, cid, cfg, model, binding)
                units.append(
                    RunUnit(
                        item_id=item.id,
                        condition_id=cid,
                        model_id=model.id,
                        prompt=prompt,
                        response_format=item.response_format,
                        org_binding=used,
                    )
                )
    return units


def parse_output(raw: str, rf: ResponseFormat) -> Optional[dict]:
    """Best-effort structured parse of a completion per its response format."""
    if rf.type == "mcq" and rf.require_confidence:
        m = re.search(r"ANSWER:\s*([A-Za-z]+)", raw)
        if not m:
            return None
        out: dict[str, Any] = {"answer": m.group(1).strip().upper()}
        c = re.search(r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)", raw)
        if c:
            out["confidence"] = float(c.group(1))
        return out
    if rf.type == "mcq":
        m = re.search(r"(?:ANSWER|CHOICE):\s*([A-Za-z]+)", raw)
        return {"answer": m.group(1).strip().upper()} if m else None
    if rf.type == "stance":
        m = re.search(r"STANCE:\s*([0-9]+)", raw)
        return {"stance": int(m.group(1))} if m else None
    return {"text": raw.strip()}


def run_id() -> str:
    """Sortable run identifier: UTC timestamp + short random suffix."""
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{random.randint(0, 0xFFFF):04x}"


async def run(
    units: Sequence[RunUnit],
    adapters: Mapping[str, CallFn],
    registry: Mapping[str, ModelInfo],
    cfg: RunConfig,
) -> Path:
    """Execute units async + batched; append Completions to completions.jsonl."""
    out_dir = Path(cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(cfg.concurrency)

    async def one(u: RunUnit) -> Completion:
        info = registry[u.model_id]
        call = adapters[info.provider]
        params = {
            "model": u.model_id,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "item_id": u.item_id,
            "condition_id": u.condition_id,
            "model_id": u.model_id,
        }
        async with sem:
            try:
                raw = await call(u.prompt, params)
                return Completion(u.item_id, u.condition_id, u.model_id, raw, parse_output(raw, u.response_format))
            except Exception as e:  # captured, not raised
                return Completion(u.item_id, u.condition_id, u.model_id, "", None, {}, f"{type(e).__name__}: {e}")

    results: list[Completion] = []
    for i in range(0, len(units), cfg.batch_size):
        chunk = units[i : i + cfg.batch_size]
        results.extend(await asyncio.gather(*(one(u) for u in chunk)))

    path = out_dir / "completions.jsonl"
    write_jsonl(path, (completion_to_dict(c) for c in results))
    return path
