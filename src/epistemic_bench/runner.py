"""Runner (SPEC §7.4): expand conditions, call models async+batched, dump raw.

Errors are captured on the Completion (never raised) so one failing call can't
sink a whole run. Transient adapter failures are retried with exponential
backoff (``RunConfig.max_retries``); configuration errors
(``adapters.AdapterConfigError``) are not retried. Completions are streamed to
``completions.jsonl`` batch by batch, so a crashed run keeps everything already
answered and can be resumed (``run(..., resume=True)`` / ``epb run --resume``).
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .adapters import AdapterConfigError, CallFn
from .jsonlio import read_jsonl
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
    max_retries: int = 2  # transient-failure retries per unit (config errors are not retried)
    retry_base_delay: float = 1.0  # seconds; backoff = base * 2**attempt


class _Default(dict):
    """format_map helper that leaves unknown placeholders intact."""

    def __missing__(self, key: str) -> str:  # pragma: no cover - trivial
        return "{" + key + "}"


def _norm_org(name: str) -> str:
    return name.strip().casefold()


def _org_binding(item: Item, model: ModelInfo, cfg: RunConfig) -> dict[str, str]:
    """Resolve creator-bias org roles to concrete orgs, deterministically."""
    if item.metric != "creator_bias":
        return {}
    rng = random.Random(zlib.crc32(f"{cfg.seed}|{model.id}|{item.id}".encode("utf-8")))
    self_org = model.maker or "the model's maker"
    # Compare normalized so a casing/whitespace mismatch between the model's
    # maker and the org pool can't leak the self org into the rival pool.
    pool = [o for o in cfg.org_pool if _norm_org(o) != _norm_org(self_org)]
    rng.shuffle(pool)
    binding = {"{{ORG_SELF}}": self_org}
    n_rivals = sum(1 for cid in item.conditions if cid.startswith("org:rival"))
    for i in range(1, n_rivals + 1):
        binding[f"{{{{ORG_RIVAL_{i}}}}}"] = pool[(i - 1) % len(pool)] if pool else "a competing organization"
    return binding


def _apply_binding(text: str, binding: Mapping[str, str], used: dict[str, str]) -> str:
    for token, concrete in binding.items():
        if token in text:
            text = text.replace(token, concrete)
            used[token] = concrete
    return text


def _render(item: Item, condition_id: str, cfg: RunConfig, model: ModelInfo, binding: Mapping[str, str]):
    cond = item.conditions[condition_id]
    template = cond.template_override or item.prompt_template
    merged = {**dict(item.template_vars), **dict(cond.vars or {})}
    # Bind org-role tokens BEFORE str.format_map: format_map treats "{{" as an
    # escaped brace and collapses "{{ORG_SELF}}" to "{ORG_SELF}", which would
    # silently defeat the replacement for tokens written directly in a template.
    used: dict[str, str] = {}
    template = _apply_binding(template, binding, used)
    bound: dict[str, Any] = {}
    for k, v in merged.items():
        if isinstance(v, str) and ("{" + k + "}") in template:
            v = _apply_binding(v, binding, used)
        bound[k] = v
    prompt = template.format_map(_Default(bound))
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


def _match_option(raw: str, keywords: Sequence[str], options: Optional[Sequence[str]]) -> Optional[str]:
    """Find ``KEYWORD: <option>``; constrained to the item's options when given."""
    key = "|".join(keywords)
    if options:
        # Longest options first so overlapping alternatives ("NO" vs "NONE") can't
        # short-circuit; answers outside the option set are unparseable, not wrong.
        alts = sorted({str(o).strip() for o in options}, key=len, reverse=True)
        alt_re = "|".join(re.escape(a) for a in alts)
        m = re.search(rf"(?:{key}):\s*[\*_\"'(\[]*({alt_re})\b", raw, flags=re.IGNORECASE)
        return m.group(1).strip().upper() if m else None
    m = re.search(rf"(?:{key}):\s*([A-Za-z]+)", raw)
    return m.group(1).strip().upper() if m else None


def _parse_confidence(raw: str) -> Optional[float]:
    """Parse ``CONFIDENCE:`` as a probability; accepts percent-style answers.

    Real models frequently answer "CONFIDENCE: 85%" (or a bare "85"); treating
    that as 85.0 and clamping to 1.0 would score it as certainty. Values in
    (1, 100] are read as percentages; values above 100 are unparseable.
    """
    m = re.search(r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)\s*(%?)", raw)
    if not m:
        return None
    val = float(m.group(1))
    if m.group(2) == "%" or 1.0 < val <= 100.0:
        val /= 100.0
    if not 0.0 <= val <= 1.0:
        return None
    return val


def parse_output(raw: str, rf: ResponseFormat) -> Optional[dict]:
    """Best-effort structured parse of a completion per its response format."""
    if rf.type == "mcq" and rf.require_confidence:
        answer = _match_option(raw, ("ANSWER",), rf.options)
        if answer is None:
            return None
        out: dict[str, Any] = {"answer": answer}
        conf = _parse_confidence(raw)
        if conf is not None:
            out["confidence"] = conf
        return out
    if rf.type == "mcq":
        answer = _match_option(raw, ("ANSWER", "CHOICE"), rf.options)
        return {"answer": answer} if answer is not None else None
    if rf.type == "stance":
        m = re.search(r"STANCE:\s*(-?[0-9]+)", raw)
        if not m:
            return None
        stance = int(m.group(1))
        if rf.stance_scale:
            lo, hi = rf.stance_scale
            if not int(lo) <= stance <= int(hi):
                return None  # out-of-scale stance is unparseable, not data
        return {"stance": stance}
    return {"text": raw.strip()}


def run_id() -> str:
    """Sortable run identifier: UTC timestamp + short random suffix."""
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{random.randint(0, 0xFFFF):04x}"


def _unit_key(u: RunUnit) -> tuple[str, str, str]:
    return (u.item_id, u.condition_id, u.model_id)


def load_completed(path: Path) -> dict[tuple[str, str, str], dict]:
    """Successful completion records already on disk, keyed by unit."""
    done: dict[tuple[str, str, str], dict] = {}
    if path.exists():
        for d in read_jsonl(path):
            if not d.get("error"):
                done[(d["item_id"], d["condition_id"], d["model_id"])] = d
    return done


async def run(
    units: Sequence[RunUnit],
    adapters: Mapping[str, CallFn],
    registry: Mapping[str, ModelInfo],
    cfg: RunConfig,
    *,
    resume: bool = False,
) -> Path:
    """Execute units async + batched; stream Completions to completions.jsonl.

    Each batch is appended and flushed as soon as it finishes, so a crashed run
    keeps everything already answered. With ``resume=True``, units that already
    have a successful record in ``completions.jsonl`` are skipped and new
    results are appended (the score stage groups by unit with last-record-wins,
    so re-attempted failures are superseded cleanly).
    """
    out_dir = Path(cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "completions.jsonl"

    todo: Sequence[RunUnit] = units
    mode = "w"
    if resume:
        done = load_completed(path)
        todo = [u for u in units if _unit_key(u) not in done]
        mode = "a" if path.exists() else "w"

    sem = asyncio.Semaphore(cfg.concurrency)

    async def one(u: RunUnit) -> Completion:
        info = registry[u.model_id]
        call = adapters[info.provider]
        params = {
            "model": u.model_id,
            "model_version": info.version,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "item_id": u.item_id,
            "condition_id": u.condition_id,
            "model_id": u.model_id,
        }
        async with sem:
            last_err: Optional[Exception] = None
            attempt = 0
            while attempt <= cfg.max_retries:
                t0 = time.monotonic()
                try:
                    out = await call(u.prompt, params)
                except AdapterConfigError as e:  # missing SDK/key: retrying can't help
                    last_err = e
                    break
                except Exception as e:  # transient: captured, retried with backoff
                    last_err = e
                    if attempt < cfg.max_retries:
                        await asyncio.sleep(cfg.retry_base_delay * (2**attempt))
                    attempt += 1
                    continue
                raw, usage = out if isinstance(out, tuple) else (out, {})
                usage = {
                    **dict(usage),
                    "latency_ms": int((time.monotonic() - t0) * 1000),
                    "retries": attempt,
                }
                return Completion(u.item_id, u.condition_id, u.model_id, raw, parse_output(raw, u.response_format), usage)
            return Completion(
                u.item_id,
                u.condition_id,
                u.model_id,
                "",
                None,
                {"retries": attempt},
                f"{type(last_err).__name__}: {last_err}",
            )

    with path.open(mode, encoding="utf-8") as fh:
        for i in range(0, len(todo), cfg.batch_size):
            chunk = todo[i : i + cfg.batch_size]
            for c in await asyncio.gather(*(one(u) for u in chunk)):
                fh.write(json.dumps(completion_to_dict(c), ensure_ascii=False))
                fh.write("\n")
            fh.flush()
    return path
