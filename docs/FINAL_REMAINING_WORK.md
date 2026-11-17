# Final Remaining Work

**Status date:** 2026-11-17

## Completed and verified

- Core hybrid NLP + local Qwen Bash-generation application, deterministic entity extraction, parse-only Bash validation, safety heuristics, and end-to-end CLI are implemented.
- NL2Bash data partitions, annotation provenance, checksums, and frozen classifier/generation configuration are committed.
- The project owner reviewed the 500 training and 375 development intent annotations after AI-assisted labelling and reported zero further corrections.
- All 375 test intent proposals were accepted by the project owner without corrections. They remain AI-assisted and owner-approved, not independently adjudicated.
- The one-time classifier test evaluation completed successfully. Results: accuracy 0.6853, macro-F1 0.6400, weighted-F1 0.6793, macro precision 0.7854, macro recall 0.6186, and coverage 0.9947 (373/375) at the frozen development threshold 0.1361115729921777. Report: artifacts/evaluation/test_report.json; guard: artifacts/evaluation/test_evaluation.lock. Do not rerun or reset this evaluation.
- The ten-request generation v6 development comparison is recorded in artifacts/evaluation/generation_dev_v6_report.json.
- The 40-request paired generation v7 development comparison completed successfully on the frozen model, prompt, classifier, threshold, and pipeline. Its report is artifacts/evaluation/generation_dev_v7_report.json; its 80-row condition-masked semantic worksheet is data/annotations/generation_dev_v7_semantic_review.csv. No test data was used and no generated command was executed.
- The project owner reviewed all 66 assistant-reviewed entity proposals and requested no corrections. The confirmed review CSV contains 113 exact spans across 58 requests and eight approved empty-entity rows. The provenance manifest explicitly describes the labels as AI-assisted and owner-approved, not independently annotated.
- The guarded entity exact-span test evaluation ran once locally from a fresh checkout after uv sync --locked. Results: micro precision 0.8588, recall 0.6460, F1 0.7374; macro-F1 0.7517 across nine entity types with gold support. Full per-type metrics and support are in docs/ENTITY_EVALUATION.md and artifacts/evaluation/entity_test_report.json; the one-time guard is artifacts/evaluation/entity_test_evaluation.lock. Do not rerun or reset this evaluation.
- A clean Python 3.10 uv sync --locked smoke run passed in GitHub Actions. The current local fresh checkout also synchronized successfully and exposed the entity evaluator module CLI.
- Parse-only Bash smoke checks accepted a safe command, flagged sudo rm -rf / as high risk, rejected invalid Bash syntax, and confirmed executed: false for all three. No generated command was executed.
- Entity sample integrity checks passed: 66 distinct source examples/groups, source checksums matched, and every reviewed span matched its exact request offsets.

## Remaining work

### 1. Owner semantic sign-off

A separate assistant-only pass rated all 80 v7 candidates: 11 correct as written, 25 partial, and 44 incorrect or unsafe. The ratings and rubric are in docs/GENERATION_V7_ASSISTANT_REVIEW.md and data/annotations/generation_dev_v7_assistant_semantic_review.csv. This is preliminary assistant feedback, not human gold labels or independent adjudication. The original owner-facing worksheet remains blank. If the project requires an owner-confirmed semantic benchmark, that worksheet still needs ratings; keep its A/B-to-condition mapping hidden until those ratings are finalized.

The automated v7 report records generation success, syntax validity, selected constraint-pass counts, exact-match counts, warning counts, and latency. These are not substitutes for semantic correctness ratings.

### 2. Engineering audit

The selected clean-install, malformed-output, missing-model/runtime, grounding, frozen-checksum, and parse-only safety checks passed locally. Known validator gaps are documented in docs/ENGINEERING_AUDIT.md. Any post-freeze code changes require a separate development configuration/evaluation and must not use held-out test data. Do not reset or clean the user's original /home/user/projects/remote-coding-agent/workspace.

### 3. Academic submission

Prepare the final report, presentation, and demonstration using the completed classifier and entity metrics, automated generation v7 metrics, and clearly labelled preliminary assistant semantic review. Disclose that owner-facing semantic ratings remain blank and that the engineering audit found validator limitations. Include dataset and license provenance, AI-assisted annotation limitations, architecture, per-class support, entity coverage limitations, error analysis, safety boundaries, and reproducibility details. Do not invent missing results.

## Evaluation safeguards

- The one-time classifier test report and guard are complete. Do not rerun them.
- The one-time entity test report and guard are complete. Do not rerun them.
- The frozen model, prompt, classifier, threshold, and safety rules must not be tuned using held-out test data.
- Generated Bash commands are proposals only; never execute them as part of generation or evaluation.
- The entity test sample is targeted, not prevalence-representative, and the labels are AI-assisted and owner-approved rather than independently adjudicated.
- Keep temporary test source and fixtures outside Git.
