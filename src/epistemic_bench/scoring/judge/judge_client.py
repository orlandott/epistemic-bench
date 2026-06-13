"""Judge client (SPEC §7.5, §10).

The scorer↔judge boundary is a **synchronous** ``JudgeFn``: it takes a
``JudgeRequest`` (rendered prompt + pinned rubric + machine-readable context) and
returns a verdict as text (JSON), which the metric scorer parses. Keeping it sync
and injectable (via ``ScoringContext.judge``) keeps the scorers pure and
unit-testable: a test passes a fake judge that returns canned verdicts.

Two implementations:

- ``make_real_judge``: a key-gated stub. A real judge model must be pinned and
  versioned, and must not share a maker with the model under test (SPEC §10
  OPEN); wire the actual API call here.
- ``make_mock_judge``: deterministic synthetic verdicts for offline demos/tests,
  driven by per-model quality profiles. It does NOT read the candidate text; it
  simulates a judge's verdict distribution. Any leaderboard built from it is
  stamped ``demo: true``. The mock judge is for pipeline demonstration only and
  is never used to validate a judged metric for publication.
"""

from __future__ import annotations

import json
import random
import zlib
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

JUDGE_RUBRIC_DEFAULT = "epistemic-bench/judge/v1"


@dataclass(frozen=True)
class JudgeRequest:
    prompt: str  # fully rendered judge prompt (candidate output + sources/key points + task)
    rubric: str  # pinned rubric text (see rubric.py)
    metric: str  # "pedantic" | "thoroughness"
    item_id: str
    model_id: str  # the model under test (so the judge can be checked for same-maker conflict)
    payload: Mapping[str, Any] = field(default_factory=dict)  # metric-specific machine-readable inputs


JudgeFn = Callable[[JudgeRequest], str]  # returns verdict as JSON text


def make_real_judge(judge_id: str = "") -> JudgeFn:
    def judge(req: JudgeRequest) -> str:
        raise RuntimeError(
            "real judge is not configured in this build. Pin a judge model "
            "(must not share a maker with the model under test, SPEC §10), set "
            "its API key, and implement the call in judge_client.make_real_judge."
        )

    return judge


def _rng(seed: int, *parts: str) -> random.Random:
    return random.Random(zlib.crc32("|".join([str(seed), *parts]).encode("utf-8")))


def make_mock_judge(profiles: Mapping[str, dict], seed: int = 0, judge_id: str = "mock-judge-v1") -> JudgeFn:
    """Synthetic judge: produces verdicts from per-model quality profiles."""

    def judge(req: JudgeRequest) -> str:
        prof = profiles.get(req.model_id, {})
        if req.metric == "pedantic":
            n = int(req.payload.get("n_claims", 6))
            p_support = float(prof.get("pedantic_precision", 0.85))
            p_false = float(prof.get("pedantic_false_rate", 0.06))
            p_amb = float(prof.get("pedantic_ambiguity", 0.12))
            claims = []
            for i in range(n):
                r = _rng(seed, "ped", req.model_id, req.item_id, str(i))
                u = r.random()
                if u < p_false:
                    verdict = "contradicted"
                elif u < p_false + p_support:
                    verdict = "supported"
                else:
                    verdict = "unsupported"
                ambiguous = r.random() < p_amb
                claims.append({"text": f"claim-{i}", "verdict": verdict, "ambiguous": ambiguous})
            return json.dumps({"claims": claims})

        if req.metric == "thoroughness":
            key_points = list(req.payload.get("key_points", []))
            budget = int(req.payload.get("budget", 150))
            cov = float(prof.get("thoroughness_coverage", 0.8))
            bal = float(prof.get("thoroughness_balance", 0.82))
            verbosity = float(prof.get("thoroughness_verbosity", 0.1))  # fraction over (or under) budget
            covered = []
            for kp in key_points:
                if _rng(seed, "thr-cov", req.model_id, req.item_id, str(kp)).random() < cov:
                    covered.append(kp)
            jitter = _rng(seed, "thr-bal", req.model_id, req.item_id).gauss(0.0, 0.05)
            balance = min(1.0, max(0.0, bal + jitter))
            word_count = int(round(budget * (1.0 + verbosity)))
            return json.dumps({"covered_points": covered, "balance": round(balance, 3), "word_count": word_count})

        return json.dumps({})

    judge.judge_id = judge_id  # type: ignore[attr-defined]
    return judge
