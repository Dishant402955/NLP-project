"""Validate owner-reviewed entity annotations and evaluate exact-span extraction."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from nl2bash.annotations import AnnotationError, _read_partition, restore_spreadsheet_text
from nl2bash.entity_evaluation import evaluate_entity_extraction
from nl2bash.entity_extraction import ENTITY_TYPES, ExtractedEntity
from nl2bash.preprocessing import normalize_request


DEFAULT_REVIEW = Path("data/annotations/entity_test_human_review.csv")
DEFAULT_REVIEW_MANIFEST = Path("data/annotations/entity_test_review_manifest.json")
DEFAULT_PARTITION = Path("data/processed/nl2bash/test.jsonl")
DEFAULT_DATASET_MANIFEST = Path("data/processed/nl2bash/manifest.json")
DEFAULT_REPORT = Path("artifacts/evaluation/entity_test_report.json")
DEFAULT_GUARD = Path("artifacts/evaluation/entity_test_evaluation.lock")
REVIEW_FIELDS = (
    "example_id", "group_id", "request", "confirmed_entities_json",
    "review_status", "reviewer_note",
)


class EntityBenchmarkError(RuntimeError):
    """Raised when entity benchmark data or provenance is invalid."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EntityBenchmarkError(f"cannot read {description} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise EntityBenchmarkError(f"invalid JSON in {description} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EntityBenchmarkError(f"{description} must contain a JSON object")
    return value


def _read_review(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != REVIEW_FIELDS:
                raise EntityBenchmarkError("entity review CSV columns do not match the required schema")
            rows = list(reader)
    except OSError as exc:
        raise EntityBenchmarkError(f"cannot read entity review CSV {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise EntityBenchmarkError(f"entity review CSV is not valid UTF-8: {exc}") from exc
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise EntityBenchmarkError("entity review CSV contains missing or extra columns")
    return rows


def _parse_entities(raw: str, request: str, example_id: str) -> tuple[ExtractedEntity, ...]:
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EntityBenchmarkError(f"invalid confirmed_entities_json for {example_id}: {exc}") from exc
    if not isinstance(values, list):
        raise EntityBenchmarkError(f"confirmed_entities_json for {example_id} must be a JSON array")
    entities: list[ExtractedEntity] = []
    seen: set[tuple[str, str, int, int]] = set()
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            raise EntityBenchmarkError(f"entity {index} for {example_id} must be a JSON object")
        required = {"entity_type", "value", "start", "end"}
        if not required.issubset(value):
            raise EntityBenchmarkError(f"entity {index} for {example_id} is missing {sorted(required - value.keys())}")
        entity_type = value["entity_type"]
        if entity_type not in ENTITY_TYPES:
            raise EntityBenchmarkError(f"entity {index} for {example_id} has unsupported type {entity_type!r}")
        try:
            entity = ExtractedEntity(
                entity_type=entity_type,
                value=value["value"],
                start=value["start"],
                end=value["end"],
                normalized_value=value.get("normalized_value"),
            )
        except (TypeError, ValueError) as exc:
            raise EntityBenchmarkError(f"invalid entity {index} for {example_id}: {exc}") from exc
        if entity.end > len(request) or request[entity.start:entity.end] != entity.value:
            raise EntityBenchmarkError(
                f"entity {index} for {example_id} does not exactly match the normalized request span"
            )
        key = (entity.entity_type, entity.value, entity.start, entity.end)
        if key in seen:
            raise EntityBenchmarkError(f"duplicate entity {key} for {example_id}")
        seen.add(key)
        entities.append(entity)
    return tuple(entities)


def evaluate_entity_benchmark(
    *,
    review_csv: str | Path = DEFAULT_REVIEW,
    review_manifest_file: str | Path = DEFAULT_REVIEW_MANIFEST,
    partition_file: str | Path = DEFAULT_PARTITION,
    dataset_manifest_file: str | Path = DEFAULT_DATASET_MANIFEST,
    output_file: str | Path = DEFAULT_REPORT,
    guard_file: str | Path = DEFAULT_GUARD,
) -> dict[str, Any]:
    """Evaluate exact-span entity extraction once on owner-confirmed test rows."""
    review_path = Path(review_csv)
    review_manifest_path = Path(review_manifest_file)
    partition_path = Path(partition_file)
    dataset_manifest_path = Path(dataset_manifest_file)
    output_path = Path(output_file)
    guard_path = Path(guard_file)

    if len({review_path.resolve(), review_manifest_path.resolve(), partition_path.resolve(),
            dataset_manifest_path.resolve(), output_path.resolve(), guard_path.resolve()}) != 6:
        raise EntityBenchmarkError("review, source, report, and guard paths must all be different")
    if output_path.exists() or guard_path.exists():
        raise EntityBenchmarkError("entity test evaluation report or one-time guard already exists")

    review_manifest = _read_json(review_manifest_path, "entity review manifest")
    if review_manifest.get("artifact_type") != "request_only_ai_entity_annotation_suggestions":
        raise EntityBenchmarkError("unexpected entity benchmark manifest type")
    if review_manifest.get("source_partition") != "test":
        raise EntityBenchmarkError("entity test evaluation requires the test partition")
    if review_manifest.get("source_worklist") != "data/annotations/test_review.csv":
        raise EntityBenchmarkError("entity review manifest refers to an unexpected intent test worklist")

    source_worklist_path = Path(review_manifest["source_worklist"])
    expected_worklist_sha = review_manifest.get("source_worklist_sha256")
    if not isinstance(expected_worklist_sha, str) or _sha256(source_worklist_path) != expected_worklist_sha:
        raise EntityBenchmarkError("intent test worklist checksum differs from the entity sample manifest")

    partition_records, dataset_manifest, partition_sha = _read_partition(
        partition_path, dataset_manifest_path, "test"
    )
    expected_partition_sha = review_manifest.get("source_partition_sha256")
    if partition_sha != expected_partition_sha:
        raise EntityBenchmarkError("test partition checksum differs from the entity sample manifest")
    dataset_source = dataset_manifest.get("source", {})
    if not isinstance(dataset_source, dict):
        raise EntityBenchmarkError("dataset manifest has invalid source metadata")

    annotation_provenance = review_manifest.get("annotation_provenance")
    if (
        not isinstance(annotation_provenance, dict)
        or annotation_provenance.get("method")
        != "request-only AI-assisted entity candidates reviewed and approved by project owner"
        or annotation_provenance.get("owner_approved_rows") != review_manifest.get("sample_size")
        or annotation_provenance.get("independent_annotation_claimed") is not False
    ):
        raise EntityBenchmarkError(
            "entity benchmark manifest must record complete AI-assisted owner-review provenance"
        )

    rows = _read_review(review_path)
    sample_size = review_manifest.get("sample_size")
    if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 1:
        raise EntityBenchmarkError("entity benchmark manifest has invalid sample_size")
    if len(rows) != sample_size:
        raise EntityBenchmarkError(f"entity review has {len(rows)} rows; manifest expects {sample_size}")

    source_by_id = {record["example_id"]: record for record in partition_records}
    expected_ids = review_manifest.get("sample_example_ids")
    expected_groups = review_manifest.get("sample_group_ids")
    if not isinstance(expected_ids, list) or not isinstance(expected_groups, list):
        raise EntityBenchmarkError("entity benchmark manifest is missing its sample IDs/groups")
    if len(expected_ids) != sample_size or len(expected_groups) != sample_size:
        raise EntityBenchmarkError("entity sample manifest ID/group counts are inconsistent")
    if len(set(expected_ids)) != sample_size or len(set(expected_groups)) != sample_size:
        raise EntityBenchmarkError("entity sample manifest contains duplicate IDs or groups")

    requests: list[str] = []
    gold_entities: list[tuple[ExtractedEntity, ...]] = []
    seen_ids: set[str] = set()
    seen_groups: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        example_id = row["example_id"]
        group_id = row["group_id"]
        if not example_id or example_id in seen_ids:
            raise EntityBenchmarkError(f"missing or duplicate example ID at review CSV line {line_number}")
        if not group_id or group_id in seen_groups:
            raise EntityBenchmarkError(f"missing or duplicate duplicate-group ID at review CSV line {line_number}")
        seen_ids.add(example_id)
        seen_groups.add(group_id)
        source = source_by_id.get(example_id)
        if source is None:
            raise EntityBenchmarkError(f"entity review example {example_id} is not in the test partition")
        request = restore_spreadsheet_text(row["request"])
        if request != source["request"] or group_id != source["group_id"]:
            raise EntityBenchmarkError(f"entity review source identity mismatch for {example_id}")
        if normalize_request(request) != request:
            raise EntityBenchmarkError(f"request {example_id} is not in normalized form required by span offsets")
        if row["review_status"] != "confirmed":
            raise EntityBenchmarkError(f"entity review row {example_id} is not confirmed")
        if not row["reviewer_note"].strip():
            raise EntityBenchmarkError(f"entity review row {example_id} requires a provenance/review note")
        entities = _parse_entities(row["confirmed_entities_json"], request, example_id)
        requests.append(request)
        gold_entities.append(entities)

    if list(seen_ids) and set(expected_ids) != seen_ids:
        raise EntityBenchmarkError("entity review IDs do not match the sample manifest")
    if set(expected_groups) != seen_groups:
        raise EntityBenchmarkError("entity review duplicate groups do not match the sample manifest")

    report_metrics = evaluate_entity_extraction(requests, gold_entities)
    report = {
        "schema_version": 1,
        "artifact_type": "entity_extraction_test_evaluation",
        "evaluated_once": True,
        "evaluation_policy": "exact_type_value_and_span_match_on_owner_reviewed_ai_assisted_sample",
        "sample_selection": review_manifest.get("selection"),
        "sample_size": sample_size,
        "source": {
            "dataset_revision": dataset_source.get("revision"),
            "partition": "test",
            "partition_sha256": partition_sha,
            "review_csv": str(review_path),
            "review_csv_sha256": _sha256(review_path),
            "review_manifest": str(review_manifest_path),
            "review_manifest_sha256": _sha256(review_manifest_path),
        },
        "annotation_provenance": annotation_provenance,
        "metrics": asdict(report_metrics),
        "limitations": [
            "Entity labels are AI-assisted and owner-approved, not independently adjudicated ground truth.",
            "The sample is targeted for explicit entity cues and is not a prevalence-representative random sample.",
            "Rare entity types may have zero or very small support; per-type results must show support.",
            "No rule changes may be made using the held-out entity sample or its evaluation results.",
        ],
    }

    guard_path.parent.mkdir(parents=True, exist_ok=True)
    guard_path.write_text(json.dumps({
        "schema_version": 1,
        "status": "completed",
        "sample_size": sample_size,
        "review_csv_sha256": report["source"]["review_csv_sha256"],
        "report_sha256": hashlib.sha256(
            (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        ).hexdigest(),
    }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if output_path.exists():
        raise EntityBenchmarkError(f"refusing to overwrite existing entity report: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nl2bash-entity-eval",
        description="Validate owner-reviewed entity annotations and run exact-span evaluation once.",
    )
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--review-manifest", type=Path, default=DEFAULT_REVIEW_MANIFEST)
    parser.add_argument("--partition-file", type=Path, default=DEFAULT_PARTITION)
    parser.add_argument("--dataset-manifest", type=Path, default=DEFAULT_DATASET_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--guard", type=Path, default=DEFAULT_GUARD)
    args = parser.parse_args(argv)
    try:
        report = evaluate_entity_benchmark(
            review_csv=args.review_csv,
            review_manifest_file=args.review_manifest,
            partition_file=args.partition_file,
            dataset_manifest_file=args.dataset_manifest,
            output_file=args.output,
            guard_file=args.guard,
        )
    except (AnnotationError, EntityBenchmarkError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "operation": "entity-test-evaluation",
        "report_file": str(args.output),
        "sample_size": report["sample_size"],
        "metrics": report["metrics"],
    }, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
