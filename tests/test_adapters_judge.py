"""Real adapters + real judge: configuration gating (no network, no SDKs needed)."""

import asyncio
import os
import unittest
from unittest import mock

import _bootstrap  # noqa: F401

from epistemic_bench.adapters import ADAPTERS, AdapterConfigError
from epistemic_bench.scoring.judge.judge_client import JudgeRequest, make_real_judge
from epistemic_bench.types import ModelInfo


def _req(model_id="m-under-test"):
    return JudgeRequest(prompt="p", rubric="r", metric="pedantic", item_id="pedantic/v1/x", model_id=model_id)


class TestRealAdaptersUnconfigured(unittest.TestCase):
    """Without SDKs/keys the real adapters must fail fast with a config error
    (which the runner records once, without retrying)."""

    def _call(self, provider):
        return asyncio.run(ADAPTERS[provider]("hi", {"model": "x", "model_version": "x-1"}))

    def test_all_real_providers_raise_config_error(self):
        for provider in ("anthropic", "openai", "google", "openweights"):
            with self.subTest(provider=provider):
                env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_BASE_URL"))}
                with mock.patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(AdapterConfigError) as cm:
                        self._call(provider)
                self.assertIn(provider, str(cm.exception))


class TestRealJudgeGate(unittest.TestCase):
    def test_unconfigured_judge_raises_on_use(self):
        judge = make_real_judge({}, {})
        with self.assertRaises(RuntimeError) as cm:
            judge(_req())
        self.assertIn("not configured", str(cm.exception))

    def test_partial_config_counts_as_unconfigured(self):
        judge = make_real_judge({"provider": "openai", "model": "gpt-x"}, {})  # maker missing
        with self.assertRaises(RuntimeError) as cm:
            judge(_req())
        self.assertIn("not configured", str(cm.exception))

    def test_same_maker_refused_before_any_network(self):
        registry = {"m-under-test": ModelInfo("m-under-test", "openai", "OpenAI", "M")}
        judge = make_real_judge({"provider": "openai", "model": "gpt-x", "maker": "OpenAI"}, registry)
        with self.assertRaises(RuntimeError) as cm:
            judge(_req())
        self.assertIn("same maker", str(cm.exception))

    def test_same_maker_check_is_case_insensitive(self):
        registry = {"m-under-test": ModelInfo("m-under-test", "openai", "openai ", "M")}
        judge = make_real_judge({"provider": "openai", "model": "gpt-x", "maker": "OpenAI"}, registry)
        with self.assertRaises(RuntimeError) as cm:
            judge(_req())
        self.assertIn("same maker", str(cm.exception))

    def test_cross_maker_proceeds_to_provider_call(self):
        registry = {"m-under-test": ModelInfo("m-under-test", "anthropic", "Anthropic", "M")}
        judge = make_real_judge({"provider": "openai", "model": "gpt-x", "maker": "OpenAI"}, registry)
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as cm:
                judge(_req())
        # Passed the maker gate; failed only on the missing SDK/key.
        self.assertNotIn("same maker", str(cm.exception))

    def test_judge_id_attribute(self):
        judge = make_real_judge({"provider": "openai", "model": "gpt-x", "maker": "OpenAI", "id": "j1"}, {})
        self.assertEqual(judge.judge_id, "j1")


if __name__ == "__main__":
    unittest.main()
