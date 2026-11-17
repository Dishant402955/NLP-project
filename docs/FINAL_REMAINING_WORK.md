# Final Remaining Work

**Status date:** 2026-11-17

## Completed and verified

- Core hybrid NLP + local Qwen Bash-generation application, deterministic entity extraction, parse-only Bash validation, safety heuristics, and CLI are implemented.
- NL2Bash data partitions, annotation provenance, checksums, and frozen classifier/generation configuration are committed.
- The project owner reviewed the 500 training and 375 development intent annotations with zero further corrections.
- All 375 test intent proposals were accepted by the project owner without corrections. They remain AI-assisted and owner-approved, not independently adjudicated.
- The one-time classifier test evaluation completed successfully. Results: accuracy 0.6853, macro-F1 0.6400, weighted-F1 0.6793, macro precision 0.7854, macro recall 0.6186, and coverage 0.9947 (373/375) at the frozen development threshold 0.1361115729921777. Report: `artifacts/evaluation/test_report.json`; guard: `artifacts/evaluation/test_evaluation.lock`. **Do not rerun or reset this evaluation.**
- The ten-request generation v6 development comparison is recorded in `artifacts/evaluation/generation_dev_v6_report.json`.
- The entity exact-span evaluator and module CLI are implemented. Its 66-row targeted request-only AI suggestion sample, owner-review CSV, and manifest are committed. The [assistant-reviewed entity proposal sheet](ENTITY_ANNOTATION_REVIEW.md) contains the 66 requests, proposed exact spans, offsets, and review notes. The separate owner-review CSV remains blank/pending.
- A clean Python 3.10 `uv sync --locked` smoke run passed. All package CLI entry points, including `nl2bash-entity-eval`, imported and exposed help successfully.
- Parse-only Bash smoke checks accepted a safe command, flagged `sudo rm -rf /` as high risk, rejected invalid Bash syntax, and confirmed `executed: false` for all three. No generated command was executed.
- Entity sample checks passed: 66 distinct source examples/groups, checksums matched, all 119 original AI candidate spans matched their exact source offsets, and all 66 human-review rows remained pending.

## Remaining owner-review work

### 1. Entity benchmark review

Review all 66 rows in [Entity Annotation Review](ENTITY_ANNOTATION_REVIEW.md). Correct or approve the proposed entity types, exact values, and half-open offsets. After approval, populate `data/annotations/entity_test_human_review.csv`, mark each row confirmed, add reviewer notes, and record owner-review provenance in the manifest. Validate the complete worksheet and run the guarded entity test evaluator exactly once.

The sample is targeted, not prevalence-representative. It has no observed `process_name` or `process_metric` candidates and only one explicit port candidate. Any resulting metrics must display support and this limitation. Do not tune extraction rules using this held-out sample.

### 2. Command-generation v7 evaluation and semantic review

The 40-request paired development workflow has completed its model, frozen-configuration, and generation stages in a prior run, but that run's final Git push was rejected because `main` advanced during inference. The workflow now uploads its outputs and rebases before publishing. The corrected run is in progress.

When it completes, verify that `artifacts/evaluation/generation_dev_v7_report.json` and `data/annotations/generation_dev_v7_semantic_review.csv` are committed. The CSV contains 80 condition-masked candidates (two per request). Reviewers must see only request text and A/B commands; do not disclose the A/B-to-condition mapping until ratings are complete. Do not execute generated commands or use reference commands to create semantic ratings.

### 3. Final engineering audit

The clean locked Python 3.10 installation, package entry points, entity sample integrity, parse-only syntax checks, and high-risk detection smoke checks have passed in GitHub Actions. The generation v7 workflow also verifies the pinned CPU runtime, Qwen model checksum, and frozen configuration before evaluation.

After the outstanding owner reviews, complete the remaining adversarial/integration review for malformed model output, missing model/runtime, unresolved or invented constraints, and frozen-configuration mismatch. Reconfirm that no temporary test scripts/fixtures, caches, virtual environments, or secrets are committed. Preserve the user's existing uncommitted workspace; the remote coding-agent workspace was previously dirty and stale, so it must not be reset or cleaned to perform this audit.

### 4. Academic submission

After the entity and command-generation reviews and final audit, prepare the final report, presentation, and demonstration. Include dataset and license provenance, AI-assisted annotation limitations, architecture, classifier metrics and per-class support, exact-span entity metrics and coverage limits, generation metrics and blind semantic ratings, error analysis, safety boundaries, and reproducibility details. Do not invent missing results.

## Evaluation safeguards

- The one-time classifier test report and guard are complete. Do not rerun them.
- Entity test evaluation is one-time and must not run until all 66 owner decisions are finalized and provenance is recorded.
- The frozen model, prompt, classifier, threshold, and safety rules must not be tuned using held-out test data.
- Generated Bash commands are proposals only; never execute them as part of generation or evaluation.
- Keep temporary test source and fixtures outside Git.
