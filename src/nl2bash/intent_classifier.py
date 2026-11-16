"""TF-IDF and Logistic Regression intent-classification baseline."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from nl2bash.annotations import INTENT_LABELS
from nl2bash.classifier_data import IntentTrainingData


@dataclass(frozen=True)
class ClassifierConfig:
    """Reproducible baseline hyperparameters."""

    max_features: int = 50_000
    ngram_min: int = 1
    ngram_max: int = 2
    lowercase: bool = True
    sublinear_tf: bool = True
    regularization_c: float = 1.0
    solver: str = "lbfgs"
    max_iter: int = 2_000
    random_seed: int = 42
    min_per_label: int = 2


@dataclass(frozen=True)
class TrainingArtifact:
    """Paths and provenance for a fitted local classifier."""

    model_path: Path
    manifest_path: Path
    manifest: dict[str, Any]


DEFAULT_CONFIDENCE_THRESHOLD = 0.45


class ClassifierTrainingError(RuntimeError):
    """Raised when the intent classifier cannot be trained safely."""


def validate_classifier_config(config: ClassifierConfig) -> None:
    """Reject invalid or unsupported baseline configuration values."""
    if not isinstance(config, ClassifierConfig):
        raise TypeError("config must be a ClassifierConfig")
    for name, value in (
        ("max_features", config.max_features),
        ("ngram_min", config.ngram_min),
        ("ngram_max", config.ngram_max),
        ("max_iter", config.max_iter),
        ("min_per_label", config.min_per_label),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
    if config.max_features < 1:
        raise ValueError("max_features must be at least 1")
    if config.ngram_min < 1 or config.ngram_max < config.ngram_min:
        raise ValueError("ngram range must satisfy 1 <= ngram_min <= ngram_max")
    if not isinstance(config.lowercase, bool) or not isinstance(config.sublinear_tf, bool):
        raise TypeError("lowercase and sublinear_tf must be boolean values")
    if isinstance(config.regularization_c, bool) or not isinstance(config.regularization_c, (int, float)):
        raise TypeError("regularization_c must be numeric")
    if not np.isfinite(config.regularization_c) or config.regularization_c <= 0:
        raise ValueError("regularization_c must be finite and greater than zero")
    if config.solver != "lbfgs":
        raise ValueError("the initial baseline supports only the lbfgs solver")
    if config.max_iter < 1:
        raise ValueError("max_iter must be at least 1")
    if isinstance(config.random_seed, bool) or not isinstance(config.random_seed, int):
        raise TypeError("random_seed must be an integer")
    if config.min_per_label < 1:
        raise ValueError("min_per_label must be at least 1")


def build_classifier_pipeline(config: ClassifierConfig | None = None) -> Pipeline:
    """Create one fitted-together TF-IDF and Logistic Regression pipeline."""
    selected = config or ClassifierConfig()
    validate_classifier_config(selected)

    vectorizer = TfidfVectorizer(
        lowercase=selected.lowercase,
        ngram_range=(selected.ngram_min, selected.ngram_max),
        max_features=selected.max_features,
        sublinear_tf=selected.sublinear_tf,
    )
    classifier = LogisticRegression(
        C=float(selected.regularization_c),
        solver=selected.solver,
        max_iter=selected.max_iter,
        random_state=selected.random_seed,
    )
    return Pipeline(
        steps=(
            ("tfidf", vectorizer),
            ("classifier", classifier),
        )
    )


def _validate_training_data(
    data: IntentTrainingData,
    min_per_label: int,
) -> dict[str, int]:
    if not isinstance(data, IntentTrainingData):
        raise TypeError("data must be validated IntentTrainingData")
    lengths = {
        len(data.requests),
        len(data.labels),
        len(data.example_ids),
        len(data.group_ids),
    }
    if len(lengths) != 1 or not data.requests:
        raise ClassifierTrainingError("training data fields must have the same non-zero length")
    if any(not isinstance(text, str) or not text.strip() for text in data.requests):
        raise ClassifierTrainingError("training data contains an empty or invalid request")
    if any(label not in INTENT_LABELS for label in data.labels):
        raise ClassifierTrainingError("training data contains an unknown intent label")
    if any(not isinstance(value, str) or not value for value in data.example_ids):
        raise ClassifierTrainingError("training data contains an invalid example ID")
    if any(not isinstance(value, str) or not value for value in data.group_ids):
        raise ClassifierTrainingError("training data contains an invalid duplicate-group ID")
    if len(set(data.example_ids)) != len(data.example_ids):
        raise ClassifierTrainingError("training data contains duplicate example IDs")
    if len(set(data.group_ids)) != len(data.group_ids):
        raise ClassifierTrainingError("training data contains duplicate duplicate-group IDs")

    provenance_fields = (
        ("dataset_revision", data.dataset_revision),
        ("training_partition_sha256", data.training_partition_sha256),
        ("confirmed_annotations_sha256", data.confirmed_annotations_sha256),
        ("annotation_manifest_sha256", data.annotation_manifest_sha256),
        ("reviewed_csv_sha256", data.reviewed_csv_sha256),
    )
    for name, value in provenance_fields:
        if not isinstance(value, str) or not value.strip():
            raise ClassifierTrainingError(f"training data is missing {name}")
    for name, value in provenance_fields[1:]:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ClassifierTrainingError(f"training data has an invalid {name}")

    counts = Counter(data.labels)
    supplied_counts = data.class_counts
    if not isinstance(supplied_counts, dict):
        raise ClassifierTrainingError("training data class_counts must be a dictionary")
    expected_counts = {label: counts.get(label, 0) for label in INTENT_LABELS}
    if supplied_counts != expected_counts:
        raise ClassifierTrainingError("training data class counts do not match its labels")

    shortages = {
        label: count
        for label, count in expected_counts.items()
        if count < min_per_label
    }
    if shortages:
        detail = ", ".join(
            f"{label}: {expected_counts[label]} (need {min_per_label})"
            for label in INTENT_LABELS
            if label in shortages
        )
        raise ClassifierTrainingError(
            "training data does not meet the per-label minimum: " + detail
        )
    return expected_counts


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def train_intent_classifier(
    data: IntentTrainingData,
    model_file: str | Path,
    manifest_file: str | Path,
    *,
    config: ClassifierConfig | None = None,
) -> TrainingArtifact:
    """Fit and persist the baseline using confirmed training requests only.

    The model manifest is the completion marker. Any previous manifest is
    removed before replacing model bytes so an interrupted save cannot leave
    stale metadata describing a newer or partial model file.
    """
    selected = config or ClassifierConfig()
    validate_classifier_config(selected)
    class_counts = _validate_training_data(data, selected.min_per_label)

    model_path = Path(model_file)
    manifest_path = Path(manifest_file)
    if model_path.resolve() == manifest_path.resolve():
        raise ValueError("model file and manifest file must use different paths")

    model_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.unlink(missing_ok=True)

    pipeline = build_classifier_pipeline(selected)
    try:
        pipeline.fit(list(data.requests), list(data.labels))
    except ValueError as exc:
        raise ClassifierTrainingError(f"TF-IDF or Logistic Regression training failed: {exc}") from exc

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{model_path.name}.", suffix=".tmp", dir=model_path.parent
    )
    os.close(descriptor)
    temporary_model = Path(temporary_name)
    try:
        joblib.dump(pipeline, temporary_model)
        with temporary_model.open("rb") as stream:
            model_bytes = stream.read()
            os.fsync(stream.fileno())
        model_sha256 = hashlib.sha256(model_bytes).hexdigest()
        os.replace(temporary_model, model_path)
    except Exception as exc:
        temporary_model.unlink(missing_ok=True)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise ClassifierTrainingError(f"could not write model artifact: {exc}") from exc

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "model_type": "tfidf_logistic_regression",
        "dataset": "NL2Bash",
        "source": {
            "dataset_revision": data.dataset_revision,
            "training_partition_sha256": data.training_partition_sha256,
            "confirmed_annotations_sha256": data.confirmed_annotations_sha256,
            "annotation_manifest_sha256": data.annotation_manifest_sha256,
            "reviewed_csv_sha256": data.reviewed_csv_sha256,
        },
        "training": {
            "record_count": len(data.requests),
            "class_counts": class_counts,
            "labels": list(INTENT_LABELS),
            "feature_configuration": {
                "type": "TfidfVectorizer",
                "lowercase": selected.lowercase,
                "ngram_range": [selected.ngram_min, selected.ngram_max],
                "max_features": selected.max_features,
                "sublinear_tf": selected.sublinear_tf,
            },
            "classifier_configuration": {
                "type": "LogisticRegression",
                "C": float(selected.regularization_c),
                "solver": selected.solver,
                "max_iter": selected.max_iter,
                "random_state": selected.random_seed,
                "class_weight": None,
            },
            "minimum_examples_per_label": selected.min_per_label,
        },
        "libraries": {
            "scikit_learn": sklearn.__version__,
            "numpy": np.__version__,
            "joblib": joblib.__version__,
        },
        "artifact": {
            "file": str(model_path),
            "sha256": model_sha256,
        },
        "training_policy": "only explicitly confirmed annotations from the training partition are used",
        "prediction": {
            "default_confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
            "threshold_status": "provisional_not_selected_on_development_data",
        },
        "evaluation_status": "not_evaluated",
    }
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    try:
        _atomic_write_bytes(manifest_path, manifest_payload)
    except Exception as exc:
        manifest_path.unlink(missing_ok=True)
        raise ClassifierTrainingError(f"could not write model manifest: {exc}") from exc

    return TrainingArtifact(
        model_path=model_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
