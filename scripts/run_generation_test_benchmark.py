#!/usr/bin/env python3
"""Run the frozen NL2Bash generator on every unique held-out test request.

Reference commands are used only for scoring. Generated commands are parsed and
statically checked, never executed. Outputs are versioned and never overwritten.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from importlib.metadata import PackageNotFoundError, version
import math
import os
from pathlib import Path
import platform
import random
import shlex
import statistics
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nl2bash.cli import _generate_one, _load_runtime, build_parser  # noqa: E402
from nl2bash.command_generation import CommandGenerationError, LocalGeneratorRequired, generate_bash_command  # noqa: E402
from nl2bash.entity_extraction import extract_entities  # noqa: E402
from nl2bash.intent_prediction import ModelLoadError, predict_intent  # noqa: E402
from nl2bash.preprocessing import InvalidRequestError, normalize_request  # noqa: E402

VERSION = "generation-test-benchmark-v1"
COLD_PROBE_REQUEST = "Enables shell option 'progcomp'."
TEST_PATH = ROOT / "data/processed/nl2bash/test.jsonl"
DEV_PATH = ROOT / "data/processed/nl2bash/dev.jsonl"
TRAIN_PATH = ROOT / "data/processed/nl2bash/train.jsonl"
MANIFEST_PATH = ROOT / "data/processed/nl2bash/manifest.json"
OUTPUT_DIR = ROOT / "artifacts/evaluation"
REPORT_PATH = OUTPUT_DIR / f"{VERSION}_report.json"
EXAMPLES_PATH = OUTPUT_DIR / f"{VERSION}_examples.jsonl"
REVIEW_PATH = OUTPUT_DIR / f"{VERSION}_semantic_review.csv"
CHECKPOINT_PATH = OUTPUT_DIR / f"{VERSION}_checkpoint.jsonl"


class BenchmarkError(RuntimeError):
    """Raised when the benchmark cannot meet its integrity protocol."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BenchmarkError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise BenchmarkError(f"expected JSON object at {path}:{line_number}")
            rows.append(row)
    return rows


def group_unique_requests(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate repeated prompts while retaining all paired gold commands."""
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        request, reference = row.get("request"), row.get("reference_command")
        if not isinstance(request, str) or not request.strip():
            raise BenchmarkError("test row contains an empty or non-text request")
        if not isinstance(reference, str) or not reference.strip():
            raise BenchmarkError("test row contains an empty or non-text reference command")
        key = request.strip()
        item = grouped.setdefault(key, {"request": key, "example_ids": [], "group_ids": [], "reference_commands": []})
        item["example_ids"].append(str(row.get("example_id", "")))
        item["group_ids"].append(str(row.get("group_id", "")))
        if reference.strip() not in item["reference_commands"]:
            item["reference_commands"].append(reference.strip())
    result = list(grouped.values())
    for index, item in enumerate(result, 1):
        item["benchmark_id"] = f"unique-request-{index:04d}"
        item["example_ids"].sort()
        item["group_ids"] = sorted(set(item["group_ids"]))
        item["reference_commands"].sort()
    return result


def shell_tokens(command: str) -> tuple[str, ...] | None:
    """Tokenize shell words/operators without executing or expanding them."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        return tuple(lexer)
    except ValueError:
        return None


def score_command(command: str | None, references: list[str]) -> dict[str, bool]:
    if not command:
        return {"exact_match": False, "whitespace_normalized_match": False, "shell_token_match": False}
    normalized = " ".join(command.split())
    generated_tokens = shell_tokens(command)
    return {
        "exact_match": command.strip() in references,
        "whitespace_normalized_match": any(normalized == " ".join(ref.split()) for ref in references),
        "shell_token_match": generated_tokens is not None and any(
            generated_tokens == shell_tokens(ref) for ref in references
        ),
    }


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * (p / 100.0)
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def latency_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    ordered = sorted(float(value) for value in values)
    q1, q3 = percentile(ordered, 25) or 0.0, percentile(ordered, 75) or 0.0
    mean, stdev = statistics.fmean(ordered), statistics.pstdev(ordered)
    return {
        "count": len(ordered), "min_seconds": round(ordered[0], 6), "max_seconds": round(ordered[-1], 6),
        "mean_seconds": round(mean, 6), "median_seconds": round(statistics.median(ordered), 6),
        "p90_seconds": round(percentile(ordered, 90) or 0.0, 6),
        "p95_seconds": round(percentile(ordered, 95) or 0.0, 6),
        "p99_seconds": round(percentile(ordered, 99) or 0.0, 6),
        "q1_seconds": round(q1, 6), "q3_seconds": round(q3, 6),
        "interquartile_range_seconds": round(q3 - q1, 6),
        "range_seconds": round(ordered[-1] - ordered[0], 6),
        "population_stddev_seconds": round(stdev, 6),
        "population_variance_seconds_squared": round(statistics.pvariance(ordered), 8),
        "coefficient_of_variation": round(stdev / mean, 6) if mean else 0.0,
    }


def partition_integrity(train: list[dict[str, Any]], dev: list[dict[str, Any]], test: list[dict[str, Any]]) -> dict[str, int]:
    sets = {}
    for name, rows in (("train", train), ("dev", dev), ("test", test)):
        sets[name] = {
            "requests": {str(row["request"]).strip() for row in rows},
            "commands": {str(row["reference_command"]).strip() for row in rows},
        }
    pairs = (("train", "dev"), ("train", "test"), ("dev", "test"))
    return {
        "request_overlap_across_partitions": sum(len(sets[a]["requests"] & sets[b]["requests"]) for a, b in pairs),
        "command_overlap_across_partitions": sum(len(sets[a]["commands"] & sets[b]["commands"]) for a, b in pairs),
    }


def hardware_snapshot() -> dict[str, Any]:
    cpu_model = platform.processor() or None
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    memory_bytes = None
    try:
        memory_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        pass
    packages = {}
    for package in ("numpy", "scikit-learn", "joblib", "llama-cpp-python", "bashlex"):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = None
    return {"platform": platform.platform(), "system": platform.system(), "kernel_release": platform.release(),
            "machine": platform.machine(), "cpu_model": cpu_model, "logical_cpu_count": os.cpu_count(),
            "physical_memory_bytes": memory_bytes, "python_version": sys.version, "packages": packages}


def find_dev_fallback_requests(dev_rows: list[dict[str, Any]], runtime: Any,
                               args: argparse.Namespace, count: int, seed: int) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for row in dev_rows:
        raw = str(row.get("request", "")).strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        try:
            request = normalize_request(raw)
            prediction = predict_intent(runtime.classifier, request, confidence_threshold=runtime.threshold)
            extraction = extract_entities(request)
            generate_bash_command(request, prediction, extraction, generator=None, max_tokens=args.max_tokens)
        except LocalGeneratorRequired:
            candidates.append(raw)
        except (CommandGenerationError, InvalidRequestError, TypeError, ValueError):
            continue
    random.Random(seed).shuffle(candidates)
    if len(candidates) < count:
        raise BenchmarkError(f"need {count} distinct dev-only LLM fallback requests; found {len(candidates)}")
    return candidates[:count]


def cold_process_probe(request: str, index: int) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    command = [sys.executable, "-m", "nl2bash.cli", "generate", "--request", request, "--json", "--timings"]
    started = time.perf_counter()
    process = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    elapsed = time.perf_counter() - started
    try:
        output = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise BenchmarkError(
            f"cold probe {index} did not return JSON (exit={process.returncode}): "
            f"{process.stderr[-1000:]} {process.stdout[-1000:]}"
        ) from exc
    if not isinstance(output, dict) or not isinstance(output.get("generation"), dict):
        raise BenchmarkError(f"cold probe {index} returned an unexpected CLI payload")
    startup = output.get("timings", {}).get("startup_seconds", {})
    request_timings = output.get("timings", {}).get("request_seconds", {})
    return {
        "probe": index, "exit_code": process.returncode, "process_wall_seconds": round(elapsed, 6),
        "startup_timings": startup,
        "request_total_seconds": request_timings.get("request_total_seconds"),
        "model_load_seconds": startup.get("llm_model_load_seconds"),
        "generation_path": output.get("timings", {}).get("llm_inference", {}).get("generation_path"),
        "generation_success": bool(output.get("generation", {}).get("command")),
        "syntax_valid": output.get("validation", {}).get("syntax_valid"),
        "risk_level": output.get("validation", {}).get("risk_level"),
    }


def run_benchmark(*, seed: int = 20261124, warmup_count: int = 5,
                  cold_probe_count: int = 3, resume: bool = False) -> dict[str, Any]:
    run_started_at = datetime.now(timezone.utc).isoformat()
    for path in (REPORT_PATH, EXAMPLES_PATH, REVIEW_PATH):
        if path.exists():
            raise BenchmarkError(f"refusing to overwrite existing benchmark artifact: {path}")
    if CHECKPOINT_PATH.exists() and not resume:
        raise BenchmarkError(f"incomplete checkpoint exists at {CHECKPOINT_PATH}; rerun with --resume")
    if resume and not CHECKPOINT_PATH.exists():
        raise BenchmarkError("--resume requested but no benchmark checkpoint exists")

    test_rows, dev_rows, train_rows = read_jsonl(TEST_PATH), read_jsonl(DEV_PATH), read_jsonl(TRAIN_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_test_sha = manifest["partitions"]["test"]["sha256"]
    actual_test_sha = sha256_file(TEST_PATH)
    raw_request_sha = sha256_file(ROOT / "data/raw/nl2bash/all.nl")
    raw_command_sha = sha256_file(ROOT / "data/raw/nl2bash/all.cm")
    if raw_request_sha != manifest["source"]["request_file"]["sha256"] or raw_command_sha != manifest["source"]["command_file"]["sha256"]:
        raise BenchmarkError("raw source dataset checksums do not match the committed manifest")
    if not (ROOT / "data/raw/nl2bash/LICENSE").is_file():
        raise BenchmarkError("NL2Bash dataset MIT license notice is missing")
    for partition_name, rows in (("train", train_rows), ("dev", dev_rows), ("test", test_rows)):
        if len(rows) != manifest["partitions"][partition_name]["record_count"]:
            raise BenchmarkError(f"{partition_name} row count differs from the dataset manifest")
    if actual_test_sha != expected_test_sha:
        raise BenchmarkError("test partition SHA-256 does not match its committed manifest")
    integrity = partition_integrity(train_rows, dev_rows, test_rows)
    manifest_leakage = manifest.get("leakage_checks", {})
    if integrity["request_overlap_across_partitions"] or integrity["command_overlap_across_partitions"]:
        raise BenchmarkError(f"cross-partition leakage detected: {integrity}")
    if manifest_leakage.get("request_overlap_across_partitions") != 0 or manifest_leakage.get("command_overlap_across_partitions") != 0:
        raise BenchmarkError("dataset manifest does not certify zero cross-partition overlap")

    cases = group_unique_requests(test_rows)
    if len(cases) < 500:
        raise BenchmarkError(f"held-out unique-request test set unexpectedly small: {len(cases)}")
    test_requests = {case["request"] for case in cases}
    dev_requests = {str(row.get("request", "")).strip() for row in dev_rows}
    train_requests = {str(row.get("request", "")).strip() for row in train_rows}
    if test_requests & dev_requests or test_requests & train_requests:
        raise BenchmarkError("a test request appears in train or development data")

    args = build_parser().parse_args(["generate", "--interactive", "--json", "--timings"])
    git_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
    config_sha = sha256_file(ROOT / "artifacts/evaluation/frozen_generation_config.json")
    checkpoint_metadata = {
        "record_type": "metadata", "benchmark_version": VERSION, "git_commit": git_commit,
        "test_partition_sha256": actual_test_sha, "generation_config_sha256": config_sha,
        "seed": seed, "case_count": len(cases),
    }
    completed_by_id: dict[str, dict[str, Any]] = {}
    if resume:
        with CHECKPOINT_PATH.open(encoding="utf-8") as checkpoint_stream:
            first = checkpoint_stream.readline()
            try:
                saved_metadata = json.loads(first)
            except json.JSONDecodeError as exc:
                raise BenchmarkError("benchmark checkpoint header is corrupt") from exc
            if saved_metadata != checkpoint_metadata:
                raise BenchmarkError("checkpoint metadata differs from current code, test data, config, or seed")
            for line_number, line in enumerate(checkpoint_stream, 2):
                try:
                    saved_row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise BenchmarkError(f"checkpoint line {line_number} is corrupt; refuse to skip unknown results") from exc
                if saved_row.get("record_type") != "example" or saved_row.get("benchmark_id") in completed_by_id:
                    raise BenchmarkError(f"checkpoint line {line_number} has an invalid or duplicate record")
                saved_row.pop("record_type", None)
                completed_by_id[saved_row["benchmark_id"]] = saved_row
        if len(completed_by_id) > len(cases):
            raise BenchmarkError("checkpoint contains more rows than the selected benchmark population")

    runtime_started = time.perf_counter()
    runtime = _load_runtime(args)
    runtime_init_wall = time.perf_counter() - runtime_started
    dev_request_set = {str(row.get("request", "")).strip() for row in dev_rows}
    if COLD_PROBE_REQUEST not in dev_request_set:
        raise BenchmarkError("the fixed cold-start probe is no longer present in the development partition")
    dev_candidates = find_dev_fallback_requests(dev_rows, runtime, args, warmup_count + 1, seed)
    # Assert the cold probe still follows the LLM route; otherwise this would
    # stop measuring cold model initialization after a future template change.
    cold_text = normalize_request(COLD_PROBE_REQUEST)
    cold_intent = predict_intent(runtime.classifier, cold_text, confidence_threshold=runtime.threshold)
    cold_entities = extract_entities(cold_text)
    try:
        generate_bash_command(cold_text, cold_intent, cold_entities, generator=None, max_tokens=args.max_tokens)
    except LocalGeneratorRequired:
        pass
    else:
        raise BenchmarkError("fixed cold-start probe unexpectedly matched a deterministic template")
    cold_requests = [COLD_PROBE_REQUEST] * cold_probe_count
    warmup_requests = [request for request in dev_candidates if request != COLD_PROBE_REQUEST][:warmup_count]
    if len(warmup_requests) != warmup_count:
        raise BenchmarkError("could not select enough distinct development-only warm-up requests")
    cold_probes = [cold_process_probe(request, index + 1) for index, request in enumerate(cold_requests)]
    if len(cold_probes) != cold_probe_count or any(not row["generation_success"] or row["generation_path"] != "local_llm" for row in cold_probes):
        raise BenchmarkError("one or more fresh-process cold-start probes failed to complete local LLM generation")

    warmup_rows: list[dict[str, Any]] = []
    for index, request in enumerate(warmup_requests, 1):
        started = time.perf_counter()
        try:
            output = _generate_one(request, args, runtime)
            warmup_rows.append({
                "index": index, "success": True,
                "elapsed_seconds": round(time.perf_counter() - started, 6),
                "generation_path": output.get("timings", {}).get("llm_inference", {}).get("generation_path"),
            })
        except (CommandGenerationError, ModelLoadError, InvalidRequestError, OSError, TypeError, ValueError, RuntimeError) as exc:
            warmup_rows.append({
                "index": index, "success": False,
                "elapsed_seconds": round(time.perf_counter() - started, 6),
                "error": f"{type(exc).__name__}: {exc}",
            })
    if runtime.generator is None or not any(row["success"] for row in warmup_rows):
        raise BenchmarkError("development-only warm-up did not initialize the local model successfully")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not resume:
        with CHECKPOINT_PATH.open("x", encoding="utf-8") as checkpoint_stream:
            checkpoint_stream.write(json.dumps(checkpoint_metadata, sort_keys=True) + "\n")
            checkpoint_stream.flush()
    example_results: list[dict[str, Any]] = []
    with CHECKPOINT_PATH.open("a", encoding="utf-8") as checkpoint_stream:
        for index, case in enumerate(cases, 1):
            if case["benchmark_id"] in completed_by_id:
                example_results.append(completed_by_id[case["benchmark_id"]])
                continue
            request_started = time.perf_counter()
            base = {
                "benchmark_id": case["benchmark_id"], "example_ids": case["example_ids"],
                "group_ids": case["group_ids"], "request": case["request"],
                "reference_commands": case["reference_commands"],
                "reference_command_count": len(case["reference_commands"]),
            }
            try:
                # The reference commands are deliberately not passed to this call.
                output = _generate_one(case["request"], args, runtime)
                command = output["generation"]["command"]
                validation, constraint = output["validation"], output["constraint_check"]
                inference = output.get("timings", {}).get("llm_inference", {})
                scoring = score_command(command, case["reference_commands"])
                row = {
                    **base, "generation_success": True, "generated_command": command, **scoring,
                    "syntax_valid": bool(validation["syntax_valid"]), "risk_level": validation["risk_level"],
                    "review_required": bool(output["review_required"]),
                    "high_risk": validation["risk_level"] == "high",
                    "safety_findings": validation.get("findings", []),
                    "constraint_check_passed": bool(constraint["passed"]),
                    "constraint_findings": constraint.get("findings", []),
                    "predicted_intent": output.get("intent", {}).get("label"),
                    "intent_confidence": output.get("intent", {}).get("confidence"),
                    "generation_path": inference.get("generation_path", "unknown"),
                    "llm_model_call_seconds": inference.get("model_call_seconds"),
                    "prompt_tokens": inference.get("prompt_tokens"),
                    "completion_tokens": inference.get("completion_tokens"),
                    "generation_tokens_per_second": inference.get("generation_tokens_per_second"),
                    "request_pipeline_seconds": output.get("timings", {}).get("request_seconds", {}).get("request_total_seconds"),
                    "generation_total_seconds": output.get("timings", {}).get("request_seconds", {}).get("generation_total_seconds"),
                    "validation_seconds": output.get("timings", {}).get("request_seconds", {}).get("validation_seconds"),
                    "wall_latency_seconds": round(time.perf_counter() - request_started, 6),
                    "generation_error": None, "executed": False,
                }
            except (CommandGenerationError, ModelLoadError, InvalidRequestError, OSError, TypeError, ValueError, RuntimeError) as exc:
                row = {
                    **base, "generation_success": False, "generated_command": None,
                    "exact_match": False, "whitespace_normalized_match": False, "shell_token_match": False,
                    "syntax_valid": False, "risk_level": "unavailable", "review_required": True,
                    "high_risk": False, "safety_findings": [], "constraint_check_passed": False,
                    "constraint_findings": [], "predicted_intent": None, "generation_path": "generation_error",
                    "wall_latency_seconds": round(time.perf_counter() - request_started, 6),
                    "generation_error": f"{type(exc).__name__}: {exc}", "executed": False,
                }
            row["record_type"] = "example"
            checkpoint_stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            checkpoint_stream.flush()
            row.pop("record_type", None)
            example_results.append(row)
            if index % 25 == 0 or index == len(cases):
                print(f"benchmark progress: {index}/{len(cases)} (completed: {len(example_results)})", flush=True)
    total_wall = sum(row["wall_latency_seconds"] for row in example_results)
    with EXAMPLES_PATH.open("x", encoding="utf-8") as stream:
        for row in example_results:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    success_rows = [row for row in example_results if row["generation_success"]]
    all_latencies = [row["wall_latency_seconds"] for row in example_results]
    route_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    intent_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in example_results:
        route_groups[str(row["generation_path"])].append(row)
        intent_groups[str(row.get("predicted_intent") or "unavailable")].append(row)

    route_metrics = {}
    for route, rows in sorted(route_groups.items()):
        route_metrics[route] = {
            "count": len(rows), "generation_success_count": sum(row["generation_success"] for row in rows),
            "exact_match_count": sum(row.get("exact_match", False) for row in rows),
            "exact_match_rate": round(sum(row.get("exact_match", False) for row in rows) / len(rows), 6),
            "syntax_valid_count": sum(row.get("syntax_valid", False) for row in rows),
            "constraint_pass_count": sum(row.get("constraint_check_passed", False) for row in rows),
            "latency": latency_summary([row["wall_latency_seconds"] for row in rows]),
        }
    intent_metrics = {
        label: {
            "count": len(rows),
            "exact_match_rate": round(sum(row.get("exact_match", False) for row in rows) / len(rows), 6),
            "syntax_valid_rate": round(sum(row.get("syntax_valid", False) for row in rows) / len(rows), 6),
        }
        for label, rows in sorted(intent_groups.items())
    }

    exact_count = sum(row.get("exact_match", False) for row in example_results)
    whitespace_count = sum(row.get("whitespace_normalized_match", False) for row in example_results)
    token_count = sum(row.get("shell_token_match", False) for row in example_results)
    syntax_count = sum(row.get("syntax_valid", False) for row in example_results)
    constraint_count = sum(row.get("constraint_check_passed", False) for row in example_results)
    high_risk_rows = [row for row in example_results if row.get("high_risk", False)]
    mismatch_rows = [row for row in example_results if row["generation_success"] and not row.get("shell_token_match", False)]
    generation_failures = [row for row in example_results if not row["generation_success"]]

    review_rows = sorted(mismatch_rows + generation_failures, key=lambda row: row["benchmark_id"])
    with REVIEW_PATH.open("x", encoding="utf-8", newline="") as stream:
        fields = ["benchmark_id", "example_ids", "request", "reference_commands", "generated_command",
                  "exact_match", "whitespace_normalized_match", "shell_token_match", "syntax_valid",
                  "risk_level", "constraint_check_passed", "safety_findings", "constraint_findings",
                  "generation_error", "semantic_correctness_review", "reviewer_notes"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in review_rows:
            writer.writerow({
                "benchmark_id": row["benchmark_id"], "example_ids": ";".join(row["example_ids"]),
                "request": row["request"],
                "reference_commands": json.dumps(row["reference_commands"], ensure_ascii=False),
                "generated_command": row.get("generated_command") or "",
                "exact_match": row.get("exact_match", False),
                "whitespace_normalized_match": row.get("whitespace_normalized_match", False),
                "shell_token_match": row.get("shell_token_match", False),
                "syntax_valid": row.get("syntax_valid", False), "risk_level": row.get("risk_level"),
                "constraint_check_passed": row.get("constraint_check_passed", False),
                "safety_findings": json.dumps(row.get("safety_findings", []), ensure_ascii=False),
                "constraint_findings": json.dumps(row.get("constraint_findings", []), ensure_ascii=False),
                "generation_error": row.get("generation_error") or "",
                "semantic_correctness_review": "", "reviewer_notes": "",
            })

    model_config = json.loads((ROOT / "artifacts/evaluation/frozen_generation_config.json").read_text(encoding="utf-8"))
    examples_sha = sha256_file(EXAMPLES_PATH)
    report = {
        "schema_version": 1, "benchmark_version": VERSION,
        "benchmark_type": "frozen_held_out_generation_correctness_and_latency",
        "started_at_utc": run_started_at,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                                     capture_output=True, check=True).stdout.strip(),
        "dataset": {
            "name": "NL2Bash", "source_revision": manifest["source"]["revision"],
            "source_citation": "Lin et al., LREC 2018, NL2Bash corpus",
            "license": "MIT (data/raw/nl2bash/LICENSE)",
            "raw_record_count": manifest["summary"]["record_count"],
            "test_partition_record_count": len(test_rows), "unique_test_request_count": len(cases),
            "unique_reference_command_count": len({row["reference_command"].strip() for row in test_rows}),
            "test_partition_sha256": actual_test_sha,
            "source_request_sha256": raw_request_sha,
            "source_command_sha256": raw_command_sha,
            "raw_request_file_sha256_verified": raw_request_sha,
            "duplicate_handling": "One generation per distinct natural-language request; all gold commands paired to that exact request are acceptable references.",
            "split": manifest["split_configuration"],
        },
        "integrity_checks": {
            **integrity,
            "manifest_request_overlap_claim": manifest_leakage.get("request_overlap_across_partitions"),
            "manifest_command_overlap_claim": manifest_leakage.get("command_overlap_across_partitions"),
            "test_checksum_matches_manifest": actual_test_sha == expected_test_sha,
            "test_requests_disjoint_from_train_and_dev": True,
            "reference_commands_read_only_for_scoring": True,
            "reference_commands_in_generation_prompts": False,
            "generated_commands_executed": False,
            "model_or_prompt_tuned_on_test_run": False,
        },
        "system": hardware_snapshot(),
        "generator": {
            "model": model_config["model"]["name"], "model_sha256": model_config["model"]["sha256"],
            "model_license": model_config["model"]["license"], "runtime": model_config["runtime"],
            "prompt_version": model_config["prompt"]["version"],
            "generation_config_sha256": sha256_file(ROOT / "artifacts/evaluation/frozen_generation_config.json"),
            "classifier_sha256": sha256_file(ROOT / "models/intent_classifier.joblib"),
            "generation_architecture": "deterministic common-command templates plus local Qwen fallback",
            "offline_inference": True,
        },
        "methodology": {
            "accuracy_population": "All unique requests in the committed held-out test partition; no random sample.",
            "latency_population": "The same unique requests, after development-only model warm-up.",
            "cold_start": "Three fresh CLI processes using the same fixed development-only LLM-fallback request. Process wall time includes Python startup, classifier/config initialization, model loading, generation and validation. OS page-cache state is not forced cold.",
            "warm_up": "Five distinct development-partition LLM-fallback requests; excluded from test metrics.",
            "warm_latency_definition": "In-process wall time around the request pipeline (normalization, intent prediction, entity extraction, generation and static validation); excludes one-time process/model loading and output serialization.",
            "latency_percentiles": "Linear interpolation over sorted latencies; standard deviation and variance are population statistics.",
            "semantic_correctness": "Not automatically claimed. Exact reference and shell-token matches are proxies; non-matching outputs are exported for human review.",
            "safety": "Bash syntax and static risk heuristics only. Commands are never executed; clean static checks do not prove safety.",
            "reproducibility_seed": seed,
        },
        "runtime_measurements": {
            "main_process_runtime_initialization_seconds": round(runtime_init_wall, 6),
            "main_process_startup_timings": runtime.startup_timings,
            "development_warmup": warmup_rows,
            "cold_process_probes": cold_probes,
            "cold_process_wall_latency": latency_summary([row["process_wall_seconds"] for row in cold_probes]),
            "cold_probe_count": len(cold_probes), "warmup_count": len(warmup_rows),
            "warm_test_wall_latency": latency_summary(all_latencies),
            "test_loop_wall_seconds": round(total_wall, 6),
            "resumed_from_checkpoint": resume,
            "checkpoint_completed_before_this_run": len(completed_by_id),
            "test_requests_per_second": round(len(example_results) / total_wall, 4) if total_wall else None,
            "requests_under_5_seconds": sum(value < 5.0 for value in all_latencies),
            "under_5_seconds_rate": round(sum(value < 5.0 for value in all_latencies) / len(all_latencies), 6) if all_latencies else 0.0,
        },
        "correctness": {
            "request_count": len(example_results),
            "generation_success_count": len(success_rows), "generation_failure_count": len(generation_failures),
            "generation_success_rate": round(len(success_rows) / len(example_results), 6),
            "strict_reference_exact_match_count": exact_count,
            "strict_reference_exact_match_rate": round(exact_count / len(example_results), 6),
            "whitespace_normalized_match_count": whitespace_count,
            "whitespace_normalized_match_rate": round(whitespace_count / len(example_results), 6),
            "shell_token_match_count": token_count,
            "shell_token_match_rate": round(token_count / len(example_results), 6),
            "bash_syntax_valid_count": syntax_count,
            "bash_syntax_valid_rate": round(syntax_count / len(example_results), 6),
            "explicit_entity_constraint_pass_count": constraint_count,
            "explicit_entity_constraint_pass_rate": round(constraint_count / len(example_results), 6),
            "review_required_count": sum(row.get("review_required", True) for row in example_results),
            "high_risk_static_flag_count": len(high_risk_rows),
            "generation_error_count": len(generation_failures),
            "token_budget_or_truncation_error_count": sum(
                "token" in str(row.get("generation_error", "")).lower() for row in generation_failures
            ),
            "non_matching_generated_output_count": len(mismatch_rows),
            "human_semantic_review_status": "pending; accompanying CSV contains all non-matching outputs",
            "route_metrics": route_metrics, "predicted_intent_metrics": intent_metrics,
        },
        "latency": {
            "warm_end_to_end_wall_seconds": latency_summary(all_latencies),
            "warm_request_pipeline_seconds": latency_summary([
                float(row["request_pipeline_seconds"]) for row in success_rows
                if row.get("request_pipeline_seconds") is not None
            ]),
            "llm_model_call_seconds": latency_summary([
                float(row["llm_model_call_seconds"]) for row in success_rows
                if row.get("llm_model_call_seconds") is not None
            ]),
            "cold_fresh_process_seconds": latency_summary([row["process_wall_seconds"] for row in cold_probes]),
        },
        "artifacts": {
            "per_example_jsonl": str(EXAMPLES_PATH.relative_to(ROOT)),
            "per_example_jsonl_sha256": examples_sha,
            "semantic_review_csv": str(REVIEW_PATH.relative_to(ROOT)),
            "semantic_review_row_count": len(review_rows),
            "report_json": str(REPORT_PATH.relative_to(ROOT)),
        },
        "limitations": [
            "The benchmark covers the NL2Bash one-line command domain, not arbitrary Bash scripts.",
            "The 1,261 source rows contain repeated prompts; results count 879 unique prompts once, accepting all paired references per exact prompt.",
            "Exact match penalizes semantically equivalent commands; shell-token match is a lexical proxy, not semantic equivalence.",
            "Entity-constraint checks cover only values detected by project extraction rules, not complete intent correctness.",
            "Syntax validity does not prove a command accomplishes the task or is safe to execute.",
            "Human semantic review is pending for every generated output with no shell-token reference match.",
            "Fresh-process cold probes do not force the OS file cache cold.",
            "Latency applies to this Intel i3-1005G1, CPU-only host and local Q4_K_M model; other machines will differ.",
        ],
    }
    temporary = REPORT_PATH.with_suffix(REPORT_PATH.suffix + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    temporary.replace(REPORT_PATH)
    CHECKPOINT_PATH.unlink(missing_ok=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261124)
    parser.add_argument("--warmup-count", type=int, default=5)
    parser.add_argument("--cold-probe-count", type=int, default=3)
    parser.add_argument("--resume", action="store_true", help="continue a checkpointed interrupted run")
    args = parser.parse_args()
    if args.warmup_count < 1 or args.cold_probe_count < 1:
        parser.error("warm-up and cold-probe counts must be at least one")
    try:
        report = run_benchmark(seed=args.seed, warmup_count=args.warmup_count,
                               cold_probe_count=args.cold_probe_count, resume=args.resume)
    except (BenchmarkError, CommandGenerationError, ModelLoadError, OSError, ValueError, RuntimeError) as exc:
        print(f"benchmark error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "report": str(REPORT_PATH.relative_to(ROOT)),
        "examples": str(EXAMPLES_PATH.relative_to(ROOT)),
        "semantic_review": str(REVIEW_PATH.relative_to(ROOT)),
        "dataset_records": report["dataset"]["test_partition_record_count"],
        "unique_requests": report["dataset"]["unique_test_request_count"],
        "correctness": report["correctness"], "latency": report["latency"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
