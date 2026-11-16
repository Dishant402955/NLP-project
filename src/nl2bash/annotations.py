"""Human-reviewed intent annotation worklists and validation."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import tempfile
from typing import Any


INTENT_LABELS = (
    "file_discovery",
    "text_search_processing",
    "file_directory_management",
    "permissions_ownership",
    "process_job_management",
    "system_information",
    "network_remote_operations",
    "archive_compression",
    "shell_environment_session",
    "other_or_ambiguous",
)

WORKLIST_FIELDS = (
    "example_id",
    "group_id",
    "request",
    "reference_command",
    "suggested_intent",
    "suggestion_reason",
    "confirmed_intent",
    "review_status",
    "reviewer_note",
)

ANNOTATION_STATUSES = ("pending", "confirmed", "ambiguous", "rejected")
SUGGESTION_RULESET = "request-keywords-v1"
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def protect_spreadsheet_text(value: str) -> str:
    """Prefix formula-leading CSV text so spreadsheets treat it as text."""
    formula_after_whitespace = value.lstrip(" \t\r\n")
    if (
        value.startswith("'")
        or value.startswith(_CSV_FORMULA_PREFIXES)
        or formula_after_whitespace.startswith(("=", "+", "-", "@"))
    ):
        return "'" + value
    return value


def restore_spreadsheet_text(value: str) -> str:
    """Reverse the worklist's formula-safe prefix without changing source text."""
    if value.startswith("''"):
        return value[1:]
    if len(value) > 1 and value[0] == "'":
        remainder = value[1:]
        formula_after_whitespace = remainder.lstrip(" \t\r\n")
        if (
            remainder.startswith(_CSV_FORMULA_PREFIXES)
            or formula_after_whitespace.startswith(("=", "+", "-", "@"))
        ):
            return remainder
    return value

# Rules are ordered from the most specific/less frequent categories to the
# broad categories. They inspect request text only; reference commands are
# included for reviewer context but never used to create a label suggestion.
_SUGGESTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "other_or_ambiguous",
        re.compile(
            r"\b(cron(?:tab)?|mysqldump|pg_dump|database (?:backup|dump|restore|query|migration)|"
            r"apt(?:-get)? (?:search|install|remove|update|upgrade|list|purge)|yum (?:search|install|remove|update|list)|"
            r"dnf (?:search|install|remove|update|list)|brew (?:search|install|uninstall|update)|package manager|"
            r"git (?:diff|commit|branch|log|status|checkout|reset|rebase|stash|add|clone|pull|push)|"
            r"docker (?:container|cp|exec|run)|ffmpeg|imagemagick|rpm -|systemctl|useradd|usermod|userdel|"
            r"create (?:a )?user account|add (?:a )?user account|delete (?:a )?user account|change (?:the )?user password)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "permissions_ownership",
        re.compile(
            r"\b(chmod|chown|chgrp)\b|"
            r"\b(?:set|change|add|remove|grant|revoke|modify|give|allow|deny|clear|reset)\b"
            r".{0,60}\b(permission|permissions|ownership|owner|access rights?)\b|"
            r"\b(executable permission|execute permission)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "process_job_management",
        re.compile(
            r"\b(process information|process list|process id|process tree|processes? (?:belonging|using|running|listening)|"
            r"pid\b|cpu usage|kill (?:the )?process|terminate (?:the )?process|signal (?:the )?process|"
            r"job control|foreground process|background process|pstree|top (?:command|to monitor)|"
            r"monitor (?:all )?processes)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "network_remote_operations",
        re.compile(
            r"\b(ssh(?:\s|$)|scp\b|rsync\b|ping (?:the )?(?:host|server|[\w.-]+)|network interface|network configuration|"
            r"remote host|remote server|ip address|dns record|download|upload|port forward(?:ing)?|ssh tunnel|"
            r"via ssh|ssh connection|ssh into|ssh to|connect to (?:a )?(?:host|server)|curl|wget)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_information",
        re.compile(
            r"\b(disk space|filesystem usage|file system usage|free memory|available memory|ram usage|kernel version|"
            r"current kernel|hostname|host name|uptime|mount point|system information|cpu cores|"
            r"processor architecture|operating system version|os version|hardware information|list partitions|"
            r"filesystem type|(?:display|show) (?:the )?(?:current )?kernel(?:'s)? (?:name|version|release|configuration))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "archive_compression",
        re.compile(
            r"\b(archive (?:all|the|a|directory|file)|create .*archive|tar archive|tarball|tar ball|compress(?:ion)?|"
            r"decompress|uncompress|extract (?:the )?(?:archive|tar|zip|compressed)|\.tar(?:\.gz|\.bz2|\.xz)?|"
            r"gzip (?:file|the)|gunzip|bzip2 (?:file|the)|zip file|unzip|cpio archive)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "shell_environment_session",
        re.compile(
            r"\b(alias|history|environment variable|shell variable|export (?:the )?(?:variable|path)|"
            r"source (?:the )?(?:file|script)|shell option|login shell|show (?:the )?(?:current )?working directory|print (?:the )?(?:current )?working directory|"
            r"pwd|change (?:the )?current directory|change directory|shell session)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "text_search_processing",
        re.compile(
            r"\b(search (?:the )?(?:contents?|text|inside)|search for .{1,80}\b(?:in|inside)\b.{0,50}\bfiles?\b|lines? containing|files? containing|replace occurrences of|count (?:the )?(?:number|lines|words)|"
            r"number of lines|sort (?:the )?(?:lines|output|files)|filter out|remove (?:(?:all|leading and trailing|leading|trailing) )?(?:spaces|tabs|characters|prefix|suffix|lines)|replace (?:the )?(?:text|string|pattern|word)|"
            r"extract (?:the )?(?:first|last|column|field)|unique lines?|duplicate lines?|compare (?:the )?files?|"
            r"word count|matching lines?|grep|awk|sed|cut|sort|uniq|wc|head|tail|tr|diff|comm|join|paste)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "file_directory_management",
        re.compile(
            r"\b(copy|move|rename|delete|remove|create|make|touch|link|unlink)\b.{0,60}\b"
            r"(files?|directories|folders|symlinks?|symbolic links?|hard links?|file names?)\b|"
            r"\b(cp|mv|rm|mkdir|rmdir|ln|touch)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "file_discovery",
        re.compile(
            r"\b(find|locate|list|which|whereis|search for)\b.{0,100}\b"
            r"(files?|directories|folders|paths?|symlinks?|symbolic links?|file names?|file extensions?|makefiles?)\b|"
            r"\b(files?|directories|folders) (?:named|ending|matching|with extension)\b|"
            r"\b(?:display|show|list)\b.{0,60}\b(files?|directories|folders)\b",
            re.IGNORECASE,
        ),
    ),
)


class AnnotationError(ValueError):
    """Raised when a worklist or reviewed annotation file is invalid."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AnnotationError(f"cannot read JSON file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AnnotationError(f"invalid JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AnnotationError(f"JSON file must contain an object: {path}")
    return value


def _read_partition(
    partition_file: str | Path,
    dataset_manifest_file: str | Path,
    partition_name: str = "train",
) -> tuple[list[dict[str, str]], dict[str, Any], str]:
    if not isinstance(partition_name, str) or partition_name not in {"train", "dev", "test"}:
        raise ValueError("partition_name must be train, dev, or test")
    source_path = Path(partition_file)
    manifest_path = Path(dataset_manifest_file)
    manifest = _read_json(manifest_path)
    partitions = manifest.get("partitions", {})
    if not isinstance(partitions, dict):
        raise AnnotationError("dataset manifest has no valid partitions object")
    partition = partitions.get(partition_name, {})
    if not isinstance(partition, dict):
        raise AnnotationError(f"dataset manifest has no valid {partition_name} partition entry")
    relative_name = partition.get("file")
    if not isinstance(relative_name, str) or not relative_name:
        raise AnnotationError(f"dataset manifest has no {partition_name} partition filename")
    relative_path = Path(relative_name)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise AnnotationError(f"dataset manifest {partition_name} path must stay inside its directory")
    manifest_root = manifest_path.parent.resolve()
    declared_path = (manifest_root / relative_path).resolve()
    if manifest_root not in declared_path.parents:
        raise AnnotationError(f"dataset manifest {partition_name} path escapes its directory")

    if not declared_path.is_file() or source_path.resolve() != declared_path:
        raise AnnotationError(
            f"partition file must be the {partition_name} partition declared by the dataset manifest"
        )

    try:
        raw = source_path.read_bytes()
    except OSError as exc:
        raise AnnotationError(f"cannot read {partition_name} partition {source_path}: {exc}") from exc

    checksum = hashlib.sha256(raw).hexdigest()
    expected_checksum = partition.get("sha256")
    if not isinstance(expected_checksum, str) or len(expected_checksum) != 64:
        raise AnnotationError(f"dataset manifest has an invalid {partition_name} checksum")
    if checksum != expected_checksum:
        raise AnnotationError(f"{partition_name} partition checksum does not match dataset manifest")

    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise AnnotationError(f"{partition_name} partition is not valid UTF-8 at byte {exc.start}") from exc

    record_count = partition.get("record_count")
    if isinstance(record_count, bool) or not isinstance(record_count, int) or record_count < 0:
        raise AnnotationError(f"dataset manifest has an invalid {partition_name} record count")
    if len(lines) != record_count:
        raise AnnotationError(f"{partition_name} partition record count does not match dataset manifest")

    records: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    request_groups: dict[str, str] = {}
    command_groups: dict[str, str] = {}

    for line_number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AnnotationError(
                f"invalid JSONL record in {partition_name} partition at line {line_number}: {exc}"
            ) from exc
        required = {"example_id", "group_id", "request", "reference_command"}
        if not isinstance(row, dict) or not required.issubset(row):
            raise AnnotationError(
                f"{partition_name} partition line {line_number} is missing required fields"
            )
        if any(not isinstance(row[field], str) or not row[field] for field in required):
            raise AnnotationError(
                f"{partition_name} partition line {line_number} has empty or invalid fields"
            )
        example_id = row["example_id"]
        group_id = row["group_id"]
        if example_id in seen_ids:
            raise AnnotationError(f"duplicate example ID in {partition_name} partition: {example_id}")
        seen_ids.add(example_id)
        for value, registry, label in (
            (row["request"].strip(), request_groups, "request"),
            (row["reference_command"].strip(), command_groups, "reference command"),
        ):
            previous_group = registry.setdefault(value, group_id)
            if previous_group != group_id:
                raise AnnotationError(
                    f"duplicate {label} appears in multiple {partition_name} groups: {example_id}"
                )
        records.append({field: row[field] for field in required})

    return records, manifest, checksum


def _read_training_partition(
    training_file: str | Path,
    dataset_manifest_file: str | Path,
) -> tuple[list[dict[str, str]], dict[str, Any], str]:
    """Backward-compatible reader for the training partition."""
    return _read_partition(training_file, dataset_manifest_file, "train")


def suggest_intent(request: str) -> tuple[str | None, str]:
    """Return a weak suggestion based only on request wording.

    The suggestion is not a ground-truth label. The caller must keep it in a
    separate field and require explicit reviewer confirmation.
    """
    if not isinstance(request, str):
        raise TypeError("request must be a string")
    for label, pattern in _SUGGESTION_RULES:
        match = pattern.search(request)
        if match:
            phrase = " ".join(match.group(0).split())
            return label, f"request-text rule matched: {phrase}"
    return None, "no request-text rule matched; manual classification required"


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def create_annotation_worklist(
    training_file: str | Path,
    dataset_manifest_file: str | Path,
    output_csv: str | Path,
    pilot_manifest_file: str | Path,
    *,
    per_label: int = 50,
    seed: int = 42,
    partition_name: str = "train",
    selection_mode: str | None = None,
) -> dict[str, Any]:
    """Create a suggested training pilot or a blind held-out review worklist.

    suggested_balanced is intended for the training pilot only.
    manual_all_groups selects one original record per duplicate group
    without generating any suggested label.
    """
    if not isinstance(partition_name, str) or partition_name not in {"train", "dev", "test"}:
        raise ValueError("partition_name must be train, dev, or test")
    if isinstance(per_label, bool) or not isinstance(per_label, int) or per_label < 1:
        raise ValueError("per_label must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")

    if selection_mode is None:
        selection_mode = "suggested_balanced" if partition_name == "train" else "manual_all_groups"
    if selection_mode not in {"suggested_balanced", "manual_all_groups"}:
        raise ValueError("selection_mode must be suggested_balanced or manual_all_groups")
    if partition_name != "train" and selection_mode != "manual_all_groups":
        raise ValueError("development and test worklists must use blind manual review")

    records, dataset_manifest, partition_sha256 = _read_partition(
        training_file, dataset_manifest_file, partition_name
    )
    source_revision = dataset_manifest.get("source", {}).get("revision")
    if not isinstance(source_revision, str) or not source_revision:
        raise AnnotationError("dataset manifest has no source revision")

    selected_rows: list[dict[str, str]] = []
    candidate_group_counts: dict[str, int] = {}
    selected_per_label: dict[str, int] = {}
    shortages: dict[str, int] = {}

    if selection_mode == "suggested_balanced":
        candidates: dict[str, list[dict[str, str]]] = {
            label: [] for label in (rule[0] for rule in _SUGGESTION_RULES)
        }
        for record in records:
            label, reason = suggest_intent(record["request"])
            if label is not None:
                candidates[label].append(
                    {**record, "suggested_intent": label, "suggestion_reason": reason}
                )

        rng = random.Random(seed)
        selected_groups: set[str] = set()
        for label, _pattern in _SUGGESTION_RULES:
            label_candidates = candidates[label]
            candidate_group_counts[label] = len({row["group_id"] for row in label_candidates})
            rng.shuffle(label_candidates)
            chosen: list[dict[str, str]] = []
            for row in label_candidates:
                if row["group_id"] in selected_groups:
                    continue
                selected_groups.add(row["group_id"])
                chosen.append(row)
                if len(chosen) == per_label:
                    break
            selected_per_label[label] = len(chosen)
            if len(chosen) < per_label:
                shortages[label] = per_label - len(chosen)
            selected_rows.extend(
                {
                    **{key: row[key] for key in ("example_id", "group_id", "request", "reference_command")},
                    "suggested_intent": label,
                    "suggestion_reason": row["suggestion_reason"],
                }
                for row in chosen
            )
        selection_method = "request_text_heuristics_then_seeded_unique_group_sampling"
        ruleset: str | None = SUGGESTION_RULESET
        requested_per_label: int | None = per_label
    else:
        representative_by_group: dict[str, dict[str, str]] = {}
        for record in records:
            representative_by_group.setdefault(record["group_id"], record)
        selected_groups = set(representative_by_group)
        selected_rows = [
            {
                **record,
                "suggested_intent": "",
                "suggestion_reason": "blind manual review; no heuristic suggestion supplied",
            }
            for record in representative_by_group.values()
        ]
        selection_method = "one_source_record_per_duplicate_group_blind_manual_review"
        ruleset = None
        requested_per_label = None

    rows = [
        {
            **{key: record[key] for key in ("example_id", "group_id", "request", "reference_command")},
            "suggested_intent": record["suggested_intent"],
            "suggestion_reason": record["suggestion_reason"],
            "confirmed_intent": "",
            "review_status": "pending",
            "reviewer_note": "",
        }
        for record in selected_rows
    ]

    output_path = Path(output_csv)
    manifest_path = Path(pilot_manifest_file)
    protected_paths = {
        Path(training_file).resolve(),
        Path(dataset_manifest_file).resolve(),
    }
    if output_path.resolve() == manifest_path.resolve():
        raise AnnotationError("worklist CSV and pilot manifest must use different paths")
    if output_path.resolve() in protected_paths or manifest_path.resolve() in protected_paths:
        raise AnnotationError("annotation outputs must not overwrite the source partition or dataset manifest")

    manifest_path.unlink(missing_ok=True)
    csv_tmp_path: Path | None = None
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as stream:
            csv_tmp_path = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=WORKLIST_FIELDS, lineterminator="\n")
            writer.writeheader()
            safe_rows = [
                {field: protect_spreadsheet_text(row[field]) for field in WORKLIST_FIELDS}
                for row in rows
            ]
            writer.writerows(safe_rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(csv_tmp_path, output_path)
    except OSError as exc:
        if csv_tmp_path is not None:
            csv_tmp_path.unlink(missing_ok=True)
        raise AnnotationError(f"cannot write annotation worklist {output_path}: {exc}") from exc

    source_metadata: dict[str, Any] = {
        "dataset_manifest": str(Path(dataset_manifest_file)),
        "partition_name": partition_name,
        "partition_file": str(Path(training_file)),
        "partition_sha256": partition_sha256,
        "dataset_revision": source_revision,
    }
    if partition_name == "train":
        source_metadata["training_file"] = str(Path(training_file))
        source_metadata["training_sha256"] = partition_sha256

    summary: dict[str, Any] = {
        "partition_records_available": len(records),
        "partition_groups_available": len({row["group_id"] for row in records}),
        "pilot_records": len(rows),
        "unique_duplicate_groups": len(selected_groups),
        "all_review_statuses_pending": True,
        "blind_manual_review": selection_mode == "manual_all_groups",
    }
    if partition_name == "train":
        summary["training_records_available"] = len(records)

    pilot_manifest: dict[str, Any] = {
        "schema_version": 1,
        "dataset": "NL2Bash",
        "source": source_metadata,
        "selection": {
            "method": selection_method,
            "ruleset": ruleset,
            "seed": seed,
            "requested_per_label": requested_per_label,
            "candidate_unique_groups": candidate_group_counts,
            "selected_per_label": selected_per_label,
            "shortages": shortages,
        },
        "summary": summary,
        "review_file": str(output_path),
        "pilot_example_ids": [row["example_id"] for row in rows],
        "pilot_group_ids": [row["group_id"] for row in rows],
        "pilot_example_metadata": {
            row["example_id"]: {
                "group_id": row["group_id"],
                "suggested_intent": row["suggested_intent"],
                "suggestion_reason": row["suggestion_reason"],
            }
            for row in rows
        },
    }
    manifest_payload = (
        json.dumps(pilot_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    _write_atomic(manifest_path, manifest_payload)
    return pilot_manifest
