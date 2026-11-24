# Command-Generation Development Evaluation

**Latest optimization check:** generation v17, 2026-11-24
**Model:** Qwen2.5-1.5B-Instruct Q4_K_M GGUF  
**Historical v7 runtime:** llama-cpp-python 0.3.37, CPU, four threads, 4,096-token context, temperature 0.0, 512-token output limit. This describes the preserved v7 comparison only.

## Current offline runtime defaults

The current local CLI uses command-only generation, `max_tokens=48`, 2 CPU threads, `n_batch=128`, `n_ubatch=128`, a 1,024-token context, and zero GPU layers on the tested 2-core CPU. Deterministic templates handle common, explicit patterns; other requests use the local Qwen fallback. The LLM is loaded only after a template miss and is reused in interactive mode. Stage timings include llama.cpp prompt-evaluation and token-generation counters. The older v8 smoke report is retained as a historical implementation checkpoint.

## Current hybrid optimization result (v17)

A seeded sample of 20 requests from the confirmed development partition was run in both request-only and NLP-context conditions. No test partition or test labels were used.

| Automated metric | Request-only LLM | Hybrid system with NLP context |
|---|---:|---:|
| Generation success | 19/20 (95%) | 20/20 (100%) |
| Bash syntax valid | 19/20 (95%) | 20/20 (100%) |
| Selected explicit constraints passed | 17/20 (85%) | 19/20 (95%) |
| Strict exact reference-command match | 1/20 (5%) | 1/20 (5%) |
| High-risk warnings | 0 | 2 |
| Mean request latency | 1.477 s | 0.729 s |
| Median request latency | 1.451 s | 0.802 s |
| Maximum request latency | not used as a frozen statistic | 1.919 s |

The NLP-context path used deterministic templates for 7 requests and the local Qwen model for 13. All 20 NLP-context requests completed below 5 seconds; the sample maximum was 1.919 seconds. These per-request evaluation timings reuse an already-loaded evaluator model, so they do not include one-shot process/model startup.

Cold one-shot CLI wall-clock checks, including Python process startup and with the local integrity sidecar present, measured 0.98 seconds for a deterministic request, 1.02 seconds for a filename-sort request, 0.98 seconds for a primary-interface lookup, and 3.35 seconds for an LLM fallback. After simulating a fresh install by deleting the sidecar, the first LLM fallback performed the one-time full model SHA-256 check and completed in 4.32 seconds. These are representative measured runs, not a guarantee for every arbitrary Linux task or machine.

The Qwen3-0.6B Q4_0 experiment was not adopted: although it decoded faster, command correctness and formatting were not acceptable on the sampled tasks. The 1.5B model remains the offline fallback while templates handle common patterns.

The latest report is `artifacts/evaluation/generation_dev_v17_report.json`. The runtime is frozen in `artifacts/evaluation/frozen_generation_config.json` (versioned snapshot: `artifacts/evaluation/frozen_generation_config_v13.json`). The optional GitHub workflow verifies this configuration and writes a separate artifact; it does not overwrite v7 records.

## Method

A seeded sample of 40 requests was selected from the confirmed development annotation partition. Each request was evaluated under two conditions on the same input:

1. **Raw LLM baseline (request-only):** the generator receives only the original natural-language request.
2. **Final system (NLP context):** the generator receives the original request, frozen intent prediction, and deterministic extracted entities and extraction issues.

Paired reference Bash commands were used only after generation for scoring. They were never included in either generation prompt. No test partition, test request, or test label was used. The comparison produced 80 candidates.

## End-to-end results

| Automated metric | Raw LLM (request-only) | Final system (NLP context) |
|---|---:|---:|
| Generation success | 39/40 (97.5%) | 40/40 (100%) |
| Bash syntax valid | 39/40 (97.5%) | 40/40 (100%) |
| Selected explicit constraints passed | 33/40 (82.5%) | 34/40 (85.0%) |
| Strict exact reference-command match | 2/40 (5.0%) | 2/40 (5.0%) |
| High-risk warnings | 3 | 2 |
| Mean latency | 5.52 s | 6.21 s |
| Median latency | 4.57 s | 5.82 s |

The final NLP-context system produced one additional successful generation and syntax-valid output, and one additional request passed the selected explicit-constraint checks. Strict exact matching was unchanged. The mean latency increased by approximately 0.69 seconds.

## Interpretation and limitations

- This is a 40-request development comparison, not a held-out generation test estimate.
- Exact string matching does not establish semantic equivalence; different commands can perform the same task.
- Bash syntax validity establishes only that Bash accepts the syntax. It does not establish that the command performs the requested task.
- Entity grounding checks selected explicit constraints only. They are not a semantic-equivalence checker.
- High-risk warning counts are based on heuristics. A zero-warning result would not prove safety.
- The project owner confirmed that all 80 candidates received human semantic review. The attestation records completion, but the completion confirmation did not include row-level ratings or comments. No human semantic score or A/B condition win rate is published.
- The development annotations were AI-assisted and then reviewed by the project owner. They are not an inter-annotator agreement study.

The report records generation success, syntax validity, selected explicit-constraint checks, exact reference string matches, heuristic high-risk warnings, and latency. None of these measures establishes semantic correctness.

## Frozen generation configuration

The selected CLI generation mode is the hybrid NLP-context path. The frozen configuration binds:

- The portable local Qwen GGUF SHA-256 and Hugging Face model revision. A separate machine-local sidecar caches successful verification against that machine's file identity.
- llama-cpp-python version and CPU generation settings.
- Prompt version and prompt source checksum.
- Intent classifier artifact and manifest checksums.
- Frozen development confidence threshold checksum and value.
- Checksums of the pipeline, extractor, grounding checker, validator, CLI, evaluation code, package configuration, and lockfile.
- The development report checksum and the fact that no test data was used.

Normal CLI startup checks a machine-local integrity sidecar rather than rereading the full 1.1 GB model. A missing or stale sidecar triggers full SHA-256 verification and refresh. The portable frozen configuration can therefore be used on other machines without depending on the original host's inode or timestamps. Other frozen component and classifier/threshold checks are performed at startup. The model and its local sidecar are stored outside Git.

## Reproduction

From the repository root, after installing the optional local model dependency and downloading the model as described in [Local Model Setup](LOCAL_MODEL_SETUP.md):

```bash
uv run nl2bash evaluate-generation-dev \
  --llm-model "$HOME/.cache/nl2bash/models/qwen2.5-1.5b-instruct-q4_k_m.gguf" \
  --sample-size 40 \
  --seed 20261117 \
  --output /tmp/nl2bash-generation-dev-reproduction.json
```

The CLI refuses to overwrite an existing report. Results may vary with hardware and native build settings. The committed report remains the canonical result of the recorded run. Keep the evaluation development-only and do not tune the frozen configuration against held-out test data.

## Historical pilot and human-review record

The earlier ten-request v6 pilot is retained as a historical artifact and superseded by the v7 comparison. It is not used as the headline project result.

The v7 blinded worksheet is `data/annotations/generation_dev_v7_semantic_review.csv`; it contains 80 candidates, two for each of the 40 requests. The owner-completion attestation is `data/annotations/generation_dev_v7_human_review_attestation.json`. The original worksheet remains in its blinded A/B format. Its semantic-rating and reviewer-note fields remain blank because individual score values and comments were not included in the completion confirmation.

The supplementary assistant-only review in `data/annotations/generation_dev_v7_assistant_semantic_review.csv` is not human ground truth and is not substituted for the owner review.


## Post-v1 template-routing hardening (2026-11-24)

A conservative request-coverage gate now sits between deterministic template matching and returning a command. The gate checks extracted paths, all explicitly named file extensions, home-directory scope, supported time/size filters, file-versus-directory scope, and selected action verbs such as convert, append, move, copy, delete, archive, extract, permission change, count, and sort. It also checks explicit content-search, case-insensitive, and recursive requirements. If a check shows that a candidate omits a request requirement, the candidate is discarded and the request falls through to the local LLM.

This is a fail-closed guard for known, mechanically checkable omissions, not a semantic-equivalence proof. It deliberately trades some template speed for a lower chance of returning a command that obviously omits the requested operation. The consumed v1 held-out partition was not used for implementation or tuning.


## Post-v1 bounded generation retry (2026-11-24)

The initial generation budget remains 48 tokens to preserve the common-path latency profile. When llama.cpp explicitly reports `finish_reason=length`, generation retries once with a 96-token ceiling using the same request and prompt. A second length cutoff is a failure; no truncated command is returned. Successful results record the initial/retry call durations, retry count, initial/retry token ceilings, and aggregate API-reported token usage. The development evaluator includes retry counts in its summary.

The retry behavior is covered with deterministic fake-model tests for successful retry, second-attempt truncation, and no retry on a normal first-pass completion. It is a bounded recovery, not a guarantee that all commands fit in 96 tokens. The 879-request v1 benchmark measured the earlier single-pass 48-token behavior and must not be used to claim the retry's accuracy or latency.


## Development-only model verification after generation hardening (2026-11-24)

A GitHub Actions run on implementation commit `d1659f2c9e3a10bee6470c73a1268802b02373f5` completed the seeded 20-request development comparison (seed `20261127`, `dev` partition, dataset revision `d6b9f5bdff45621d190134e31ab63b7bf7002190`). The report declared `test_data_used=false`; references were excluded from generation prompts. The full per-example JSON is retained as [workflow artifact 14906354383](https://github.com/Dishant402955/NLP-project/actions/runs/45366209580/artifacts/14906354383).

| Metric | Request-only local LLM | Hybrid NLP-context |
|---|---:|---:|
| Requests | 20 | 20 |
| Generation success | 20/20 (100%) | 20/20 (100%) |
| Bash syntax valid | 20/20 (100%) | 20/20 (100%) |
| Selected constraints passed | 18/20 (90%) | 18/20 (90%) |
| Exact reference matches | 1/20 (5%) | 1/20 (5%) |
| High-risk flags | 0 | 1 |
| Retry attempts | 1 | 0 |
| Route counts | 20 LLM | 7 templates, 13 LLM |
| Minimum latency | 0.503754 s | 0.002106 s |
| Mean latency | 1.449816 s | 0.690222 s |
| Median latency | 1.347501 s | 0.682358 s |
| p90 latency | 2.010147 s | 1.425619 s |
| p95 latency | 2.368270 s | 1.561336 s |
| Maximum latency | 4.483385 s | 1.844542 s |
| Range | 3.979631 s | 1.842436 s |

Interpretation: the retry completed one request that hit the initial ceiling in the request-only condition; none of the 20 hybrid requests needed retry. The hybrid path was faster on this small sample partly because seven requests used deterministic templates and did not load the LLM. This does not establish semantic accuracy: exact match is only a lexical reference metric, and selected-constraint checks are not a semantic-equivalence proof.

**Revision note:** this model-backed report was produced on `d1659f2`, before the final Python escape/test-import cleanup in `4067d01`. The final source commit passed package-smoke independently. A second model-backed run was triggered for `4067d01` (run 45366673492); its outcome is not included here until it completes. These results are development evidence, not a new held-out test result and not comparable as a guarantee to the 879-request benchmark on the Intel i3 host.


## Final-source verification after template hardening and bounded recovery — 24 November 2026

The final-source workflow completed successfully on commit `4067d01ba18f7f174754763fa11bd0f940794946`: [workflow run 45366673492](https://github.com/Dishant402955/NLP-project/actions/runs/45366673492). The workflow verified the frozen hybrid configuration, ran a separate paired development-only comparison, verified evaluation isolation, and uploaded [artifact 14908375296](https://github.com/Dishant402955/NLP-project/actions/runs/45366673492/artifacts/14908375296).

The sample contains 20 requests from the development partition. Both conditions used the same requests. The reference commands were not included in generation prompts, and `test_data_used=false`.

| Automated metric | Request-only local LLM | Final hybrid pipeline |
|---|---:|---:|
| Generation success | 20/20 (100%) | 20/20 (100%) |
| Bash syntax valid | 20/20 (100%) | 20/20 (100%) |
| Selected explicit constraints passed | 18/20 (90%) | 18/20 (90%) |
| Strict exact reference-command match | 1/20 (5%) | 1/20 (5%) |
| High-risk warnings | 0 | 1 |
| Requests that retried | 1 | 0 |
| Retry attempts | 1 | 0 |
| Generation routes | 20 local-model | 7 deterministic templates, 13 local-model fallback |
| Mean latency | 1.249595 s | 0.595200 s |
| Median latency | 1.188471 s | 0.618001 s |
| Minimum latency | 0.479235 s | 0.002487 s |
| p90 latency | 1.624674 s | 1.178148 s |
| p95 latency | 1.903935 s | 1.302335 s |
| Maximum latency | 3.566361 s | 1.543935 s |

The final-source hybrid pipeline generated all sampled requests and passed Bash syntax checks on all of them. The selected explicit-constraint checks passed on 18 requests. One output exactly matched a reference command. These checks are automated correctness proxies only: exact matching is lexical, selected-constraint validation covers only chosen explicit requirements, and valid Bash syntax does not prove task semantics. No human semantic-accuracy percentage is claimed.

The hybrid route used templates for seven requests and local-model fallback for thirteen. Its mean latency was 0.595200 s, median 0.618001 s, p90 1.178148 s, p95 1.302335 s, and maximum 1.543935 s. Request-only generation had mean 1.249595 s, median 1.188471 s, p90 1.624674 s, p95 1.903935 s, and maximum 3.566361 s. These figures are from a 20-request development sample, not a universal performance guarantee or held-out quality estimate.

This run supersedes the earlier duplicate-run-pending note and is the latest final-source model-backed development evidence. The earlier run on `d1659f2` remains recorded as historical engineering evidence. The separate package-smoke verification on final source passed as workflow [45366673886](https://github.com/Dishant402955/NLP-project/actions/runs/45366673886), with all 26 unit tests passing.

The consumed 879-request generation v1 holdout and the one-time classifier/entity test evaluations remain untouched. A newly frozen, independently held-out generation set and structured human semantic ratings are required before claiming final semantic accuracy.
