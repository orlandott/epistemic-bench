import unittest

import _bootstrap  # noqa: F401

from epistemic_bench.aggregate import (
    _ece_and_bins,
    _quantile_reliability,
    _wilson,
    aggregate,
)
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


class TestReliabilityDiagram(unittest.TestCase):
    def test_quantile_bins_are_equal_mass_and_populated(self):
        confs = [i / 30 for i in range(30)]
        corrects = [float(i % 2) for i in range(30)]
        rel = _quantile_reliability(confs, corrects, n_bins=5)
        self.assertEqual(len(rel), 5)
        self.assertEqual(sum(b.n for b in rel), 30)
        self.assertTrue(all(b.n > 0 for b in rel))  # no empty plotted points
        # bins are ordered by confidence and carry a valid accuracy band
        self.assertEqual([round(b.mean_conf, 6) for b in rel],
                         sorted(round(b.mean_conf, 6) for b in rel))
        self.assertTrue(all(0.0 <= b.acc_lo <= b.accuracy <= b.acc_hi <= 1.0 for b in rel))

    def test_fewer_bins_than_requested_when_sparse(self):
        rel = _quantile_reliability([0.3, 0.8], [1.0, 0.0], n_bins=5)
        self.assertEqual(len(rel), 2)  # renderer suppresses the line below 3 points

    def test_wilson_stays_in_unit_interval_at_extremes(self):
        lo, hi = _wilson(0, 5)
        self.assertAlmostEqual(lo, 0.0)
        self.assertLess(hi, 1.0)
        lo, hi = _wilson(5, 5)
        self.assertAlmostEqual(hi, 1.0)
        self.assertGreater(lo, 0.0)
        self.assertEqual(_wilson(0, 0), (0.0, 0.0))

    def test_score_uses_fixed_bin_ece_not_quantile(self):
        # quantile binning is display-only; the published score keeps fixed-bin ECE
        scores = [
            MetricScore("i1", "calibration", "m", 0.0, {"correct": 1.0, "confidence": 0.95}, valid=True),
            MetricScore("i2", "calibration", "m", 0.9025, {"correct": 0.0, "confidence": 0.95}, valid=True),
        ]
        registry = {"m": ModelInfo("m", "mock", "X", "M")}
        s = aggregate(scores, registry, seed=1, n_boot=20)[0]
        self.assertAlmostEqual(s.raw["ece"], 0.45, places=4)  # fixed-bin definition


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
