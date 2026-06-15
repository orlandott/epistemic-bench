import os
import unittest

import _bootstrap  # noqa: F401

from epistemic_bench.aggregate import ModelMetricSummary, to_report
from epistemic_bench.itembank import load_items
from epistemic_bench.rotation import (
    load_manifest,
    rotation_group_of,
    rotation_plan,
    select_active,
    split_counts,
)
from epistemic_bench.types import ModelInfo

REPO = os.path.join(os.path.dirname(__file__), "..")
MANIFEST = os.path.join(REPO, "itembank", "manifest.yaml")


class TestManifestAndSelection(unittest.TestCase):
    def setUp(self):
        self.m = load_manifest(MANIFEST)
        self.items = load_items(os.path.join(REPO, "itembank", "public"))

    def test_manifest_fields(self):
        self.assertEqual(self.m.canonical_split, "private")
        self.assertEqual(self.m.active["calibration"], "cal-v1a")
        self.assertIn("cal-v1b", self.m.operationalizations["calibration"])

    def test_rotation_group_parsed(self):
        cal = next(it for it in self.items if it.metric == "calibration")
        self.assertTrue(rotation_group_of(cal).startswith("cal-v1"))

    def test_select_active_excludes_reserve(self):
        active = select_active(self.items, self.m)
        groups = {rotation_group_of(it) for it in active if it.metric == "calibration"}
        self.assertEqual(groups, {"cal-v1a"})  # cal-v1b reserve excluded
        # all active calibration items are cal-v1a
        self.assertEqual(sum(1 for it in active if it.metric == "calibration"), 100)

    def test_burned_group_excluded(self):
        m2 = load_manifest(MANIFEST)
        m2 = type(m2)(**{**m2.__dict__, "burned": frozenset({"cal-v1a"})})
        active = select_active(self.items, m2)
        self.assertEqual(sum(1 for it in active if it.metric == "calibration"), 0)

    def test_rotation_plan(self):
        plan = rotation_plan(self.items, self.m, burn_fraction=0.25)
        cal = plan["metrics"]["calibration"]
        self.assertEqual(cal["n_public"], 100)
        self.assertEqual(cal["burn_n"], 25)
        self.assertEqual(cal["next_active"], "cal-v1b")
        self.assertEqual(len(cal["burn_ids"]), 25)

    def test_split_counts(self):
        c = split_counts(self.items)
        self.assertEqual(c["private"], 0)
        self.assertGreaterEqual(c["public"], 96)


class TestPrivateExampleLoads(unittest.TestCase):
    def test_private_items_load_and_are_active(self):
        m = load_manifest(MANIFEST)
        items = load_items(
            os.path.join(REPO, "itembank", "public"),
            os.path.join(REPO, "itembank", "private.example"),
            splits=("public", "private"),
        )
        active = select_active(items, m)
        priv = [it for it in active if it.split == "private"]
        self.assertTrue(priv)  # private example items are in active groups
        self.assertTrue(all(rotation_group_of(it) == m.active[it.metric] for it in priv))


class TestCanonicalSplitPolicy(unittest.TestCase):
    def _reg(self):
        return {"m": ModelInfo("m", "mock", "X", "M")}

    def test_private_is_canonical_with_public_reference(self):
        summaries = [
            ModelMetricSummary("m", "calibration", 30, 0.90, {"ece": 0.10}, (0.85, 0.94), (), "public"),
            ModelMetricSummary("m", "calibration", 4, 0.92, {"ece": 0.08}, (0.80, 0.97), (), "private"),
        ]
        report = to_report(summaries, {}, self._reg(), canonical_split="private")
        cal = report["virtues"]["calibration"]
        self.assertEqual(cal["canonical_split"], "private")
        self.assertEqual(cal["by_model"]["m"]["score"], 0.92)  # private headline
        self.assertEqual(cal["by_model"]["m"]["public_reference"]["score"], 0.90)

    def test_falls_back_to_public_when_private_absent(self):
        summaries = [ModelMetricSummary("m", "calibration", 30, 0.90, {"ece": 0.10}, None, (), "public")]
        report = to_report(summaries, {}, self._reg(), canonical_split="private")
        cal = report["virtues"]["calibration"]
        self.assertEqual(cal["canonical_split"], "public")  # fallback
        self.assertNotIn("public_reference", cal["by_model"]["m"])


if __name__ == "__main__":
    unittest.main()
