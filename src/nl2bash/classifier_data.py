"""Load and validate human-confirmed intent examples for model training."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from nl2bash.annotations import INTENT_LABELS, AnnotationError


@dataclass(frozen=True)
class IntentTrainingData:
    """Validated request text and labels with source provenance."""

    requests: tuple[str, ...]
    labels: tuple[str, ...]
    example_ids: tuple[str, ...]
    group_ids: tuple[str, ...]
    class_counts: dict[str, int]
    dataset_revision: str
    training_partition_sha256: str
    confirmed_annotations_sha256: str
    annotation_manifest_sha256: str
    reviewed_csv_sha256: str


def _read_json_object(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AnnotationError(f"cannot read {description} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AnnotationError(f"invalid JSON in {description} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AnnotationError(f"{description} must contain a JSON object: {path}")
    return value


def _read_bytes(path: Path, description: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AnnotationError(f"cannot read {description} {path}: {exc}") from exc


def _safe_partition_path(manifest_path: Path, relative_name: Any) -> Path:
    if not isinstance(relative_name, str) or not relative_name:
        raise AnnotationError("dataset manifest has no training partition filename")
    relative_path = Path(relative_name)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise AnnotationError("dataset manifest training path must stay inside its directory")
    manifest_root = manifest_path.parent.resolve()
    resolved = (manifest_root / relative_path).resolve()
    if manifest_root not in resolved.parents:
        raise AnnotationError("dataset manifest training path escapes its directory")
    return resolved


def _read_jsonl_records(raw: bytes, description: str) -> list[dict[str, Any]]:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise AnnotationError(f"{description} is not valid UTF-8 at byte {exc.start}") from exc

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AnnotationError(
                f"invalid JSON in {description} at line {line_number}: {exc}"
            ) from exc
        if not isinstance(record, dict):
            raise AnnotationError(f"{description} line {line_number} must be a JSON object")
        records.append(record)
    return records


def load_confirmed_training_data(
    annotations_file: str | Path,
    annotation_manifest_file: str | Path,
    training_file: str | Path,
    dataset_manifest_file: str | Path,
    *,
    min_per_label: int = 2,
) -> IntentTrainingData:
    """Load only confirmed labels that match the manifested training source.

    The function does not infer, repair, or promote labels. Every annotation
    must be present in the confirmed-only export and match its source record.
    """
    if isinstance(min_per_label, bool) or not isinstance(min_per_label, int):
        raise TypeError("min_per_label must be an integer")
    if min_per_label < 1:
        raise ValueError("min_per_label must be at least 1")

    annotations_path = Path(annotations_file)
    annotation_manifest_path = Path(annotation_manifest_file)
    training_path = Path(training_file)
    dataset_manifest_path = Path(dataset_manifest_file)

    annotation_manifest_raw = _read_bytes(annotation_manifest_path, "annotation manifest")
    annotation_manifest = _read_json_object(annotation_manifest_path, "annotation manifest")
    dataset_manifest = _read_json_object(dataset_manifest_path, "dataset manifest")
    if annotation_manifest.get("schema_version") != 1:
        raise AnnotationError("unsupported annotation manifest schema version")
    if dataset_manifest.get("schema_version") != 1:
        raise AnnotationError("unsupported dataset manifest schema version")

    dataset_source = dataset_manifest.get("source")
    partitions = dataset_manifest.get("partitions")
    if not isinstance(dataset_source, dict) or not isinstance(partitions, dict):
        raise AnnotationError("dataset manifest is missing source or partition metadata")
    train_partition = partitions.get("train")
    if not isinstance(train_partition, dict):
        raise AnnotationError("dataset manifest has no valid train partition")

    declared_training_path = _safe_partition_path(
        dataset_manifest_path, train_partition.get("file")
    )
    if training_path.resolve() != declared_training_path or not declared_training_path.is_file():
        raise AnnotationError(
            "training file must be the train partition declared by the dataset manifest"
        )

    training_raw = _read_bytes(training_path, "training partition")
    training_sha256 = hashlib.sha256(training_raw).hexdigest()
    expected_training_sha256 = train_partition.get("sha256")
    if not isinstance(expected_training_sha256, str) or training_sha256 != expected_training_sha256:
        raise AnnotationError("training partition checksum does not match dataset manifest")

    training_count = train_partition.get("record_count")
    if isinstance(training_count, bool) or not isinstance(training_count, int):
        raise AnnotationError("dataset manifest has an invalid training record count")
    training_records = _read_jsonl_records(training_raw, "training partition")
    if len(training_records) != training_count:
        raise AnnotationError("training partition record count does not match dataset manifest")

    training_by_id: dict[str, dict[str, str]] = {}
    for line_number, row in enumerate(training_records, start=1):
        required = ("example_id", "group_id", "request", "reference_command")
        if any(not isinstance(row.get(field), str) or not row[field] for field in required):
            raise AnnotationError(
                f"training partition line {line_number} has missing or invalid source fields"
            )
        example_id = row["example_id"]
        if example_id in training_by_id:
            raise AnnotationError(f"duplicate source example ID: {example_id}")
        training_by_id[example_id] = row

    annotation_source = annotation_manifest.get("source")
    confirmed_output = annotation_manifest.get("confirmed_output")
    if not isinstance(annotation_source, dict) or not isinstance(confirmed_output, dict):
        raise AnnotationError("annotation manifest is missing source or confirmed-output metadata")
    annotation_partition = annotation_source.get("partition_name", "train")
    if annotation_partition != "train":
        raise AnnotationError(
            f"classifier fitting accepts only training annotations, not {annotation_partition} annotations"
        )
    annotation_partition_sha256 = annotation_source.get(
        "partition_sha256", annotation_source.get("training_sha256")
    )
    if annotation_partition_sha256 != training_sha256:
        raise AnnotationError("confirmed annotations refer to a different training partition")
    if annotation_source.get("training_sha256", training_sha256) != training_sha256:
        raise AnnotationError("confirmed annotations refer to a different training partition")
    dataset_revision = dataset_source.get("revision")
    if not isinstance(dataset_revision, str) or not dataset_revision:
        raise AnnotationError("dataset manifest has no source revision")
    if annotation_source.get("dataset_revision") != dataset_revision:
        raise AnnotationError("confirmed annotations refer to a different dataset revision")

    declared_annotations_file = confirmed_output.get("file")
    if not isinstance(declared_annotations_file, str) or not declared_annotations_file:
        raise AnnotationError("annotation manifest has no confirmed-output filename")
    if Path(declared_annotations_file).resolve() != annotations_path.resolve():
        raise AnnotationError("annotation file path does not match its confirmed-output manifest")

    annotations_raw = _read_bytes(annotations_path, "confirmed annotation export")
    annotations_sha256 = hashlib.sha256(annotations_raw).hexdigest()
    if confirmed_output.get("sha256") != annotations_sha256:
        raise AnnotationError("confirmed annotation checksum does not match its manifest")

    annotation_count = confirmed_output.get("record_count")
    if isinstance(annotation_count, bool) or not isinstance(annotation_count, int) or annotation_count < 0:
        raise AnnotationError("annotation manifest has an invalid confirmed record count")
    annotation_records = _read_jsonl_records(annotations_raw, "confirmed annotation export")
    if len(annotation_records) != annotation_count:
        raise AnnotationError("confirmed annotation record count does not match its manifest")
    annotation_summary = annotation_manifest.get("summary")
    if not isinstance(annotation_summary, dict):
        raise AnnotationError("annotation manifest has no valid summary")
    summary_count = annotation_summary.get("confirmed_records")
    if isinstance(summary_count, bool) or not isinstance(summary_count, int) or summary_count != annotation_count:
        raise AnnotationError("annotation manifest summary does not match confirmed record count")
    if not annotation_records:
        raise AnnotationError(
            "no confirmed training annotations are available; complete and validate the annotation pilot first"
        )

    reviewed_csv_path = annotation_source.get("reviewed_csv")
    reviewed_csv_sha256 = annotation_source.get("reviewed_csv_sha256")
    if not isinstance(reviewed_csv_path, str) or not reviewed_csv_path:
        raise AnnotationError("annotation manifest has no reviewed CSV path")
    if not isinstance(reviewed_csv_sha256, str) or len(reviewed_csv_sha256) != 64:
        raise AnnotationError("annotation manifest has an invalid reviewed CSV checksum")
    reviewed_csv_raw = _read_bytes(Path(reviewed_csv_path), "reviewed annotation CSV")
    if hashlib.sha256(reviewed_csv_raw).hexdigest() != reviewed_csv_sha256:
        raise AnnotationError("reviewed annotation CSV checksum does not match its manifest")

    seen_ids: set[str] = set()
    seen_groups: set[str] = set()
    requests: list[str] = []
    labels: list[str] = []
    example_ids: list[str] = []
    group_ids: list[str] = []

    for line_number, row in enumerate(annotation_records, start=1):
        required = (
            "example_id",
            "group_id",
            "request",
            "reference_command",
            "intent_label",
            "annotation_status",
        )
        if any(not isinstance(row.get(field), str) or not row[field] for field in required):
            raise AnnotationError(
                f"confirmed annotation line {line_number} has missing or invalid fields"
            )
        if row["annotation_status"] != "confirmed":
            raise AnnotationError(
                f"annotation {row['example_id']} is not explicitly marked confirmed"
            )
        if row["intent_label"] not in INTENT_LABELS:
            raise AnnotationError(
                f"annotation {row['example_id']} has unknown intent label: {row['intent_label']}"
            )

        example_id = row["example_id"]
        group_id = row["group_id"]
        if example_id in seen_ids:
            raise AnnotationError(f"duplicate confirmed example ID: {example_id}")
        if group_id in seen_groups:
            raise AnnotationError(f"duplicate confirmed duplicate-group ID: {group_id}")
        seen_ids.add(example_id)
        seen_groups.add(group_id)

        source_row = training_by_id.get(example_id)
        if source_row is None:
            raise AnnotationError(
                f"confirmed annotation {example_id} is not in the training partition"
            )
        for field in ("group_id", "request", "reference_command"):
            if row[field] != source_row[field]:
                raise AnnotationError(
                    f"confirmed annotation {example_id} does not match source field {field}"
                )

        requests.append(row["request"])
        labels.append(row["intent_label"])
        example_ids.append(example_id)
        group_ids.append(group_id)

    counts = Counter(labels)
    shortages = {
        label: min_per_label - counts.get(label, 0)
        for label in INTENT_LABELS
        if counts.get(label, 0) < min_per_label
    }
    if shortages:
        detail = ", ".join(
            f"{label}: {counts.get(label, 0)} (need {min_per_label})"
            for label in INTENT_LABELS
            if label in shortages
        )
        raise AnnotationError(
            "confirmed training annotations do not meet the per-label minimum: " + detail
        )

    return IntentTrainingData(
        requests=tuple(requests),
        labels=tuple(labels),
        example_ids=tuple(example_ids),
        group_ids=tuple(group_ids),
        class_counts={label: counts.get(label, 0) for label in INTENT_LABELS},
        dataset_revision=dataset_revision,
        training_partition_sha256=training_sha256,
        confirmed_annotations_sha256=annotations_sha256,
        annotation_manifest_sha256=hashlib.sha256(annotation_manifest_raw).hexdigest(),
        reviewed_csv_sha256=reviewed_csv_sha256,
    )
