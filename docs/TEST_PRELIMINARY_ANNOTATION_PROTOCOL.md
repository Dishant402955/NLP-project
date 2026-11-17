# Final Test Annotation Review and Provenance

**Date:** 2026-11-17  
**Status:** Completed; evaluation remains pending.

## Test annotation outcome

All 375 test requests have a confirmed intent label in:

- `data/annotations/test_review.csv`
- `data/annotations/test_confirmed_intents.jsonl`

The owner-reviewed worksheet is `data/annotations/test_human_review.csv`. The request-only AI suggestions and their provenance are recorded in:

- `data/annotations/test_ai_suggestions.csv`
- `data/annotations/test_ai_suggestions_manifest.json`

The project owner reviewed all 375 proposed labels and accepted them without corrections. The distribution is recorded in [Annotation Review Status](ANNOTATION_REVIEW_STATUS.md).

## Provenance and limitations

The suggestions were based only on the natural-language requests. The suggestion pass did not use reference Bash commands or predictions from the project's intent classifier. The project owner was shown the suggested labels and accepted all of them.

Therefore this is **request-only AI-assisted annotation with owner approval**, not independent human annotation and not an inter-annotator agreement study. The final report must disclose this limitation. Test classifier metrics measure agreement with these owner-approved AI-assisted labels; they must not be described as performance against independently adjudicated ground truth.

The reviewed worksheet itself contains no reference commands or classifier predictions. The canonical test worklist preserves the original source pair and records only the final owner-approved decisions. The test annotations must not be used to tune the classifier, threshold, generator, prompt, entity rules, or safety checks.

## Integrity checks

The published annotation export contains 375 records, all marked confirmed, with 375 unique example IDs and all ten taxonomy labels represented. The request, reference command, and duplicate-group identity of each record were checked against the source test partition. The 22 `other_or_ambiguous` labels have reviewer notes. The reviewed CSV and JSONL SHA-256 values match the checksums in `test_confirmed_intents_manifest.json`.

The files have been prepared to the schema enforced by the project validator. Run the CLI validator in the project environment before evaluating:

```bash
uv sync --locked
uv run nl2bash-annotations validate --partition test
```

The repository-side construction and checksum checks do not substitute for that runtime validator invocation.

## One-time classifier test evaluation

After the annotation validator passes, run exactly once:

```bash
uv run nl2bash-classifier evaluate-test
```

The command uses the frozen development threshold and writes `artifacts/evaluation/test_report.json`. It also creates `artifacts/evaluation/test_evaluation.lock` to prevent an accidental second evaluation. Do not delete or reset that guard unless the evaluation process was inspected and confirmed to have failed before producing a report.

Report accuracy, macro/weighted and per-class precision/recall/F1, per-class support, confusion matrix, coverage, low-confidence count, model checksum, test partition checksum, annotation checksum, and the frozen threshold. Disclose the AI-assisted annotation provenance whenever reporting the test metrics.
