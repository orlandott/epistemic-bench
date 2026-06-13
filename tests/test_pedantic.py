import json
import unittest

import _bootstrap  # noqa: F401

from epistemic_bench.scoring.judge.pedantic import score_pedantic
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
        id="pedantic/v1/ped-test",
        schema_version="1.0",
        metric="pedantic",
        split="public",
        prompt_template="Q",
        conditions={"base": Condition(id="base")},
        response_format=ResponseFormat(type="free_text"),
        reference=Reference(kind="sources_only"),
        sources=({"title": "S", "quote": "fact"},),
        params={"n_claims": 4},
    )


def _comp():
    return Completion("pedantic/v1/ped-test", "base", "m", "an answer", {"text": "an answer"})


def _ctx(judge):
    return ScoringContext(model=ModelInfo("m", "mock", "X", "M"), judge=judge)


def _fake_judge(verdict_obj):
    return lambda req: json.dumps(verdict_obj)


class TestPedanticScorer(unittest.TestCase):
    def test_credit_formula(self):
        # 3 supported & clear (+1 each) + 1 contradicted (-1) over n=4 -> 2/4 = 0.5
        judge = _fake_judge(
            {
                "claims": [
                    {"verdict": "supported", "ambiguous": False},
                    {"verdict": "supported", "ambiguous": False},
                    {"verdict": "supported", "ambiguous": False},
                    {"verdict": "contradicted", "ambiguous": False},
                ]
            }
        )
        s = score_pedantic(_item(), {"base": _comp()}, _ctx(judge))
        self.assertTrue(s.valid)
        self.assertAlmostEqual(s.value, 0.5)
        self.assertEqual(s.components["contradicted"], 1.0)

    def test_ambiguous_supported_is_half_credit(self):
        judge = _fake_judge({"claims": [{"verdict": "supported", "ambiguous": True}, {"verdict": "unsupported"}]})
        s = score_pedantic(_item(), {"base": _comp()}, _ctx(judge))
        self.assertAlmostEqual(s.value, 0.25)  # (0.5 + 0) / 2

    def test_requires_judge(self):
        with self.assertRaises(RuntimeError):
            score_pedantic(_item(), {"base": _comp()}, ScoringContext(model=ModelInfo("m", "mock", "X", "M")))

    def test_bad_json_is_invalid(self):
        s = score_pedantic(_item(), {"base": _comp()}, _ctx(lambda req: "not json"))
        self.assertFalse(s.valid)


if __name__ == "__main__":
    unittest.main()
