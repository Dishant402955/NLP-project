"""Serialize duplicate-safe dataset partitions and a reproducibility manifest."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

from nl2bash.corpus import ParallelCorpus
from nl2bash.grouping import DuplicateGroup
from nl2bash.splitting import DatasetSplits


SPLIT_ALGORITHM = "seeded_greedy_largest_group_first_normalized_squared_error"


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    lines = [
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in rows
    ]
    return ("\n".join(lines) + "\n").encode("utf-8") if lines else b""


def _write_atomic(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def write_dataset_artifacts(
    corpus: ParallelCorpus,
    groups: Sequence[DuplicateGroup],
    splits: DatasetSplits,
    output_dir: str | Path,
    *,
    source_revision: str,
    seed: int,
    train_ratio: float = 0.8,
    dev_ratio: float = 0.1,
    test_ratio: float = 0.1,
) -> dict[str, Any]:
    """Write train/dev/test JSONL partitions and a checksum manifest.

    Each JSONL record contains its source example ID, original request,
    reference command, and duplicate-group ID. The manifest is written last
    and includes the checksum of every partition file.
    """
    if not isinstance(source_revision, str) or not source_revision.strip():
        raise ValueError("source_revision must be a non-empty string")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")

    ratios = {"train": train_ratio, "dev": dev_ratio, "test": test_ratio}
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in ratios.values()
    ):
        raise TypeError("split ratios must be numeric")
    if any(not math.isfinite(value) or value <= 0 for value in ratios.values()):
        raise ValueError("split ratios must be finite and greater than zero")
    if not math.isclose(sum(ratios.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("split ratios must sum to 1.0")

    group_by_record: dict[str, str] = {}
    source_record_by_id = {record.example_id: record for record in corpus.records}
    if len(source_record_by_id) != len(corpus.records):
        raise ValueError("corpus contains duplicate example IDs")
    request_group_owner: dict[str, str] = {}
    command_group_owner: dict[str, str] = {}
    group_ids: set[str] = set()
    for group in groups:
        if group.group_id in group_ids:
            raise ValueError(f"duplicate group ID: {group.group_id}")
        group_ids.add(group.group_id)
        for record in group.records:
            if record.example_id in group_by_record:
                raise ValueError(f"duplicate example ID: {record.example_id}")
            if source_record_by_id.get(record.example_id) != record:
                raise ValueError(f"group record does not match corpus source: {record.example_id}")
            group_by_record[record.example_id] = group.group_id
            request_key = record.request.strip()
            command_key = record.reference_command.strip()
            previous_group = request_group_owner.setdefault(request_key, group.group_id)
            if previous_group != group.group_id:
                raise ValueError("duplicate request appears in multiple duplicate groups")
            previous_group = command_group_owner.setdefault(command_key, group.group_id)
            if previous_group != group.group_id:
                raise ValueError("duplicate command appears in multiple duplicate groups")

    if set(group_by_record) != set(source_record_by_id):
        raise ValueError("duplicate groups do not cover every corpus record exactly once")

    assignments = dict(splits.group_assignments)
    expected_group_ids = group_ids
    if len(assignments) != len(splits.group_assignments) or set(assignments) != expected_group_ids:
        raise ValueError("split assignments do not match the supplied duplicate groups")
    if set(assignments.values()) - set(ratios):
        raise ValueError("split assignments contain an unknown partition")

    records_by_split = splits.records_by_split()
    seen_record_ids: set[str] = set()
    request_owner: dict[str, str] = {}
    command_owner: dict[str, str] = {}
    partition_rows: dict[str, list[dict[str, str]]] = {}
    partition_group_ids: dict[str, set[str]] = {name: set() for name in ratios}

    for split_name, records in records_by_split.items():
        rows: list[dict[str, str]] = []
        for record in records:
            if source_record_by_id.get(record.example_id) != record:
                raise ValueError(f"split record does not match corpus source: {record.example_id}")
            if record.example_id in seen_record_ids:
                raise ValueError(f"record appears more than once in splits: {record.example_id}")
            seen_record_ids.add(record.example_id)
            group_id = group_by_record.get(record.example_id)
            if group_id is None:
                raise ValueError(f"split contains a record outside supplied groups: {record.example_id}")
            if assignments[group_id] != split_name:
                raise ValueError(f"duplicate group {group_id} is split across partitions")

            request_key = record.request.strip()
            command_key = record.reference_command.strip()
            previous = request_owner.setdefault(request_key, split_name)
            if previous != split_name:
                raise ValueError("duplicate request crosses data partitions")
            previous = command_owner.setdefault(command_key, split_name)
            if previous != split_name:
                raise ValueError("duplicate reference command crosses data partitions")

            partition_group_ids[split_name].add(group_id)
            rows.append(
                {
                    "example_id": record.example_id,
                    "request": record.request,
                    "reference_command": record.reference_command,
                    "group_id": group_id,
                }
            )
        partition_rows[split_name] = rows

    if seen_record_ids != set(group_by_record):
        raise ValueError("split records do not cover every corpus record exactly once")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # The manifest is the completion marker. Remove an older one before
    # replacing partition files so an interrupted rebuild cannot leave a
    # stale manifest describing a mixture of old and new outputs.
    manifest_path = output_path / "manifest.json"
    manifest_path.unlink(missing_ok=True)

    partition_details: dict[str, dict[str, Any]] = {}
    for split_name in ratios:
        payload = _jsonl_bytes(partition_rows[split_name])
        filename = f"{split_name}.jsonl"
        _write_atomic(output_path / filename, payload)
        partition_details[split_name] = {
            "file": filename,
            "record_count": len(partition_rows[split_name]),
            "group_count": len(partition_group_ids[split_name]),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "dataset": "NL2Bash",
        "source": {
            "revision": source_revision.strip(),
            "request_file": {
                "filename": corpus.request_filename,
                "sha256": corpus.request_sha256,
            },
            "command_file": {
                "filename": corpus.command_filename,
                "sha256": corpus.command_sha256,
            },
        },
        "split_configuration": {
            "algorithm": SPLIT_ALGORITHM,
            "seed": seed,
            "ratios": ratios,
        },
        "summary": {
            "record_count": len(group_by_record),
            "duplicate_group_count": len(groups),
            "largest_group_size": max((len(group.records) for group in groups), default=0),
        },
        "partitions": partition_details,
        "leakage_checks": {
            "request_overlap_across_partitions": 0,
            "command_overlap_across_partitions": 0,
        },
    }
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    _write_atomic(manifest_path, manifest_payload)
    return manifest
