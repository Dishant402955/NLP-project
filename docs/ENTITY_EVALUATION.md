# Entity Extraction Evaluation Protocol

**Evaluation date:** 2026-11-17  
**Partition:** held-out NL2Bash test requests  
**Sample:** 66 targeted requests, one per duplicate group  
**Evaluation policy:** exact entity type, exact source value, and exact character-span match

## Annotation provenance and scope

The project owner reviewed all 66 assistant-reviewed request-only proposal rows and requested no corrections. The confirmed review CSV contains 113 entity spans across 58 requests and eight approved empty-entity rows. The corresponding manifest records the owner-approved review provenance and explicitly states that the labels are AI-assisted, not independently annotated ground truth.

The sample was selected to exercise explicit entity cues. It is not a prevalence-representative random sample. It has one gold port span and no gold process_name or process_metric spans. It should therefore be treated as a targeted engineering sample, not a corpus-wide estimate.

## Evaluation method

A match requires the entity type, exact source value, start offset, and exclusive end offset all to agree. Partial overlaps receive no credit. The evaluator validates the review CSV against the test partition, source worklist and manifest checksums, example/group IDs, normalized request text, exact offsets, row status, reviewer notes, and owner-review provenance.

The one-time guarded evaluation has been completed. Component-level score values are intentionally omitted from the committed report artifact. The artifact retains the evaluation-completion status, sample metadata, annotation provenance, and source checksums for audit. The project report and README focus on the paired end-to-end comparison between the raw LLM request-only baseline and the final NLP-context system.

## Interpretation limits

- The annotations were AI-assisted and approved by the project owner; they are not independent ground truth.
- The sample was targeted to exercise explicit entity cues, not randomly drawn to estimate corpus prevalence.
- Some entity types have no gold examples, while the port category has only one example.
- The benchmark must not be rerun or used to tune extraction rules on this held-out sample.

## Reproducibility

The committed one-time artifacts are:

- `data/annotations/entity_test_human_review.csv`
- `data/annotations/entity_test_review_manifest.json`
- `artifacts/evaluation/entity_test_report.json`
- `artifacts/evaluation/entity_test_evaluation.lock`

The evaluation was run locally from a fresh checkout of the committed project, after `uv sync --locked`. Do not remove the guard or rerun this held-out evaluation. Do not change extraction rules based on this sample. Any future rule work must use separate development/challenge examples and be reported as post-test exploratory work.
