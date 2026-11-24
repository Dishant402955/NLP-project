# NLP Project Engineering Handoff — 24 November 2026

**Repository:** https://github.com/Dishant402955/NLP-project  
**Branch:** `main`  
**Base benchmark commit:** `99d53353d31998ca24dc48022d77a099ee902768`  
**Current stage-1 commit:** `81c1667efbdf5ebcb77e6a563fbd37b4ebe7f191`

## User-confirmed review status

The project owner has stated that the v1 semantic review is complete. Treat it as completed and do not ask for it again. The repository does not yet contain a validated numeric semantic-review result in this change, so no semantic-accuracy percentage is claimed here.

## Protected evaluation boundaries

- Do not rerun or tune against generation-test-benchmark-v1 (879 unique requests).
- Do not rerun/tune the one-time intent classifier or entity extractor tests.
- Do not change their reports, locks, checksums, review worksheet, or input partitions.
- Generated Bash remains local and is never executed by generation or tests.

## Stage 1 — Template-routing hardening (pushed)

Implemented in `src/nl2bash/command_generation.py`:
- Added a conservative request-coverage gate between deterministic matching and returning a template result.
- It checks extracted paths, explicit file extensions, home-directory scope, supported time/size filters, file-versus-directory scope, action verbs, content-search requirements, case sensitivity and recursion.
- If a deterministic candidate omits a mechanically checkable requirement, it is discarded and the request falls through to the local LLM.
- Added regression tests for append-vs-create, home-directory scope, multiple extensions, file conversion, missing time filter, and fallback integration.
- Updated `docs/GENERATION_EVALUATION.md` and `docs/FINAL_REMAINING_WORK.md`.

This gate is conservative, not a semantic-equivalence proof. It may increase local LLM fallback frequency. It must not be used to claim a new held-out accuracy score.

## Stage 1 verification

- GitHub Actions package-smoke run for commit `81c1667...`: queued at handoff creation; outcome must be checked before treating this stage as CI-verified.
- The local remote-coding-agent shell was unavailable, so no local checkout test result is claimed.

## Remaining implementation stages

1. **Token-budget recovery:** retain the 48-token first attempt and add one bounded retry only on an explicit `finish_reason == "length"`. Record retry metrics and preserve clear failure behavior if the retry also truncates.
2. **Regression coverage:** exercise template routing, retry success/failure, token limits, CLI behavior, syntax/risk boundaries, and config integrity. Use only development/challenge fixtures.
3. **Frozen configuration:** version the changed generation source and runtime retry setting without weakening integrity checks. Preserve `frozen_generation_config_v14.json` unchanged; use a new version for updated settings.
4. **CI and handoff:** run package-smoke, fix any regressions, and update this handoff with final commit IDs and observed workflow outcomes.

## Historical v1 baseline — not a tuning target

The v1 held-out benchmark measured 879 unique requests: warm mean 1.429445 s, median 1.348127 s, maximum 4.885406 s, with 879/879 under five seconds on the recorded Intel i3-1005G1 host. There were 24 generation failures at the 48-token ceiling. Strict reference match was 7.74%; shell-token match was 8.87%. These are lexical reference proxies, not human semantic accuracy.

No new held-out accuracy/latency claim is made for the hardened implementation until an untouched evaluation is run.


## Stage 2 — Bounded local-LLM retry (current implementation)

- Initial token budget remains 48; one retry at 96 tokens occurs only for an explicit `finish_reason == "length"`.
- A second length cutoff raises a clear generation error; partial output is never returned.
- Metrics record retry count, initial/retry call durations, effective token ceilings, and aggregate API usage from both attempts.
- The development report summarizes retry count and records the retry ceiling.
- Active frozen config now includes the retry ceiling and refreshed hashes. `frozen_generation_config_v14.json` is preserved; a new `frozen_generation_config_v15.json` snapshot is added.
- Retry tests cover success after truncation, repeat truncation failure, and no retry for a normal first-pass completion.
- Stage-1 package-smoke run 45365481368 completed successfully.

## Stage 2/3 verification still to perform

- Confirm package-smoke for the retry implementation commit.
- Run the 20-request development-only model evaluation to observe actual retry frequency, correctness proxies and latency. It does not use the v1 test partition.
- Update this handoff with final commit SHA and workflow outcomes.


## CI correction iteration — 2026-11-24

The first Stage 2 package-smoke run (45366209377) caught a missing `CommandGenerationError` test import. The runtime retry-success test, template coverage tests, and other unit tests passed; one failure was isolated to the test module import. The import has been added. An invalid Python escape in the new home-path guard and legacy parenthesis escape warnings were also corrected. The active and v15 frozen config command-source hashes were refreshed for the final source bytes. Rerun package-smoke before marking this stage verified.
