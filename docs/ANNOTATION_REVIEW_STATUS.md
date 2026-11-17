# Annotation Review Status

**Status date:** 2026-11-17

## Current annotation state

| Partition | Worklist rows | Confirmed export | Pending | Current use |
|---|---:|---:|---:|---|
| Training | 500 | 500 | 0 | Model fitting |
| Development | 375 | 375 | 0 | Model and threshold development |
| Test | 375 | 375 | 0 | One-time held-out classifier evaluation completed |

The training and development annotations were initially AI-assisted. A second-pass AI audit changed 30 labels (10 training, 20 development); see [Intent Audit Log](INTENT_AUDIT_LOG.md). The project owner subsequently reviewed all 875 rows and reported zero further changes. See [Human Review Attestation](HUMAN_REVIEW_ATTESTATION.md).

The test annotation suggestions were created from the 375 natural-language requests only. The suggestion pass did not use paired reference commands or classifier predictions. The project owner reviewed all 375 suggestions and accepted every suggestion without correction. The canonical test worklist and confirmed JSONL export now contain 375 confirmed labels. The annotation export manifest records this provenance and explicitly does not claim independent adjudication.

**Interpretation caveat:** the test labels are AI-assisted and owner-approved, not independently annotated ground truth. The classifier test metrics will measure agreement with these labels. This is weaker evidence than a separately annotated or independently adjudicated test set and must be disclosed in the report.

The test worklist and export passed the project CLI validator: all 375 IDs and duplicate-group IDs match, request and reference-command source pairs match, all labels belong to the ten-label taxonomy, all rows are confirmed, all 22 `other_or_ambiguous` rows have reviewer notes, and the reviewed-CSV/export SHA-256 values match their manifests. The clean Python 3.10 `uv sync --locked` run and one-time classifier evaluation succeeded in GitHub Actions.

## Test label distribution

| Intent | Test |
|---|---:|
| `archive_compression` | 14 |
| `file_directory_management` | 58 |
| `file_discovery` | 125 |
| `network_remote_operations` | 11 |
| `other_or_ambiguous` | 22 |
| `permissions_ownership` | 48 |
| `process_job_management` | 6 |
| `shell_environment_session` | 15 |
| `system_information` | 16 |
| `text_search_processing` | 60 |
| **Total** | **375** |

The test partition is imbalanced. `file_discovery` has 125 examples while `process_job_management` has six. Per-class support and metrics must be shown alongside macro averages.

## Training and development label provenance

| Intent | Training | Development |
|---|---:|---:|
| `archive_compression` | 37 | 9 |
| `file_directory_management` | 54 | 67 |
| `file_discovery` | 51 | 125 |
| `network_remote_operations` | 50 | 9 |
| `other_or_ambiguous` | 54 | 21 |
| `permissions_ownership` | 54 | 31 |
| `process_job_management` | 42 | 6 |
| `shell_environment_session` | 76 | 29 |
| `system_information` | 22 | 14 |
| `text_search_processing` | 60 | 64 |

## Development classifier diagnostics

The classifier was fitted on the 500 confirmed training rows. Its confidence threshold was selected on the 375 confirmed development rows by maximizing macro-F1 subject to at least 80% prediction coverage. A fresh retraining in a temporary location reproduced every development prediction and every class probability exactly; reselecting the threshold returned the same value.

| Metric | Development result |
|---|---:|
| Accuracy | 0.6880 |
| Macro-F1 | 0.6709 |
| Weighted-F1 | 0.6801 |
| Prediction coverage | 0.9893 |
| Low-confidence requests | 4 / 375 |
| Frozen confidence threshold | 0.1361115729921777 |

These are development-set results, not final test results. The model scores are uncalibrated probability estimates.

## Final held-out classifier result

<badge color="success">One-time evaluation completed</badge>

The classifier was evaluated once on all 375 confirmed test examples using the frozen development-selected threshold of `0.1361115729921777`. The model and threshold checksums are recorded in `artifacts/evaluation/test_report.json`; the completed one-time guard is `artifacts/evaluation/test_evaluation.lock`.

| Metric | Test result |
|---|---:|
| Accuracy | 0.6853 |
| Macro precision | 0.7854 |
| Macro recall | 0.6186 |
| Macro-F1 | 0.6400 |
| Weighted precision | 0.7285 |
| Weighted recall | 0.6853 |
| Weighted-F1 | 0.6793 |
| Prediction coverage | 0.9947 |
| Low-confidence requests | 2 / 375 |
| Frozen threshold | 0.1361115729921777 |

Per-class test F1:

| Intent | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| `archive_compression` | 14 | 1.0000 | 0.7143 | 0.8333 |
| `file_directory_management` | 58 | 0.8214 | 0.7931 | 0.8070 |
| `file_discovery` | 125 | 0.6577 | 0.7840 | 0.7153 |
| `network_remote_operations` | 11 | 1.0000 | 0.8182 | 0.9000 |
| `other_or_ambiguous` | 22 | 0.5385 | 0.3182 | 0.4000 |
| `permissions_ownership` | 48 | 0.8235 | 0.5833 | 0.6829 |
| `process_job_management` | 6 | 1.0000 | 0.5000 | 0.6667 |
| `shell_environment_session` | 15 | 0.3514 | 0.8667 | 0.5000 |
| `system_information` | 16 | 1.0000 | 0.1250 | 0.2222 |
| `text_search_processing` | 60 | 0.6613 | 0.6833 | 0.6721 |

**Interpretation:** macro-F1 is materially lower than the development macro-F1 (0.6709 vs 0.6400), with particularly weak recall for `system_information` and `other_or_ambiguous`. Supports are small for several classes. Because the 375 test labels were AI-proposed and then accepted by the project owner, these results are agreement with an AI-assisted owner-approved label set, not a fully independent gold-standard estimate. The one-time test guard is complete; do not rerun this evaluation.

## Frozen configuration and remaining evaluation

The classifier artifact, development-selected confidence threshold, local command-generation model, prompt, runtime settings, and validation configuration are frozen. Test annotations must not be used to change them.

## Entity benchmark result

The project owner reviewed all 66 request-only AI-assisted entity proposals and requested no corrections. The canonical CSV records 66 confirmed rows, 113 exact spans, and eight approved empty rows, with per-row notes. The manifest records owner-review provenance and explicitly does not claim independent annotation.

The guarded exact-span entity test evaluation ran once. It produced 0.8588 micro precision, 0.6460 micro recall, 0.7374 micro F1, and 0.7517 macro-F1 over nine entity types with gold support. Per-type results and support appear in [Entity Evaluation](ENTITY_EVALUATION.md). The sample is targeted rather than prevalence-representative; it has zero gold support for process_name and process_metric and only one port example. Do not rerun the evaluation or tune extraction rules on this held-out sample.

## Remaining work

1. The 40-request generation v7 development comparison is complete. A separate assistant-only pass rated all 80 A/B candidates (11 correct, 25 partial, 44 incorrect/unsafe); see [Generation v7 Assistant Semantic Review](GENERATION_V7_ASSISTANT_REVIEW.md). The original owner-facing worksheet remains blank, so owner semantic sign-off is still pending. Do not execute candidates or use reference commands to determine ratings. Keep the A/B-to-condition mapping hidden until owner ratings are finalized.
2. The final engineering audit completed its selected clean-install, malformed-output, missing-model/runtime, grounding, frozen-checksum, and parse-only safety checks. Known gaps are recorded in [Engineering Audit](ENGINEERING_AUDIT.md); do not patch the frozen pipeline without a new development evaluation.
3. Prepare the final report, presentation, and demonstration. Include classifier and entity results, generation metrics plus semantic-review status, dataset/license provenance, AI-assisted annotation limitations, error analysis, safety boundaries, and reproducibility details. Do not invent missing semantic ratings.
