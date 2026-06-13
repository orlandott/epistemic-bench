import os
import unittest

import _bootstrap  # noqa: F401

from epistemic_bench.aggregate import ModelMetricSummary, to_report
from epistemic_bench.types import ModelInfo
from epistemic_bench.validation import cohens_kappa, pearson, run_validation

REPO = os.path.join(os.path.dirname(__file__), "..")
VDIR = os.path.join(REPO, "validation", "judge")


class TestAgreementStats(unittest.TestCase):
    def test_kappa_perfect_and_chance(self):
        self.assertAlmostEqual(cohens_kappa(["a", "b", "a"], ["a", "b", "a"]), 1.0)
        # all same label on both sides but constant -> pe=1 -> defined as 1.0
        self.assertAlmostEqual(cohens_kappa(["a", "a"], ["a", "a"]), 1.0)

    def test_pearson_basic(self):
        self.assertAlmostEqual(pearson([1, 2, 3], [2, 4, 6]), 1.0, places=6)
        self.assertAlmostEqual(pearson([1, 2, 3], [3, 2, 1]), -1.0, places=6)


class TestRunValidation(unittest.TestCase):
    def test_pedantic_sample_passes(self):
        r = run_validation("pedantic", os.path.join(VDIR, "pedantic.sample.jsonl"), threshold=0.6)
        self.assertEqual(r.agreement_metric, "cohen_kappa")
        self.assertGreaterEqual(r.agreement_value, 0.6)
        self.assertTrue(r.passed)

    def test_thoroughness_sample_passes(self):
        r = run_validation("thoroughness", os.path.join(VDIR, "thoroughness.sample.jsonl"), threshold=0.6)
        self.assertEqual(r.agreement_metric, "pearson_r")
        self.assertTrue(r.passed)

    def test_threshold_can_fail(self):
        r = run_validation("pedantic", os.path.join(VDIR, "pedantic.sample.jsonl"), threshold=0.99)
        self.assertFalse(r.passed)


class TestPublicationGate(unittest.TestCase):
    def _summaries(self):
        return [
            ModelMetricSummary("m", "calibration", 10, 0.9, {"ece": 0.1, "n_items": 10}),
            ModelMetricSummary("m", "pedantic", 6, 0.75, {"precision": 0.75, "n_items": 6}),
        ]

    def _registry(self):
        return {"m": ModelInfo("m", "mock", "X", "M")}

    def test_validated_judge_metric_is_published(self):
        validation = {"pedantic": {"passed": True, "agreement_metric": "cohen_kappa", "agreement_value": 0.73, "threshold": 0.6}}
        report = to_report(self._summaries(), {"demo": True}, self._registry(), validation)
        self.assertIn("pedantic", report["virtues"])
        self.assertTrue(report["virtues"]["pedantic"]["judge_validated"])
        self.assertEqual(report["withheld"], {})

    def test_unvalidated_judge_metric_is_withheld(self):
        report = to_report(self._summaries(), {"demo": True}, self._registry(), validation={})
        self.assertNotIn("pedantic", report["virtues"])
        self.assertIn("pedantic", report["withheld"])
        # non-judged metric still published
        self.assertIn("calibration", report["virtues"])

    def test_failed_validation_is_withheld(self):
        validation = {"pedantic": {"passed": False, "agreement_metric": "cohen_kappa", "agreement_value": 0.4, "threshold": 0.6}}
        report = to_report(self._summaries(), {"demo": True}, self._registry(), validation)
        self.assertNotIn("pedantic", report["virtues"])
        self.assertIn("pedantic", report["withheld"])


if __name__ == "__main__":
    unittest.main()
