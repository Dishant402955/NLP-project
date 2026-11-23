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

## Component evaluation status

The classifier's development diagnostics and one-time held-out evaluation were completed and are retained in the canonical artifacts with their source and annotation checksums. Their component-level scores are not included in the report's headline results. The project-level quantitative comparison is the paired raw LLM request-only baseline versus the final NLP-context system, described in [Command-Generation Evaluation](GENERATION_EVALUATION.md).

## Frozen configuration and remaining evaluation

The classifier artifact, development-selected confidence threshold, local command-generation model, prompt, runtime settings, and validation configuration are frozen. Test annotations must not be used to change them.

## Entity benchmark result

The project owner reviewed all 66 request-only AI-assisted entity proposals and requested no corrections. The canonical CSV records 66 confirmed rows, 113 exact spans, and eight approved empty rows, with per-row notes. The manifest records owner-review provenance and explicitly does not claim independent annotation.

The guarded exact-span entity evaluation ran once on this targeted sample. Its report and guard are retained as reproducibility artifacts, but component-level entity scores are not included in the headline project results. The sample is targeted rather than prevalence-representative; it has zero gold support for process_name and process_metric and only one port example. Do not rerun the evaluation or tune extraction rules on this held-out sample.

## Final review and completion status

1. **Generation v7 human semantic review: complete.** The project owner confirmed that all 80 candidates from the 40-request v7 development comparison were reviewed. The completion attestation is `data/annotations/generation_dev_v7_human_review_attestation.json`. The confirmation did not include row-level ratings or comments, so no human aggregate score or A/B condition comparison is published. The original candidate CSV remains unchanged rather than receiving invented ratings.
2. **Engineering audit: complete for the selected checks.** Clean install, CLI entry points, malformed-output rejection, missing-model/runtime fail-closed behavior, selected constraint grounding, frozen-component checksum rejection, and parse-only safety checks passed. Known limitations remain documented in [Engineering Audit](ENGINEERING_AUDIT.md); the audit is not a formal safety guarantee.
3. **Presentation: approved and complete.** The project owner confirmed the presentation is good and requires no further project edits.
4. **Technical project status: complete.** No additional feature implementation or held-out evaluation is required. Use the [Reproducibility Guide](REPRODUCIBILITY.md) for clean-clone setup and safe reproduction.

Institution-specific details such as college, department, supervisor, student identifiers, submission date, and declaration wording belong in the final report only where the institution requires them. They do not change the technical completion status.

## Evaluation safeguards

- The one-time classifier test report and guard are complete. Do not rerun them.
- The one-time entity test report and guard are complete. Do not rerun them.
- Keep the frozen model, prompt, classifier, threshold, and safety rules unchanged for the published results.
- Generated Bash commands are proposals only; never execute them as part of generation or evaluation.
- The entity test sample is targeted, not prevalence-representative, and its labels are AI-assisted and owner-approved rather than independently adjudicated.
- The generation human-review milestone is attested as complete, but row-level human score values were not included in the completion record. Do not report numeric human semantic metrics.
- Keep temporary test source and fixtures outside Git.
