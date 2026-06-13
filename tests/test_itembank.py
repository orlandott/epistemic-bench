import os
import unittest

import _bootstrap  # noqa: F401  (adds src/ to path)

from epistemic_bench.itembank import load_items, validate_file, validate_item

REPO = os.path.join(os.path.dirname(__file__), "..")
CAL = os.path.join(REPO, "itembank", "public", "calibration.v1.jsonl")


class TestItemBank(unittest.TestCase):
    def test_public_calibration_loads(self):
        items = load_items(os.path.join(REPO, "itembank", "public"))
        self.assertGreaterEqual(len(items), 30)
        self.assertTrue(all(it.metric == "calibration" for it in items))
        self.assertTrue(all(it.split == "public" for it in items))
        self.assertTrue(all("base" in it.conditions for it in items))
        self.assertTrue(all(it.reference.answer in {"A", "B", "C", "D"} for it in items))

    def test_validate_file_clean(self):
        self.assertEqual(validate_file(CAL), [])

    def test_validate_item_flags_problems(self):
        bad = {
            "id": "BadId",  # wrong pattern
            "schema_version": "1.0",
            "metric": "nope",  # unknown metric
            "split": "public",
            "prompt_template": "x",
            "conditions": {},  # empty
            "response_format": {"type": "mcq"},  # missing options
            "reference": {"kind": "answer"},  # missing answer
        }
        errs = validate_item(bad)
        self.assertTrue(any("id must match" in e for e in errs))
        self.assertTrue(any("unknown metric" in e for e in errs))
        self.assertTrue(any("at least one condition" in e for e in errs))
        self.assertTrue(any("requires 'options'" in e for e in errs))
        self.assertTrue(any("requires 'answer'" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
