import unittest

import _bootstrap  # noqa: F401

from epistemic_bench.scoring.clarity import score_clarity
from epistemic_bench.types import (
    Completion,
    Condition,
    Item,
    ModelInfo,
    Reference,
    ResponseFormat,
    ScoringContext,
)


def _item():
    return Item(
        id="clarity/v1/clr-test",
        schema_version="1.0",
        metric="clarity",
        split="public",
        prompt_template="Q",
        conditions={"base": Condition(id="base")},
        response_format=ResponseFormat(type="free_text"),
        reference=Reference(kind="sources_only"),
    )


def _ctx():
    return ScoringContext(model=ModelInfo("m", "mock", "X", "M"))


def _run(text):
    comp = Completion("clarity/v1/clr-test", "base", "m", text, {"text": text})
    return score_clarity(_item(), {"base": comp}, _ctx())


class TestClarityScorer(unittest.TestCase):
    def test_crisp_text_scores_high(self):
        s = _run("The sky is blue because air scatters short wavelengths. This is well established.")
        self.assertTrue(s.valid)
        self.assertEqual(s.components["hedge_count"], 0.0)
        self.assertEqual(s.components["commitment_shifts"], 0.0)
        self.assertAlmostEqual(s.value, 1.0)

    def test_hedges_reduce_score(self):
        crisp = _run("The cause is well understood. The mechanism is clear.")
        hedgy = _run("Arguably the cause is sort of understood. Perhaps the mechanism is in a sense clear.")
        self.assertLess(hedgy.value, crisp.value)
        self.assertGreater(hedgy.components["hedge_count"], 0.0)

    def test_commitment_shift_detected(self):
        s = _run("This is definitely true, although it might be wrong.")
        self.assertGreaterEqual(s.components["commitment_shifts"], 1.0)
        self.assertLess(s.value, 1.0)

    def test_calibrated_probability_not_penalized(self):
        # "probably"/"likely" are calibrated uncertainty, not vague hedges
        s = _run("The result is probably correct. It is likely accurate.")
        self.assertEqual(s.components["hedge_count"], 0.0)
        self.assertAlmostEqual(s.value, 1.0)

    def test_empty_is_invalid(self):
        self.assertFalse(_run("").valid)


if __name__ == "__main__":
    unittest.main()
