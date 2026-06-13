import json
import unittest

import _bootstrap  # noqa: F401

from epistemic_bench.scoring.judge.thoroughness import score_thoroughness
from epistemic_bench.types import (
    Completion,
    Condition,
    Item,
    ModelInfo,
    Reference,
    ResponseFormat,
    ScoringContext,
)


def _item(budget=100):
    return Item(
        id="thoroughness/v1/thr-test",
        schema_version="1.0",
        metric="thoroughness",
        split="public",
        prompt_template="Q",
        conditions={"base": Condition(id="base")},
        response_format=ResponseFormat(type="free_text"),
        reference=Reference(kind="sources_only"),
        params={"key_points": ["a", "b", "c", "d"], "conciseness_budget": budget},
    )


def _comp():
    return Completion("thoroughness/v1/thr-test", "base", "m", "resp", {"text": "resp"})


def _ctx(judge):
    return ScoringContext(model=ModelInfo("m", "mock", "X", "M"), judge=judge)


class TestThoroughnessScorer(unittest.TestCase):
    def test_score_combination(self):
        # coverage 2/4=0.5, balance 0.8, conciseness 1.0 (wc==budget)
        # 0.5*0.5 + 0.3*0.8 + 0.2*1.0 = 0.69
        judge = lambda req: json.dumps({"covered_points": ["a", "b"], "balance": 0.8, "word_count": 100})
        s = score_thoroughness(_item(100), {"base": _comp()}, _ctx(judge))
        self.assertTrue(s.valid)
        self.assertAlmostEqual(s.value, 0.69, places=6)
        self.assertAlmostEqual(s.components["coverage"], 0.5)

    def test_verbosity_penalizes_conciseness(self):
        # word_count 200 vs budget 100 -> over by 100% -> conciseness clamps to 0
        judge = lambda req: json.dumps({"covered_points": ["a", "b", "c", "d"], "balance": 1.0, "word_count": 200})
        s = score_thoroughness(_item(100), {"base": _comp()}, _ctx(judge))
        self.assertAlmostEqual(s.components["conciseness"], 0.0)
        self.assertAlmostEqual(s.value, 0.5 * 1.0 + 0.3 * 1.0 + 0.2 * 0.0, places=6)

    def test_requires_judge(self):
        with self.assertRaises(RuntimeError):
            score_thoroughness(_item(), {"base": _comp()}, ScoringContext(model=ModelInfo("m", "mock", "X", "M")))


if __name__ == "__main__":
    unittest.main()
