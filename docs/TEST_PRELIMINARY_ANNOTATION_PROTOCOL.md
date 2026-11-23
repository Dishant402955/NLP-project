# Final Test Annotation Review and Provenance

**Date:** 2026-11-17  
**Status:** Completed; one-time classifier test evaluation completed successfully.

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

The project validator passed in the clean Python 3.10 GitHub Actions environment on all 375 rows. The one-time classifier evaluation then completed successfully. The validator/evaluation workflow is recorded in GitHub Actions; do not rerun the final test evaluation.

## One-time classifier test evaluation

The one-time evaluation used the frozen development-selected threshold and completed successfully. Its canonical report is `artifacts/evaluation/test_report.json`, and the completed one-time guard is `artifacts/evaluation/test_evaluation.lock`.

The component-level classifier score values are intentionally omitted from the committed report artifact. The artifact retains evaluation-completion status, annotation provenance, source checksums, and its one-time guard. The report's quantitative results focus on the paired end-to-end raw LLM request-only baseline versus the final NLP-context system. Test annotations remain request-only AI-assisted proposals accepted by the project owner, not independently adjudicated ground truth.

**Do not rerun this evaluation, reset the guard, or use the held-out annotations to tune the system.**
