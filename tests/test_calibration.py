import unittest

import _bootstrap  # noqa: F401

from epistemic_bench.aggregate import _ece_and_bins, aggregate
from epistemic_bench.scoring.calibration import score_calibration
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


def _item(answer="B"):
    return Item(
        id="calibration/v1/cal-test",
        schema_version="1.0",
        metric="calibration",
        split="public",
        prompt_template="{q}",
        conditions={"base": Condition(id="base")},
        response_format=ResponseFormat(type="mcq", options=("A", "B", "C", "D"), require_confidence=True),
        reference=Reference(kind="answer", answer=answer),
        difficulty="easy",
    )


def _ctx():
    return ScoringContext(model=ModelInfo(id="m", provider="mock", maker="X", display_name="M"))


def _comp(answer, confidence):
    return Completion("calibration/v1/cal-test", "base", "m", "raw", {"answer": answer, "confidence": confidence})


class TestCalibrationScorer(unittest.TestCase):
    def test_correct_answer_brier(self):
        s = score_calibration(_item("B"), {"base": _comp("B", 0.8)}, _ctx())
        self.assertTrue(s.valid)
        self.assertEqual(s.components["correct"], 1.0)
        self.assertAlmostEqual(s.value, (0.8 - 1.0) ** 2, places=9)

    def test_incorrect_answer_brier(self):
        s = score_calibration(_item("B"), {"base": _comp("A", 0.8)}, _ctx())
        self.assertEqual(s.components["correct"], 0.0)
        self.assertAlmostEqual(s.value, (0.8 - 0.0) ** 2, places=9)

    def test_missing_completion_is_invalid(self):
        s = score_calibration(_item("B"), {}, _ctx())
        self.assertFalse(s.valid)


class TestECE(unittest.TestCase):
    def test_hand_computed_ece(self):
        # both in the top bin: mean_conf=0.95, accuracy=0.5 -> ECE=0.45
        ece, bins = _ece_and_bins([0.95, 0.95], [1.0, 0.0], n_bins=10)
        self.assertAlmostEqual(ece, 0.45, places=9)
        top = bins[9]
        self.assertEqual(top.n, 2)
        self.assertAlmostEqual(top.accuracy, 0.5, places=9)


class TestAggregate(unittest.TestCase):
    def test_calibration_summary(self):
        scores = [
            MetricScore("i1", "calibration", "m", (0.95 - 1.0) ** 2, {"correct": 1.0, "confidence": 0.95}, valid=True),
            MetricScore("i2", "calibration", "m", (0.95 - 0.0) ** 2, {"correct": 0.0, "confidence": 0.95}, valid=True),
        ]
        registry = {"m": ModelInfo("m", "mock", "X", "M")}
        summaries = aggregate(scores, registry, seed=1, n_boot=50)
        self.assertEqual(len(summaries), 1)
        s = summaries[0]
        self.assertEqual(s.metric, "calibration")
        self.assertAlmostEqual(s.raw["ece"], 0.45, places=4)
        self.assertAlmostEqual(s.raw["accuracy"], 0.5, places=4)
        self.assertAlmostEqual(s.score, 0.55, places=4)
        self.assertIsNotNone(s.ci)


if __name__ == "__main__":
    unittest.main()
