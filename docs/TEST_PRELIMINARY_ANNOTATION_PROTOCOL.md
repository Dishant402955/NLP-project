# Final Test Annotation Review Protocol

**Date:** 2026-11-17

## Purpose

The 375-row test worklist is the final held-out partition. The classifier, confidence threshold, local generator, prompt, and validation configuration have been frozen using training and development data. This protocol describes the final human intent review before the one-time test evaluation.

## Blind review worksheet

Open `data/annotations/test_human_review.csv`. It contains only:

- The stable `example_id`.
- The natural-language `request`.
- Blank `confirmed_intent`, `review_status`, and `reviewer_note` fields.

It contains no paired reference Bash commands, model predictions, or AI-suggested labels. The canonical `data/annotations/test_review.csv` remains untouched until the completed human decisions are imported.

## Decision rules

Read each request and choose one primary label from the [Intent Taxonomy](INTENT_TAXONOMY.md). Record the decision in `confirmed_intent` and set `review_status=confirmed`.

For a request that cannot be reliably assigned, choose `ambiguous` or `rejected`, leave `confirmed_intent` blank, and provide a concise rationale in `reviewer_note`. A confirmed `other_or_ambiguous` label also requires a reviewer note.

Review all 375 rows. Keep the example IDs and request text unchanged. Do not inspect paired reference commands or classifier predictions. Do not use test errors to revise the taxonomy, classifier, prompt, model, confidence threshold, or validation rules.

## Import and validate

From the repository root:

```bash
uv run nl2bash-annotations apply-test-review \
  --review-csv data/annotations/test_human_review.csv
uv run nl2bash-annotations validate --partition test
```

The importer verifies the source worklist checksum, IDs, and request text. It copies only the three human-decision fields into the canonical test worklist. It refuses incomplete reviews and validates taxonomy labels and required notes. The standard annotation validator then exports confirmed labels to `test_confirmed_intents.jsonl`.

The final test evaluation is performed once, after the human-reviewed export validates. No test labels or results may be used for tuning.
