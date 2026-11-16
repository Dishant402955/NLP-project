"""Verified loading and low-confidence prediction for the intent classifier."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.utils.validation import check_is_fitted

from nl2bash.annotations import INTENT_LABELS
from nl2bash.intent_classifier import DEFAULT_CONFIDENCE_THRESHOLD
from nl2bash.preprocessing import InvalidRequestError, normalize_request


class ModelLoadError(RuntimeError):
    """Raised when a saved classifier cannot be safely loaded."""


class PredictionError(RuntimeError):
    """Raised when the loaded classifier cannot produce a valid prediction."""


@dataclass(frozen=True)
class LoadedIntentClassifier:
    """A verified local model pipeline and its provenance manifest."""

    pipeline: Pipeline
    manifest: dict[str, Any]
    model_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class IntentPrediction:
    """One intent prediction with a diagnostic top label and confidence."""

    request: str
    intent_label: str
    raw_top_label: str | None
    confidence: float
    low_confidence: bool
    confidence_threshold: float


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ModelLoadError(f"cannot read model manifest {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ModelLoadError(f"invalid model manifest JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ModelLoadError("model manifest must contain a JSON object")
    return value


def _validate_pipeline(
    pipeline: Any,
    manifest: dict[str, Any],
) -> Pipeline:
    if not isinstance(pipeline, Pipeline):
        raise ModelLoadError("model artifact is not a Scikit-learn Pipeline")
    if tuple(pipeline.named_steps) != ("tfidf", "classifier"):
        raise ModelLoadError("model pipeline has unexpected steps")

    vectorizer = pipeline.named_steps["tfidf"]
    classifier = pipeline.named_steps["classifier"]
    if not isinstance(vectorizer, TfidfVectorizer):
        raise ModelLoadError("model pipeline has an invalid TF-IDF component")
    if not isinstance(classifier, LogisticRegression):
        raise ModelLoadError("model pipeline has an invalid Logistic Regression component")
    try:
        check_is_fitted(vectorizer)
        check_is_fitted(classifier)
    except Exception as exc:
        raise ModelLoadError("model pipeline components are not fitted") from exc

    training = manifest.get("training")
    if not isinstance(training, dict):
        raise ModelLoadError("model manifest has no valid training metadata")
    if training.get("labels") != list(INTENT_LABELS):
        raise ModelLoadError("model manifest taxonomy labels do not match this application")
    counts = training.get("class_counts")
    if not isinstance(counts, dict) or set(counts) != set(INTENT_LABELS):
        raise ModelLoadError("model manifest class counts do not match the taxonomy")
    if any(isinstance(count, bool) or not isinstance(count, int) or count < 1 for count in counts.values()):
        raise ModelLoadError("model manifest has invalid class counts")
    minimum = training.get("minimum_examples_per_label")
    record_count = training.get("record_count")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise ModelLoadError("model manifest has an invalid per-label minimum")
    if any(count < minimum for count in counts.values()):
        raise ModelLoadError("model manifest contains a class below its training minimum")
    if isinstance(record_count, bool) or not isinstance(record_count, int) or record_count < 1:
        raise ModelLoadError("model manifest has an invalid training record count")
    if sum(counts.values()) != record_count:
        raise ModelLoadError("model manifest record count does not match class counts")

    if set(classifier.classes_) != set(INTENT_LABELS):
        raise ModelLoadError("fitted classifier classes do not match the intent taxonomy")

    feature_config = training.get("feature_configuration")
    classifier_config = training.get("classifier_configuration")
    if not isinstance(feature_config, dict) or not isinstance(classifier_config, dict):
        raise ModelLoadError("model manifest is missing pipeline configuration")
    if feature_config.get("type") != "TfidfVectorizer":
        raise ModelLoadError("model manifest has an unsupported feature extractor")
    if feature_config.get("lowercase") != vectorizer.lowercase:
        raise ModelLoadError("model TF-IDF lowercase setting does not match its manifest")
    if feature_config.get("ngram_range") != list(vectorizer.ngram_range):
        raise ModelLoadError("model TF-IDF n-gram range does not match its manifest")
    if feature_config.get("max_features") != vectorizer.max_features:
        raise ModelLoadError("model TF-IDF vocabulary limit does not match its manifest")
    if feature_config.get("sublinear_tf") != vectorizer.sublinear_tf:
        raise ModelLoadError("model TF-IDF sublinear setting does not match its manifest")

    if classifier_config.get("type") != "LogisticRegression":
        raise ModelLoadError("model manifest has an unsupported classifier")
    if classifier_config.get("C") != classifier.C:
        raise ModelLoadError("model regularization setting does not match its manifest")
    if classifier_config.get("solver") != classifier.solver:
        raise ModelLoadError("model solver does not match its manifest")
    if classifier_config.get("max_iter") != classifier.max_iter:
        raise ModelLoadError("model iteration setting does not match its manifest")
    if classifier_config.get("random_state") != classifier.random_state:
        raise ModelLoadError("model random seed does not match its manifest")
    return pipeline


def load_intent_classifier(
    model_file: str | Path,
    manifest_file: str | Path,
) -> LoadedIntentClassifier:
    """Verify model bytes and environment metadata before loading joblib data.

    Joblib uses Python object serialization. Only load model files generated
    by this project in a trusted local workspace.
    """
    model_path = Path(model_file)
    manifest_path = Path(manifest_file)
    manifest = _read_manifest(manifest_path)

    if manifest.get("schema_version") != 1:
        raise ModelLoadError("unsupported model manifest schema version")
    if manifest.get("model_type") != "tfidf_logistic_regression":
        raise ModelLoadError("unsupported model type")

    artifact = manifest.get("artifact")
    libraries = manifest.get("libraries")
    if not isinstance(artifact, dict) or not isinstance(libraries, dict):
        raise ModelLoadError("model manifest is missing artifact or library metadata")
    declared_path = artifact.get("file")
    if not isinstance(declared_path, str) or Path(declared_path).resolve() != model_path.resolve():
        raise ModelLoadError("model path does not match its manifest")
    if not model_path.is_file():
        raise ModelLoadError(f"model artifact does not exist: {model_path}")

    expected_versions = {
        "scikit_learn": sklearn.__version__,
        "numpy": np.__version__,
        "joblib": joblib.__version__,
    }
    for name, current_version in expected_versions.items():
        if libraries.get(name) != current_version:
            raise ModelLoadError(
                f"{name} version mismatch: model requires {libraries.get(name)}, "
                f"environment has {current_version}; recreate the model in this environment"
            )

    try:
        model_bytes = model_path.read_bytes()
    except OSError as exc:
        raise ModelLoadError(f"cannot read model artifact {model_path}: {exc}") from exc
    actual_sha256 = hashlib.sha256(model_bytes).hexdigest()
    if artifact.get("sha256") != actual_sha256:
        raise ModelLoadError("model artifact checksum does not match its manifest")

    try:
        pipeline = joblib.load(model_path)
    except Exception as exc:
        raise ModelLoadError(f"could not load trusted model artifact: {exc}") from exc
    pipeline = _validate_pipeline(pipeline, manifest)
    prediction = manifest.get("prediction")
    if not isinstance(prediction, dict):
        raise ModelLoadError("model manifest has no prediction configuration")
    threshold = prediction.get("default_confidence_threshold")
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not math.isfinite(threshold)
        or not 0.0 <= threshold <= 1.0
    ):
        raise ModelLoadError("model manifest has an invalid default confidence threshold")
    if prediction.get("threshold_status") != "provisional_not_selected_on_development_data":
        raise ModelLoadError("model manifest has an unexpected threshold status")

    return LoadedIntentClassifier(
        pipeline=pipeline,
        manifest=manifest,
        model_path=model_path,
        manifest_path=manifest_path,
    )


def predict_intent(
    model: LoadedIntentClassifier,
    request: str,
    *,
    confidence_threshold: float | None = None,
) -> IntentPrediction:
    """Predict one intent and apply a conservative low-confidence fallback."""
    if not isinstance(model, LoadedIntentClassifier):
        raise TypeError("model must be a LoadedIntentClassifier")
    normalized = normalize_request(request)

    if confidence_threshold is None:
        configured = model.manifest["prediction"]["default_confidence_threshold"]
        threshold = float(configured)
    else:
        if isinstance(confidence_threshold, bool) or not isinstance(confidence_threshold, (int, float)):
            raise TypeError("confidence_threshold must be numeric")
        threshold = float(confidence_threshold)
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("confidence_threshold must be between 0 and 1")

    vectorizer = model.pipeline.named_steps["tfidf"]
    classifier = model.pipeline.named_steps["classifier"]
    try:
        features = vectorizer.transform([normalized])
        if features.nnz == 0:
            return IntentPrediction(
                request=normalized,
                intent_label="other_or_ambiguous",
                raw_top_label=None,
                confidence=0.0,
                low_confidence=True,
                confidence_threshold=threshold,
            )

        scores = classifier.predict_proba(features)[0]
    except Exception as exc:
        raise PredictionError(f"intent prediction failed: {exc}") from exc

    if scores.ndim != 1 or scores.size != len(classifier.classes_):
        raise PredictionError("classifier returned an invalid probability vector")
    if not np.all(np.isfinite(scores)) or np.any(scores < 0.0) or np.any(scores > 1.0):
        raise PredictionError("classifier returned invalid probability values")
    total = float(scores.sum())
    if not math.isclose(total, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise PredictionError("classifier probability scores do not sum to one")

    best_index = int(np.argmax(scores))
    raw_label = str(classifier.classes_[best_index])
    confidence = float(scores[best_index])
    low_confidence = confidence < threshold
    return IntentPrediction(
        request=normalized,
        intent_label="other_or_ambiguous" if low_confidence else raw_label,
        raw_top_label=raw_label,
        confidence=confidence,
        low_confidence=low_confidence,
        confidence_threshold=threshold,
    )
