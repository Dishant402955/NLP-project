"""Command-line interface for training and predicting intent categories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from nl2bash.annotations import AnnotationError
from nl2bash.classifier_data import (
    load_confirmed_evaluation_data,
    load_confirmed_training_data,
)
from nl2bash.evaluation import (
    DEFAULT_MINIMUM_COVERAGE,
    EvaluationError,
    evaluate_test_once,
    load_frozen_development_threshold,
    select_development_threshold,
)
from nl2bash.intent_classifier import (
    ClassifierConfig,
    ClassifierTrainingError,
    train_intent_classifier,
)
from nl2bash.intent_prediction import (
    ModelLoadError,
    PredictionError,
    load_intent_classifier,
    predict_intent,
)


DEFAULT_ANNOTATIONS_FILE = Path("data/annotations/confirmed_intents.jsonl")
DEFAULT_ANNOTATION_MANIFEST = Path("data/annotations/confirmed_intents_manifest.json")
DEFAULT_TRAINING_FILE = Path("data/processed/nl2bash/train.jsonl")
DEFAULT_DATASET_MANIFEST = Path("data/processed/nl2bash/manifest.json")
DEFAULT_MODEL_DIR = Path("models")
DEFAULT_MODEL_FILE = DEFAULT_MODEL_DIR / "intent_classifier.joblib"
DEFAULT_MODEL_MANIFEST = DEFAULT_MODEL_DIR / "intent_classifier_manifest.json"


def _validate_paths(
    output_paths: Sequence[Path],
    input_paths: Sequence[Path],
) -> None:
    outputs = [path.resolve() for path in output_paths]
    if len(set(outputs)) != len(outputs):
        raise ValueError("output paths must be different")
    protected = {path.resolve() for path in input_paths}
    collisions = protected.intersection(outputs)
    if collisions:
        collision = sorted(str(path) for path in collisions)[0]
        raise ValueError(f"output must not overwrite an input file: {collision}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nl2bash-classifier",
        description="Train and use the TF-IDF intent-classification baseline.",
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    train_parser = subparsers.add_parser(
        "train",
        help="fit the classifier using explicitly confirmed training annotations",
    )
    train_parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS_FILE)
    train_parser.add_argument(
        "--annotation-manifest",
        type=Path,
        default=DEFAULT_ANNOTATION_MANIFEST,
    )
    train_parser.add_argument("--training-file", type=Path, default=DEFAULT_TRAINING_FILE)
    train_parser.add_argument("--dataset-manifest", type=Path, default=DEFAULT_DATASET_MANIFEST)
    train_parser.add_argument("--model-file", type=Path, default=DEFAULT_MODEL_FILE)
    train_parser.add_argument("--model-manifest", type=Path, default=DEFAULT_MODEL_MANIFEST)
    train_parser.add_argument("--min-per-label", type=int, default=2)

    predict_parser = subparsers.add_parser(
        "predict",
        help="predict the intent of one natural-language request",
    )
    predict_parser.add_argument("--request", required=True)
    predict_parser.add_argument("--model-file", type=Path, default=DEFAULT_MODEL_FILE)
    predict_parser.add_argument(
        "--model-manifest",
        type=Path,
        default=DEFAULT_MODEL_MANIFEST,
    )
    prediction_threshold = predict_parser.add_mutually_exclusive_group()
    prediction_threshold.add_argument("--confidence-threshold", type=float)
    prediction_threshold.add_argument(
        "--frozen-threshold",
        type=Path,
        help="use a threshold selected and frozen using confirmed development labels",
    )

    dev_parser = subparsers.add_parser(
        "select-threshold",
        help="select and freeze the confidence threshold using confirmed development labels",
    )
    dev_parser.add_argument("--annotations", type=Path, default=Path("data/annotations/dev_confirmed_intents.jsonl"))
    dev_parser.add_argument("--annotation-manifest", type=Path, default=Path("data/annotations/dev_confirmed_intents_manifest.json"))
    dev_parser.add_argument("--partition-file", type=Path, default=Path("data/processed/nl2bash/dev.jsonl"))
    dev_parser.add_argument("--dataset-manifest", type=Path, default=DEFAULT_DATASET_MANIFEST)
    dev_parser.add_argument("--model-file", type=Path, default=DEFAULT_MODEL_FILE)
    dev_parser.add_argument("--model-manifest", type=Path, default=DEFAULT_MODEL_MANIFEST)
    dev_parser.add_argument("--output", type=Path, default=Path("artifacts/evaluation/frozen_dev_threshold.json"))
    dev_parser.add_argument("--minimum-coverage", type=float, default=DEFAULT_MINIMUM_COVERAGE)
    dev_parser.add_argument("--min-per-label", type=int, default=0)

    test_parser = subparsers.add_parser(
        "evaluate-test",
        help="run the single final test evaluation using the frozen development threshold",
    )
    test_parser.add_argument("--annotations", type=Path, default=Path("data/annotations/test_confirmed_intents.jsonl"))
    test_parser.add_argument("--annotation-manifest", type=Path, default=Path("data/annotations/test_confirmed_intents_manifest.json"))
    test_parser.add_argument("--partition-file", type=Path, default=Path("data/processed/nl2bash/test.jsonl"))
    test_parser.add_argument("--dataset-manifest", type=Path, default=DEFAULT_DATASET_MANIFEST)
    test_parser.add_argument("--model-file", type=Path, default=DEFAULT_MODEL_FILE)
    test_parser.add_argument("--model-manifest", type=Path, default=DEFAULT_MODEL_MANIFEST)
    test_parser.add_argument("--frozen-threshold", type=Path, default=Path("artifacts/evaluation/frozen_dev_threshold.json"))
    test_parser.add_argument("--output", type=Path, default=Path("artifacts/evaluation/test_report.json"))
    test_parser.add_argument("--min-per-label", type=int, default=0)

    return parser


def _run_train(args: argparse.Namespace) -> int:
    _validate_paths(
        output_paths=(args.model_file, args.model_manifest),
        input_paths=(
            args.annotations,
            args.annotation_manifest,
            args.training_file,
            args.dataset_manifest,
        ),
    )
    data = load_confirmed_training_data(
        args.annotations,
        args.annotation_manifest,
        args.training_file,
        args.dataset_manifest,
        min_per_label=args.min_per_label,
    )
    artifact = train_intent_classifier(
        data,
        args.model_file,
        args.model_manifest,
        config=ClassifierConfig(min_per_label=args.min_per_label),
    )
    result = {
        "operation": "train",
        "model_file": str(artifact.model_path),
        "model_manifest": str(artifact.manifest_path),
        "record_count": artifact.manifest["training"]["record_count"],
        "class_counts": artifact.manifest["training"]["class_counts"],
        "scikit_learn": artifact.manifest["libraries"]["scikit_learn"],
        "evaluation_status": artifact.manifest["evaluation_status"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _run_predict(args: argparse.Namespace) -> int:
    model = load_intent_classifier(args.model_file, args.model_manifest)
    confidence_threshold = args.confidence_threshold
    threshold_source = (
        "explicit_override"
        if confidence_threshold is not None
        else "model_provisional_default"
    )
    frozen_threshold_sha256 = None
    if args.frozen_threshold is not None:
        _frozen, confidence_threshold, frozen_threshold_sha256 = (
            load_frozen_development_threshold(model, args.frozen_threshold)
        )
        threshold_source = "frozen_development_threshold"
    prediction = predict_intent(
        model,
        args.request,
        confidence_threshold=confidence_threshold,
    )
    result = {
        "operation": "predict",
        "request": prediction.request,
        "intent_label": prediction.intent_label,
        "raw_top_label": prediction.raw_top_label,
        "confidence": prediction.confidence,
        "confidence_interpretation": "uncalibrated model probability estimate",
        "low_confidence": prediction.low_confidence,
        "confidence_threshold": prediction.confidence_threshold,
        "threshold_source": threshold_source,
        "frozen_threshold_sha256": frozen_threshold_sha256,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _run_select_threshold(args: argparse.Namespace) -> int:
    _validate_paths(
        output_paths=(args.output,),
        input_paths=(
            args.annotations,
            args.annotation_manifest,
            args.partition_file,
            args.dataset_manifest,
            args.model_file,
            args.model_manifest,
        ),
    )
    model = load_intent_classifier(args.model_file, args.model_manifest)
    data = load_confirmed_evaluation_data(
        args.annotations,
        args.annotation_manifest,
        args.partition_file,
        args.dataset_manifest,
        partition_name="dev",
        min_per_label=args.min_per_label,
    )
    result = select_development_threshold(
        model,
        data,
        args.output,
        minimum_coverage=args.minimum_coverage,
    )
    print(
        json.dumps(
            {
                "operation": "select-threshold",
                "frozen_threshold_file": str(args.output),
                "threshold": result["threshold"],
                "minimum_coverage": result["minimum_coverage"],
                "development_metrics": result["development_metrics"],
                "model_sha256": result["model"]["sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


def _run_evaluate_test(args: argparse.Namespace) -> int:
    _validate_paths(
        output_paths=(args.output,),
        input_paths=(
            args.annotations,
            args.annotation_manifest,
            args.partition_file,
            args.dataset_manifest,
            args.model_file,
            args.model_manifest,
            args.frozen_threshold,
        ),
    )
    model = load_intent_classifier(args.model_file, args.model_manifest)
    data = load_confirmed_evaluation_data(
        args.annotations,
        args.annotation_manifest,
        args.partition_file,
        args.dataset_manifest,
        partition_name="test",
        min_per_label=args.min_per_label,
    )
    result = evaluate_test_once(
        model,
        data,
        args.frozen_threshold,
        args.output,
    )
    print(
        json.dumps(
            {
                "operation": "evaluate-test",
                "report_file": str(args.output),
                "metrics": result["metrics"],
                "model_sha256": result["model"]["sha256"],
                "frozen_threshold": result["frozen_development_threshold"]["threshold"],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.operation == "train":
            return _run_train(args)
        if args.operation == "predict":
            return _run_predict(args)
        if args.operation == "select-threshold":
            return _run_select_threshold(args)
        if args.operation == "evaluate-test":
            return _run_evaluate_test(args)
        parser.error(f"unsupported operation: {args.operation}")
    except (
        AnnotationError,
        ClassifierTrainingError,
        ModelLoadError,
        PredictionError,
        EvaluationError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
