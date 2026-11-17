# Annotation Review Status

**Status date:** 2026-11-17

## Current annotation state

| Partition | Worklist rows | Confirmed export | Pending | Current use |
|---|---:|---:|---:|---|
| Training | 500 | 500 | 0 | Model fitting |
| Development | 375 | 375 | 0 | Model and threshold development |
| Test | 375 | 375 | 0 | One-time held-out classifier evaluation pending |

The training and development annotations were initially AI-assisted. A second-pass AI audit changed 30 labels (10 training, 20 development); see [Intent Audit Log](INTENT_AUDIT_LOG.md). The project owner subsequently reviewed all 875 rows and reported zero further changes. See [Human Review Attestation](HUMAN_REVIEW_ATTESTATION.md).

The test annotation suggestions were created from the 375 natural-language requests only. The suggestion pass did not use paired reference commands or classifier predictions. The project owner reviewed all 375 suggestions and accepted every suggestion without correction. The canonical test worklist and confirmed JSONL export now contain 375 confirmed labels. The annotation export manifest records this provenance and explicitly does not claim independent adjudication.

**Interpretation caveat:** the test labels are AI-assisted and owner-approved, not independently annotated ground truth. The classifier test metrics will measure agreement with these labels. This is weaker evidence than a separately annotated or independently adjudicated test set and must be disclosed in the report.

The test worklist and export were checked against the test partition: all 375 IDs and duplicate-group IDs match, request and reference-command source pairs match, all labels belong to the ten-label taxonomy, all rows are confirmed, all 22 `other_or_ambiguous` rows have reviewer notes, and the reviewed-CSV/export SHA-256 values match their manifests. The project CLI validator and model evaluation have not yet been executed in the target Python environment.

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

## Frozen configuration and remaining evaluation

The classifier artifact, development-selected confidence threshold, local command-generation model, prompt, runtime settings, and validation configuration are frozen. Test annotations must not be used to change them.

The next steps are:

1. Run `uv run nl2bash-annotations validate --partition test` in a clean project environment.
2. Run `uv run nl2bash-classifier evaluate-test` once and preserve the report and evaluation guard.
3. Build a separate manually adjudicated entity benchmark and report exact-span metrics. Do not tune extraction rules against its held-out portion.
4. Run a larger command-generation experiment and obtain human semantic-correctness ratings. The existing ten-request development comparison is an engineering sample only.
5. Complete the final clean-install, integration, and adversarial engineering audit.

No test result may be used to revise intent labels, prompt text, model parameters, thresholds, or safety rules. Any change motivated by test errors must be reported as post-test exploratory work, not as part of the evaluated system.
