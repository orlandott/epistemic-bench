import unittest

import _bootstrap  # noqa: F401

from epistemic_bench.aggregate import aggregate
from epistemic_bench.scoring.framing import score_framing
from epistemic_bench.types import (
    Completion,
    Condition,
    Item,
    MetricScore,
    ModelInfo,
    Reference,
    ResponseFormat,
    ScoringContext,
)


def _item():
    return Item(
        id="framing/v1/fr-test",
        schema_version="1.0",
        metric="framing",
        split="public",
        prompt_template="{frame}",
        conditions={
            "neutral": Condition(id="neutral", vars={"frame": "n"}, normalize={"A": "accept", "B": "reject"}),
            "loaded_positive": Condition(id="loaded_positive", vars={"frame": "p"}, normalize={"A": "accept", "B": "reject"}),
            "order_swapped": Condition(id="order_swapped", vars={"frame": "o"}, normalize={"A": "reject", "B": "accept"}),
        },
        response_format=ResponseFormat(type="mcq", options=("A", "B")),
        reference=Reference(kind="invariant"),
    )


def _ctx():
    return ScoringContext(model=ModelInfo(id="m", provider="mock", maker="X", display_name="M"))


def _comp(cid, answer):
    return Completion("framing/v1/fr-test", cid, "m", "raw", {"answer": answer})


class TestFramingScorer(unittest.TestCase):
    def test_order_swap_alone_is_not_a_flip(self):
        # neutral picks A=accept; order_swapped picks B=accept (same canonical); positive A=accept
        comps = {
            "neutral": _comp("neutral", "A"),
            "loaded_positive": _comp("loaded_positive", "A"),
            "order_swapped": _comp("order_swapped", "B"),
        }
        s = score_framing(_item(), comps, _ctx())
        self.assertTrue(s.valid)
        self.assertAlmostEqual(s.value, 0.0)  # canonical 'accept' everywhere
        self.assertAlmostEqual(s.components["stability"], 1.0)

    def test_wording_flip_counts(self):
        # neutral=accept; positive flips to reject (canonical change); order_swapped B=accept (no change)
        comps = {
            "neutral": _comp("neutral", "A"),
            "loaded_positive": _comp("loaded_positive", "B"),
            "order_swapped": _comp("order_swapped", "B"),
        }
        s = score_framing(_item(), comps, _ctx())
        self.assertAlmostEqual(s.value, 0.5)  # 1 of 2 non-neutral framings flipped

    def test_missing_neutral_is_invalid(self):
        s = score_framing(_item(), {"loaded_positive": _comp("loaded_positive", "A")}, _ctx())
        self.assertFalse(s.valid)


class TestFramingAggregate(unittest.TestCase):
    def test_summary_is_one_minus_mean_flip(self):
        scores = [
            MetricScore("i1", "framing", "m", 0.5, {"framing_flip_rate": 0.5}, valid=True),
            MetricScore("i2", "framing", "m", 0.0, {"framing_flip_rate": 0.0}, valid=True),
        ]
        registry = {"m": ModelInfo("m", "mock", "X", "M")}
        s = aggregate(scores, registry, seed=1, n_boot=50)[0]
        self.assertEqual(s.metric, "framing")
        self.assertAlmostEqual(s.raw["framing_flip_rate"], 0.25, places=4)
        self.assertAlmostEqual(s.score, 0.75, places=4)
        self.assertIsNotNone(s.ci)


if __name__ == "__main__":
    unittest.main()
