"""Validation and import of human-reviewed intent annotations."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from nl2bash.annotations import (
    ANNOTATION_STATUSES,
    INTENT_LABELS,
    WORKLIST_FIELDS,
    AnnotationError,
    _read_json,
    _read_partition,
    _write_atomic,
    restore_spreadsheet_text,
)

def validate_reviewed_annotations(
    reviewed_csv: str | Path,
    training_file: str | Path,
    dataset_manifest_file: str | Path,
    pilot_manifest_file: str | Path,
    output_jsonl: str | Path,
    output_manifest_file: str | Path,
    *,
    partition_name: str = "train",
) -> dict[str, Any]:
    """Validate a review worklist against one manifested partition.

    The default remains the training partition for backward compatibility.
    Development and test worklists must be generated in blind manual-review
    mode and their exports retain an explicit partition name.
    """
    records, dataset_manifest, partition_sha256 = _read_partition(
        training_file, dataset_manifest_file, partition_name
    )
    dataset_source = dataset_manifest.get("source", {})
    if not isinstance(dataset_source, dict):
        raise AnnotationError("dataset manifest has invalid source metadata")
    dataset_revision = dataset_source.get("revision")
    if not isinstance(dataset_revision, str) or not dataset_revision:
        raise AnnotationError("dataset manifest has no source revision")

    pilot_manifest = _read_json(Path(pilot_manifest_file))
    pilot_source = pilot_manifest.get("source", {})
    if not isinstance(pilot_source, dict):
        raise AnnotationError("pilot manifest has invalid source metadata")
    if pilot_source.get("dataset_revision") != dataset_revision:
        raise AnnotationError("pilot and dataset manifests refer to different source revisions")
    declared_partition = pilot_source.get("partition_name", "train")
    if declared_partition != partition_name:
        raise AnnotationError(
            f"pilot manifest belongs to the {declared_partition} partition, not {partition_name}"
        )
    declared_partition_sha256 = pilot_source.get(
        "partition_sha256",
        pilot_source.get("training_sha256") if partition_name == "train" else None,
    )
    if declared_partition_sha256 != partition_sha256:
        raise AnnotationError(
            f"pilot manifest does not match the current {partition_name} partition"
        )
    pilot_summary = pilot_manifest.get("summary")
    if not isinstance(pilot_summary, dict):
        raise AnnotationError("pilot manifest has no valid summary")
    blind_manual_review = pilot_summary.get("blind_manual_review", False)
    if partition_name in {"dev", "test"} and blind_manual_review is not True:
        raise AnnotationError("development and test annotations require blind manual review")

    expected_metadata = pilot_manifest.get("pilot_example_metadata")
    expected_ids = pilot_manifest.get("pilot_example_ids")
    expected_groups = pilot_manifest.get("pilot_group_ids")
    if (
        not isinstance(expected_metadata, dict)
        or not isinstance(expected_ids, list)
        or not isinstance(expected_groups, list)
    ):
        raise AnnotationError("pilot manifest is missing its example metadata")
    if any(not isinstance(value, str) or not value for value in expected_ids + expected_groups):
        raise AnnotationError("pilot manifest contains invalid example or group IDs")
    if len(expected_ids) != len(set(expected_ids)) or len(expected_groups) != len(set(expected_groups)):
        raise AnnotationError("pilot manifest contains duplicate example or group IDs")
    if len(expected_groups) != len(expected_ids):
        raise AnnotationError("pilot manifest group list does not match its example list")
    if set(expected_metadata) != set(expected_ids):
        raise AnnotationError("pilot manifest metadata does not match its example IDs")

    metadata_groups: set[str] = set()
    for example_id, metadata in expected_metadata.items():
        if not isinstance(metadata, dict):
            raise AnnotationError(f"invalid pilot metadata for {example_id}")
        group_id = metadata.get("group_id")
        suggested = metadata.get("suggested_intent")
        reason = metadata.get("suggestion_reason")
        if not all(isinstance(value, str) for value in (group_id, suggested, reason)):
            raise AnnotationError(f"incomplete pilot metadata for {example_id}")
        if not group_id or not reason:
            raise AnnotationError(f"incomplete pilot metadata for {example_id}")
        if suggested and suggested not in INTENT_LABELS:
            raise AnnotationError(f"invalid suggested intent in pilot metadata for {example_id}")
        if not suggested and not blind_manual_review:
            raise AnnotationError(
                f"empty suggested intent is permitted only for blind manual review: {example_id}"
            )
        metadata_groups.add(group_id)
    if metadata_groups != set(expected_groups):
        raise AnnotationError("pilot manifest group metadata does not match its group IDs")

    records_by_id = {record["example_id"]: record for record in records}
    csv_path = Path(reviewed_csv)
    expected_review_file = pilot_manifest.get("review_file")
    if not isinstance(expected_review_file, str) or Path(expected_review_file).resolve() != csv_path.resolve():
        raise AnnotationError("reviewed CSV path does not match the pilot manifest")
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != WORKLIST_FIELDS:
                raise AnnotationError(
                    "review CSV columns do not match the annotation worklist schema"
                )
            rows = list(reader)
            for line_number, row in enumerate(rows, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise AnnotationError(
                        f"review CSV has missing or extra columns at line {line_number}"
                    )
    except OSError as exc:
        raise AnnotationError(f"cannot read reviewed annotation CSV {csv_path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise AnnotationError(f"reviewed annotation CSV is not valid UTF-8: {exc}") from exc

    if len(rows) != len(expected_ids):
        raise AnnotationError(
            f"review CSV has {len(rows)} rows; pilot manifest expects {len(expected_ids)}"
        )

    seen_ids: set[str] = set()
    seen_groups: set[str] = set()
    confirmed: list[dict[str, str]] = []
    status_counts = {status: 0 for status in ANNOTATION_STATUSES}

    for line_number, row in enumerate(rows, start=2):
        example_id = row.get("example_id", "")
        group_id = row.get("group_id", "")
        if not example_id or example_id not in expected_metadata:
            raise AnnotationError(f"unknown pilot example ID at CSV line {line_number}: {example_id}")
        if example_id in seen_ids:
            raise AnnotationError(f"duplicate pilot example ID at CSV line {line_number}: {example_id}")
        seen_ids.add(example_id)

        expected = expected_metadata[example_id]
        if group_id != expected.get("group_id"):
            raise AnnotationError(f"group ID changed for {example_id}")
        if group_id in seen_groups:
            raise AnnotationError(f"duplicate pilot group ID at CSV line {line_number}: {group_id}")
        seen_groups.add(group_id)

        source = records_by_id.get(example_id)
        if source is None:
            raise AnnotationError(
                f"pilot example {example_id} is not present in the {partition_name} partition"
            )
        for field in ("request", "reference_command"):
            restored = restore_spreadsheet_text(row.get(field, ""))
            if restored != source[field]:
                raise AnnotationError(f"source field {field} was changed for {example_id}")
        if row.get("group_id") != source["group_id"]:
            raise AnnotationError(f"source field group_id was changed for {example_id}")

        if row.get("suggested_intent") != expected.get("suggested_intent"):
            raise AnnotationError(f"suggested label was changed for {example_id}")
        if row.get("suggestion_reason") != expected.get("suggestion_reason"):
            raise AnnotationError(f"suggestion reason was changed for {example_id}")

        status = row.get("review_status", "")
        confirmed_value = row.get("confirmed_intent", "")
        note_value = row.get("reviewer_note", "")
        if not isinstance(status, str) or not isinstance(confirmed_value, str) or not isinstance(note_value, str):
            raise AnnotationError(f"invalid review fields at CSV line {line_number}")
        confirmed_intent = confirmed_value.strip()
        note = note_value.strip()
        if status not in ANNOTATION_STATUSES:
            raise AnnotationError(f"invalid review status at CSV line {line_number}: {status}")
        status_counts[status] += 1

        if status == "confirmed":
            if confirmed_intent not in INTENT_LABELS:
                raise AnnotationError(
                    f"confirmed row {example_id} must contain a valid confirmed_intent"
                )
            if confirmed_intent == "other_or_ambiguous" and not note:
                raise AnnotationError(
                    f"confirmed fallback label for {example_id} requires a reviewer note"
                )
            confirmed.append(
                {
                    "example_id": example_id,
                    "group_id": group_id,
                    "request": source["request"],
                    "reference_command": source["reference_command"],
                    "intent_label": confirmed_intent,
                    "annotation_status": "confirmed",
                    "reviewer_note": note,
                }
            )
        elif confirmed_intent:
            raise AnnotationError(
                f"{status} row {example_id} must not contain confirmed_intent"
            )
        elif status in {"ambiguous", "rejected"} and not note:
            raise AnnotationError(
                f"{status} row {example_id} requires a reviewer note"
            )

    missing_ids = set(expected_ids) - seen_ids
    if missing_ids:
        raise AnnotationError(
            f"review CSV is missing {len(missing_ids)} pilot examples; first missing ID: "
            f"{sorted(missing_ids)[0]}"
        )
    if seen_groups != set(expected_groups):
        raise AnnotationError("review CSV group IDs do not match the pilot manifest")

    output_path = Path(output_jsonl)
    output_manifest_path = Path(output_manifest_file)
    protected_paths = {
        csv_path.resolve(),
        Path(training_file).resolve(),
        Path(dataset_manifest_file).resolve(),
        Path(pilot_manifest_file).resolve(),
    }
    if output_path.resolve() == output_manifest_path.resolve():
        raise AnnotationError("confirmed JSONL and output manifest must use different paths")
    if output_path.resolve() in protected_paths or output_manifest_path.resolve() in protected_paths:
        raise AnnotationError("confirmed outputs must not overwrite source or review files")

    output_manifest_path.unlink(missing_ok=True)
    output_lines = [
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in confirmed
    ]
    output_payload = ("\n".join(output_lines) + "\n").encode("utf-8") if output_lines else b""
    _write_atomic(output_path, output_payload)

    try:
        reviewed_csv_sha256 = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise AnnotationError(f"cannot checksum reviewed annotation CSV {csv_path}: {exc}") from exc

    output_source: dict[str, Any] = {
        "dataset_revision": dataset_revision,
        "partition_name": partition_name,
        "partition_sha256": partition_sha256,
        "dataset_manifest": str(Path(dataset_manifest_file)),
        "partition_file": str(Path(training_file)),
        "pilot_manifest": str(Path(pilot_manifest_file)),
        "reviewed_csv": str(csv_path),
        "reviewed_csv_sha256": reviewed_csv_sha256,
    }
    if partition_name == "train":
        output_source["training_sha256"] = partition_sha256

    output_manifest = {
        "schema_version": 1,
        "dataset": "NL2Bash",
        "source": output_source,
        "summary": {
            "partition_records": len(records),
            "pilot_records": len(rows),
            "confirmed_records": len(confirmed),
            "status_counts": status_counts,
            "blind_manual_review": blind_manual_review,
        },
        "confirmed_output": {
            "file": str(output_path),
            "record_count": len(confirmed),
            "sha256": hashlib.sha256(output_payload).hexdigest(),
        },
        "training_policy": (
            "only rows explicitly marked confirmed are exported; held-out exports must not be used for fitting"
            if partition_name in {"dev", "test"}
            else "only rows explicitly marked confirmed are exported"
        ),
    }
    manifest_payload = (
        json.dumps(output_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    _write_atomic(output_manifest_path, manifest_payload)
    return output_manifest
