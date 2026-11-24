"""Development-only comparison of generation with and without NLP context."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import random
from pathlib import Path
import statistics
import time
from typing import Any

from nl2bash.bash_validation import validate_bash_command
from nl2bash.classifier_data import load_confirmed_evaluation_data
from nl2bash.command_generation import CommandGenerationError, PROMPT_VERSION, generate_bash_command
from nl2bash.entity_extraction import extract_entities
from nl2bash.entity_validation import validate_entity_grounding
from nl2bash.evaluation import load_frozen_development_threshold
from nl2bash.intent_prediction import load_intent_classifier, predict_intent


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_partition(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid development JSONL at line {line_number}: {exc}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("example_id"), str):
            raise ValueError(f"development record at line {line_number} has no stable example_id")
        records[value["example_id"]] = value
    return records


def _summarize(items: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    count = len(items)
    exact = sum(item[f"{prefix}_exact_match"] for item in items)
    syntax = sum(item[f"{prefix}_syntax_valid"] for item in items)
    grounded = sum(item[f"{prefix}_constraints_passed"] for item in items)
    unsafe = sum(item[f"{prefix}_high_risk"] for item in items)
    latencies = [item[f"{prefix}_latency_seconds"] for item in items]
    return {
        "example_count": count,
        "generation_success_count": sum(item[f"{prefix}_success"] for item in items),
        "generation_success_rate": sum(item[f"{prefix}_success"] for item in items) / count if count else 0.0,
        "generation_failure_count": sum(not item[f"{prefix}_success"] for item in items),
        "exact_match_count": exact,
        "exact_match_rate": exact / count if count else 0.0,
        "syntax_valid_count": syntax,
        "syntax_valid_rate": syntax / count if count else 0.0,
        "explicit_constraint_pass_count": grounded,
        "explicit_constraint_pass_rate": grounded / count if count else 0.0,
        "high_risk_warning_count": unsafe,
        "mean_latency_seconds": statistics.fmean(latencies) if latencies else 0.0,
        "median_latency_seconds": statistics.median(latencies) if latencies else 0.0,
    }


def evaluate_generation_on_development(
    *,
    model_path: str | Path,
    classifier_model_path: str | Path = "models/intent_classifier.joblib",
    classifier_manifest_path: str | Path = "models/intent_classifier_manifest.json",
    frozen_threshold_path: str | Path = "artifacts/evaluation/frozen_dev_threshold.json",
    annotations_path: str | Path = "data/annotations/dev_confirmed_intents.jsonl",
    annotation_manifest_path: str | Path = "data/annotations/dev_confirmed_intents_manifest.json",
    partition_path: str | Path = "data/processed/nl2bash/dev.jsonl",
    dataset_manifest_path: str | Path = "data/processed/nl2bash/manifest.json",
    sample_size: int = 10,
    seed: int = 20261117,
    output_path: str | Path = "artifacts/evaluation/generation_dev_report.json",
    context_size: int = 4096, threads: int | None = None, batch_size: int = 256,
    gpu_layers: int = 0, max_tokens: int = 256,
) -> dict[str, Any]:
    """Evaluate the two prompt conditions on a seeded, label-stratified dev sample.

    Reference commands are read solely for scoring. They are never included in
    either generation prompt. This function cannot load or evaluate test data.
    """
    if isinstance(sample_size, bool) or not isinstance(sample_size, int) or not 1 <= sample_size <= 40:
        raise ValueError("sample_size must be an integer between 1 and 40")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")

    model_path = Path(model_path)
    classifier_model_path = Path(classifier_model_path)
    classifier_manifest_path = Path(classifier_manifest_path)
    frozen_threshold_path = Path(frozen_threshold_path)
    annotations_path = Path(annotations_path)
    annotation_manifest_path = Path(annotation_manifest_path)
    partition_path = Path(partition_path)
    dataset_manifest_path = Path(dataset_manifest_path)
    output_path = Path(output_path)

    held_out = load_confirmed_evaluation_data(
        annotations_path, annotation_manifest_path, partition_path,
        dataset_manifest_path, partition_name="dev", min_per_label=0,
    )
    classifier = load_intent_classifier(classifier_model_path, classifier_manifest_path)
    _frozen, confidence_threshold, threshold_sha = load_frozen_development_threshold(
        classifier, frozen_threshold_path,
    )
    partition_records = _read_partition(partition_path)
    by_id = {example_id: partition_records[example_id] for example_id in held_out.example_ids
             if example_id in partition_records}
    if len(by_id) != len(held_out.example_ids):
        raise ValueError("development annotations do not resolve to all source partition records")

    # One seeded example per available label first, then fill without replacement.
    rng = random.Random(seed)
    grouped: dict[str, list[str]] = {}
    label_by_id = dict(zip(held_out.example_ids, held_out.labels))
    for example_id, label in label_by_id.items():
        grouped.setdefault(label, []).append(example_id)
    selected: list[str] = []
    available_labels = sorted(grouped)
    if sample_size < len(available_labels):
        chosen_labels = sorted(rng.sample(available_labels, sample_size))
        selected.extend(rng.choice(sorted(grouped[label])) for label in chosen_labels)
        sampling_description = f"one seeded example from each of {sample_size} sampled intent labels"
    else:
        for label in available_labels:
            selected.append(rng.choice(sorted(grouped[label])))
        remainder = [example_id for example_id in held_out.example_ids if example_id not in selected]
        rng.shuffle(remainder)
        selected.extend(remainder[:max(0, sample_size - len(selected))])
        selected = selected[:sample_size]
        sampling_description = "one seeded example per available intent label, then seeded fill without replacement"
    # Seeded shuffle prevents label order from becoming a presentation artifact.
    rng.shuffle(selected)

    from nl2bash.command_generation import DEFAULT_THREADS, load_local_generator
    import os
    generator = load_local_generator(
        model_path, context_size=context_size, threads=threads,
        batch_size=batch_size, gpu_layers=gpu_layers,
    )
    effective_threads = threads if threads is not None else min(DEFAULT_THREADS, os.cpu_count() or 1)
    rows: list[dict[str, Any]] = []
    for example_id in selected:
        record = by_id[example_id]
        request = record["request"]
        reference = record["reference_command"]
        intent = predict_intent(classifier, request, confidence_threshold=confidence_threshold)
        extraction = extract_entities(request)
        row: dict[str, Any] = {
            "example_id": example_id,
            "intent_label": label_by_id[example_id],
            "request": request,
            "reference_command": reference,
        }
        for use_context, prefix in ((False, "request_only"), (True, "nlp_context")):
            started = time.perf_counter()
            try:
                generated = generate_bash_command(
                    request, intent, extraction, generator=generator,
                    max_tokens=max_tokens, include_nlp_context=use_context,
                )
                validation = validate_bash_command(generated.command)
                grounding = validate_entity_grounding(generated.command, extraction)
                row[f"{prefix}_success"] = True
                row[f"{prefix}_command"] = generated.command
                row[f"{prefix}_exact_match"] = generated.command.strip() == reference.strip()
                row[f"{prefix}_syntax_valid"] = validation.syntax_valid
                row[f"{prefix}_constraints_passed"] = not grounding
                row[f"{prefix}_high_risk"] = validation.risk_level == "high"
                row[f"{prefix}_risk_level"] = validation.risk_level
                row[f"{prefix}_constraint_findings"] = [item.message for item in grounding]
                row[f"{prefix}_generation_error"] = None
                row[f"{prefix}_inference_metrics"] = generated.inference_metrics
            except CommandGenerationError as exc:
                row[f"{prefix}_success"] = False
                row[f"{prefix}_command"] = None
                row[f"{prefix}_exact_match"] = False
                row[f"{prefix}_syntax_valid"] = False
                row[f"{prefix}_constraints_passed"] = False
                row[f"{prefix}_high_risk"] = False
                row[f"{prefix}_risk_level"] = "unavailable"
                row[f"{prefix}_constraint_findings"] = []
                row[f"{prefix}_generation_error"] = str(exc)
                row[f"{prefix}_inference_metrics"] = {}
            elapsed = time.perf_counter() - started
            row[f"{prefix}_latency_seconds"] = round(elapsed, 6)
        rows.append(row)

    report = {
        "schema_version": 1,
        "evaluation_type": "development_generation_comparison",
        "test_data_used": False,
        "reference_commands_in_generation_prompts": False,
        "seed": seed,
        "sample_size": len(rows),
        "sampling": sampling_description,
        "development_source": {
            "partition": "dev",
            "partition_sha256": _sha256(partition_path),
            "annotations_sha256": _sha256(annotations_path),
            "annotation_manifest_sha256": _sha256(annotation_manifest_path),
            "dataset_revision": held_out.dataset_revision,
        },
        "classifier": {
            "file": str(classifier_model_path),
            "sha256": _sha256(classifier_model_path),
            "threshold_sha256": threshold_sha,
            "confidence_threshold": confidence_threshold,
        },
        "generator": {
            "model": "Qwen2.5-1.5B-Instruct-Q4_K_M",
            "model_file": str(model_path),
            "model_sha256": _sha256(model_path),
            "prompt_version": PROMPT_VERSION,
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "context_size": context_size,
            "threads": effective_threads,
            "batch_size": batch_size,
            "gpu_layers": gpu_layers,
            "runtime": "llama-cpp-python local inference",
        },
        "conditions": {
            "request_only": "Original request only; no classifier prediction or extracted entities passed to the generator.",
            "nlp_context": "Original request plus frozen intent prediction and deterministic extracted entities/issues.",
        },
        "metrics": {
            "request_only": _summarize(rows, "request_only"),
            "nlp_context": _summarize(rows, "nlp_context"),
        },
        "limitations": [
            "Exact match is a strict textual metric and can penalize semantically equivalent Bash commands.",
            "Syntax validity does not establish semantic correctness or safety.",
            "Explicit-constraint checks cover selected extracted values only and are not a complete semantic verifier.",
            "The sample is a small development-set engineering experiment, not a final test estimate.",
            "No human semantic-accuracy score is claimed.",
        ],
        "examples": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite existing development generation report: {output_path}")
    temp = output_path.with_name(output_path.name + ".tmp")
    temp.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temp.replace(output_path)
    return report
