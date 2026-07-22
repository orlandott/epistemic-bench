"""Judge client (SPEC §7.5, §10).

The scorer↔judge boundary is a **synchronous** ``JudgeFn``: it takes a
``JudgeRequest`` (rendered prompt + pinned rubric + machine-readable context) and
returns a verdict as text (JSON), which the metric scorer parses. Keeping it sync
and injectable (via ``ScoringContext.judge``) keeps the scorers pure and
unit-testable — a test passes a fake judge that returns canned verdicts.

Two implementations:

- ``make_real_judge`` — a pinned, versioned judge model called synchronously via
  the provider SDKs (lazy imports, key-gated). It **refuses to judge a model
  that shares its maker** (SPEC §10): the creator-bias metric makes self-judging
  acutely conflicted, so the gate is enforced per request against the model
  registry, before any network call.
- ``make_mock_judge`` — deterministic synthetic verdicts for offline demos/tests,
  driven by per-model quality profiles. It does NOT read the candidate text; it
  simulates a judge's verdict distribution. Any leaderboard built from it is
  stamped ``demo: true``. The mock judge is for pipeline demonstration only and
  is never used to validate a judged metric for publication.
"""

from __future__ import annotations

import json
import os
import random
import zlib
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from ...types import ModelInfo

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


def _norm_maker(name: str) -> str:
    return (name or "").strip().casefold()


def _sync_provider_call(provider: str, model: str, prompt: str, max_tokens: int = 2048) -> str:
    """One synchronous judge call via the pinned provider's SDK (lazy import)."""

    def _need_env(name: str) -> str:
        val = os.environ.get(name, "")
        if not val:
            raise RuntimeError(f"judge provider '{provider}' requires the {name} environment variable")
        return val

    if provider == "anthropic":
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError("judge provider 'anthropic' requires: pip install 'epistemic-bench[anthropic]'") from e
        _need_env("ANTHROPIC_API_KEY")
        resp = anthropic.Anthropic().messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")

    if provider in ("openai", "openweights"):
        try:
            import openai
        except ImportError as e:
            raise RuntimeError(f"judge provider '{provider}' requires: pip install 'epistemic-bench[openai]'") from e
        if provider == "openweights":
            base_url = os.environ.get("OPENWEIGHTS_BASE_URL", "")
            if not base_url:
                raise RuntimeError("judge provider 'openweights' requires the OPENWEIGHTS_BASE_URL environment variable")
            client = openai.OpenAI(base_url=base_url, api_key=os.environ.get("OPENWEIGHTS_API_KEY", "EMPTY"))
        else:
            _need_env("OPENAI_API_KEY")
            client = openai.OpenAI()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "") if resp.choices else ""

    if provider == "google":
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise RuntimeError("judge provider 'google' requires: pip install 'epistemic-bench[google]'") from e
        genai.configure(api_key=_need_env("GOOGLE_API_KEY"))
        resp = genai.GenerativeModel(model).generate_content(
            prompt, generation_config={"temperature": 0.0, "max_output_tokens": max_tokens}
        )
        try:
            return resp.text
        except Exception:
            return ""

    raise RuntimeError(f"no judge implementation for provider {provider!r}")


def make_real_judge(
    cfg: Optional[Mapping[str, Any]] = None,
    registry: Optional[Mapping[str, ModelInfo]] = None,
) -> JudgeFn:
    """Build the pinned real judge from run-config ``judge`` settings.

    ``cfg`` needs ``provider``, ``model`` (exact pinned version), and ``maker``
    (the judge model's maker, used for the SPEC §10 same-maker refusal). Without
    them the returned judge raises on use, so unconfigured judged metrics are
    skipped rather than silently mis-scored.
    """
    cfg = dict(cfg or {})
    provider = str(cfg.get("provider", "") or "")
    model = str(cfg.get("model", "") or "")
    maker = str(cfg.get("maker", "") or "")
    judge_id = str(cfg.get("id") or model or "")

    if not provider or not model or not maker:
        def unconfigured(req: JudgeRequest) -> str:
            raise RuntimeError(
                "real judge is not configured: set judge.provider, judge.model (pinned "
                "version), and judge.maker in the run config (SPEC §10). The judge must "
                "not share a maker with any model under test."
            )

        unconfigured.judge_id = judge_id or "unconfigured"  # type: ignore[attr-defined]
        return unconfigured

    def judge(req: JudgeRequest) -> str:
        # Cross-maker gate first (SPEC §10) — enforced before any SDK/network work.
        under_test = (registry or {}).get(req.model_id)
        if under_test is not None and _norm_maker(maker) == _norm_maker(under_test.maker):
            raise RuntimeError(
                f"judge {judge_id!r} (maker {maker!r}) must not judge {req.model_id!r} "
                f"from the same maker (SPEC §10 self-judging policy)"
            )
        prompt = (
            f"{req.rubric}\n\n{req.prompt}\n"
            "Respond with the JSON verdict only — no prose before or after."
        )
        return _sync_provider_call(provider, model, prompt)

    judge.judge_id = judge_id  # type: ignore[attr-defined]
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
