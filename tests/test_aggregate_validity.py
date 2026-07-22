"""Exclusion accounting: invalid (unparseable/errored) items must be visible in
every summary's raw block, so dropped items can't silently flatter a model."""

import unittest

import _bootstrap  # noqa: F401

from epistemic_bench.aggregate import aggregate
from epistemic_bench.types import MetricScore, ModelInfo


def _reg():
    return {"m": ModelInfo("m", "mock", "X", "M")}


class TestInvalidSurfaced(unittest.TestCase):
    def test_calibration_reports_n_invalid(self):
        scores = [
            MetricScore("i1", "calibration", "m", 0.04, {"correct": 1.0, "confidence": 0.8}, valid=True),
            MetricScore("i2", "calibration", "m", 0.0, {}, valid=False),  # parse failure
            MetricScore("i3", "calibration", "m", 0.0, {}, valid=False),
        ]
        s = aggregate(scores, _reg(), n_boot=10)[0]
        self.assertEqual(s.n_items, 1)
        self.assertEqual(s.raw["n_invalid"], 2)

    def test_all_invalid_still_reports_counts(self):
        scores = [MetricScore("i1", "sycophancy", "m", 0.0, {}, valid=False)]
        s = aggregate(scores, _reg(), n_boot=10)[0]
        self.assertIsNone(s.score)
        self.assertEqual(s.raw["n_items"], 0)
        self.assertEqual(s.raw["n_invalid"], 1)

    def test_framing_reports_modal_agreement_and_invalid(self):
        scores = [
            MetricScore(
                "i1", "framing", "m", 0.0,
                {"framing_flip_rate": 0.0, "stability": 1.0, "modal_agreement": 1.0}, valid=True,
            ),
            MetricScore("i2", "framing", "m", 0.0, {}, valid=False),
        ]
        s = aggregate(scores, _reg(), n_boot=10)[0]
        self.assertEqual(s.raw["n_invalid"], 1)
        self.assertAlmostEqual(s.raw["mean_modal_agreement"], 1.0)

    def test_judged_metric_reports_n_invalid(self):
        scores = [
            MetricScore("i1", "pedantic", "m", 0.8, {"precision": 0.8}, valid=True),
            MetricScore("i2", "pedantic", "m", 0.0, {}, valid=False),
        ]
        s = aggregate(scores, _reg(), n_boot=10)[0]
        self.assertEqual(s.raw["n_invalid"], 1)


if __name__ == "__main__":
    unittest.main()
