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
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from . import rotation as rotation_mod
from . import validation as validation_mod
from .adapters import build_adapters, load_models
from .aggregate import aggregate, to_report
from .itembank import load_items, validate_file
from .jsonlio import read_json, read_jsonl, write_json, write_jsonl
from .report import write_report
from .runner import RunConfig, expand, run, run_id
from .scoring import JUDGED_METRICS, get_scorer  # noqa: F401  (import populates SCORERS)
from .scoring.judge.judge_client import make_mock_judge, make_real_judge
from .scoring.judge.rubric import RUBRIC_VERSION
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
DEFAULT_VALIDATION_DIR = "validation/judge"
DEFAULT_MANIFEST = "itembank/manifest.yaml"


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
    manifest_path: Optional[str] = DEFAULT_MANIFEST,
    rotate: bool = True,
) -> Path:
    registry, profiles, seed = load_models(models_path)
    rc = read_json(run_config_path) if (run_config_path and run_config_path.endswith(".json")) else _read_yaml(run_config_path)
    # Load both splits; the private split (if a private root is given) is the
    # canonical anti-train-to-test surface (SPEC §8).
    items = load_items(*itembank_roots, splits=("public", "private"))

    manifest = None
    canonical_split = "public"
    active_ops: dict = {}
    bank_version = _bank_version(items)
    if manifest_path and Path(manifest_path).exists():
        manifest = rotation_mod.load_manifest(manifest_path)
        canonical_split = manifest.canonical_split
        bank_version = manifest.bank_version
        active_ops = dict(manifest.active)
        if rotate:
            # Score only the active operationalization; reserve/burned groups sit out.
            items = rotation_mod.select_active(items, manifest)

    if metric:
        items = [it for it in items if it.metric == metric]
    if not items:
        raise SystemExit("no items to run (check --itembank / --metric / manifest active groups)")

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
    splits_loaded = sorted({it.split for it in items}) or ["public"]
    run_meta = {
        "run_id": rid,
        "generated_at": _now(),
        "demo": demo,
        "itembank_roots": [str(r) for r in itembank_roots],
        "bank_version": bank_version,
        "canonical_split": canonical_split,
        "splits_loaded": splits_loaded,
        "private_loaded": "private" in splits_loaded,
        "split_counts": rotation_mod.split_counts(items),
        "active_operationalizations": active_ops,
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
        "judge": rc.get("judge", {"id": "mock-judge-v1", "rubric_version": RUBRIC_VERSION}),
        "mock_profiles": profiles,  # lets the score stage rebuild the mock judge
        "models": [
            {"id": m.id, "provider": m.provider, "maker": m.maker, "display_name": m.display_name, "version": m.version}
            for m in registry.values()
        ],
    }
    write_json(run_dir / "run_meta.json", run_meta)
    sc = run_meta["split_counts"]
    print(
        f"[run] {len(units)} units across {len(registry)} models "
        f"(bank {bank_version}, splits public={sc.get('public',0)}/private={sc.get('private',0)}"
        f"{', rotated to active operationalizations' if (manifest and rotate) else ''}) -> {run_dir}/completions.jsonl"
    )
    return run_dir


def do_score(run_dir: str | Path, itembank_roots: Optional[Sequence[str]] = None) -> Path:
    run_dir = Path(run_dir)
    run_meta = read_json(run_dir / "run_meta.json")
    roots = list(itembank_roots) if itembank_roots else run_meta["itembank_roots"]
    items_by_id = {it.id: it for it in load_items(*roots, splits=("public", "private"))}
    registry = {m["id"]: modelinfo_from_dict(m) for m in run_meta["models"]}

    grouped: dict[tuple[str, str], dict] = {}
    for d in read_jsonl(run_dir / "completions.jsonl"):
        c = completion_from_dict(d)
        grouped.setdefault((c.item_id, c.model_id), {})[c.condition_id] = c

    # Judge for v2 metrics: mock for demo runs, key-gated real judge otherwise.
    if run_meta.get("demo"):
        judge = make_mock_judge(
            run_meta.get("mock_profiles", {}),
            seed=int(run_meta.get("seed", 0)),
            judge_id=run_meta.get("judge", {}).get("id", "mock-judge-v1"),
        )
    else:
        judge = make_real_judge(run_meta.get("judge", {}).get("id", ""))

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
        ctx = ScoringContext(model=registry.get(mid, ModelInfo(mid, "mock", "", mid)), judge=judge)
        try:
            scores.append(replace(scorer(item, cmap, ctx), split=item.split))  # stamp the item's split
        except (NotImplementedError, RuntimeError):
            skipped_metrics.add(item.metric)  # stub, or judge not configured

    path = write_jsonl(run_dir / "scores.jsonl", (metricscore_to_dict(s) for s in scores))
    msg = f"[score] {len(scores)} scores -> {path}"
    if skipped_metrics:
        msg += f"  (skipped stub metrics: {', '.join(sorted(skipped_metrics))})"
    print(msg)
    return path


def do_aggregate(run_dir: str | Path, validation_dir: str = DEFAULT_VALIDATION_DIR) -> Path:
    run_dir = Path(run_dir)
    run_meta = read_json(run_dir / "run_meta.json")
    registry = {m["id"]: modelinfo_from_dict(m) for m in run_meta["models"]}
    scores = [metricscore_from_dict(d) for d in read_jsonl(run_dir / "scores.jsonl")]
    summaries = aggregate(
        scores, registry, seed=int(run_meta.get("seed", 0)), bank_version=run_meta.get("bank_version", "")
    )

    # Load judge-validation records for the publication gate (SPEC §10).
    validation = {}
    for metric in JUDGED_METRICS:
        vr = validation_mod.load_result(validation_dir, metric)
        if vr is not None:
            validation[metric] = asdict(vr)

    report = to_report(
        summaries, run_meta, registry, validation, canonical_split=run_meta.get("canonical_split", "public")
    )
    path = write_report(report, run_dir)
    print(f"[aggregate] report -> {path}")
    cs = report.get("canonical_split")
    if not run_meta.get("private_loaded", False) and cs != "public":
        print(f"  [split] canonical policy = {cs}, but no private split loaded; showing PUBLIC (reproducible, not held-out)")
    _print_calibration_table(report)
    _print_sycophancy_table(report)
    _print_creator_bias_table(report)
    _print_framing_table(report)
    _print_clarity_table(report)
    _print_judged_tables(report)
    return path


def do_validate_judge(
    metric: str,
    sample_path: Optional[str] = None,
    out_dir: str = DEFAULT_VALIDATION_DIR,
    threshold: Optional[float] = None,
    judge_id: str = "mock-judge-v1",
) -> Path:
    sample = sample_path or str(Path(out_dir) / f"{metric}.sample.jsonl")
    result = validation_mod.run_validation(
        metric, sample, threshold=threshold, judge_id=judge_id, rubric_version=RUBRIC_VERSION
    )
    path = validation_mod.write_result(result, out_dir)
    status = "PASS ✓ (publishable)" if result.passed else "FAIL ✗ (withheld)"
    print(
        f"[validate-judge] {metric}: {result.agreement_metric}={result.agreement_value} "
        f"vs threshold {result.threshold} on n={result.n} -> {status}"
    )
    return path


def do_report(run_dir: str | Path, site_out: str) -> Path:
    run_dir = Path(run_dir)
    out = build_site(run_dir / "report.json", site_out)
    print(f"[report] leaderboard -> {out}")
    return out


def do_manifest(manifest_path: str = DEFAULT_MANIFEST, itembank_roots: Sequence[str] = DEFAULT_ITEMBANK) -> None:
    m = rotation_mod.load_manifest(manifest_path)
    items = load_items(*itembank_roots, splits=("public", "private"))
    print(f"bank {m.bank_version} | canonical split: {m.canonical_split} | cadence: {m.cadence}")
    print(f"{'metric':<14} {'active':<10} {'reserve':<22} {'public':>6} {'private':>7}")
    for metric, active in m.active.items():
        in_active = [it for it in items if it.metric == metric and rotation_mod.rotation_group_of(it) == active]
        pub = sum(1 for it in in_active if it.split == "public")
        priv = sum(1 for it in in_active if it.split == "private")
        reserve = [g for g in m.operationalizations.get(metric, []) if g != active and g not in m.burned]
        print(f"{metric:<14} {active:<10} {(','.join(reserve) or 'none'):<22} {pub:>6} {priv:>7}")
    if m.burned:
        print(f"burned: {', '.join(sorted(m.burned))}")


def do_rotate_plan(
    manifest_path: str = DEFAULT_MANIFEST,
    itembank_roots: Sequence[str] = DEFAULT_ITEMBANK,
    burn_fraction: float = 0.25,
) -> None:
    m = rotation_mod.load_manifest(manifest_path)
    items = load_items(*itembank_roots, splits=("public", "private"))
    plan = rotation_mod.rotation_plan(items, m, burn_fraction=burn_fraction)
    print(f"Rotation plan from release {plan['release_from']} (burn {int(burn_fraction*100)}% of active public items):\n")
    for metric, p in plan["metrics"].items():
        print(
            f"  {metric:<14} active {p['active']:<9} burn {p['burn_n']:>2} of {p['n_public']:>2} public "
            f"-> next active: {p['next_active']}"
        )
    print(
        "\nMaintainer steps (see methodology/rotation.md): burn the listed public ids, promote fresh\n"
        "private items into public to refill, mint new private items, then bump the manifest's active group."
    )


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
        print("  [demo: synthetic mock data, not real model results]")
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
        print("  [demo: synthetic mock data, not real model results]")
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
        print("  [demo: synthetic mock data, not real model results]")
    print()


def _print_framing_table(report: dict) -> None:
    virtue = report.get("virtues", {}).get("framing")
    if not virtue:
        return
    print("  Framing consistency (score = 1 - flip-across-framings rate, higher is better):")
    print(f"  {'model':<18} {'flip':>6} {'score':>6}")
    for m in report.get("models", []):
        d = virtue["by_model"].get(m["id"])
        if not d:
            continue
        r = d.get("raw", {})
        print(f"  {m['display_name'][:18]:<18} {r.get('framing_flip_rate',0):>6.3f} {(d.get('score') or 0):>6.3f}")
    if report.get("demo"):
        print("  [demo: synthetic mock data, not real model results]")
    print()


def _print_clarity_table(report: dict) -> None:
    virtue = report.get("virtues", {}).get("clarity")
    if not virtue:
        return
    print("  Clarity (score = crispness, 1 - hedge/commitment-shift penalties, higher is better):")
    print(f"  {'model':<18} {'hedge%':>7} {'shifts':>6} {'score':>6}")
    for m in report.get("models", []):
        d = virtue["by_model"].get(m["id"])
        if not d:
            continue
        r = d.get("raw", {})
        print(
            f"  {m['display_name'][:18]:<18} {r.get('hedge_density',0)*100:>6.1f}% "
            f"{r.get('commitment_shifts',0):>6.2f} {(d.get('score') or 0):>6.3f}"
        )
    if report.get("demo"):
        print("  [demo: synthetic mock data, not real model results]")
    print()


def _print_judged_tables(report: dict) -> None:
    for metric in ("pedantic", "thoroughness"):
        v = report.get("virtues", {}).get(metric)
        if not v:
            continue
        jv = v.get("judge", {})
        print(
            f"  {metric.title()} (v2, judge-validated, "
            f"{jv.get('agreement_metric')}={jv.get('agreement_value')} >= {jv.get('threshold')}):"
        )
        print(f"  {'model':<18} {'score':>6}")
        for m in report.get("models", []):
            d = v["by_model"].get(m["id"])
            if d:
                print(f"  {m['display_name'][:18]:<18} {(d.get('score') or 0):>6.3f}")
        if report.get("demo"):
            print("  [demo: synthetic mock judge, not real model results]")
        print()
    for metric, w in report.get("withheld", {}).items():
        val = w.get("validation") or {}
        detail = (
            f" ({val.get('agreement_metric')}={val.get('agreement_value')} < {val.get('threshold')})" if val else ""
        )
        print(f"  [withheld] {metric}: not on leaderboard: {w.get('reason')}{detail}\n")


# ---- argparse glue ---------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="epb", description="epistemic-bench CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("validate", help="JSON-validate item bank files")
    pv.add_argument("roots", nargs="*", default=DEFAULT_ITEMBANK)

    pr = sub.add_parser("run", help="call models, dump raw completions")
    pr.add_argument("--models", default=DEFAULT_MODELS)
    pr.add_argument("--run-config", default=DEFAULT_RUN_CONFIG)
    pr.add_argument("--itembank", nargs="*", default=DEFAULT_ITEMBANK, help="public dir, plus a private root at eval time")
    pr.add_argument("--out", default="runs")
    pr.add_argument("--metric", default=None)
    pr.add_argument("--manifest", default=DEFAULT_MANIFEST)
    pr.add_argument("--no-rotate", action="store_true", help="score all operationalizations, not just the active one")

    ps = sub.add_parser("score", help="completions -> per-item scores")
    ps.add_argument("--run", required=True)
    ps.add_argument("--itembank", nargs="*", default=None)

    pa = sub.add_parser("aggregate", help="scores -> report.json")
    pa.add_argument("--run", required=True)

    prp = sub.add_parser("report", help="report.json -> static leaderboard")
    prp.add_argument("--run", required=True)
    prp.add_argument("--site", default="site/out")

    pvj = sub.add_parser("validate-judge", help="validate a v2 judge vs a human-labeled sample (SPEC §10)")
    pvj.add_argument("--metric", required=True, choices=sorted(JUDGED_METRICS))
    pvj.add_argument("--sample", default=None)
    pvj.add_argument("--out", default=DEFAULT_VALIDATION_DIR)
    pvj.add_argument("--threshold", type=float, default=None)

    pm = sub.add_parser("manifest", help="show the item-bank manifest: active operationalizations + split counts")
    pm.add_argument("--manifest", default=DEFAULT_MANIFEST)
    pm.add_argument("--itembank", nargs="*", default=DEFAULT_ITEMBANK)

    pro = sub.add_parser("rotate", help="dry-run the next-release rotation plan (SPEC §8.2)")
    pro.add_argument("--manifest", default=DEFAULT_MANIFEST)
    pro.add_argument("--itembank", nargs="*", default=DEFAULT_ITEMBANK)
    pro.add_argument("--burn-fraction", type=float, default=0.25)

    pd = sub.add_parser("demo", help="run -> score -> validate-judge -> aggregate -> report (defaults)")
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
        do_run(args.models, args.run_config, args.itembank, args.out, args.metric, args.manifest, not args.no_rotate)
        return 0
    if args.cmd == "manifest":
        do_manifest(args.manifest, args.itembank)
        return 0
    if args.cmd == "rotate":
        do_rotate_plan(args.manifest, args.itembank, args.burn_fraction)
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
    if args.cmd == "validate-judge":
        do_validate_judge(args.metric, args.sample, args.out, args.threshold)
        return 0
    if args.cmd == "demo":
        run_dir = do_run(args.models, args.run_config, args.itembank, args.out, args.metric)
        do_score(run_dir)
        for metric in sorted(JUDGED_METRICS):
            do_validate_judge(metric)
        do_aggregate(run_dir)
        do_report(run_dir, args.site)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
