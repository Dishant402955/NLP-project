"""Offline regression tests for local generation latency improvements."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from nl2bash.cli import _run_generate, build_parser
from nl2bash.command_generation import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_GPU_LAYERS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_THREADS,
    PROMPT_VERSION,
    _prompt,
    generate_bash_command,
    load_local_generator,
)
from nl2bash.entity_extraction import extract_entities
from nl2bash.generation_configuration import (
    _sha256_file_cached,
    sha256_file_cached,
)
from nl2bash.intent_prediction import IntentPrediction


class FakeGenerator:
    def __init__(self) -> None:
        self.kwargs = None

    def create_chat_completion(self, **kwargs):
        self.kwargs = kwargs
        return {
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "command": "find . -type f -name '*.py'",
                        "explanation": "Find Python files.",
                        "assumptions": [],
                    }),
                },
            }],
            "usage": {"prompt_tokens": 80, "completion_tokens": 18, "total_tokens": 98},
        }


class LatencyOptimizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = "Find Python files in the current directory."
        self.intent = IntentPrediction(
            request=self.request,
            intent_label="file_discovery",
            raw_top_label="file_discovery",
            confidence=0.8,
            low_confidence=False,
            confidence_threshold=0.13,
        )
        self.extraction = extract_entities(self.request)

    def test_offline_runtime_defaults_are_conservative_for_two_core_cpu(self) -> None:
        self.assertEqual(DEFAULT_THREADS, 2)
        self.assertEqual(DEFAULT_BATCH_SIZE, 512)
        self.assertEqual(DEFAULT_GPU_LAYERS, 0)
        self.assertEqual(DEFAULT_MAX_TOKENS, 256)
        self.assertEqual(PROMPT_VERSION, "qwen-bash-json-v7")

    def test_prompt_is_compact_and_preserves_critical_filename_rules(self) -> None:
        messages = _prompt(self.request, self.intent, self.extraction)
        joined = "\n".join(message["content"] for message in messages)
        payload = json.loads(messages[1]["content"])
        self.assertIn("case-sensitive by default", joined)
        self.assertIn("never -mtime -1440", joined)
        self.assertNotIn("intent_confidence", payload)
        self.assertNotIn("span", json.dumps(payload))
        self.assertLess(len(joined), 3000)

    def test_generation_uses_reduced_token_budget_and_exposes_usage(self) -> None:
        generator = FakeGenerator()
        result = generate_bash_command(
            self.request,
            self.intent,
            self.extraction,
            generator=generator,
        )
        self.assertEqual(generator.kwargs["max_tokens"], DEFAULT_MAX_TOKENS)
        self.assertEqual(result.command, "find . -type f -name '*.py'")
        self.assertEqual(result.inference_metrics["prompt_tokens"], 80)
        self.assertEqual(result.inference_metrics["completion_tokens"], 18)
        self.assertIn("prompt_build_seconds", result.inference_metrics)
        self.assertIn("model_call_seconds", result.inference_metrics)

    def test_interactive_cli_does_not_require_a_single_request(self) -> None:
        args = build_parser().parse_args(["generate", "--interactive"])
        self.assertTrue(args.interactive)
        self.assertIsNone(args.request)
        self.assertTrue(args.timings is False)
        self.assertEqual(args.batch_size, DEFAULT_BATCH_SIZE)
        self.assertEqual(args.max_tokens, DEFAULT_MAX_TOKENS)

    def test_interactive_session_loads_runtime_once_for_multiple_requests(self) -> None:
        args = build_parser().parse_args(["generate", "--interactive"])
        runtime = SimpleNamespace(startup_timings={"total_startup_seconds": 0.01})
        fake_output = {"result": "ok"}
        with patch("nl2bash.cli._load_runtime", return_value=runtime) as load_runtime, \
             patch("nl2bash.cli._generate_one", return_value=fake_output) as generate_one, \
             patch("nl2bash.cli._print_generate_output") as print_output, \
             patch("sys.stdin", io.StringIO("first task\nsecond task\nexit\n")), \
             patch("sys.stdout", io.StringIO()), \
             patch("sys.stderr", io.StringIO()):
            status = _run_generate(args)
        self.assertEqual(status, 0)
        load_runtime.assert_called_once_with(args)
        self.assertEqual(generate_one.call_count, 2)
        self.assertEqual(print_output.call_count, 2)

    def test_prompt_cache_metrics_keep_full_and_evaluated_tokens_separate(self) -> None:
        generator = FakeGenerator()
        generator._ctx = SimpleNamespace(ctx=object())
        fake_runtime = types.ModuleType("llama_cpp")
        fake_runtime.llama_perf_context_reset = Mock()
        fake_runtime.llama_perf_context = Mock(return_value=SimpleNamespace(
            t_p_eval_ms=1000.0, t_eval_ms=900.0, n_p_eval=80, n_eval=18, n_reused=120,
        ))
        with patch.dict(sys.modules, {"llama_cpp": fake_runtime}):
            result = generate_bash_command(
                self.request, self.intent, self.extraction, generator=generator,
            )
        self.assertEqual(result.inference_metrics["prompt_tokens"], 80)
        self.assertEqual(result.inference_metrics["prompt_eval_tokens"], 80)
        self.assertEqual(result.inference_metrics["compute_graph_reuse_count"], 120)
        self.assertEqual(result.inference_metrics["completion_tokens"], 18)
        self.assertEqual(result.inference_metrics["prompt_eval_tokens_per_second"], 80.0)
        fake_runtime.llama_perf_context_reset.assert_called_once()

    def test_local_loader_passes_tuned_cpu_and_batch_settings(self) -> None:
        with tempfile.NamedTemporaryFile() as model_file:
            fake_runtime = types.ModuleType("llama_cpp")
            fake_runtime.Llama = Mock(return_value=object())
            with patch.dict(sys.modules, {"llama_cpp": fake_runtime}):
                load_local_generator(model_file.name)
            kwargs = fake_runtime.Llama.call_args.kwargs
            self.assertEqual(kwargs["n_threads"], DEFAULT_THREADS)
            self.assertEqual(kwargs["n_batch"], DEFAULT_BATCH_SIZE)
            self.assertEqual(kwargs["n_gpu_layers"], DEFAULT_GPU_LAYERS)

    def test_file_hash_is_reused_until_file_stat_changes(self) -> None:
        _sha256_file_cached.cache_clear()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.bin"
            path.write_bytes(b"first")
            with patch("nl2bash.generation_configuration.sha256_file", wraps=lambda p: __import__("hashlib").sha256(Path(p).read_bytes()).hexdigest()) as digest:
                first = sha256_file_cached(path)
                second = sha256_file_cached(path)
                self.assertEqual(first, second)
                self.assertEqual(digest.call_count, 1)
                path.write_bytes(b"second content is different")
                third = sha256_file_cached(path)
                self.assertNotEqual(first, third)
                self.assertEqual(digest.call_count, 2)
        _sha256_file_cached.cache_clear()


if __name__ == "__main__":
    unittest.main()
