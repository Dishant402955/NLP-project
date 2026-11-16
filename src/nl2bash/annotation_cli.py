"""Command-line interface for intent annotation review workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from nl2bash.annotation_validation import validate_reviewed_annotations
from nl2bash.annotations import AnnotationError, create_annotation_worklist


DEFAULT_TRAINING_FILE = Path("data/processed/nl2bash/train.jsonl")
DEFAULT_DATASET_MANIFEST = Path("data/processed/nl2bash/manifest.json")
DEFAULT_ANNOTATION_DIR = Path("data/annotations")


def _validate_distinct_paths(
    output_paths: Sequence[Path],
    input_paths: Sequence[Path],
) -> None:
    resolved_outputs = [path.resolve() for path in output_paths]
    if len(set(resolved_outputs)) != len(resolved_outputs):
        raise ValueError("annotation output paths must be different")

    protected = {path.resolve() for path in input_paths}
    collisions = protected.intersection(resolved_outputs)
    if collisions:
        collision = sorted(str(path) for path in collisions)[0]
        raise ValueError(f"annotation output must not overwrite an input file: {collision}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nl2bash-annotations",
        description="Create and validate a human-reviewed intent annotation pilot.",
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    create_parser = subparsers.add_parser(
        "create",
        help="create a deterministic training-only annotation worklist",
    )
    create_parser.add_argument("--training-file", type=Path, default=DEFAULT_TRAINING_FILE)
    create_parser.add_argument("--dataset-manifest", type=Path, default=DEFAULT_DATASET_MANIFEST)
    create_parser.add_argument(
        "--output-csv",
        type=Path,
        default=DEFAULT_ANNOTATION_DIR / "intent_pilot.csv",
    )
    create_parser.add_argument(
        "--pilot-manifest",
        type=Path,
        default=DEFAULT_ANNOTATION_DIR / "intent_pilot_manifest.json",
    )
    create_parser.add_argument("--per-label", type=int, default=50)
    create_parser.add_argument("--seed", type=int, default=42)

    validate_parser = subparsers.add_parser(
        "validate",
        help="validate reviewer decisions and export confirmed labels only",
    )
    validate_parser.add_argument(
        "--reviewed-csv",
        type=Path,
        default=DEFAULT_ANNOTATION_DIR / "intent_pilot.csv",
    )
    validate_parser.add_argument("--training-file", type=Path, default=DEFAULT_TRAINING_FILE)
    validate_parser.add_argument("--dataset-manifest", type=Path, default=DEFAULT_DATASET_MANIFEST)
    validate_parser.add_argument(
        "--pilot-manifest",
        type=Path,
        default=DEFAULT_ANNOTATION_DIR / "intent_pilot_manifest.json",
    )
    validate_parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=DEFAULT_ANNOTATION_DIR / "confirmed_intents.jsonl",
    )
    validate_parser.add_argument(
        "--output-manifest",
        type=Path,
        default=DEFAULT_ANNOTATION_DIR / "confirmed_intents_manifest.json",
    )

    return parser


def _run_create(args: argparse.Namespace) -> int:
    _validate_distinct_paths(
        output_paths=(args.output_csv, args.pilot_manifest),
        input_paths=(args.training_file, args.dataset_manifest),
    )
    manifest = create_annotation_worklist(
        args.training_file,
        args.dataset_manifest,
        args.output_csv,
        args.pilot_manifest,
        per_label=args.per_label,
        seed=args.seed,
    )
    result = {
        "operation": "create",
        "review_file": str(args.output_csv),
        "pilot_manifest": str(args.pilot_manifest),
        **manifest["summary"],
        "requested_per_label": manifest["selection"]["requested_per_label"],
        "selected_per_label": manifest["selection"]["selected_per_label"],
        "shortages": manifest["selection"]["shortages"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    _validate_distinct_paths(
        output_paths=(args.output_jsonl, args.output_manifest),
        input_paths=(
            args.reviewed_csv,
            args.training_file,
            args.dataset_manifest,
            args.pilot_manifest,
        ),
    )
    manifest = validate_reviewed_annotations(
        args.reviewed_csv,
        args.training_file,
        args.dataset_manifest,
        args.pilot_manifest,
        args.output_jsonl,
        args.output_manifest,
    )
    result = {
        "operation": "validate",
        "confirmed_file": str(args.output_jsonl),
        "output_manifest": str(args.output_manifest),
        **manifest["summary"],
        "confirmed_sha256": manifest["confirmed_output"]["sha256"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.operation == "create":
            return _run_create(args)
        if args.operation == "validate":
            return _run_validate(args)
        parser.error(f"unsupported operation: {args.operation}")
    except (AnnotationError, OSError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
