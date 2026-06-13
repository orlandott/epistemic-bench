"""Scoring package. Importing it registers all v1 scorers in ``SCORERS``.

v2 judge scorers (``scoring.judge.*``) are intentionally NOT imported here: they
must pass the validation gate (SPEC §10) before being registered/published.
"""

from __future__ import annotations

from . import calibration, clarity, creator_bias, framing, sycophancy  # noqa: F401  (registration side effects)
from .base import SCORERS, Scorer, get_scorer, register

__all__ = ["SCORERS", "Scorer", "get_scorer", "register"]
