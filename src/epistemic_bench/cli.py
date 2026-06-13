"""Command-line interface (SPEC §7.8).

    epb validate  <itembank_root>...
    epb run       --models ... --run-config ... --itembank ...
    epb score     --run runs/<id> [--itembank ...]
    epb aggregate --run runs/<id>
    epb report    --run runs/<id> --site site/out
    epb demo      # run -> score -> aggregate -> report, with defaults

Runnable without install via:  PYTHONPATH=src python -m epistemic_bench ...
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from .adapters import build_adapters, load_models
from .aggregate import aggregate, to_report
from .itembank import load_items, validate_file
from .jsonlio import read_json, read_jsonl, write_json, write_jsonl
from .report import write_report
from .runner import RunConfig, expand, run, run_id
from .scoring import get_scorer  # noqa: F401  (import populates SCORERS)
from .site_build import build_site
from .types import (
    ModelInfo,
    ScoringContext,
    completion_from_dict,
    metricscore_from_dict,
    metricscore_to_dict,
    modelinfo_from_dict,
)

DEFAULT_MODELS = "config/models.example.yaml"
DEFAULT_RUN_CONFIG = "config/run.example.yaml"
DEFAULT_ITEMBANK = ["itembank/public"]


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _bank_version(items) -> str:
    for it in items:
        parts = it.id.split("/")
        if len(parts) >= 2 and parts[1].startswith("v"):
            return parts[1]
    return "v?"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- pipeline stages (reusable) -------------------------------------------


def do_run(
    models_path: str,
    run_config_path: Optional[str],
    itembank_roots: Sequence[str],
    out_root: str,
    metric: Optional[str] = None,
) -> Path:
    registry, profiles, seed = load_models(models_path)
    rc = read_json(run_config_path) if (run_config_path and run_config_path.endswith(".json")) else _read_yaml(run_config_path)
    items = load_items(*itembank_roots)
    if metric:
        items = [it for it in items if it.metric == metric]
    if not items:
        raise SystemExit("no items to run (check --itembank / --metric)")

    rid = run_id()
    run_dir = Path(out_root) / rid
    cfg = RunConfig(
        models=list(registry.values()),
        out_dir=run_dir,
        concurrency=int(rc.get("concurrency", 16)),
        batch_size=int(rc.get("batch_size", 32)),
        temperature=float(rc.get("temperature", 0.0)),
        max_tokens=int(rc.get("max_tokens", 1024)),
        seed=seed,
        org_pool=tuple(rc.get("org_pool", [])),
    )
    adapters = build_adapters(registry, items, profiles, seed)
    units = expand(items, cfg)
    asyncio.run(run(units, adapters, registry, cfg))

    demo = any(m.provider == "mock" for m in registry.values())
    run_meta = {
        "run_id": rid,
        "generated_at": _now(),
        "demo": demo,
        "itembank_roots": [str(r) for r in itembank_roots],
        "bank_version": _bank_version(items),
        "seed": seed,
        "params": {
            "concurrency": cfg.concurrency,
            "batch_size": cfg.batch_size,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "org_pool": list(cfg.org_pool),
        },
        "code_sha": _git_sha(),
        "n_units": len(units),
        "n_items": len(items),
        "models": [
            {"id": m.id, "provider": m.provider, "maker": m.maker, "display_name": m.display_name, "version": m.version}
            for m in registry.values()
        ],
    }
    write_json(run_dir / "run_meta.json", run_meta)
    print(f"[run] {len(units)} units across {len(registry)} models -> {run_dir}/completions.jsonl")
    return run_dir


def do_score(run_dir: str | Path, itembank_roots: Optional[Sequence[str]] = None) -> Path:
    run_dir = Path(run_dir)
    run_meta = read_json(run_dir / "run_meta.json")
    roots = list(itembank_roots) if itembank_roots else run_meta["itembank_roots"]
    items_by_id = {it.id: it for it in load_items(*roots)}
    registry = {m["id"]: modelinfo_from_dict(m) for m in run_meta["models"]}

    grouped: dict[tuple[str, str], dict] = {}
    for d in read_jsonl(run_dir / "completions.jsonl"):
        c = completion_from_dict(d)
        grouped.setdefault((c.item_id, c.model_id), {})[c.condition_id] = c

    scores = []
    skipped_metrics: set[str] = set()
    for (iid, mid), cmap in grouped.items():
        item = items_by_id.get(iid)
        if item is None:
            continue
        try:
            scorer = get_scorer(item.metric)
        except KeyError:
            skipped_metrics.add(item.metric)
            continue
        ctx = ScoringContext(model=registry.get(mid, ModelInfo(mid, "mock", "", mid)))
        try:
            scores.append(scorer(item, cmap, ctx))
        except NotImplementedError:
            skipped_metrics.add(item.metric)

    path = write_jsonl(run_dir / "scores.jsonl", (metricscore_to_dict(s) for s in scores))
    msg = f"[score] {len(scores)} scores -> {path}"
    if skipped_metrics:
        msg += f"  (skipped stub metrics: {', '.join(sorted(skipped_metrics))})"
    print(msg)
    return path


def do_aggregate(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir)
    run_meta = read_json(run_dir / "run_meta.json")
    registry = {m["id"]: modelinfo_from_dict(m) for m in run_meta["models"]}
    scores = [metricscore_from_dict(d) for d in read_jsonl(run_dir / "scores.jsonl")]
    summaries = aggregate(
        scores, registry, seed=int(run_meta.get("seed", 0)), bank_version=run_meta.get("bank_version", "")
    )
    report = to_report(summaries, run_meta, registry)
    path = write_report(report, run_dir)
    print(f"[aggregate] report -> {path}")
    _print_calibration_table(report)
    _print_sycophancy_table(report)
    _print_creator_bias_table(report)
    return path


def do_report(run_dir: str | Path, site_out: str) -> Path:
    run_dir = Path(run_dir)
    out = build_site(run_dir / "report.json", site_out)
    print(f"[report] leaderboard -> {out}")
    return out


def _read_yaml(path: Optional[str]) -> dict:
    if not path:
        return {}
    import yaml

    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def _print_calibration_table(report: dict) -> None:
    virtue = report.get("virtues", {}).get("calibration")
    if not virtue:
        return
    print("\n  Calibration (score = 1 - ECE, higher is better):")
    print(f"  {'model':<18} {'acc':>6} {'ECE':>6} {'Brier':>6} {'score':>6}")
    for m in report.get("models", []):
        d = virtue["by_model"].get(m["id"])
        if not d:
            continue
        r = d.get("raw", {})
        print(
            f"  {m['display_name'][:18]:<18} {r.get('accuracy',0):>6.3f} {r.get('ece',0):>6.3f} "
            f"{r.get('brier',0):>6.3f} {(d.get('score') or 0):>6.3f}"
        )
    if report.get("demo"):
        print("  [demo: synthetic mock data — not real model results]")
    print()


def _print_sycophancy_table(report: dict) -> None:
    virtue = report.get("virtues", {}).get("sycophancy")
    if not virtue:
        return
    print("  Sycophancy resistance (score = 1 - flip-to-user rate, higher is better):")
    print(f"  {'model':<18} {'toward':>7} {'flip':>6} {'shift':>7} {'score':>6}")
    for m in report.get("models", []):
        d = virtue["by_model"].get(m["id"])
        if not d:
            continue
        r = d.get("raw", {})
        print(
            f"  {m['display_name'][:18]:<18} {r.get('toward_user_rate',0):>7.3f} {r.get('flip_rate',0):>6.3f} "
            f"{r.get('mean_conf_shift',0):>+7.3f} {(d.get('score') or 0):>6.3f}"
        )
    if report.get("demo"):
        print("  [demo: synthetic mock data — not real model results]")
    print()


def _print_creator_bias_table(report: dict) -> None:
    virtue = report.get("virtues", {}).get("creator_bias")
    if not virtue:
        return
    print("  Creator-bias resistance (score = 1 - toward-own-maker skew, higher is better):")
    print(f"  {'model':<18} {'self':>6} {'rival':>6} {'skew':>7} {'score':>6}")
    for m in report.get("models", []):
        d = virtue["by_model"].get(m["id"])
        if not d:
            continue
        r = d.get("raw", {})
        print(
            f"  {m['display_name'][:18]:<18} {r.get('mean_self_stance',0):>6.2f} {r.get('mean_rival_stance',0):>6.2f} "
            f"{r.get('mean_skew',0):>+7.3f} {(d.get('score') or 0):>6.3f}"
        )
    if report.get("demo"):
        print("  [demo: synthetic mock data — not real model results]")
    print()


# ---- argparse glue ---------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="epb", description="epistemic-bench CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("validate", help="JSON-validate item bank files")
    pv.add_argument("roots", nargs="*", default=DEFAULT_ITEMBANK)

    pr = sub.add_parser("run", help="call models, dump raw completions")
    pr.add_argument("--models", default=DEFAULT_MODELS)
    pr.add_argument("--run-config", default=DEFAULT_RUN_CONFIG)
    pr.add_argument("--itembank", nargs="*", default=DEFAULT_ITEMBANK)
    pr.add_argument("--out", default="runs")
    pr.add_argument("--metric", default=None)

    ps = sub.add_parser("score", help="completions -> per-item scores")
    ps.add_argument("--run", required=True)
    ps.add_argument("--itembank", nargs="*", default=None)

    pa = sub.add_parser("aggregate", help="scores -> report.json")
    pa.add_argument("--run", required=True)

    prp = sub.add_parser("report", help="report.json -> static leaderboard")
    prp.add_argument("--run", required=True)
    prp.add_argument("--site", default="site/out")

    pd = sub.add_parser("demo", help="run -> score -> aggregate -> report (defaults)")
    pd.add_argument("--models", default=DEFAULT_MODELS)
    pd.add_argument("--run-config", default=DEFAULT_RUN_CONFIG)
    pd.add_argument("--itembank", nargs="*", default=DEFAULT_ITEMBANK)
    pd.add_argument("--out", default="runs")
    pd.add_argument("--site", default="site/out")
    pd.add_argument("--metric", default=None, help="restrict to one metric; default runs all implemented")

    args = p.parse_args(argv)

    if args.cmd == "validate":
        total = 0
        for root in args.roots:
            for path in sorted(Path(root).rglob("*.jsonl")) if Path(root).is_dir() else [Path(root)]:
                errs = validate_file(path)
                total += len(errs)
                if errs:
                    print(f"FAIL {path}")
                    for e in errs:
                        print(f"  {e}")
                else:
                    print(f"OK   {path}")
        if total:
            print(f"\n{total} validation error(s)")
            return 1
        print("\nall items valid")
        return 0

    if args.cmd == "run":
        do_run(args.models, args.run_config, args.itembank, args.out, args.metric)
        return 0
    if args.cmd == "score":
        do_score(args.run, args.itembank)
        return 0
    if args.cmd == "aggregate":
        do_aggregate(args.run)
        return 0
    if args.cmd == "report":
        do_report(args.run, args.site)
        return 0
    if args.cmd == "demo":
        run_dir = do_run(args.models, args.run_config, args.itembank, args.out, args.metric)
        do_score(run_dir)
        do_aggregate(run_dir)
        do_report(run_dir, args.site)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
