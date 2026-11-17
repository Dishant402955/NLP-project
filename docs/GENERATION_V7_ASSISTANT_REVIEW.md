# Generation v7 Assistant Semantic Review

**Review date:** 2026-11-17
**Scope:** 80 condition-masked generated-command candidates from 40 development requests
**Reviewer:** OpenAI assistant
**Status:** preliminary assistant assessment; not human gold labels

## Method and rubric

Each candidate was judged against its own natural-language request using only the request text and candidate command in the blinded worksheet. Reference commands were not used to assign ratings, and no generated command was executed. Candidates retained their A/B review IDs. The A/B-to-condition mapping is intentionally not reproduced here while the owner-facing blind review remains open.

The rubric is:

- correct_as_written: command reasonably satisfies the request without material missing constraints or unintended side effects.
- partially_correct_needs_edits: command addresses the task but needs a substantive correction, tighter selection, or removal of an unrequested assumption.
- incorrect_or_unsafe: command fails the requested task, is materially unrelated, introduces unsafe/unrequested destructive behavior, or fails to generate a usable command.

## Candidate-level results

| Blinded candidate | Correct as written | Partial / needs edits | Incorrect or unsafe | Total |
|---|---:|---:|---:|---:|
| A | 2 | 15 | 23 | 40 |
| B | 9 | 10 | 21 | 40 |
| **Total** | **11** | **25** | **44** | **80** |

Using an illustrative ordinal score of 2 for correct, 1 for partial, and 0 for incorrect/unsafe, A scored 19/80 and B scored 28/80. In paired comparisons, B received the higher rating on 12 requests, A on 4, and the ratings tied on 24. This is a reviewer-specific preliminary signal, not a statistical estimate or an independent human comparison.

The candidate-by-candidate ratings and notes are in data/annotations/generation_dev_v7_assistant_semantic_review.csv. The original data/annotations/generation_dev_v7_semantic_review.csv remains unchanged with blank semantic_rating and reviewer_note fields; it is reserved for the owner-facing review.

## Important limitations

This is one assistant review pass, not independent adjudication or inter-rater agreement. Some tasks are underspecified, environment-dependent, or ambiguous, and another reviewer may reasonably disagree with individual ratings. The ordinal score is descriptive only. Do not treat these ratings as gold labels, test-set metrics, or proof that one generation condition is superior.

The assessment suggests the generator still has substantial semantic reliability problems: only 11 of 80 candidates were rated correct as written, while 44 were rated incorrect or unsafe. The frozen generation configuration was not changed as part of this review. Any model, prompt, extractor, or validator improvements must be evaluated as a new development experiment; do not tune against the held-out test set.
