"""Exact-span precision, recall, and F1 for entity extraction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from nl2bash.entity_extraction import ENTITY_TYPES, ExtractedEntity, extract_entities


@dataclass(frozen=True, slots=True)
class EntityTypeMetrics:
    """Counts and exact-match metrics for one entity type."""

    true_positive: int
    false_positive: int
    false_negative: int
    support: int
    predicted: int
    precision: float
    recall: float
    f1: float


@dataclass(frozen=True, slots=True)
class EntityEvaluationReport:
    """Micro-averaged and per-type exact-span extraction metrics."""

    request_count: int
    total_gold: int
    total_predicted: int
    total_correct: int
    precision: float
    recall: float
    f1: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    macro_entity_type_count: int
    per_entity_type: dict[str, EntityTypeMetrics]


def _metrics(true_positive: int, false_positive: int, false_negative: int) -> EntityTypeMetrics:
    support = true_positive + false_negative
    predicted = true_positive + false_positive
    precision = true_positive / predicted if predicted else 0.0
    recall = true_positive / support if support else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return EntityTypeMetrics(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        support=support,
        predicted=predicted,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def _entity_key(entity: ExtractedEntity) -> tuple[str, int, int, str]:
    return entity.entity_type, entity.start, entity.end, entity.value


def evaluate_entity_extraction(
    requests: Sequence[str],
    gold_entities: Sequence[Sequence[ExtractedEntity]],
) -> EntityEvaluationReport:
    """Evaluate exact entity type, value, and character-span predictions.

    Gold entity offsets must refer to each corresponding normalized request.
    A prediction is correct only when entity type, exact value, start, and end
    all match. This deliberately strict metric makes span and boundary errors
    visible. It does not assign partial credit for overlapping spans.
    """
    if isinstance(requests, (str, bytes)) or not isinstance(requests, Sequence):
        raise TypeError("requests must be a sequence of request strings")
    if isinstance(gold_entities, (str, bytes)) or not isinstance(gold_entities, Sequence):
        raise TypeError("gold_entities must be a sequence of entity sequences")
    if len(requests) != len(gold_entities):
        raise ValueError("requests and gold_entities must contain the same number of records")
    if not requests:
        raise ValueError("at least one request is required for entity evaluation")

    type_counts = {
        entity_type: {"tp": 0, "fp": 0, "fn": 0}
        for entity_type in ENTITY_TYPES
    }

    for index, (request, gold_for_request) in enumerate(zip(requests, gold_entities)):
        if not isinstance(request, str):
            raise TypeError(f"request at index {index} must be a string")
        if isinstance(gold_for_request, (str, bytes)) or not isinstance(gold_for_request, Sequence):
            raise TypeError(f"gold entities at index {index} must be a sequence")

        normalized_request = request.strip()
        if not normalized_request:
            raise ValueError(f"request at index {index} must contain non-whitespace text")
        if request != normalized_request:
            raise ValueError(
                f"request at index {index} must be normalized before annotating entity offsets"
            )

        gold_keys: set[tuple[str, int, int, str]] = set()
        for entity in gold_for_request:
            if not isinstance(entity, ExtractedEntity):
                raise TypeError(f"gold entity at request index {index} has an invalid type")
            if entity.end > len(request) or request[entity.start:entity.end] != entity.value:
                raise ValueError(f"gold entity at request index {index} has an invalid source span")
            key = _entity_key(entity)
            if key in gold_keys:
                raise ValueError(f"duplicate gold entity at request index {index}: {key}")
            gold_keys.add(key)

        predicted = extract_entities(request)
        predicted_keys = {_entity_key(entity) for entity in predicted.entities}
        for entity_type in ENTITY_TYPES:
            gold_type = {key for key in gold_keys if key[0] == entity_type}
            predicted_type = {key for key in predicted_keys if key[0] == entity_type}
            type_counts[entity_type]["tp"] += len(gold_type & predicted_type)
            type_counts[entity_type]["fp"] += len(predicted_type - gold_type)
            type_counts[entity_type]["fn"] += len(gold_type - predicted_type)

    per_type = {
        entity_type: _metrics(counts["tp"], counts["fp"], counts["fn"])
        for entity_type, counts in type_counts.items()
    }
    total_tp = sum(value.true_positive for value in per_type.values())
    total_fp = sum(value.false_positive for value in per_type.values())
    total_fn = sum(value.false_negative for value in per_type.values())
    micro = _metrics(total_tp, total_fp, total_fn)
    supported = [metrics for metrics in per_type.values() if metrics.support > 0]
    macro_count = len(supported)
    macro_precision = sum(metrics.precision for metrics in supported) / macro_count if macro_count else 0.0
    macro_recall = sum(metrics.recall for metrics in supported) / macro_count if macro_count else 0.0
    macro_f1 = sum(metrics.f1 for metrics in supported) / macro_count if macro_count else 0.0
    return EntityEvaluationReport(
        request_count=len(requests),
        total_gold=micro.support,
        total_predicted=micro.predicted,
        total_correct=total_tp,
        precision=micro.precision,
        recall=micro.recall,
        f1=micro.f1,
        macro_precision=macro_precision,
        macro_recall=macro_recall,
        macro_f1=macro_f1,
        macro_entity_type_count=macro_count,
        per_entity_type=per_type,
    )
