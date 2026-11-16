# Annotation Review Status

**Status date:** 2026-11-17

## Current versioned annotation state

| Partition | Worklist size | Confirmed export | Pending | Use
|---|---:|---:|---:|---|
| Training | 500 | 500 | 0 | Provisional model fitting
| Development | 375 | 375 | 0 | Provisional threshold selection
| Test | 375 | 0 | 375 | Sealed; do not inspect or label until configuration is frozen

The training and development annotations were initially generated through an AI-assisted review of each natural-language request against the project intent taxonomy. A second-pass AI audit reviewed all 875 annotated rows and changed 30 labels (10 training, 20 development); the detailed record is in [Intent Audit Log](INTENT_AUDIT_LOG.md). The development review did not use heuristic suggestions, classifier predictions, or paired Bash commands. The training review also assigned labels from the request text rather than promoting the generated suggestions.

Every annotation note records that the decision is AI-assisted, including the second-pass corrections. The validator confirms source identity, partition provenance, allowed labels, review status, and output checksums. It does not establish that an annotation was made by a human or that multiple annotators agree.

## Observed label distribution

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

The development sample is notably imbalanced, especially for file discovery and process management. Macro-F1 therefore averages over classes with very different support; per-class results and support must be considered alongside the aggregate score.

## Provisional classifier run

The corrected training export contains all ten taxonomy labels and passes the per-label training minimum. The TF-IDF/Logistic Regression baseline was retrained from 500 training examples. The development threshold was reselected using 375 development examples, maximizing macro-F1 subject to at least 80% coverage. The threshold artifact is bound to the current model and development-export checksums.

| Metric | Provisional result |
|---|---:|
| Development accuracy | 0.6880 |
| Development macro-F1 | 0.6709 |
| Development weighted-F1 | 0.6801 |
| Prediction coverage | 0.9893 |
| Low-confidence requests | 4 of 375 |
| Selected confidence threshold | 0.13611 |

These values are engineering diagnostics only. Since the same AI annotator labelled training and development, shared annotation bias can inflate or distort the apparent performance. Do not present these numbers as final research results or compare them as if they came from independent human ground truth.

## Required before final evaluation

1. Have a human reviewer independently audit the training and development decisions, especially borderline requests and the `other_or_ambiguous` category. Record corrections in the existing CSVs and rerun the validators.
2. After human corrections, retrain the classifier and reselect the development threshold again.
3. Freeze the final taxonomy and model configuration.
4. Only then review the 375 test requests without predictions or paired commands, validate the test export, and run the one-time test evaluation.

The raw dataset and MIT notice, processed train/dev/test splits, annotation worklists and confirmed exports, classifier model and manifest, and frozen development-threshold artifact are versioned in Git. The test worklist and test partition have not been opened or modified during this second-pass audit. Their checksums and source revision are recorded in the accompanying manifests. Test labels remain pending and are not included in the confirmed export.
