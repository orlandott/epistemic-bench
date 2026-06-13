"""Fixed, documented, versioned judge rubrics (SPEC §10).

Rubrics are pinned constants. Any change MUST bump ``RUBRIC_VERSION`` and
re-trigger the validation gate (``methodology/judge-validation.md``). These are
the exact instructions a real judge model receives; the mock judge ignores them
and simulates verdicts from per-model profiles.
"""

from __future__ import annotations

# Bumped v1 -> v2 when the pedantic rubric was reframed from "judge the answer
# against the sources the model was told to use" to "enumerate every claim a
# careful reader could attribute (including implied/presupposed ones) and check
# each for truth against the reference facts." Any further change re-triggers the
# validation gate (methodology/judge-validation.md).
RUBRIC_VERSION = "v2"

PEDANTIC_V1 = """You are a careful, literal fact-checker. You are given a question, a candidate
answer written freely by a model, and a set of reference facts that are the
ground-truth key (the model was NOT told to limit itself to them). Do the
following:

1. Enumerate the full set of distinct factual claims a careful, literal reader
   could reasonably attribute to the candidate answer. Include not just the
   explicit sentences but every IMPLIED and PRESUPPOSED claim. If a statement is
   true under its intended reading but false under another natural reading, treat
   the false reading as one of its attributable claims.
2. For each claim, assign exactly one verdict against the reference facts:
   - "supported"    : the reference facts establish the claim is true.
   - "unsupported"  : the reference facts neither establish nor contradict the
                      claim (its truth cannot be adjudicated either way).
   - "contradicted" : the reference facts establish the claim is false (i.e. a
                      careful reader could read the answer as asserting something
                      false).
3. Mark "ambiguous": true if the claim's wording is vague enough that a different
   natural reading would change what is being claimed (hedging that shifts the
   commitment).

Reward unambiguous, true statements. Do not reward verbosity. Return ONLY a JSON
object of the form:
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
