# Annotation Review Status

**Status date:** 2026-11-17

## Current annotation state

| Partition | Worklist rows | Confirmed export | Pending | Current use |
|---|---:|---:|---:|---|
| Training | 500 | 500 | 0 | Model fitting |
| Development | 375 | 375 | 0 | Model and threshold development |
| Test | 375 | 0 | 375 | Sealed; final independent review is pending |

The training and development annotations were initially created through an AI-assisted review of the natural-language requests against the project taxonomy. A second-pass AI audit changed 30 labels (10 training, 20 development); see [Intent Audit Log](INTENT_AUDIT_LOG.md). On 2026-11-17, the project owner independently reviewed all 875 rows and reported zero further changes. The final human-review attestation is recorded in [Human Review Attestation](HUMAN_REVIEW_ATTESTATION.md). Original row notes retain the AI-assisted origin of the initial labels; the attestation records the later human review and agreement.

Both reviewed annotation files pass their source, partition, label, status, and checksum validators. The training export has 500 confirmed rows; the development export has 375 confirmed rows. The test CSV remains 375 pending rows and its confirmed export is empty. No test labels or test metrics have been used.

## Label distribution

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

The development set is imbalanced. For example, `file_discovery` has 125 examples while `process_job_management` has six. Per-class support and metrics must be shown alongside macro averages.

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

These are development-set results, not final test results. The model scores are uncalibrated probability estimates. The test set remains sealed and has not been used for model or prompt selection.

## Final test protocol

The taxonomy, classifier artifact, confidence threshold, local command-generation model, prompt version, and validation configuration are now frozen. A blind human review worksheet is prepared at `data/annotations/test_human_review.csv`. It contains only the 375 natural-language requests, stable IDs, and blank human-decision fields; it contains no reference commands or AI suggestions. The canonical test worklist remains sealed with 375 pending rows. Only the project owner's final human decisions can be merged into the canonical worklist. See [Test Review Protocol](TEST_PRELIMINARY_ANNOTATION_PROTOCOL.md). The one-time test evaluation will run only after the test export validates.

No test examples may be used to revise intent labels, prompt text, model parameters, thresholds, or safety rules. Any future implementation change motivated by test errors must be reported as post-test exploratory work, not as part of the evaluated system.
