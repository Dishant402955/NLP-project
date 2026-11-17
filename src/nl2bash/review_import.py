"""Merge a blind human test-review sheet into the canonical test worklist."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from nl2bash.annotations import (
    AnnotationError,
    INTENT_LABELS,
    WORKLIST_FIELDS,
    restore_spreadsheet_text,
)

HUMAN_REVIEW_FIELDS = (
    "example_id",
    "request",
    "confirmed_intent",
    "review_status",
    "reviewer_note",
)
HUMAN_DECISION_FIELDS = ("confirmed_intent", "review_status", "reviewer_note")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path, expected_fields: tuple[str, ...], description: str) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != expected_fields:
                raise AnnotationError(f"{description} columns do not match the expected schema")
            rows = list(reader)
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise AnnotationError(f"{description} contains missing or extra columns")
            return rows
    except OSError as exc:
        raise AnnotationError(f"cannot read {description}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise AnnotationError(f"{description} is not valid UTF-8: {exc}") from exc


def apply_human_test_review(
    human_review_csv: str | Path,
    *,
    worklist_csv: str | Path = "data/annotations/test_review.csv",
    review_manifest: str | Path = "data/annotations/test_human_review_manifest.json",
) -> dict[str, Any]:
    """Merge only the three human decision fields from a blind 375-row worksheet.

    The worksheet contains no reference commands and no AI suggestions. All
    request text and IDs are checked against the canonical test worklist.
    """
    human_path = Path(human_review_csv)
    worklist_path = Path(worklist_csv)
    manifest_path = Path(review_manifest)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AnnotationError(f"cannot read test human-review manifest: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AnnotationError(f"invalid test human-review manifest: {exc}") from exc

    if not isinstance(manifest, dict) or manifest.get("artifact_type") != "blind_test_human_review_worklist":
        raise AnnotationError("unexpected test human-review manifest type")
    if manifest.get("review_file") != str(human_path):
        raise AnnotationError("human review CSV path does not match its manifest")
    if manifest.get("source_worklist") != str(worklist_path):
        raise AnnotationError("canonical test worklist path does not match the review manifest")
    expected_source_sha = manifest.get("source_worklist_sha256")
    if not isinstance(expected_source_sha, str) or _sha256(worklist_path) != expected_source_sha:
        raise AnnotationError("canonical test worklist changed since the human worksheet was created")

    human_rows = _read_csv(human_path, HUMAN_REVIEW_FIELDS, "human test review CSV")
    worklist_rows = _read_csv(worklist_path, WORKLIST_FIELDS, "canonical test worklist")
    expected_count = manifest.get("row_count")
    if expected_count != 375 or len(human_rows) != expected_count or len(worklist_rows) != expected_count:
        raise AnnotationError("expected exactly 375 human review rows matching the canonical test worklist")

    human_by_id: dict[str, dict[str, str]] = {}
    for line_number, row in enumerate(human_rows, start=2):
        example_id = row.get("example_id", "")
        if not example_id or example_id in human_by_id:
            raise AnnotationError(f"missing or duplicate example ID in human review CSV at line {line_number}")
        human_by_id[example_id] = row

    canonical_ids = [row["example_id"] for row in worklist_rows]
    if len(set(canonical_ids)) != expected_count or set(human_by_id) != set(canonical_ids):
        raise AnnotationError("human review example IDs do not exactly match the canonical test worklist")

    confirmed = ambiguous = rejected = pending = 0
    for row in worklist_rows:
        example_id = row["example_id"]
        human = human_by_id[example_id]
        if restore_spreadsheet_text(human.get("request", "")) != restore_spreadsheet_text(row["request"]):
            raise AnnotationError(f"request text was changed for {example_id}")

        status = human.get("review_status", "")
        label = human.get("confirmed_intent", "").strip()
        note = human.get("reviewer_note", "").strip()
        if status == "confirmed":
            if label not in INTENT_LABELS:
                raise AnnotationError(f"confirmed row {example_id} has an invalid taxonomy label")
            if label == "other_or_ambiguous" and not note:
                raise AnnotationError(f"confirmed other_or_ambiguous row {example_id} requires a reviewer note")
            confirmed += 1
        elif status == "ambiguous":
            if label or not note:
                raise AnnotationError(f"ambiguous row {example_id} requires a note and a blank confirmed label")
            ambiguous += 1
        elif status == "rejected":
            if label or not note:
                raise AnnotationError(f"rejected row {example_id} requires a note and a blank confirmed label")
            rejected += 1
        elif status == "pending":
            if label:
                raise AnnotationError(f"pending row {example_id} must have a blank confirmed label")
            pending += 1
        else:
            raise AnnotationError(f"invalid review status for {example_id}: {status}")

        for field in HUMAN_DECISION_FIELDS:
            row[field] = human[field]

    if pending:
        raise AnnotationError(f"human test review is incomplete: {pending} rows remain pending")

    fd, temporary_name = tempfile.mkstemp(
        prefix=worklist_path.name + ".", suffix=".tmp", dir=worklist_path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=WORKLIST_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(worklist_rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, worklist_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise

    return {
        "operation": "apply-test-review",
        "worklist_file": str(worklist_path),
        "rows": len(worklist_rows),
        "confirmed": confirmed,
        "ambiguous": ambiguous,
        "rejected": rejected,
        "pending": pending,
        "ai_suggestions_promoted": 0,
        "worklist_sha256": _sha256(worklist_path),
    }
