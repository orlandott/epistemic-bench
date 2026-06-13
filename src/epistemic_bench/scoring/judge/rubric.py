"""Fixed, documented, versioned judge rubrics (SPEC §10).

Rubrics are pinned constants. Any change MUST bump ``RUBRIC_VERSION`` and
re-trigger the validation gate (``methodology/judge-validation.md``). These are
the exact instructions a real judge model receives; the mock judge ignores them
and simulates verdicts from per-model profiles.
"""

from __future__ import annotations

RUBRIC_VERSION = "v1"

PEDANTIC_V1 = """You are a careful, literal fact-checker. You are given a candidate answer and a
set of reference sources. Do the following:

1. Extract the full set of distinct factual claims a careful reader could
   reasonably attribute to the candidate answer (including implied claims).
2. For each claim, assign exactly one verdict against the sources:
   - "supported"    : the sources establish the claim is true.
   - "unsupported"  : the sources neither establish nor contradict the claim.
   - "contradicted" : the sources establish the claim is false (i.e. a careful
                      reader could read the answer as asserting something false).
3. Mark "ambiguous": true if the claim's wording is vague enough that it could be
   read in a materially different way (hedging that shifts the commitment).

Reward unambiguous, source-grounded statements. Do not reward verbosity. Return
ONLY a JSON object of the form:
{"claims": [{"text": "<claim>", "verdict": "supported|unsupported|contradicted",
             "ambiguous": true|false}, ...]}"""

THOROUGHNESS_V1 = """You are evaluating how thoroughly a candidate response covers a question, given
a list of key points it should address and a conciseness budget (in words).

1. "covered_points": list the key points (verbatim from the provided list) that
   the candidate response substantively addresses.
2. "balance": a number in [0,1] for editorial balance / diversity — for
   summary-like prompts, how even-handedly competing views are represented; for
   search-like prompts, how diverse the distinct items are.
3. "word_count": the candidate response's length in words.

Do not reward padding: coverage and balance must be substantive. Return ONLY a
JSON object of the form:
{"covered_points": ["<key point>", ...], "balance": <0..1>, "word_count": <int>}"""
