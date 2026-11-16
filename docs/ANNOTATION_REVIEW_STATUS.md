# Annotation Review Status

**Status date:** 2026-11-16

## Current versioned annotation state

| Partition | Worklist size | Confirmed export | Pending | Use
|---|---:|---:|---:|---|
| Training | 500 | 500 | 0 | Provisional model fitting
| Development | 375 | 375 | 0 | Provisional threshold selection
| Test | 375 | 0 | 375 | Sealed; do not inspect or label until configuration is frozen

The training and development annotations were generated through an AI-assisted review of each natural-language request against the project intent taxonomy. The development review did not use heuristic suggestions, classifier predictions, or paired Bash commands. The training review also assigned labels from the request text rather than promoting the generated suggestions.

Every annotation note records that the decision is AI-assisted. The local validator confirms source identity, partition provenance, allowed labels, review status, and output checksums. It does not establish that an annotation was made by a human or that multiple annotators agree.

## Observed label distribution

| Intent | Training | Development |
|---|---:|---:|
| `archive_compression` | 39 | 9 |
| `file_directory_management` | 52 | 67 |
| `file_discovery` | 57 | 139 |
| `network_remote_operations` | 50 | 9 |
| `other_or_ambiguous` | 54 | 23 |
| `permissions_ownership` | 48 | 18 |
| `process_job_management` | 42 | 4 |
| `shell_environment_session` | 76 | 27 |
| `system_information` | 22 | 15 |
| `text_search_processing` | 60 | 64 |

The development sample is notably imbalanced, especially for file discovery and process management. Macro-F1 therefore averages over classes with very different support; per-class results and support must be considered alongside the aggregate score.

## Provisional classifier run

The training export contains all ten taxonomy labels and passes the per-label training minimum. The TF-IDF/Logistic Regression baseline was fitted from 500 training examples. The development threshold was selected using 375 development examples, maximizing macro-F1 subject to at least 80% coverage.

| Metric | Provisional result |
|---|---:|
| Development accuracy | 0.7147 |
| Development macro-F1 | 0.7136 |
| Development weighted-F1 | 0.7020 |
| Prediction coverage | 0.9867 |
| Selected confidence threshold | 0.13653 |

These values are engineering diagnostics only. Since the same AI annotator labelled training and development, shared annotation bias can inflate or distort the apparent performance. Do not present these numbers as final research results or compare them as if they came from independent human ground truth.

## Required before final evaluation

1. Have a human reviewer independently audit the training and development decisions, especially borderline requests and the `other_or_ambiguous` category. Record corrections in the existing CSVs and rerun the validators.
2. Retrain the classifier and reselect the development threshold after any label changes.
3. Freeze the final taxonomy and model configuration.
4. Only then review the 375 test requests without predictions or paired commands, validate the test export, and run the one-time test evaluation.

The raw dataset and MIT notice, processed train/dev/test splits, annotation worklists and confirmed exports, classifier model and manifest, and frozen development-threshold artifact are versioned in Git. Their checksums and source revision are recorded in the accompanying manifests. Test labels remain pending and are not included in the confirmed export.
