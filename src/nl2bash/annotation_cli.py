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
    create_parser.add_argument("--partition", choices=("train", "dev", "test"), default="train")
    create_parser.add_argument(
        "--partition-file",
        "--training-file",
        dest="partition_file",
        type=Path,
        help="partition JSONL file; defaults to the selected partition under data/processed/nl2bash/",
    )
    create_parser.add_argument("--dataset-manifest", type=Path, default=DEFAULT_DATASET_MANIFEST)
    create_parser.add_argument("--output-csv", type=Path)
    create_parser.add_argument("--pilot-manifest", type=Path)
    create_parser.add_argument(
        "--selection-mode",
        choices=("suggested_balanced", "manual_all_groups"),
        help="held-out partitions default to blind manual review",
    )
    create_parser.add_argument("--per-label", type=int, default=50)
    create_parser.add_argument("--seed", type=int, default=42)

    validate_parser = subparsers.add_parser(
        "validate",
        help="validate reviewer decisions and export confirmed labels only",
    )
    validate_parser.add_argument("--reviewed-csv", type=Path)
    validate_parser.add_argument("--partition", choices=("train", "dev", "test"), default="train")
    validate_parser.add_argument(
        "--partition-file",
        "--training-file",
        dest="partition_file",
        type=Path,
        help="partition JSONL file; defaults to the selected partition under data/processed/nl2bash/",
    )
    validate_parser.add_argument("--dataset-manifest", type=Path, default=DEFAULT_DATASET_MANIFEST)
    validate_parser.add_argument("--pilot-manifest", type=Path)
    validate_parser.add_argument("--output-jsonl", type=Path)
    validate_parser.add_argument("--output-manifest", type=Path)

    return parser


def _run_create(args: argparse.Namespace) -> int:
    partition_file = args.partition_file or Path(
        f"data/processed/nl2bash/{args.partition}.jsonl"
    )
    if args.output_csv is None:
        filename = "intent_pilot.csv" if args.partition == "train" else f"{args.partition}_review.csv"
        args.output_csv = DEFAULT_ANNOTATION_DIR / filename
    if args.pilot_manifest is None:
        filename = (
            "intent_pilot_manifest.json"
            if args.partition == "train"
            else f"{args.partition}_review_manifest.json"
        )
        args.pilot_manifest = DEFAULT_ANNOTATION_DIR / filename
    _validate_distinct_paths(
        output_paths=(args.output_csv, args.pilot_manifest),
        input_paths=(partition_file, args.dataset_manifest),
    )
    manifest = create_annotation_worklist(
        partition_file,
        args.dataset_manifest,
        args.output_csv,
        args.pilot_manifest,
        per_label=args.per_label,
        seed=args.seed,
        partition_name=args.partition,
        selection_mode=args.selection_mode,
    )
    result = {
        "operation": "create",
        "review_file": str(args.output_csv),
        "pilot_manifest": str(args.pilot_manifest),
        **manifest["summary"],
        "partition": args.partition,
        "selection_mode": manifest["selection"]["method"],
        "requested_per_label": manifest["selection"]["requested_per_label"],
        "selected_per_label": manifest["selection"]["selected_per_label"],
        "shortages": manifest["selection"]["shortages"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    partition_file = args.partition_file or Path(
        f"data/processed/nl2bash/{args.partition}.jsonl"
    )
    if args.reviewed_csv is None:
        filename = "intent_pilot.csv" if args.partition == "train" else f"{args.partition}_review.csv"
        args.reviewed_csv = DEFAULT_ANNOTATION_DIR / filename
    if args.pilot_manifest is None:
        filename = (
            "intent_pilot_manifest.json"
            if args.partition == "train"
            else f"{args.partition}_review_manifest.json"
        )
        args.pilot_manifest = DEFAULT_ANNOTATION_DIR / filename
    if args.output_jsonl is None:
        filename = (
            "confirmed_intents.jsonl"
            if args.partition == "train"
            else f"{args.partition}_confirmed_intents.jsonl"
        )
        args.output_jsonl = DEFAULT_ANNOTATION_DIR / filename
    if args.output_manifest is None:
        filename = (
            "confirmed_intents_manifest.json"
            if args.partition == "train"
            else f"{args.partition}_confirmed_intents_manifest.json"
        )
        args.output_manifest = DEFAULT_ANNOTATION_DIR / filename
    _validate_distinct_paths(
        output_paths=(args.output_jsonl, args.output_manifest),
        input_paths=(
            args.reviewed_csv,
            partition_file,
            args.dataset_manifest,
            args.pilot_manifest,
        ),
    )
    manifest = validate_reviewed_annotations(
        args.reviewed_csv,
        partition_file,
        args.dataset_manifest,
        args.pilot_manifest,
        args.output_jsonl,
        args.output_manifest,
        partition_name=args.partition,
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
        if args.operation == "create" and args.selection_mode is None:
            args.selection_mode = (
                "suggested_balanced" if args.partition == "train" else "manual_all_groups"
            )
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
