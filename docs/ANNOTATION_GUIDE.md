# Intent Annotation Guide

## 1. Purpose

This guide explains how to review the local intent-annotation pilot for the Natural Language to Bash Command Generator.

The pilot is a manually reviewed dataset artifact. The suggested labels are weak hints generated from request-text patterns. They are not ground truth and must not be used for model training until a reviewer confirms them.

## 2. Files

The annotation workflow creates these local files:

- data/annotations/intent_pilot.csv: the editable review worklist.
- data/annotations/intent_pilot_manifest.json: source checksum, pilot seed, quotas, selected IDs, and suggestion metadata.

These files are excluded from Git. Keep reviewed copies in the same local annotation directory.

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

## 4. Blind development and test review

Development and test annotations are separate from the training pilot. They must be reviewed without heuristic suggestions so the evaluation labels are not influenced by the same rules used to create the training suggestions.

Create both held-out review files:

    .venv/bin/nl2bash-annotations create --partition dev
    .venv/bin/nl2bash-annotations create --partition test

Each command selects one original record from every duplicate group in that partition. The current partitions produce 375 review rows each. The suggestion columns are intentionally blank, and all rows begin pending.

Review each request using the intent taxonomy. Do not use model predictions or the paired command to infer the label. The paired command is shown only as context when the request is genuinely underspecified. Mark a row ambiguous or rejected when one primary label cannot be established.

Validate the reviewed files separately:

    .venv/bin/nl2bash-annotations validate --partition dev
    .venv/bin/nl2bash-annotations validate --partition test

The resulting exports are:

- data/annotations/dev_confirmed_intents.jsonl
- data/annotations/test_confirmed_intents.jsonl

Each export records its own partition name and checksum. The classifier training loader rejects development and test exports. Use development labels only for threshold/configuration selection. Keep test labels untouched until the classifier configuration is frozen, then evaluate on the test partition once.

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
