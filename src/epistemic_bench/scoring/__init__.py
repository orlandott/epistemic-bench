"""Scoring package. Importing it registers all scorers in ``SCORERS``.

v1 programmatic scorers and v2 judge scorers are all registered so the pipeline
can *compute* them. Registration is NOT publication: a judged metric
(``pedantic``, ``thoroughness``) only appears on the leaderboard if a passing
judge-validation record exists — the publication gate is enforced at report time
in ``aggregate.to_report`` (SPEC §10). v2 scorers additionally require a judge to
be injected via ``ScoringContext.judge``.
"""

from __future__ import annotations

from . import calibration, clarity, creator_bias, framing, sycophancy  # noqa: F401  (registration)
from .base import SCORERS, JUDGED_METRICS, Scorer, get_scorer, register
from .judge import pedantic, thoroughness  # noqa: F401  (registration; gated at publish time)

__all__ = ["SCORERS", "JUDGED_METRICS", "Scorer", "get_scorer", "register"]
