"""Loading and validation for the parallel NL2Bash corpus."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path


class CorpusFormatError(ValueError):
    """Raised when the paired corpus files are malformed or misaligned."""


@dataclass(frozen=True, slots=True)
class CorpusRecord:
    """One natural-language request and its reference Bash command."""

    example_id: str
    request: str
    reference_command: str


@dataclass(frozen=True, slots=True)
class ParallelCorpus:
    """Validated parallel records and source-file checksums."""

    records: tuple[CorpusRecord, ...]
    request_filename: str
    command_filename: str
    request_sha256: str
    command_sha256: str


def _read_utf8_lines(path: Path) -> tuple[bytes, list[str]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CorpusFormatError(f"cannot read corpus file {path}: {exc}") from exc

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CorpusFormatError(
            f"corpus file {path} is not valid UTF-8 at byte {exc.start}"
        ) from exc

    lines = text.split("\n") if text else []
    if lines and lines[-1] == "" and text.endswith("\n"):
        lines.pop()

    # Remove only the carriage return that belongs to a CRLF line ending.
    lines = [line[:-1] if line.endswith("\r") else line for line in lines]
    return raw, lines


def load_parallel_corpus(
    request_path: str | Path,
    command_path: str | Path,
) -> ParallelCorpus:
    """Load two line-aligned UTF-8 files without rewriting their contents.

    Only line terminators are removed. Leading and trailing spaces inside a
    record are preserved. Blank/whitespace-only records and mismatched file
    lengths are rejected rather than silently dropped or realigned.
    """
    request_file = Path(request_path)
    command_file = Path(command_path)

    request_bytes, requests = _read_utf8_lines(request_file)
    command_bytes, commands = _read_utf8_lines(command_file)

    if len(requests) != len(commands):
        raise CorpusFormatError(
            "parallel corpus files have different record counts: "
            f"{request_file} has {len(requests)}, "
            f"{command_file} has {len(commands)}"
        )

    if not requests:
        raise CorpusFormatError("parallel corpus files contain no records")

    records: list[CorpusRecord] = []
    for line_number, (request, command) in enumerate(
        zip(requests, commands), start=1
    ):
        if not request.strip():
            raise CorpusFormatError(
                f"empty natural-language request at line {line_number} "
                f"in {request_file}"
            )
        if not command.strip():
            raise CorpusFormatError(
                f"empty reference command at line {line_number} "
                f"in {command_file}"
            )

        records.append(
            CorpusRecord(
                example_id=f"nl2bash-{line_number:06d}",
                request=request,
                reference_command=command,
            )
        )

    return ParallelCorpus(
        records=tuple(records),
        request_filename=request_file.name,
        command_filename=command_file.name,
        request_sha256=hashlib.sha256(request_bytes).hexdigest(),
        command_sha256=hashlib.sha256(command_bytes).hexdigest(),
    )
