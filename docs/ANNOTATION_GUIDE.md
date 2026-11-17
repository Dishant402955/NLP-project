# Intent Annotation Guide

## 1. Purpose

This guide explains how to review the versioned intent-annotation worklists for the Natural Language to Bash Command Generator.

The worklists are project annotation artifacts. The training suggestions are weak hints generated from request-text patterns. They are not ground truth. Only explicitly confirmed labels are exported for model training.

**Current annotation provenance:** training and development labels were initially AI-assisted. The project owner subsequently reviewed all 875 rows and reported zero corrections; see [Human Review Attestation](HUMAN_REVIEW_ATTESTATION.md). The 375 test labels were proposed from request text only and all were accepted by the project owner without corrections. The test export manifest records this as AI-assisted, owner-approved annotation, not independent adjudication.

## 2. Files

The annotation workflow creates these versioned project files:

- data/annotations/intent_pilot.csv: the editable review worklist.
- data/annotations/intent_pilot_manifest.json: source checksum, pilot seed, quotas, selected IDs, and suggestion metadata.

These files are tracked in Git so annotation decisions, source identity, and provenance remain reviewable. Edit the worklist locally, validate it, then commit the updated CSV, confirmed export, and regenerated manifests together.

The CSV generator prefixes spreadsheet-formula-leading source text with an apostrophe so spreadsheet software treats it as text. The validator removes this protective prefix and verifies the original source text before importing annotations. Do not manually remove or alter the prefix.

## 3. Creating and validating the worklist

From the repository root, install the package and generate the worklist:

    uv pip install --python .venv/bin/python -e .
    .venv/bin/nl2bash-annotations create

The default command reads only the verified training partition and writes:

- data/annotations/intent_pilot.csv
- data/annotations/intent_pilot_manifest.json

Review the CSV using the decision rules below. Keep the source fields, suggestions, and suggestion reasons unchanged. Edit only confirmed_intent, review_status, and reviewer_note.

After review, validate and export confirmed labels:

    .venv/bin/nl2bash-annotations validate

The default export files are:

- data/annotations/confirmed_intents.jsonl
- data/annotations/confirmed_intents_manifest.json

The validator reports the number of confirmed, pending, ambiguous, and rejected rows. An all-pending worklist produces an empty confirmed JSONL file. That is expected; it is safer than quietly training on guesses.

Use the --help option on either subcommand to see options for alternate paths, pilot size, and seed.

## 4. Held-out development and test review

Development and test annotations use separate partition-specific worklists, with one source record selected from each duplicate group. The canonical worklists contain no heuristic suggestion labels. Training is restricted to confirmed training annotations; the development partition is used for threshold selection and development experiments only.

The 375 development labels were reviewed by the project owner after an AI-assisted annotation pass. The 375 test suggestions were generated from natural-language requests only, without paired reference commands or classifier predictions. The project owner reviewed all 375 suggestions and accepted them without corrections. The test worksheet and the separate suggestion artifact are retained so this provenance remains auditable.

The test annotation is therefore AI-assisted and owner-approved, not independently adjudicated ground truth. This limitation must be disclosed whenever test metrics are reported. Do not use test labels or results to tune the classifier, threshold, generator, prompt, entity extractor, or safety checks.

Validate the development and test exports separately:

    uv run nl2bash-annotations validate --partition dev
    uv run nl2bash-annotations validate --partition test

The test decisions have already been merged into `data/annotations/test_review.csv` and exported to `data/annotations/test_confirmed_intents.jsonl`. The checksum-bearing manifest is `data/annotations/test_confirmed_intents_manifest.json`. The CLI validator still needs to be run in the project Python environment before the one-time held-out classifier evaluation.

## 5. CSV columns

| Column | Reviewer action |
|---|---|
| example_id | Do not edit. Stable ID from the source training record. |
| group_id | Do not edit. Duplicate-linked records must remain auditable. |
| request | Do not edit. This is the text the classifier will learn from. |
| reference_command | Do not edit. Use it only as context when the request is unclear. |
| suggested_intent | Do not edit. This is a weak automated suggestion, not a confirmed label. |
| suggestion_reason | Do not edit. It explains which request-text rule produced the suggestion. |
| confirmed_intent | Enter one taxonomy label only after reviewing the request. |
| review_status | Change pending to confirmed, ambiguous, or rejected. |
| reviewer_note | Record why an item is ambiguous/rejected. A note is required for other_or_ambiguous. |

## 6. Review decisions

Use exactly these review statuses:

- pending: not reviewed yet. Leave confirmed_intent blank.
- confirmed: the reviewer selected a valid label from the taxonomy and entered it in confirmed_intent.
- ambiguous: the request cannot be assigned to one primary intent with reasonable confidence. Leave confirmed_intent blank and explain why in reviewer_note.
- rejected: the source pair is unusable for annotation, for example because the request and reference command do not correspond. Leave confirmed_intent blank and explain why in reviewer_note.

Use other_or_ambiguous as a confirmed label when the request is clearly outside the supported operation categories or the requested outcome combines independent operations. Use the ambiguous status when a reliable single label cannot be selected even after considering the reference command.

## 7. Annotation rules

1. The natural-language request is the classifier input and the primary basis for its label.
2. Read the entire request before deciding. Do not label a request solely from its first word or from the first utility in the reference command.
3. Use the reference command only as supporting context when the request is genuinely underspecified.
4. Assign one primary intent based on the requested outcome. Do not split a pipeline into several labels.
5. Apply the boundary rules and examples in the [Intent Taxonomy](INTENT_TAXONOMY.md).
6. Correct a wrong suggested label by entering the appropriate label in confirmed_intent; do not edit the suggestion column.
7. Do not confirm a label when the pair is unclear or mismatched. Use ambiguous or rejected with a note.

## 8. Valid labels

The confirmed_intent field accepts only:

- file_discovery
- text_search_processing
- file_directory_management
- permissions_ownership
- process_job_management
- system_information
- network_remote_operations
- archive_compression
- shell_environment_session
- other_or_ambiguous

The spelling must match exactly.

## 9. Import and training policy

The annotation validator checks that:
- The selected partition name and source checksum match the worklist manifest.
- All pilot example IDs and group IDs are present exactly once.
- Source request and command text have not been changed.
- Suggested labels and reasons have not been modified.
- Confirmed labels are valid taxonomy labels.
- Pending, ambiguous, and rejected rows do not contain confirmed labels.
- Ambiguous and rejected rows include reviewer notes.
- A confirmed other_or_ambiguous label includes a reviewer note.
- The CSV path and source training checksum match the pilot manifest.

Only rows explicitly marked confirmed are exported to the confirmed annotation JSONL file. Pending, ambiguous, and rejected rows are excluded. The confirmed-output manifest includes a checksum of the reviewed CSV and of the exported JSONL file. No heuristic suggestion is ever promoted automatically.

## 10. Final test review outcome

The final 375-row review is complete. The project owner accepted all 375 request-only AI-proposed labels with zero corrections. The canonical worklist `data/annotations/test_review.csv` now contains the confirmed decisions, and `data/annotations/test_confirmed_intents.jsonl` contains 375 confirmed records.

The suggestion source and review provenance are recorded in `data/annotations/test_ai_suggestions.csv`, `data/annotations/test_ai_suggestions_manifest.json`, and `data/annotations/test_confirmed_intents_manifest.json`. The suggestion pass used request text only; the project owner was shown the suggestions. Therefore, the labels are AI-assisted and owner-approved, not independent human gold labels.

The CLI import step has already been completed in the repository artifacts. Do not run `apply-test-review` again: the canonical source worklist has changed since the import manifest's original checksum. Run the standard validator:

```bash
uv sync --locked
uv run nl2bash-annotations validate --partition test
```

After the validator passes, run the one-time classifier test evaluation:

```bash
uv run nl2bash-classifier evaluate-test
```

Do not use test results to tune the evaluated configuration. Disclose the annotation provenance in the final report.

