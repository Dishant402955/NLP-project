"""Development threshold selection and one-time held-out test evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Sequence

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

from nl2bash.annotations import INTENT_LABELS
from nl2bash.classifier_data import IntentTrainingData
from nl2bash.intent_prediction import LoadedIntentClassifier, PredictionError


DEFAULT_MINIMUM_COVERAGE = 0.80
DEFAULT_TEST_EVALUATION_GUARD = Path("artifacts/evaluation/test_evaluation.lock")
THRESHOLD_SELECTION_METHOD = "maximize_development_macro_f1_with_minimum_coverage"


class EvaluationError(RuntimeError):
    """Raised when evaluation inputs or state are invalid."""


@dataclass(frozen=True)
class EvaluationPredictions:
    """Per-example predictions and confidence metadata."""

    predicted_labels: tuple[str, ...]
    raw_top_labels: tuple[str | None, ...]
    confidences: tuple[float, ...]
    low_confidence: tuple[bool, ...]


@dataclass(frozen=True)
class EvaluationMetrics:
    """Aggregate and per-class classification metrics."""

    record_count: int
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    weighted_precision: float
    weighted_recall: float
    weighted_f1: float
    coverage: float
    low_confidence_count: int
    macro_label_count: int
    per_class: dict[str, dict[str, float | int]]
    confusion_matrix: list[list[int]]


def _sha256_file(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise EvaluationError(f"cannot read file for checksum {path}: {exc}") from exc


def _validate_evaluation_data(
    data: IntentTrainingData,
    expected_partition: str,
) -> None:
    if not isinstance(data, IntentTrainingData):
        raise TypeError("data must be validated IntentTrainingData")
    if data.partition_name != expected_partition:
        raise EvaluationError(
            f"{expected_partition} evaluation requires {expected_partition} annotations, "
            f"not {data.partition_name}"
        )
    if data.blind_manual_review is not True:
        raise EvaluationError(
            f"{expected_partition} evaluation requires labels from blind manual review"
        )
    lengths = {
        len(data.requests),
        len(data.labels),
        len(data.example_ids),
        len(data.group_ids),
    }
    if len(lengths) != 1 or not data.requests:
        raise EvaluationError("evaluation fields must have the same non-zero length")
    if any(not isinstance(request, str) or not request.strip() for request in data.requests):
        raise EvaluationError("evaluation data contains empty or invalid requests")
    if any(not isinstance(label, str) or label not in INTENT_LABELS for label in data.labels):
        raise EvaluationError("evaluation data contains an unknown intent label")
    if any(not isinstance(value, str) or not value for value in data.example_ids):
        raise EvaluationError("evaluation data contains an invalid example ID")
    if any(not isinstance(value, str) or not value for value in data.group_ids):
        raise EvaluationError("evaluation data contains an invalid duplicate-group ID")
    if len(set(data.example_ids)) != len(data.example_ids):
        raise EvaluationError("evaluation data contains duplicate example IDs")
    if len(set(data.group_ids)) != len(data.group_ids):
        raise EvaluationError("evaluation data contains duplicate duplicate-group IDs")
    expected_counts = {label: data.labels.count(label) for label in INTENT_LABELS}
    if not isinstance(data.class_counts, dict) or data.class_counts != expected_counts:
        raise EvaluationError("evaluation class counts do not match labels")
    if not isinstance(data.dataset_revision, str) or not data.dataset_revision.strip():
        raise EvaluationError("evaluation data has no dataset revision")
    for name, value in (
        ("partition checksum", data.training_partition_sha256),
        ("annotation checksum", data.confirmed_annotations_sha256),
        ("annotation manifest checksum", data.annotation_manifest_sha256),
        ("reviewed CSV checksum", data.reviewed_csv_sha256),
    ):
        if not isinstance(value, str) or len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise EvaluationError(f"evaluation data has an invalid {name}")


def _predict_at_threshold(
    model: LoadedIntentClassifier,
    requests: Sequence[str],
    threshold: float,
) -> EvaluationPredictions:
    if not isinstance(model, LoadedIntentClassifier):
        raise TypeError("model must be a LoadedIntentClassifier")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise TypeError("confidence threshold must be numeric")
    threshold = float(threshold)
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("confidence threshold must be between 0 and 1")

    vectorizer = model.pipeline.named_steps["tfidf"]
    classifier = model.pipeline.named_steps["classifier"]
    try:
        features = vectorizer.transform(list(requests))
        if features.shape[0] != len(requests):
            raise PredictionError("vectorizer returned an unexpected number of rows")
        scores = classifier.predict_proba(features)
    except Exception as exc:
        raise EvaluationError(f"could not score evaluation requests: {exc}") from exc

    if scores.shape != (len(requests), len(classifier.classes_)):
        raise EvaluationError("classifier returned an invalid evaluation score matrix")
    if not np.all(np.isfinite(scores)) or np.any(scores < 0.0) or np.any(scores > 1.0):
        raise EvaluationError("classifier returned invalid evaluation score values")
    if not np.allclose(scores.sum(axis=1), 1.0, rtol=1e-6, atol=1e-6):
        raise EvaluationError("classifier score rows do not sum to one")

    predicted: list[str] = []
    raw_top: list[str | None] = []
    confidences: list[float] = []
    low_confidence: list[bool] = []
    row_nonzero = np.asarray(features.getnnz(axis=1)).reshape(-1)

    for index, row in enumerate(scores):
        if row_nonzero[index] == 0:
            predicted.append("other_or_ambiguous")
            raw_top.append(None)
            confidences.append(0.0)
            low_confidence.append(True)
            continue
        best_index = int(np.argmax(row))
        confidence = float(row[best_index])
        label = str(classifier.classes_[best_index])
        low = confidence < threshold
        predicted.append("other_or_ambiguous" if low else label)
        raw_top.append(label)
        confidences.append(confidence)
        low_confidence.append(low)

    return EvaluationPredictions(
        predicted_labels=tuple(predicted),
        raw_top_labels=tuple(raw_top),
        confidences=tuple(confidences),
        low_confidence=tuple(low_confidence),
    )


def calculate_metrics(
    true_labels: Sequence[str],
    predictions: EvaluationPredictions,
) -> EvaluationMetrics:
    """Calculate fixed-taxonomy metrics, including unsupported class counts."""
    lengths = {
        len(true_labels),
        len(predictions.predicted_labels),
        len(predictions.raw_top_labels),
        len(predictions.confidences),
        len(predictions.low_confidence),
    }
    if len(lengths) != 1 or not true_labels:
        raise EvaluationError("truth and all prediction arrays must have the same non-zero length")
    if any(not isinstance(label, str) or label not in INTENT_LABELS for label in true_labels):
        raise EvaluationError("evaluation truth contains an unknown taxonomy label")
    if any(
        not isinstance(label, str) or label not in INTENT_LABELS
        for label in predictions.predicted_labels
    ):
        raise EvaluationError("evaluation predictions contain an unknown taxonomy label")
    if any(
        label is not None and (not isinstance(label, str) or label not in INTENT_LABELS)
        for label in predictions.raw_top_labels
    ):
        raise EvaluationError("diagnostic top labels contain an unknown taxonomy label")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 <= value <= 1.0
        for value in predictions.confidences
    ):
        raise EvaluationError("evaluation predictions contain invalid confidence values")
    if any(not isinstance(value, bool) for value in predictions.low_confidence):
        raise EvaluationError("low-confidence flags must be boolean values")

    precision, recall, f1, support = precision_recall_fscore_support(
        true_labels,
        predictions.predicted_labels,
        labels=list(INTENT_LABELS),
        zero_division=0,
    )
    weighted_precision, weighted_recall, weighted_f1, _ = precision_recall_fscore_support(
        true_labels,
        predictions.predicted_labels,
        labels=list(INTENT_LABELS),
        average="weighted",
        zero_division=0,
    )
    matrix = confusion_matrix(
        true_labels,
        predictions.predicted_labels,
        labels=list(INTENT_LABELS),
    )
    count = len(true_labels)
    low_count = sum(predictions.low_confidence)
    supported = support > 0
    return EvaluationMetrics(
        record_count=count,
        accuracy=float(accuracy_score(true_labels, predictions.predicted_labels)),
        macro_precision=float(np.mean(precision[supported])),
        macro_recall=float(np.mean(recall[supported])),
        macro_f1=float(np.mean(f1[supported])),
        weighted_precision=float(weighted_precision),
        weighted_recall=float(weighted_recall),
        weighted_f1=float(weighted_f1),
        coverage=float((count - low_count) / count),
        low_confidence_count=low_count,
        macro_label_count=int(np.count_nonzero(supported)),
        per_class={
            label: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(INTENT_LABELS)
        },
        confusion_matrix=matrix.astype(int).tolist(),
    )


def _metrics_dict(metrics: EvaluationMetrics) -> dict[str, Any]:
    return asdict(metrics)


def _atomic_write_once(path: Path, payload: bytes) -> None:
    """Publish a complete artifact without replacing an existing file."""
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
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise EvaluationError(
                f"refusing to overwrite existing evaluation artifact: {path}"
            ) from exc
        temporary.unlink(missing_ok=True)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def select_development_threshold(
    model: LoadedIntentClassifier,
    development_data: IntentTrainingData,
    output_file: str | Path,
    *,
    minimum_coverage: float = DEFAULT_MINIMUM_COVERAGE,
) -> dict[str, Any]:
    """Select a threshold on confirmed dev data and freeze it exactly once."""
    _validate_evaluation_data(development_data, "dev")
    if isinstance(minimum_coverage, bool) or not isinstance(minimum_coverage, (int, float)):
        raise TypeError("minimum_coverage must be numeric")
    minimum_coverage = float(minimum_coverage)
    if not math.isfinite(minimum_coverage) or not 0.0 < minimum_coverage <= 1.0:
        raise ValueError("minimum_coverage must be greater than 0 and at most 1")

    model_sha256 = _sha256_file(model.model_path)
    expected_model_sha256 = model.manifest.get("artifact", {}).get("sha256")
    if model_sha256 != expected_model_sha256:
        raise EvaluationError("model artifact changed after it was loaded")
    model_source = model.manifest.get("source", {})
    if not isinstance(model_source, dict):
        raise EvaluationError("model manifest has no valid source provenance")
    if model_source.get("dataset_revision") != development_data.dataset_revision:
        raise EvaluationError("model and development annotations use different dataset revisions")

    # Evaluate all distinct confidence boundaries. nextafter moves just above
    # a score so ties at that score become abstentions under the strict '<' rule.
    initial = _predict_at_threshold(model, development_data.requests, 0.0)
    thresholds = {0.0, 1.0}
    thresholds.update(
        float(np.nextafter(score, 1.0))
        for score in initial.confidences
        if score < 1.0
    )

    candidates: list[tuple[float, float, float, EvaluationMetrics]] = []
    for threshold in sorted(thresholds):
        predictions = _predict_at_threshold(model, development_data.requests, threshold)
        metrics = calculate_metrics(development_data.labels, predictions)
        if metrics.coverage + 1e-12 >= minimum_coverage:
            candidates.append((metrics.macro_f1, metrics.coverage, -threshold, metrics))

    if not candidates:
        raise EvaluationError(
            "no confidence threshold satisfies the minimum development coverage; "
            "review more development examples or reconsider the coverage requirement"
        )
    best = max(candidates, key=lambda item: (item[0], item[1], item[2]))
    selected_threshold = -best[2]
    selected_metrics = best[3]

    result: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "frozen_intent_confidence_threshold",
        "selection_method": THRESHOLD_SELECTION_METHOD,
        "frozen": True,
        "threshold": selected_threshold,
        "minimum_coverage": minimum_coverage,
        "development_metrics": _metrics_dict(selected_metrics),
        "development_source": {
            "dataset_revision": development_data.dataset_revision,
            "partition_name": "dev",
            "partition_sha256": development_data.training_partition_sha256,
            "confirmed_annotations_sha256": development_data.confirmed_annotations_sha256,
            "annotation_manifest_sha256": development_data.annotation_manifest_sha256,
            "reviewed_csv_sha256": development_data.reviewed_csv_sha256,
        },
        "model": {
            "file": str(model.model_path),
            "sha256": model_sha256,
        },
        "threshold_candidates_evaluated": len(thresholds),
        "thresholds_meeting_coverage": len(candidates),
        "tie_break": "highest macro-F1, then highest coverage, then lowest threshold",
    }
    _atomic_write_once(Path(output_file), _json_bytes(result))
    return result


def load_frozen_development_threshold(
    model: LoadedIntentClassifier,
    frozen_threshold_file: str | Path,
) -> tuple[dict[str, Any], float, str]:
    """Load and verify the frozen development threshold for a specific model."""
    frozen_path = Path(frozen_threshold_file)
    try:
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EvaluationError(
            f"cannot read frozen development threshold {frozen_path}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"invalid frozen development threshold JSON: {exc}") from exc
    if not isinstance(frozen, dict):
        raise EvaluationError("frozen development threshold must be a JSON object")
    if (
        frozen.get("schema_version") != 1
        or frozen.get("artifact_type") != "frozen_intent_confidence_threshold"
    ):
        raise EvaluationError("unsupported frozen threshold artifact")
    if frozen.get("frozen") is not True:
        raise EvaluationError("development threshold is not frozen")
    if frozen.get("selection_method") != THRESHOLD_SELECTION_METHOD:
        raise EvaluationError("frozen threshold uses an unsupported selection method")

    model_sha256 = _sha256_file(model.model_path)
    expected_model = frozen.get("model")
    if not isinstance(expected_model, dict):
        raise EvaluationError("frozen threshold has no model provenance")
    if expected_model.get("sha256") != model_sha256:
        raise EvaluationError("frozen threshold refers to a different model artifact")
    if expected_model.get("sha256") != model.manifest.get("artifact", {}).get("sha256"):
        raise EvaluationError("loaded model manifest does not match the frozen threshold")
    declared_model_path = expected_model.get("file")
    if (
        not isinstance(declared_model_path, str)
        or Path(declared_model_path).resolve() != model.model_path.resolve()
    ):
        raise EvaluationError("frozen threshold refers to a different model path")

    threshold = frozen.get("threshold")
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not math.isfinite(threshold)
        or not 0.0 <= threshold <= 1.0
    ):
        raise EvaluationError("frozen threshold value is invalid")

    development_source = frozen.get("development_source")
    if not isinstance(development_source, dict):
        raise EvaluationError("frozen threshold has no development provenance")
    if development_source.get("partition_name") != "dev":
        raise EvaluationError("frozen threshold was not selected on the development partition")
    minimum_coverage = frozen.get("minimum_coverage")
    development_metrics = frozen.get("development_metrics")
    if (
        isinstance(minimum_coverage, bool)
        or not isinstance(minimum_coverage, (int, float))
        or not math.isfinite(minimum_coverage)
        or not 0.0 < minimum_coverage <= 1.0
    ):
        raise EvaluationError("frozen threshold has an invalid minimum coverage")
    if not isinstance(development_metrics, dict):
        raise EvaluationError("frozen threshold has no development metrics")
    recorded_coverage = development_metrics.get("coverage")
    if (
        isinstance(recorded_coverage, bool)
        or not isinstance(recorded_coverage, (int, float))
        or not math.isfinite(recorded_coverage)
        or recorded_coverage + 1e-12 < minimum_coverage
    ):
        raise EvaluationError("frozen development metrics do not meet the minimum coverage")
    if development_metrics.get("record_count", 0) < 1:
        raise EvaluationError("frozen development metrics contain no evaluated records")
    for name in (
        "partition_sha256",
        "confirmed_annotations_sha256",
        "annotation_manifest_sha256",
        "reviewed_csv_sha256",
    ):
        value = development_source.get(name)
        if not isinstance(value, str) or len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise EvaluationError(f"frozen threshold has invalid development {name}")

    model_source = model.manifest.get("source", {})
    if not isinstance(model_source, dict):
        raise EvaluationError("model manifest has no valid source provenance")
    if model_source.get("dataset_revision") != development_source.get("dataset_revision"):
        raise EvaluationError("model and development annotations use different dataset revisions")
    if model_source.get("training_partition_sha256") == development_source.get("partition_sha256"):
        raise EvaluationError("training and development data resolve to the same partition checksum")
    frozen_sha256 = _sha256_file(frozen_path)
    return frozen, float(threshold), frozen_sha256


def evaluate_test_once(
    model: LoadedIntentClassifier,
    test_data: IntentTrainingData,
    frozen_threshold_file: str | Path,
    output_file: str | Path,
    *,
    run_guard_file: str | Path = DEFAULT_TEST_EVALUATION_GUARD,
) -> dict[str, Any]:
    """Evaluate held-out test labels exactly once using a frozen dev threshold."""
    _validate_evaluation_data(test_data, "test")
    frozen_path = Path(frozen_threshold_file)
    report_path = Path(output_file)
    guard_path = Path(run_guard_file)
    if len({report_path.resolve(), frozen_path.resolve(), guard_path.resolve()}) != 3:
        raise ValueError("test report, frozen threshold, and one-time guard must use different paths")
    if report_path.exists():
        raise EvaluationError(
            f"test evaluation report already exists; refusing to evaluate or overwrite it: {report_path}"
        )
    if guard_path.exists():
        raise EvaluationError(
            f"test evaluation has already been started or completed for this project: {guard_path}"
        )

    frozen, threshold, frozen_sha256 = load_frozen_development_threshold(
        model, frozen_path
    )
    development_source = frozen["development_source"]
    if development_source.get("dataset_revision") != test_data.dataset_revision:
        raise EvaluationError("development and test annotations use different dataset revisions")
    if development_source.get("partition_sha256") == test_data.training_partition_sha256:
        raise EvaluationError("development and test data resolve to the same partition checksum")

    model_source = model.manifest["source"]
    if model_source.get("dataset_revision") != test_data.dataset_revision:
        raise EvaluationError("model and test annotations use different dataset revisions")
    if model_source.get("training_partition_sha256") == test_data.training_partition_sha256:
        raise EvaluationError("training and test data resolve to the same partition checksum")

    guard_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        guard_descriptor = os.open(
            guard_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        raise EvaluationError(
            f"test evaluation has already been started or completed for this project: {guard_path}"
        ) from exc

    report_written = False
    try:
        in_progress = _json_bytes({
            "schema_version": 1,
            "status": "in_progress",
            "model_sha256": _sha256_file(model.model_path),
            "frozen_threshold_sha256": frozen_sha256,
            "test_partition_sha256": test_data.training_partition_sha256,
        })
        with os.fdopen(guard_descriptor, "wb") as guard_stream:
            guard_stream.write(in_progress)
            guard_stream.flush()
            os.fsync(guard_stream.fileno())
        predictions = _predict_at_threshold(model, test_data.requests, threshold)
        metrics = calculate_metrics(test_data.labels, predictions)
        model_sha256 = _sha256_file(model.model_path)
        if model_sha256 != model.manifest.get("artifact", {}).get("sha256"):
            raise EvaluationError("model artifact changed during test evaluation")
        result: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "intent_classifier_test_evaluation",
        "evaluation_policy": "single_final_test_evaluation_after_development_threshold_freeze",
        "evaluated_once": True,
        "model": {
            "file": str(model.model_path),
            "sha256": model_sha256,
        },
        "frozen_development_threshold": {
            "file": str(frozen_path),
            "sha256": frozen_sha256,
            "threshold": threshold,
            "selection_method": frozen["selection_method"],
            "development_partition_sha256": development_source.get("partition_sha256"),
            "development_annotations_sha256": development_source.get("confirmed_annotations_sha256"),
        },
        "test_source": {
            "dataset_revision": test_data.dataset_revision,
            "partition_name": "test",
            "partition_sha256": test_data.training_partition_sha256,
            "confirmed_annotations_sha256": test_data.confirmed_annotations_sha256,
            "annotation_manifest_sha256": test_data.annotation_manifest_sha256,
            "reviewed_csv_sha256": test_data.reviewed_csv_sha256,
        },
        "metrics": _metrics_dict(metrics),
        "interpretation": (
            "The confidence value is an uncalibrated Logistic Regression probability estimate. "
            "A prediction below the frozen development threshold is mapped to other_or_ambiguous."
        ),
    }
        _atomic_write_once(report_path, _json_bytes(result))
        report_written = True
        completed = _json_bytes({
            "schema_version": 1,
            "status": "completed",
            "report_file": str(report_path),
            "report_sha256": _sha256_file(report_path),
            "model_sha256": model_sha256,
            "frozen_threshold_sha256": frozen_sha256,
            "test_partition_sha256": test_data.training_partition_sha256,
        })
        guard_path.write_bytes(completed)
        return result
    except Exception:
        if not report_written and not report_path.exists():
            guard_path.unlink(missing_ok=True)
        raise
