"""Command-line interface for preparing the NL2Bash dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from nl2bash.corpus import CorpusFormatError, load_parallel_corpus
from nl2bash.dataset_builder import write_dataset_artifacts
from nl2bash.grouping import group_duplicate_records
from nl2bash.splitting import split_duplicate_groups


def _validate_output_location(
    request_path: Path,
    command_path: Path,
    output_dir: Path,
) -> None:
    output = output_dir.resolve()
    for source in (request_path.resolve(), command_path.resolve()):
        source_parent = source.parent
        if (
            source == output
            or output in source.parents
            or source.is_relative_to(output)
            or source_parent in output.parents
        ):
            raise ValueError(
                "output directory must be separate from the raw corpus files"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nl2bash-prepare-dataset",
        description=(
            "Validate the NL2Bash parallel corpus, group duplicate-linked "
            "records, and create deterministic train/dev/test partitions."
        ),
    )
    parser.add_argument("--requests", required=True, type=Path, help="path to all.nl")
    parser.add_argument("--commands", required=True, type=Path, help="path to all.cm")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/nl2bash"),
        help="directory for JSONL partitions and manifest (default: data/processed/nl2bash)",
    )
    parser.add_argument(
        "--source-revision",
        required=True,
        help="upstream NL2Bash Git commit used to obtain the raw files",
    )
    parser.add_argument("--seed", type=int, default=42, help="split random seed (default: 42)")
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        _validate_output_location(args.requests, args.commands, args.output_dir)
        corpus = load_parallel_corpus(args.requests, args.commands)
        groups = group_duplicate_records(corpus.records)
        splits = split_duplicate_groups(
            groups,
            seed=args.seed,
            train_ratio=args.train_ratio,
            dev_ratio=args.dev_ratio,
            test_ratio=args.test_ratio,
        )
        manifest = write_dataset_artifacts(
            corpus,
            groups,
            splits,
            args.output_dir,
            source_revision=args.source_revision,
            seed=args.seed,
            train_ratio=args.train_ratio,
            dev_ratio=args.dev_ratio,
            test_ratio=args.test_ratio,
        )
    except (CorpusFormatError, OSError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    summary = {
        "output_dir": str(args.output_dir),
        "source_records": manifest["summary"]["record_count"],
        "duplicate_groups": manifest["summary"]["duplicate_group_count"],
        "largest_group_size": manifest["summary"]["largest_group_size"],
        "partitions": {
            name: details["record_count"]
            for name, details in manifest["partitions"].items()
        },
        "manifest": str(args.output_dir / "manifest.json"),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
