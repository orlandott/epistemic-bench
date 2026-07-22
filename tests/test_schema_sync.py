"""Keep the dependency-free internal validator and the shipped JSON Schema in sync.

The enum/pattern comparison always runs; full JSON-Schema validation of the
public bank runs when the optional ``jsonschema`` package is installed
(``pip install -e '.[dev]'``).
"""

import json
import os
import unittest

import _bootstrap  # noqa: F401

from epistemic_bench import itembank
from epistemic_bench.jsonlio import read_jsonl

REPO = os.path.join(os.path.dirname(__file__), "..")
SCHEMA_PATH = os.path.join(REPO, "itembank", "schema", "item.schema.json")
PUBLIC = os.path.join(REPO, "itembank", "public")

with open(SCHEMA_PATH, encoding="utf-8") as fh:
    SCHEMA = json.load(fh)


def _public_records():
    for name in sorted(os.listdir(PUBLIC)):
        if name.endswith(".jsonl"):
            yield from read_jsonl(os.path.join(PUBLIC, name))


class TestValidatorSchemaSync(unittest.TestCase):
    def test_metric_enum_matches(self):
        self.assertEqual(set(SCHEMA["properties"]["metric"]["enum"]), itembank._METRICS)

    def test_split_enum_matches(self):
        self.assertEqual(set(SCHEMA["properties"]["split"]["enum"]), itembank._SPLITS)

    def test_response_type_enum_matches(self):
        enum = SCHEMA["properties"]["response_format"]["properties"]["type"]["enum"]
        self.assertEqual(set(enum), itembank._RESP_TYPES)

    def test_reference_kind_enum_matches(self):
        enum = SCHEMA["properties"]["reference"]["properties"]["kind"]["enum"]
        self.assertEqual(set(enum), itembank._REF_KINDS)

    def test_id_pattern_matches(self):
        self.assertEqual(SCHEMA["properties"]["id"]["pattern"], itembank._ID_RE.pattern)

    def test_required_fields_match(self):
        # The internal validator's required list mirrors the schema's.
        internal_required = {
            "id", "schema_version", "metric", "split", "prompt_template",
            "conditions", "response_format", "reference",
        }
        self.assertEqual(set(SCHEMA["required"]), internal_required)


class TestBankAgainstJsonSchema(unittest.TestCase):
    def test_public_bank_validates_against_json_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed (pip install -e '.[dev]')")
        validator = jsonschema.Draft202012Validator(SCHEMA)
        for rec in _public_records():
            errors = [f"{rec.get('id')}: {e.message}" for e in validator.iter_errors(rec)]
            self.assertEqual(errors, [])

    def test_public_bank_passes_internal_validator(self):
        for rec in _public_records():
            self.assertEqual(itembank.validate_item(rec), [])


if __name__ == "__main__":
    unittest.main()
