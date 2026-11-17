# Intent Annotation Audit Log

**Audit date:** 2026-11-17
**Review type:** AI-assisted second-pass audit; not independent human adjudication
**Partitions reviewed:** training (500 rows) and development (375 rows)
**Test partition:** not opened, labelled, or modified

## Scope and method

The complete training and development worklists were reviewed from their natural-language request fields against the written intent taxonomy. The paired Bash commands were not used to infer labels. Existing source IDs, duplicate-group IDs, request text, reference commands, suggestion fields, and review statuses were preserved.

Three review passes were applied:

1. **Request-level pass:** read every training and development request in sequence and assess whether the recorded label matches the requested primary outcome.
2. **Boundary pass:** examine cross-category cases, especially ownership/permission filters versus file discovery, file-path discovery versus content search, shell state versus system information, process lifecycle, remote operations, and archive tasks versus unsupported operations.
3. **Adversarial correction pass:** recheck each proposed change against the taxonomy definition and boundary examples, confirm its source ID and prior label, add an explanatory reviewer note, and run the annotation validators and model pipeline. A tentative SSH-key-passphrase relabel was rejected: SSH authentication setup remains under `network_remote_operations`.

This is repeated review by the same AI system, not independent annotator agreement. The results remain provisional and require human adjudication before final academic claims.

## Corrections

A total of **30 labels** changed: 10 training labels and 20 development labels. All rows remain in the `confirmed` workflow state, but the reviewer notes now explicitly identify the second-pass AI audit and rationale.

### Training partition (10 corrections)

| Previous label | New label | Example IDs | Rationale |
|---|---|---|---|
| `file_discovery` | `permissions_ownership` | `nl2bash-002932`, `nl2bash-003947`, `nl2bash-003289`, `nl2bash-011304`, `nl2bash-003475`, `nl2bash-011221` | Requests filter entries by owner, group, or execute-permission bits. |
| `archive_compression` | `other_or_ambiguous` | `nl2bash-009501`, `nl2bash-009403` | One request imports decompressed SQL into MySQL; the other splits an archive file into fixed-size pieces. Neither primary outcome is archive creation/extraction/compression. |
| `other_or_ambiguous` | `file_directory_management` | `nl2bash-005566`, `nl2bash-000881` | Both requests copy a file into a local Docker container filesystem. |

### Development partition (20 corrections)

| Previous label | New label | Example IDs | Rationale |
|---|---|---|---|
| `file_discovery` | `permissions_ownership` | `nl2bash-001519`, `nl2bash-002389`, `nl2bash-002397`, `nl2bash-002398`, `nl2bash-002906`, `nl2bash-002917`, `nl2bash-003264`, `nl2bash-003731`, `nl2bash-003748`, `nl2bash-004062`, `nl2bash-004066`, `nl2bash-008515`, `nl2bash-010840` | Requests select files by owner, group, access mode, SUID/sticky bit, writability, or readability. |
| `other_or_ambiguous` | `system_information` | `nl2bash-004757` | Displays a calendar and highlights the current day. |
| `file_discovery` | `shell_environment_session` | `nl2bash-006386` | Queries the base name of the current working directory. |
| `system_information` | `other_or_ambiguous` | `nl2bash-007221`, `nl2bash-007310` | Change mount propagation or mount mode; these are system-configuration changes, not information queries. |
| `other_or_ambiguous` | `shell_environment_session` | `nl2bash-008006` | Sets an environment variable for a command invocation. |
| `other_or_ambiguous` | `process_job_management` | `nl2bash-008011`, `nl2bash-009423` | Launches an application/process in a terminal/background context. |

## Rebuilt artifacts

After the corrections:

- The training annotation validator exported 500 confirmed rows.
- The development annotation validator exported 375 confirmed rows.
- The classifier was retrained from the corrected training export.
- The development confidence threshold was selected again from the corrected development export.
- The refreshed threshold manifest was checked against the exact model SHA-256 and development-export SHA-256.
- A prediction smoke check successfully loaded the model and the refreshed frozen threshold.

The updated development metrics are recorded in [Annotation Review Status](ANNOTATION_REVIEW_STATUS.md). They are provisional diagnostics only. No test labels or test evaluation were used.

The post-audit change was checked in **ten separate verification passes**: row identity/order; immutable source fields; exact correction counts and valid labels; review states and per-row rationales; CSV-to-export parity; annotation-manifest checksums; unchanged test artifacts and empty test export; model-manifest provenance; frozen-threshold/model/development provenance and coverage; and documentation links, stale-metric checks, package compilation, and changed-path hygiene. All ten passes succeeded.

## Limitations and next action

The training and development annotations are AI-assisted and were reviewed by the project owner; this is not an inter-annotator agreement study. **Subsequent test annotation update (2026-11-17):** after the classifier, threshold, generator, prompt, and validator were frozen, request-only AI suggestions were created for the 375 test requests. The project owner accepted all 375 suggestions without corrections. No reference commands or classifier predictions were used to generate the suggestions. The test export and provenance are recorded separately in [Annotation Review Status](ANNOTATION_REVIEW_STATUS.md). These test labels are AI-assisted and owner-approved, not independently adjudicated ground truth.
