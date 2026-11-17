# Entity Extraction Test Evaluation

**Evaluation date:** 2026-11-17
**Partition:** held-out NL2Bash test requests
**Sample:** 66 targeted requests, one per duplicate group
**Evaluation policy:** exact entity type, exact source value, and exact character-span match

## Annotation provenance and scope

The project owner reviewed all 66 assistant-reviewed request-only proposal rows and requested no corrections. The confirmed review CSV contains 113 entity spans across 58 requests and eight approved empty-entity rows. The corresponding manifest records 66 owner-approved rows and explicitly states that the labels are AI-assisted, not independently annotated ground truth.

The sample was selected to exercise explicit entity cues. It is not a prevalence-representative random sample. It has one gold port span and no gold process_name or process_metric spans. Scores are therefore a targeted engineering diagnostic, not a corpus-wide estimate.

The evaluator validates the review CSV against the test partition, source worklist and manifest checksums, example/group IDs, normalized request text, exact offsets, row status, reviewer notes, and owner-review provenance. It writes a one-time guard and report. This held-out evaluation must not be rerun or used to tune extraction rules.

## Aggregate results

| Metric | Result |
|---|---:|
| Requests | 66 |
| Gold spans | 113 |
| Predicted spans | 85 |
| Exact type/value/span matches | 73 |
| Micro precision | 0.8588 |
| Micro recall | 0.6460 |
| Micro F1 | 0.7374 |
| Macro precision (supported types) | 0.8423 |
| Macro recall (supported types) | 0.7349 |
| Macro F1 (supported types) | 0.7517 |
| Entity types with gold support | 9 / 11 |

A match requires the entity type, exact source value, start offset, and exclusive end offset all to agree. Partial overlaps receive no credit. Macro metrics exclude types with zero gold support, as recorded by macro_entity_type_count = 9.

## Per-type results

| Entity type | Gold support | Predicted | Exact matches | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| case_sensitivity | 8 | 8 | 8 | 1.0000 | 1.0000 | 1.0000 |
| comparison_condition | 9 | 9 | 8 | 0.8889 | 0.8889 | 0.8889 |
| date_time | 10 | 4 | 1 | 0.2500 | 0.1000 | 0.1429 |
| file_extension | 32 | 23 | 20 | 0.8696 | 0.6250 | 0.7273 |
| file_name | 16 | 4 | 4 | 1.0000 | 0.2500 | 0.4000 |
| path | 24 | 19 | 18 | 0.9474 | 0.7500 | 0.8372 |
| port | 1 | 1 | 1 | 1.0000 | 1.0000 | 1.0000 |
| process_metric | 0 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 |
| process_name | 0 | 1 | 0 | 0.0000 | 0.0000 | 0.0000 |
| programming_language | 5 | 8 | 5 | 0.6250 | 1.0000 | 0.7692 |
| size | 8 | 8 | 8 | 1.0000 | 1.0000 | 1.0000 |

The process_name prediction is a false positive because the sample has no gold support for that entity type. process_metric has neither gold support nor predictions. The apparent perfect port score is based on one example and should not be generalized.

## Interpretation

The strongest supported results in this targeted sample are case_sensitivity, size, and path. The main gaps are temporal phrase recall (date_time, 1/10), filename recall (file_name, 4/16), and extension recall (file_extension, 20/32). These errors suggest missing extraction coverage for temporal expressions and filenames; they do not authorize tuning against this held-out sample.

The labels were AI-assisted and then approved by the project owner. The result measures agreement with that owner-approved annotation set, not independent ground truth. The sample is targeted, and several entity types have tiny or zero support. Both limitations must be stated alongside any reported metrics.

## Reproducibility

The committed one-time artifacts are:

- data/annotations/entity_test_human_review.csv
- data/annotations/entity_test_review_manifest.json
- artifacts/evaluation/entity_test_report.json
- artifacts/evaluation/entity_test_evaluation.lock

The evaluation was run locally from a fresh checkout of the committed project, after uv sync --locked. Do not remove the guard or rerun this held-out evaluation. Do not change extraction rules based on these results. Any future rule work must use separate development/challenge examples and be reported as post-test exploratory work.
