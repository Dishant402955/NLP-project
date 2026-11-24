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

from nl2bash.cli import LoadedRuntime, _generate_one, _load_runtime, _run_generate, build_parser
from nl2bash.command_generation import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CONTEXT_SIZE,
    DEFAULT_GPU_LAYERS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_THREADS,
    PROMPT_VERSION,
    _prompt,
    _fast_candidate_covers_request,
    generate_bash_command,
    GeneratedCommand,
    LocalGeneratorRequired,
    load_local_generator,
)
from nl2bash.entity_extraction import extract_entities
from nl2bash.generation_configuration import (
    _has_valid_local_model_integrity_stamp,
    _local_model_integrity_stamp_path,
    _sha256_file_cached,
    _write_local_model_integrity_stamp,
    sha256_file_cached,
)
from nl2bash.intent_prediction import IntentPrediction
from nl2bash.preprocessing import normalize_request


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
                    "content": "find . -type f -name '*.py'",
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
        self.assertEqual(DEFAULT_CONTEXT_SIZE, 1024)
        self.assertEqual(DEFAULT_BATCH_SIZE, 128)
        self.assertEqual(DEFAULT_GPU_LAYERS, 0)
        self.assertEqual(DEFAULT_MAX_TOKENS, 48)
        self.assertEqual(PROMPT_VERSION, "qwen-bash-command-v8")

    def test_prompt_is_compact_and_preserves_critical_filename_rules(self) -> None:
        messages = _prompt(self.request, self.intent, self.extraction)
        joined = "\n".join(message["content"] for message in messages)
        user_content = messages[1]["content"]
        self.assertIn("case-sensitively unless asked otherwise", joined)
        self.assertIn("match *.py", user_content)
        time_request = "Find files modified within the last 24 hours under /tmp."
        time_intent = IntentPrediction(
            request=time_request, intent_label="file_discovery", raw_top_label="file_discovery",
            confidence=0.8, low_confidence=False, confidence_threshold=0.13,
        )
        time_prompt = _prompt(time_request, time_intent, extract_entities(time_request))
        self.assertIn("time filter: -mmin -1440", time_prompt[1]["content"])
        self.assertNotIn("span", user_content)
        self.assertLess(len(joined), 3000)

    def test_generation_uses_reduced_token_budget_and_exposes_usage(self) -> None:
        generator = FakeGenerator()
        request = "Explain which mounted filesystems are active."
        intent = IntentPrediction(
            request=request, intent_label="system_information", raw_top_label="system_information",
            confidence=0.8, low_confidence=False, confidence_threshold=0.13,
        )
        extraction = extract_entities(request)
        result = generate_bash_command(
            request, intent, extraction, generator=generator,
        )
        self.assertEqual(generator.kwargs["max_tokens"], DEFAULT_MAX_TOKENS)
        self.assertEqual(result.command, "find . -type f -name '*.py'")
        self.assertEqual(result.inference_metrics["prompt_tokens"], 80)
        self.assertEqual(result.inference_metrics["completion_tokens"], 18)
        self.assertIn("prompt_build_seconds", result.inference_metrics)
        self.assertIn("model_call_seconds", result.inference_metrics)


    def test_common_requests_use_subsecond_deterministic_templates(self) -> None:
        cases = {
            "Find all Python files in the current directory.": "find . -type f -name '*.py' -print",
            "Find files larger than 10 MB under /var/log.": "find /var/log -type f -size +10000000c -print",
            "Find files modified in the last 24 hours under /tmp.": "find /tmp -type f -mmin -1440 -print",
            "List the processes using the most memory.": "ps -eo pid,comm,rss --sort=-rss | head -n 11",
            "List listening TCP ports.": "ss -ltn",
            "Show disk usage of /home in human-readable format.": "du -sh /home",
            "Create a compressed archive named logs.tar.gz containing all .log files under /var/log.":
                "find /var/log -type f -name '*.log' -print0 | tar -czf logs.tar.gz --null -T -",
            "Count the lines in all Python files recursively under the current directory.":
                "find . -type f -name '*.py' -print0 | xargs -0 wc -l",
            "List directories under /var/log that are larger than 100 MB.":
                "du -B1 --threshold=100000000 /var/log",
            "Report file system containing /example disk usage in kilobytes.": "df -k /example",
            "Print mount point of the file system containing $path.": "df -P \"$path\" | awk 'NR==2 {print $6}'",
            "Gets IP address of 'en0' network interface.": "ip -o -4 addr show dev en0",
            "Gets IP address of only primary network interface.": "ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i==\"src\") print $(i+1)}'",
            "extract \"filename.tar.xz\" with verbose output": "tar -xvf filename.tar.xz",
            "List all functions defined in the shell": "declare -F",
            "Exchanges the top two directories in the dirs stack.": "pushd +1",
            "Find all files that have been modified in the last seven days.": "find . -type f -mmin -10080 -print",
            "Find all Lemon*.mp3 files under current directory and run mplayer with these files":
                "find . -type f -name 'Lemon*.mp3' -exec mplayer {} +",
            "Find all *.c files under and below the current directory that contain \"wait_event_interruptible\"":
                "find . -type f -name '*.c' -exec grep -Hn -- wait_event_interruptible {} +",
            "Archive all filepattern-*2009* files/directories under data/ into 2009.tar":
                "find data/ -name 'filepattern-*2009*' -print0 | tar -cf 2009.tar --null -T -",
            "Change permssions of *.cgi files under directories htdocs and cgi-bin to 755":
                "find htdocs cgi-bin -type f -name '*.cgi' -exec chmod 755 {} +",
            "Find all foo.mp4 files in the current directory tree and print the pathnames of their parent directories":
                "find . -type f -name foo.mp4 -printf '%h\\n' | sort -u",
            "Search the current directory tree for file \"a.txt\"": "find . -type f -name a.txt -print",
            "Search the current directory tree for regular files whose names end in \".shtml\" or \".css\"":
                "find . -type f \\( -name '*.shtml' -o -name '*.css' \\) -print",
            "Calculate the total size of all *.jpg files in the directory tree":
                "find . -type f -name '*.jpg' -printf '%s\\n' | awk '{total += $1} END {printf \"%.0f\\n\", total}'",
            "Find files that are writable by both the \"other\" and the group":
                "find . -type f -perm -0022 -print",
            "Start from current directory, skip the directory src/emacs and print it then skip all files and directories under it, and print the names of the other files found":
                "find . -path ./src/emacs -print -prune -o -print",
            "Find all *.jpg files in */201111/* paths and numerically sort them according to the second field in the file name with a delimiter '_'":
                "find . -type f -path '*/201111/*' -name '*.jpg' -printf '%f\\n' | sort -t '_' -k2,2n",
        }
        for raw, expected in cases.items():
            with self.subTest(request=raw):
                request = normalize_request(raw)
                intent = IntentPrediction(
                    request=request, intent_label="file_discovery", raw_top_label="file_discovery",
                    confidence=0.8, low_confidence=False, confidence_threshold=0.13,
                )
                extraction = extract_entities(request)
                fake = FakeGenerator()
                generated = generate_bash_command(request, intent, extraction, generator=fake)
                self.assertEqual(generated.command, expected)
                self.assertEqual(generated.inference_metrics["generation_path"], "deterministic_template")
                self.assertIsNone(fake.kwargs)

    def test_fast_path_declines_requests_with_unhandled_constraints(self) -> None:
        raw = "Find *.conf files/directories only upto 2 levels down under /etc directory and show a few lines of output from the end"
        request = normalize_request(raw)
        intent = IntentPrediction(
            request=request, intent_label="file_discovery", raw_top_label="file_discovery",
            confidence=0.8, low_confidence=False, confidence_threshold=0.13,
        )
        extraction = extract_entities(request)
        fake = FakeGenerator()
        result = generate_bash_command(request, intent, extraction, generator=fake)
        self.assertEqual(result.command, "find /etc -maxdepth 3 -type f -name '*.conf' -exec tail -n 5 {} +")
        self.assertEqual(result.inference_metrics.get("generation_path"), "deterministic_template")
        self.assertIsNone(fake.kwargs)

        raw = "Compress all directories found in $LOGDIR wherein a file's data has been modified within the last 24 hours"
        request = normalize_request(raw)
        intent = IntentPrediction(
            request=request, intent_label="archive_compression", raw_top_label="archive_compression",
            confidence=0.8, low_confidence=False, confidence_threshold=0.13,
        )
        extraction = extract_entities(request)
        generated = generate_bash_command(request, intent, extraction, generator=FakeGenerator())
        self.assertEqual(generated.inference_metrics.get("generation_path"), "local_llm")


    def test_template_coverage_gate_rejects_known_partial_commands(self) -> None:
        cases = (
            (
                "Append files modified within the last 24 hours to existing logs.tar.",
                "find . -type f -mmin -1440 -print0 | tar -cf logs.tar --null -T -",
            ),
            (
                "Find all Python files in my home directory.",
                "find . -type f -name '*.py' -print",
            ),
            (
                "Find regular files ending in .c or .h.",
                "find . -type f -name '*.h' -print",
            ),
            (
                "Find and convert all .md files under /tmp to HTML.",
                "find /tmp -type f -name '*.md' -print",
            ),
            (
                "Find all .log files under /var/log modified in the last 24 hours.",
                "find . -type f -name '*.log' -print",
            ),
        )
        for request, command in cases:
            with self.subTest(request=request):
                self.assertFalse(
                    _fast_candidate_covers_request(request, extract_entities(request), command, "test_route"),
                )

    def test_incomplete_template_candidate_falls_back_to_local_llm(self) -> None:
        request = normalize_request("Find all Python files in my home directory.")
        intent = IntentPrediction(
            request=request, intent_label="file_discovery", raw_top_label="file_discovery",
            confidence=0.8, low_confidence=False, confidence_threshold=0.13,
        )
        fake = FakeGenerator()
        with patch(
            "nl2bash.command_generation._try_fast_command",
            return_value=("find . -type f -name '*.py' -print", "incorrect_home_path"),
        ):
            result = generate_bash_command(request, intent, extract_entities(request), generator=fake)
        self.assertEqual(result.inference_metrics["generation_path"], "local_llm")
        self.assertIsNotNone(fake.kwargs)

    def test_invalid_token_budget_is_rejected_even_on_deterministic_path(self) -> None:
        with self.assertRaises(ValueError):
            generate_bash_command(
                self.request, self.intent, self.extraction, generator=None, max_tokens=0,
            )

    def test_unsupported_requests_require_the_local_llm_fallback(self) -> None:
        request = normalize_request("Translate Unix cal output to LaTeX table code.")
        intent = IntentPrediction(
            request=request, intent_label="text_processing", raw_top_label="text_processing",
            confidence=0.8, low_confidence=False, confidence_threshold=0.13,
        )
        with self.assertRaises(LocalGeneratorRequired):
            generate_bash_command(request, intent, extract_entities(request), generator=None)

    def test_runtime_setup_does_not_load_the_llm_model(self) -> None:
        args = build_parser().parse_args(["generate", "--interactive"])
        with patch("nl2bash.cli.load_intent_classifier", return_value=object()), \
             patch("nl2bash.cli.load_frozen_development_threshold", return_value=(None, 0.13, "threshold")), \
             patch("nl2bash.cli.verify_frozen_generation_configuration", return_value="config"), \
             patch("nl2bash.cli.load_local_generator") as load_generator:
            runtime = _load_runtime(args)
        self.assertIsNone(runtime.generator)
        self.assertGreaterEqual(runtime.startup_timings["total_startup_seconds"], 0)
        load_generator.assert_not_called()

    def test_common_cli_request_skips_llm_model_loading(self) -> None:
        request = "Find Python files in the current directory."
        intent = IntentPrediction(
            request=request, intent_label="file_discovery", raw_top_label="file_discovery",
            confidence=0.8, low_confidence=False, confidence_threshold=0.13,
        )
        runtime = LoadedRuntime(None, 0.13, "threshold", "config", None, {"total_startup_seconds": 0.01})
        args = build_parser().parse_args(["generate", "--request", request, "--timings"])
        with patch("nl2bash.cli.normalize_request", return_value=request), \
             patch("nl2bash.cli.predict_intent", return_value=intent), \
             patch("nl2bash.cli.extract_entities", return_value=self.extraction), \
             patch("nl2bash.cli.load_local_generator") as load_generator:
            output = _generate_one(request, args, runtime)
        self.assertEqual(output["generation"]["command"], "find . -type f -name '*.py' -print")
        self.assertLess(output["timings"]["request_seconds"]["request_total_seconds"], 0.1)
        load_generator.assert_not_called()

    def test_unmatched_cli_request_loads_llm_once_on_demand(self) -> None:
        request = "Translate Unix cal output to LaTeX table code."
        intent = IntentPrediction(
            request=request, intent_label="text_processing", raw_top_label="text_processing",
            confidence=0.8, low_confidence=False, confidence_threshold=0.13,
        )
        extraction = extract_entities(request)
        runtime = LoadedRuntime(None, 0.13, "threshold", "config", None, {"total_startup_seconds": 0.02})
        args = build_parser().parse_args(["generate", "--request", request, "--timings"])
        result = GeneratedCommand("cal | awk '{print $1}'", "test", (), "test-model", PROMPT_VERSION)
        with patch("nl2bash.cli.normalize_request", return_value=request), \
             patch("nl2bash.cli.predict_intent", return_value=intent), \
             patch("nl2bash.cli.extract_entities", return_value=extraction), \
             patch("nl2bash.cli.load_local_generator", return_value=FakeGenerator()) as load_generator, \
             patch("nl2bash.cli.verify_frozen_generation_configuration", return_value="verified") as verify_model, \
             patch("nl2bash.cli.generate_bash_command", side_effect=[LocalGeneratorRequired("fallback"), result]) as generate:
            output = _generate_one(request, args, runtime)
        load_generator.assert_called_once()
        verify_model.assert_called_once()
        self.assertEqual(generate.call_count, 2)
        self.assertIsNotNone(runtime.generator)
        self.assertEqual(output["generation"]["command"], result.command)
        self.assertGreaterEqual(output["timings"]["startup_seconds"]["llm_model_load_seconds"], 0)

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
        metrics_request = "Explain which mounted filesystems are active."
        metrics_intent = IntentPrediction(
            request=metrics_request, intent_label="system_information", raw_top_label="system_information",
            confidence=0.8, low_confidence=False, confidence_threshold=0.13,
        )
        metrics_extraction = extract_entities(metrics_request)
        with patch.dict(sys.modules, {"llama_cpp": fake_runtime}):
            result = generate_bash_command(
                metrics_request, metrics_intent, metrics_extraction, generator=generator,
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
            self.assertEqual(kwargs["n_threads_batch"], DEFAULT_THREADS)
            self.assertEqual(kwargs["n_batch"], DEFAULT_BATCH_SIZE)
            self.assertEqual(kwargs["n_ubatch"], DEFAULT_BATCH_SIZE)
            self.assertTrue(kwargs["use_mmap"])
            self.assertEqual(kwargs["n_gpu_layers"], DEFAULT_GPU_LAYERS)

    def test_model_integrity_stamp_is_portable_and_invalidates_on_file_change(self) -> None:
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.gguf"
            model.write_bytes(b"same-model-bytes")
            digest = hashlib.sha256(model.read_bytes()).hexdigest()
            _write_local_model_integrity_stamp(model, digest)
            self.assertTrue(_has_valid_local_model_integrity_stamp(model, digest))
            self.assertTrue(_local_model_integrity_stamp_path(model).is_file())

            relocated = Path(directory) / "relocated.gguf"
            relocated.write_bytes(model.read_bytes())
            # Same content on a different inode has no portable local stamp yet.
            self.assertFalse(_has_valid_local_model_integrity_stamp(relocated, digest))
            _write_local_model_integrity_stamp(relocated, digest)
            self.assertTrue(_has_valid_local_model_integrity_stamp(relocated, digest))

            model.write_bytes(b"changed-model-bytes")
            self.assertFalse(_has_valid_local_model_integrity_stamp(model, digest))

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
