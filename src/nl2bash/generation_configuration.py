"""Checksum-bound freeze and verification for the final generation setup."""
from __future__ import annotations

import hashlib
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from nl2bash.command_generation import (
    DEFAULT_BATCH_SIZE, DEFAULT_CONTEXT_SIZE, DEFAULT_GPU_LAYERS, DEFAULT_MAX_TOKENS,
    DEFAULT_THREADS, PROMPT_VERSION,
)

COMPONENT_FILES = (
    "src/nl2bash/bash_validation.py",
    "src/nl2bash/command_generation.py",
    "src/nl2bash/entity_extraction.py",
    "src/nl2bash/entity_validation.py",
    "src/nl2bash/cli.py",
    "src/nl2bash/generation_configuration.py",
    "src/nl2bash/generation_evaluation.py",
    "pyproject.toml",
    "uv.lock",
)


class GenerationConfigurationError(RuntimeError):
    """Raised when a frozen generation configuration is missing or changed."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=128)
def _sha256_file_cached(path: str, size: int, mtime_ns: int, ctime_ns: int, inode: int) -> str:
    # A stable file is hashed once per process. The stat tuple invalidates the
    # cache when its identity, size, or timestamps change.
    return sha256_file(path)


def sha256_file_cached(path: str | Path) -> str:
    selected = Path(path).expanduser().resolve()
    stat = selected.stat()
    return _sha256_file_cached(
        str(selected), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino,
    )



def _model_file_identity(path: str | Path) -> dict[str, int]:
    stat = Path(path).stat()
    return {
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": stat.st_ctime_ns,
        "inode": stat.st_ino,
    }


def _local_model_integrity_stamp_path(model_path: str | Path) -> Path:
    selected = Path(model_path).expanduser().resolve()
    return selected.with_name(selected.name + ".nl2bash-integrity.json")


def _write_local_model_integrity_stamp(model_path: str | Path, model_sha256: str) -> None:
    """Cache a successful full model hash against this machine's file identity."""
    selected = Path(model_path).expanduser().resolve()
    stamp_path = _local_model_integrity_stamp_path(selected)
    stamp = {
        "schema_version": 1,
        "model_path": str(selected),
        "model_sha256": model_sha256,
        "file_identity": _model_file_identity(selected),
    }
    temporary = stamp_path.with_name(stamp_path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(stamp, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(stamp_path)
    except OSError:
        # The stamp is only a speed optimization; a failed write must not undo
        # the successful full SHA-256 verification that just took place.
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _has_valid_local_model_integrity_stamp(model_path: str | Path, expected_sha256: str) -> bool:
    """Return true only when this local file still matches a previously hashed identity."""
    selected = Path(model_path).expanduser().resolve()
    stamp_path = _local_model_integrity_stamp_path(selected)
    try:
        stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
        return (
            isinstance(stamp, dict)
            and stamp.get("schema_version") == 1
            and stamp.get("model_path") == str(selected)
            and stamp.get("model_sha256") == expected_sha256
            and stamp.get("file_identity") == _model_file_identity(selected)
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False

def freeze_generation_configuration(
    *, model_path: str | Path,
    development_report_path: str | Path,
    classifier_model_path: str | Path = "models/intent_classifier.joblib",
    classifier_manifest_path: str | Path = "models/intent_classifier_manifest.json",
    frozen_threshold_path: str | Path = "artifacts/evaluation/frozen_dev_threshold.json",
    output_path: str | Path = "artifacts/evaluation/frozen_generation_config.json",
    context_size: int = 1024, threads: int = DEFAULT_THREADS, batch_size: int = DEFAULT_BATCH_SIZE,
    gpu_layers: int = DEFAULT_GPU_LAYERS, max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict[str, Any]:
    """Create a configuration manifest after the development experiment is reviewed."""
    model_path = Path(model_path)
    development_report_path = Path(development_report_path)
    classifier_model_path = Path(classifier_model_path)
    classifier_manifest_path = Path(classifier_manifest_path)
    frozen_threshold_path = Path(frozen_threshold_path)
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite frozen generation configuration: {output_path}")
    report = json.loads(development_report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("evaluation_type") != "development_generation_comparison":
        raise GenerationConfigurationError("development report has an unexpected evaluation type")
    if report.get("test_data_used") is not False or report.get("reference_commands_in_generation_prompts") is not False:
        raise GenerationConfigurationError("development report does not satisfy the test-isolation protocol")
    generator = report.get("generator")
    if not isinstance(generator, dict) or generator.get("prompt_version") != PROMPT_VERSION:
        raise GenerationConfigurationError("development report does not use the current prompt version")
    model_sha = sha256_file(model_path)
    if generator.get("model_sha256") != model_sha:
        raise GenerationConfigurationError("development report model checksum differs from the supplied model")
    _write_local_model_integrity_stamp(model_path, model_sha)
    try:
        runtime = __import__("llama_cpp")
        runtime_version = runtime.__version__
    except (ImportError, AttributeError) as exc:
        raise GenerationConfigurationError("llama-cpp-python is unavailable or has no version metadata") from exc

    components = {}
    for relative in COMPONENT_FILES:
        components[relative] = sha256_file(relative)
    threshold = json.loads(frozen_threshold_path.read_text(encoding="utf-8"))
    manifest = {
        "schema_version": 1,
        "artifact_type": "frozen_nl2bash_generation_configuration",
        "frozen": True,
        "model": {
            "name": "Qwen2.5-1.5B-Instruct-Q4_K_M",
            "format": "GGUF",
            "default_path": "~/.cache/nl2bash/models/qwen2.5-1.5b-instruct-q4_k_m.gguf",
            "sha256": model_sha,
            "source_revision": "91cad51170dc346986eccefdc2dd33a9da36ead9",
            "license": "Apache-2.0",
        },
        "runtime": {
            "name": "llama-cpp-python",
            "version": runtime_version,
            "device": "GPU-offload" if gpu_layers else "CPU",
            "context_size": context_size,
            "threads": threads,
            "batch_size": batch_size,
            "gpu_layers": gpu_layers,
            "temperature": 0.0,
            "top_p": 0.9,
            "seed": 42,
            "max_tokens": max_tokens,
        },
        "prompt": {
            "version": PROMPT_VERSION,
            "source_file": "src/nl2bash/command_generation.py",
            "sha256": components["src/nl2bash/command_generation.py"],
        },
        "classifier": {
            "file": str(classifier_model_path),
            "sha256": sha256_file(classifier_model_path),
            "manifest_file": str(classifier_manifest_path),
            "manifest_sha256": sha256_file(classifier_manifest_path),
        },
        "frozen_intent_threshold": {
            "file": str(frozen_threshold_path),
            "sha256": sha256_file(frozen_threshold_path),
            "value": threshold.get("threshold"),
        },
        "validation_and_pipeline_components": components,
        "development_evidence": {
            "report_file": str(development_report_path),
            "report_sha256": sha256_file(development_report_path),
            "sample_size": report.get("sample_size"),
            "test_data_used": False,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return manifest


def verify_frozen_generation_configuration(
    config_path: str | Path,
    *,
    model_path: str | Path,
    classifier_model_path: str | Path,
    classifier_manifest_path: str | Path,
    frozen_threshold_path: str | Path,
    context_size: int = DEFAULT_CONTEXT_SIZE,
    threads: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    gpu_layers: int = DEFAULT_GPU_LAYERS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    verify_model_hash: bool = True,
) -> str:
    """Fail closed if the model, prompt, dependencies, threshold, or validators drift.

    A portable frozen SHA-256 identifies the model across machines. After a full
    verification, a local sidecar caches that successful hash against the current
    file identity (size, mtime, ctime, inode). Normal CLI startup checks the sidecar;
    a missing/stale sidecar triggers a full hash once and is then refreshed.
    """
    config_path = Path(config_path)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GenerationConfigurationError(f"cannot read frozen generation configuration: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GenerationConfigurationError(f"invalid frozen generation configuration JSON: {exc}") from exc
    if not isinstance(config, dict) or config.get("schema_version") != 1 or config.get("frozen") is not True:
        raise GenerationConfigurationError("generation configuration is not a supported frozen artifact")
    if config.get("artifact_type") != "frozen_nl2bash_generation_configuration":
        raise GenerationConfigurationError("unexpected generation configuration artifact type")

    model = config.get("model", {})
    model_path = Path(model_path)
    try:
        model_path.stat()
    except OSError as exc:
        raise GenerationConfigurationError(f"cannot stat local language-model file: {exc}") from exc
    expected_model_sha256 = model.get("sha256")
    if not isinstance(expected_model_sha256, str) or len(expected_model_sha256) != 64:
        raise GenerationConfigurationError("frozen configuration has no valid local model SHA-256")
    if verify_model_hash or not _has_valid_local_model_integrity_stamp(model_path, expected_model_sha256):
        actual_model_sha256 = sha256_file_cached(model_path)
        if expected_model_sha256 != actual_model_sha256:
            raise GenerationConfigurationError("local language-model file does not match the frozen configuration")
        _write_local_model_integrity_stamp(model_path, actual_model_sha256)
    classifier = config.get("classifier", {})
    if classifier.get("sha256") != sha256_file_cached(classifier_model_path):
        raise GenerationConfigurationError("intent classifier does not match the frozen generation configuration")
    if classifier.get("manifest_sha256") != sha256_file_cached(classifier_manifest_path):
        raise GenerationConfigurationError("intent classifier manifest does not match the frozen generation configuration")
    threshold = config.get("frozen_intent_threshold", {})
    if threshold.get("sha256") != sha256_file_cached(frozen_threshold_path):
        raise GenerationConfigurationError("frozen intent threshold does not match the generation configuration")

    prompt = config.get("prompt", {})
    components = config.get("validation_and_pipeline_components", {})
    if prompt.get("version") != PROMPT_VERSION:
        raise GenerationConfigurationError("generation prompt version differs from the frozen configuration")
    for relative in COMPONENT_FILES:
        expected = components.get(relative)
        if not isinstance(expected, str) or expected != sha256_file_cached(relative):
            raise GenerationConfigurationError(f"frozen component changed since configuration freeze: {relative}")
    try:
        import llama_cpp
    except ImportError as exc:
        raise GenerationConfigurationError("llama-cpp-python is not installed") from exc
    runtime = config.get("runtime", {})
    if runtime.get("version") != llama_cpp.__version__:
        raise GenerationConfigurationError("llama-cpp-python version differs from the frozen configuration")
    import os
    effective_threads = threads if threads is not None else min(DEFAULT_THREADS, os.cpu_count() or 1)
    if runtime.get("context_size") != context_size:
        raise GenerationConfigurationError("context size differs from the frozen generation configuration")
    if runtime.get("threads") != effective_threads:
        raise GenerationConfigurationError("CPU thread count differs from the frozen generation configuration")
    if runtime.get("batch_size") != batch_size:
        raise GenerationConfigurationError("batch size differs from the frozen generation configuration")
    if runtime.get("gpu_layers") != gpu_layers:
        raise GenerationConfigurationError("GPU layer setting differs from the frozen generation configuration")
    if runtime.get("max_tokens") != max_tokens:
        raise GenerationConfigurationError("maximum generation tokens differ from the frozen configuration")
    return sha256_file_cached(config_path)
