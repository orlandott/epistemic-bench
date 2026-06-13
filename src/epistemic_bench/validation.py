"""Judge-validation gate (SPEC §10).

Before a judged metric (pedantic, thoroughness) may be published, the pinned
judge must agree with a human-labeled sample at or above a threshold. This module
computes that agreement and records a pass/fail result; ``aggregate.to_report``
consults the result and withholds unvalidated metrics from the leaderboard.

Agreement statistics (pure stdlib):
- pedantic   : Cohen's kappa over categorical per-claim verdicts.
- thoroughness: Pearson correlation between judge and human item scores.

The gold sample stores, per record, BOTH the human label and the judge's output
(produced by running the pinned judge over the human-labeled inputs). That is the
auditable validation artifact; this module only reads it and computes the stat.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from .jsonlio import read_jsonl, read_json, write_json

DEFAULT_THRESHOLDS = {"pedantic": 0.6, "thoroughness": 0.6}


@dataclass(frozen=True)
class ValidationResult:
    metric: str
    agreement_metric: str
    agreement_value: float
    n: int
    threshold: float
    passed: bool
    judge_id: str = ""
    rubric_version: str = ""
    generated_at: str = ""


def cohens_kappa(a: Sequence, b: Sequence) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    labels = sorted(set(a) | set(b))
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((sum(1 for x in a if x == L) / n) * (sum(1 for y in b if y == L) / n) for L in labels)
    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1.0 - pe)


def pearson(a: Sequence[float], b: Sequence[float]) -> float:
    n = len(a)
    if n < 2:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def run_validation(
    metric: str,
    sample_path: Path | str,
    *,
    threshold: Optional[float] = None,
    judge_id: str = "",
    rubric_version: str = "",
) -> ValidationResult:
    records = list(read_jsonl(sample_path))
    thr = DEFAULT_THRESHOLDS.get(metric, 0.6) if threshold is None else threshold

    if metric == "pedantic":
        human = [r["human_verdict"] for r in records]
        judge = [r["judge_verdict"] for r in records]
        value, agreement_metric = cohens_kappa(human, judge), "cohen_kappa"
    elif metric == "thoroughness":
        human = [float(r["human_score"]) for r in records]
        judge = [float(r["judge_score"]) for r in records]
        value, agreement_metric = pearson(human, judge), "pearson_r"
    else:
        raise ValueError(f"no validation procedure for metric {metric!r}")

    return ValidationResult(
        metric=metric,
        agreement_metric=agreement_metric,
        agreement_value=round(value, 4),
        n=len(records),
        threshold=thr,
        passed=value >= thr,
        judge_id=judge_id,
        rubric_version=rubric_version,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def result_path(out_dir: Path | str, metric: str) -> Path:
    return Path(out_dir) / f"{metric}.result.json"


def write_result(result: ValidationResult, out_dir: Path | str) -> Path:
    return write_json(result_path(out_dir, result.metric), asdict(result))


def load_result(out_dir: Path | str, metric: str) -> Optional[ValidationResult]:
    path = result_path(out_dir, metric)
    if not path.exists():
        return None
    return ValidationResult(**read_json(path))
