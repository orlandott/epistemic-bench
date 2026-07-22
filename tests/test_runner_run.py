"""Runner execution behaviors: retries, config errors, streaming + resume, usage."""

import asyncio
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401

from epistemic_bench.adapters import AdapterConfigError
from epistemic_bench.jsonlio import read_jsonl
from epistemic_bench.runner import RunConfig, expand, load_completed, run
from epistemic_bench.types import Condition, Item, ModelInfo, Reference, ResponseFormat


def _item(iid="calibration/v1/cal-r"):
    return Item(
        id=iid,
        schema_version="1.0",
        metric="calibration",
        split="public",
        prompt_template="{q}",
        conditions={"base": Condition(id="base", vars={"q": "Q?"})},
        response_format=ResponseFormat(type="mcq", options=("A", "B"), require_confidence=True),
        reference=Reference(kind="answer", answer="A"),
    )


def _registry():
    return {"m": ModelInfo("m", "mock", "X", "M", version="m-2026")}


def _cfg(out_dir, **kw):
    kw.setdefault("retry_base_delay", 0.0)  # keep tests fast
    return RunConfig(models=list(_registry().values()), out_dir=Path(out_dir), **kw)


class TestRetries(unittest.TestCase):
    def test_transient_error_is_retried(self):
        calls = {"n": 0}

        async def flaky(prompt, params):
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("transient")
            return "ANSWER: A  CONFIDENCE: 0.9"

        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, max_retries=2)
            units = expand([_item()], cfg)
            path = asyncio.run(run(units, {"mock": flaky}, _registry(), cfg))
            recs = list(read_jsonl(path))
        self.assertEqual(calls["n"], 2)
        self.assertEqual(len(recs), 1)
        self.assertIsNone(recs[0]["error"])
        self.assertEqual(recs[0]["parsed"]["answer"], "A")
        self.assertEqual(recs[0]["usage"]["retries"], 1)
        self.assertIn("latency_ms", recs[0]["usage"])

    def test_exhausted_retries_capture_error(self):
        calls = {"n": 0}

        async def always_down(prompt, params):
            calls["n"] += 1
            raise ConnectionError("still down")

        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, max_retries=2)
            units = expand([_item()], cfg)
            path = asyncio.run(run(units, {"mock": always_down}, _registry(), cfg))
            recs = list(read_jsonl(path))
        self.assertEqual(calls["n"], 3)  # first try + 2 retries
        self.assertIn("ConnectionError", recs[0]["error"])

    def test_config_error_is_not_retried(self):
        calls = {"n": 0}

        async def unconfigured(prompt, params):
            calls["n"] += 1
            raise AdapterConfigError("no key")

        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, max_retries=5)
            units = expand([_item()], cfg)
            path = asyncio.run(run(units, {"mock": unconfigured}, _registry(), cfg))
            recs = list(read_jsonl(path))
        self.assertEqual(calls["n"], 1)  # retrying a missing key can't help
        self.assertIn("AdapterConfigError", recs[0]["error"])

    def test_tuple_result_carries_usage(self):
        async def with_usage(prompt, params):
            return "ANSWER: B  CONFIDENCE: 0.6", {"input_tokens": 12, "output_tokens": 7}

        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td)
            units = expand([_item()], cfg)
            path = asyncio.run(run(units, {"mock": with_usage}, _registry(), cfg))
            rec = next(iter(read_jsonl(path)))
        self.assertEqual(rec["usage"]["input_tokens"], 12)
        self.assertEqual(rec["usage"]["output_tokens"], 7)

    def test_model_version_passed_to_adapter(self):
        seen = {}

        async def capture(prompt, params):
            seen.update(params)
            return "ANSWER: A  CONFIDENCE: 0.5"

        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td)
            asyncio.run(run(expand([_item()], cfg), {"mock": capture}, _registry(), cfg))
        self.assertEqual(seen["model_version"], "m-2026")


class TestStreamingAndResume(unittest.TestCase):
    def test_resume_skips_successes_and_redoes_failures(self):
        items = [_item("calibration/v1/cal-r1"), _item("calibration/v1/cal-r2")]

        async def first_pass(prompt, params):
            if params["item_id"].endswith("r2"):
                raise ConnectionError("down")
            return "ANSWER: A  CONFIDENCE: 0.9"

        second_calls = []

        async def second_pass(prompt, params):
            second_calls.append(params["item_id"])
            return "ANSWER: B  CONFIDENCE: 0.8"

        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td, max_retries=0)
            units = expand(items, cfg)
            path = asyncio.run(run(units, {"mock": first_pass}, _registry(), cfg))
            self.assertEqual(len(load_completed(path)), 1)

            asyncio.run(run(units, {"mock": second_pass}, _registry(), cfg, resume=True))
            # only the failed unit re-ran
            self.assertEqual(second_calls, ["calibration/v1/cal-r2"])

            # grouping by unit with last-record-wins yields 2 successes
            latest = {}
            for d in read_jsonl(path):
                latest[(d["item_id"], d["condition_id"], d["model_id"])] = d
            self.assertEqual(len(latest), 2)
            self.assertTrue(all(d["error"] is None for d in latest.values()))

    def test_fresh_run_truncates_previous_file(self):
        async def ok(prompt, params):
            return "ANSWER: A  CONFIDENCE: 0.9"

        with tempfile.TemporaryDirectory() as td:
            cfg = _cfg(td)
            units = expand([_item()], cfg)
            asyncio.run(run(units, {"mock": ok}, _registry(), cfg))
            asyncio.run(run(units, {"mock": ok}, _registry(), cfg))  # no resume: rewrite
            self.assertEqual(len(list(read_jsonl(Path(td) / "completions.jsonl"))), 1)


if __name__ == "__main__":
    unittest.main()
