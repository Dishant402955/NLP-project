"""Lightweight checks that generated commands retain explicit request constraints."""
from __future__ import annotations

from dataclasses import dataclass
import re

from nl2bash.entity_extraction import EntityExtractionResult


@dataclass(frozen=True, slots=True)
class EntityConstraintFinding:
    code: str
    entity_type: str
    value: str
    message: str


def _contains_extension(command: str, extension: str) -> bool:
    escaped = re.escape(extension)
    return bool(re.search(rf"(?:\\*|[A-Za-z0-9_./-]*){escaped}(?![A-Za-z0-9])", command, re.I))


def _contains_size(
    command: str, value: str, normalized: str | None, comparison: str | None = None,
) -> bool:
    if not normalized:
        return False
    amount = normalized.split()[0]
    # GNU find interprets a bare -size integer as 512-byte blocks. When the
    # extractor has a normalized byte count, require an explicit byte suffix.
    find_size = re.search(r"(?:^|\s)-size\s+([+-]?)(\d+)([cwbkMG]?)\b", command)
    if find_size:
        sign, found_amount, suffix = find_size.groups()
        if found_amount != amount or suffix.lower() != "c":
            return False
        if comparison == "greater_than" and sign != "+":
            return False
        if comparison == "less_than" and sign != "-":
            return False
        if comparison == "equal_to" and sign:
            return False
        if comparison == "greater_than_or_equal" and sign != "+":
            return False
        if comparison == "less_than_or_equal" and sign != "-":
            return False
        return True
    # For other utilities allow the exact integer only when the request itself
    # supplied a unit and the amount is present. This is only a visibility check.
    return bool(re.search(rf"(?<![0-9]){re.escape(amount)}(?![0-9])", command))


def validate_entity_grounding(command: str, extraction: EntityExtractionResult) -> tuple[EntityConstraintFinding, ...]:
    """Flag explicit extracted values that are absent from generated command text.

    This deliberately conservative check catches common dropped constraints;
    it cannot establish semantic equivalence for arbitrary shell programs.
    """
    if not isinstance(command, str) or not isinstance(extraction, EntityExtractionResult):
        raise TypeError("command and extraction must be valid pipeline values")
    findings: list[EntityConstraintFinding] = []
    placeholder_pattern = re.compile(
        r"<\s*(?:pid|process_name|username|database|database_name|path|filename)\s*>"
        r"|\[(?:process_name|pid|username|database_name)\]"
        r"|\b(?:username|database_name|your_database_name|process_name)\b",
        re.I,
    )
    for match in placeholder_pattern.finditer(command):
        findings.append(EntityConstraintFinding(
            "unresolved_placeholder", "placeholder", match.group(0),
            f"The generated command contains an unresolved placeholder ({match.group(0)}); it is not a real value.",
        ))
    entity_types = {item.entity_type for item in extraction.entities}
    if "size" not in entity_types and re.search(r"(?:^|\s)-size(?:\s|$)", command):
        findings.append(EntityConstraintFinding(
            "unsupported_generated_constraint", "size", "-size",
            "The generated command adds a file-size filter that the request did not specify.",
        ))
    if "date_time" not in entity_types and re.search(r"(?:^|\s)-(?:mtime|mmin|ctime|cmin|atime|amin|newermt)(?:\s|$)", command):
        findings.append(EntityConstraintFinding(
            "unsupported_generated_constraint", "date_time", "time-filter",
            "The generated command adds a date/time filter that the request did not specify.",
        ))
    case_requirement = next(
        (item.normalized_value for item in extraction.entities if item.entity_type == "case_sensitivity"),
        None,
    )
    if case_requirement == "sensitive" and re.search(r"(?:^|\s)-(?:iname|ipath)(?:\s|$)|\bgrep\s+[^|]*\s-i(?:\s|$)", command):
        findings.append(EntityConstraintFinding(
            "case_sensitivity_mismatch", "case_sensitivity", "sensitive",
            "The request requires case-sensitive matching, but the generated command uses an ignore-case option.",
        ))
    if case_requirement == "insensitive" and re.search(r"(?:^|\s)-(?:name|path)(?:\s|$)", command) and not re.search(r"(?:^|\s)-(?:iname|ipath)(?:\s|$)", command):
        findings.append(EntityConstraintFinding(
            "case_sensitivity_mismatch", "case_sensitivity", "insensitive",
            "The request requires case-insensitive matching, but the generated find command uses a case-sensitive name/path option.",
        ))

    seen: set[tuple[str, str]] = set()
    for entity in extraction.entities:
        key = (entity.entity_type, entity.value)
        if key in seen:
            continue
        seen.add(key)
        missing = False
        message = ""
        if entity.entity_type == "programming_language" and entity.normalized_value:
            missing = not _contains_extension(command, entity.normalized_value)
            message = f"The request specifies {entity.value} files, but the command does not visibly preserve the {entity.normalized_value} file-type constraint."
        elif entity.entity_type == "file_extension":
            extension = entity.normalized_value or entity.value
            missing = not _contains_extension(command, extension)
            message = f"The request specifies the {extension} extension, but that constraint is absent from the command."
        elif entity.entity_type == "size":
            preceding = [
                item for item in extraction.entities
                if item.entity_type == "comparison_condition"
                and item.end <= entity.start and entity.start - item.end <= 32
            ]
            comparison = preceding[-1].normalized_value if preceding else None
            missing = not _contains_size(command, entity.value, entity.normalized_value, comparison)
            message = f"The requested size constraint ({entity.value}) is missing or its comparison direction is inconsistent with the request."
        elif entity.entity_type == "path":
            missing = entity.value not in command
            message = f"The requested path ({entity.value}) is not visibly represented in the command."
        elif entity.entity_type == "process_metric":
            aliases = {
                "vsz": ("vsz", "vsize", "vprvt"),
                "rss": ("rss", "res", "resident"),
                "%cpu": ("%cpu", "pcpu", "%cpu"),
            }
            missing = not any(alias in command.lower() for alias in aliases.get(entity.normalized_value or "", ()))
            message = f"The requested process metric ({entity.value}) is not visibly represented in the command."
        elif entity.entity_type in {"file_name", "port", "process_name"}:
            missing = entity.value not in command
            message = f"The requested {entity.entity_type.replace('_', ' ')} ({entity.value}) is not visibly represented in the command."
        if missing:
            findings.append(EntityConstraintFinding("entity_constraint_missing", entity.entity_type, entity.value, message))
    return tuple(findings)
