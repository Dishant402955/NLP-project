# NLP Project Engineering Handoff — 24 November 2026

**Repository:** https://github.com/Dishant402955/NLP-project  
**Branch:** `main`  
**Final source commit:** `4067d01ba18f7f174754763fa11bd0f940794946`  
**Latest documentation commit before this handoff update:** `cadf2c0b5e6cd4c4588d18a9adae4a1da8c931c4`

## Status

The requested engineering hardening, final-source CI, final-source model-backed development evaluation, report update, presentation update, and documentation handoff are complete.

The project owner confirmed that the earlier human semantic-review milestone is complete. Its repository attestation records completion but not candidate-level scores or notes. Do not request the review again and do not infer a human semantic score or A/B win rate.

## Engineering changes delivered

### Guarded deterministic-template routing

Implemented in `src/nl2bash/command_generation.py`:
- A conservative request-coverage gate runs before a deterministic template can be returned.
- The gate checks mechanically identifiable requirements including explicit paths, file extensions, home-directory scope, time/size filters, file-versus-directory scope, requested actions, content-search requirements, case sensitivity, and recursion.
- A candidate that omits a detected requirement is discarded and the request falls through to the local Qwen model.
- The gate is deliberately conservative. It is not a semantic-equivalence proof and may increase fallback frequency.

### Bounded incomplete-output recovery

- The initial generation attempt is retained.
- An explicitly truncated/incomplete model response triggers one bounded retry with a larger generation allowance.
- A second incomplete response raises a generation error; a partial command is never returned.
- Retry counts and per-attempt timing are recorded in generation metrics.
- The active frozen generation configuration was updated and integrity hashes were refreshed. The v14 snapshot remains unchanged; the newer frozen snapshot is preserved separately.

### Regression tests and CI

The tests cover:
- Template-coverage rejection and fall-through.
- Successful recovery after an explicitly incomplete generation.
- A repeated incomplete response failing closed.
- No retry when the first model response completes normally.
- Frozen configuration and safety/validation boundaries.

Final-source package-smoke workflow [45366673886](https://github.com/Dishant402955/NLP-project/actions/runs/45366673886) completed successfully:
- Python compilation passed.
- Declared package entry points passed.
- All 26 unit tests passed.
- Parse-only Bash safety and syntax checks passed.
- Protected annotation/evaluation provenance and review-attestation integrity checks passed.

## Final-source model-backed verification

The duplicate development run on final source commit `4067d01` completed successfully in workflow [45366673492](https://github.com/Dishant402955/NLP-project/actions/runs/45366673492). Its model-backed evaluation artifact is [14908375296](https://github.com/Dishant402955/NLP-project/actions/runs/45366673492/artifacts/14908375296).

The run verified the frozen hybrid configuration, evaluated a seeded paired sample of 20 development requests, confirmed that no test partition was used, and uploaded the JSON report. Reference commands were excluded from generation prompts.

| Automated diagnostic | Request-only local LLM | Final hybrid pipeline |
|---|---:|---:|
| Generation success | 20/20 (100%) | 20/20 (100%) |
| Bash syntax valid | 20/20 (100%) | 20/20 (100%) |
| Selected explicit constraints passed | 18/20 (90%) | 18/20 (90%) |
| Strict exact reference-command match | 1/20 (5%) | 1/20 (5%) |
| High-risk warnings | 0 | 1 |
| Retry attempts | 1 | 0 |
| Routes | 20 local-model | 7 templates, 13 local-model |
| Mean latency | 1.249595 s | 0.595200 s |
| Median latency | 1.188471 s | 0.618001 s |
| Minimum latency | 0.479235 s | 0.002487 s |
| p90 latency | 1.624674 s | 1.178148 s |
| p95 latency | 1.903935 s | 1.302335 s |
| Maximum latency | 3.566361 s | 1.543935 s |

Interpretation:
- Both conditions succeeded and passed syntax checks for every sampled request.
- Both passed selected explicit-constraint checks on the same 18 requests.
- Both exactly matched the reference command on the same request. Exact matching is a lexical reference proxy, not semantic accuracy.
- The hybrid mean latency was lower in this sample. Seven requests used deterministic templates and bypassed the local model; the remaining requests used local Qwen. This is a small development sample, not a universal latency guarantee.
- Syntax validity, selected-constraint checks, and exact reference matching do not prove semantic correctness or safety.

## Academic deliverables updated

The supplied source report and presentation were updated in place as new final files:
- `submission/NLP_Project_Report_Final.docx`
- `submission/NLP_Project_Presentation_Final.pptx`

Editorial constraints applied to both:
- Report end-to-end pipeline diagnostics and latency only.
- Do not present TF-IDF/Logistic Regression component accuracy or component sample counts.
- Do not include generation token-budget values.
- Describe the final hybrid flow: intent/entity context, guarded deterministic templates, local-model fallback, validation, and bounded fail-closed recovery.
- State that the experiment is development-only and that automated diagnostics are not semantic accuracy.
- Preserve the human-review caveat: completion is attested, but no structured human score was supplied.

The report has been rendered and visually inspected after editing. The PowerPoint has been rendered and visually checked slide-by-slide, including the architecture, intent-stage, hybrid-generation, results, and limitations slides.

## Frozen and protected artifacts

- The active frozen generation configuration verifies successfully in the final-source workflow.
- The older v14 configuration snapshot remains unchanged.
- The 879-request generation v1 held-out benchmark, the one-time intent test, the one-time entity test, their guards/checksums/review worksheets, and the historical v7 human-review worksheet were not used for tuning and were not modified.
- Generated Bash was never executed.

## Remaining work

There is no remaining core engineering or documentation task from the requested scope. Before institutional submission, check college-specific formatting and metadata requirements that were not supplied (college/department, supervisor, declaration/certificate, signatures, and official rubric).

A fresh untouched generation holdout with structured human semantic scoring is needed only before making a new final semantic-accuracy claim. The current 20-request development comparison is reported as development evidence only.
