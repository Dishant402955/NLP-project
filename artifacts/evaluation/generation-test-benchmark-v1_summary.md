# NL2Bash Generation Benchmark v1: Results

**Run:** 2026-11-24 (Asia/Kolkata host date)  
**Benchmark commit:** `9dc10dd3d9ba5dccf283d9cd0d6f2fdfe340f936`  
**Result:** 879 unique held-out requests evaluated. The five-second latency target was met for every measured request on this machine. Correctness is not acceptable yet based on the automatic reference metrics, and semantic accuracy has not been human-scored.

## Executive result

| Metric | Result |
|---|---:|
| Unique test requests | 879 |
| Generation succeeded | 855 / 879 (**97.27%**) |
| Generation failures | 24 / 879 (**2.73%**) |
| Strict reference-command match | 68 / 879 (**7.74%**) |
| Whitespace-normalized reference match | 68 / 879 (**7.74%**) |
| Shell-token reference match | 78 / 879 (**8.87%**) |
| Bash syntax valid | 848 / 879 (**96.47%**) |
| Explicit extracted-constraint checks passed | 782 / 879 (**88.96%**) |
| High-risk static flags | 35 |
| Review required | 131 |
| Non-matching outputs plus generation failures exported for review | 801 |

**Important:** exact and shell-token matches are reference-match proxies, not semantic accuracy. Some valid commands can differ from the references; equally, a syntactically valid command can do the wrong thing. No human semantic-accuracy percentage is claimed. The attached semantic-review CSV leaves the human rating fields blank for all 801 rows requiring review.

## Latency results

All times are seconds. The warm distribution is from the complete set of 879 unique test requests, including generation failures.

| Warm end-to-end request latency | Seconds |
|---|---:|
| Minimum | 0.002800 |
| Maximum | 4.885406 |
| Mean | 1.429445 |
| Median | 1.348127 |
| p90 | 2.481937 |
| p95 | 2.998305 |
| p99 | 3.766946 |
| Q1 | 0.930613 |
| Q3 | 1.857179 |
| Interquartile range | 0.926565 |
| Range (max - min) | 4.882606 |
| Population standard deviation | 0.839031 |
| Population variance | 0.70397374 |

- **Under five seconds:** 879 / 879 (100%) on this host. This is an observed result, not a hard timeout guarantee for future requests or other hardware.
- **Local LLM route:** 778 requests; model-call mean 1.492962 s, median 1.394232 s, p95 2.732618 s, max 4.297139 s.
- **Deterministic-template route:** 77 requests; mean 0.003593 s, median 0.003162 s, max 0.016127 s.
- **Generation errors:** 24 requests; all hit the configured 48-token output ceiling before completion. Mean 3.828258 s, max 4.885406 s. They count as failures, not successful fast responses.
- **Cold process probes:** three fresh CLI processes on the same development-only fallback request. Process wall time mean 3.626509 s, median 3.624032 s, min 3.623720 s, max 3.631776 s. Local model loading itself took 0.863702–0.891551 s. OS file-cache state was not forced cold.

The benchmark resumed from a verified checkpoint after an interruption. The total wall-clock duration across the original and resumed process is therefore unavailable. The report's `aggregate_request_latency_seconds` is the sum of individual request timings, not elapsed wall-clock time for the entire benchmark run.

## Correctness breakdown

| Route | Requests | Exact match | Shell-token match | Syntax valid | Constraint checks passed |
|---|---:|---:|---:|---:|---:|
| Deterministic templates | 77 | 0 | 0 | 77 | 65 |
| Local LLM | 778 | 68 | 78 | 771 | 717 |
| Generation error | 24 | 0 | 0 | 0 | 0 |
| **Total** | **879** | **68** | **78** | **848** | **782** |

The deterministic route deserves particular attention: it returned in milliseconds, but none of its 77 outputs matched the paired references even at the shell-token level. Spot-checking those outputs found clear intent misses, for example:

- A request to append files modified in the last 24 hours to a tar archive returned only a `find ... -print` listing; it did not update the archive.
- A request to convert Markdown files to HTML returned a file-discovery command; it did not perform conversion.
- Requests targeting the user's home directory returned `find .`, which searches the current directory instead.
- A request to search both `.c` and `.h` files returned a pattern restricted to `.h` files.

These are qualitative spot-check examples, not a human-scored accuracy sample. They are enough to show that the fast route should not be treated as correct just because it is fast.

The 24 LLM generation failures are all token-budget/truncation errors. Among the 855 successfully generated commands, 848 passed syntax validation (99.18%). Syntax success is not proof of task correctness.

## Test set and integrity

- Dataset: NL2Bash, MIT-licensed source data, upstream revision `d6b9f5bdff45621d190134e31ab63b7bf7002190`.
- Raw source corpus: 12,607 request/command pairs.
- Project-held-out partition: 1,261 rows, deduplicated to 879 unique request texts.
- A request was generated once; all reference commands paired with that exact request were accepted during scoring.
- Raw source and test partition hashes matched the committed dataset manifest.
- Request overlap and command overlap across train/dev/test partitions were both zero.
- Reference commands were not added to generation prompts.
- No generated command was executed.

The benchmark is on NL2Bash's one-line Linux command translation domain. It does not measure arbitrary multi-line Bash scripts or general interactive-shell behaviour.

## Runtime configuration

- Model: Qwen2.5-1.5B-Instruct, GGUF Q4_K_M, local/offline.
- Runtime: `llama-cpp-python` 0.3.37.
- Host: Intel Core i3-1005G1, 2 physical cores / 4 logical CPUs, approximately 7.5 GiB RAM, CPU-only.
- Context: 1,024 tokens; CPU threads: 2; batch and micro-batch: 128; output ceiling: 48 tokens; temperature: 0.

## Verdict

**Latency objective: met empirically. Correctness objective: not met / not yet established.** The maximum observed warm request latency was below five seconds, but the 7.74% exact-match and 8.87% shell-token-match rates are weak. The 96.47% syntax-valid rate must not be presented as command accuracy. In addition, template-route spot checks show concrete semantic failures. The system should remain a command suggestion tool with mandatory review; do not auto-execute its output.

The next engineering work should use development data to repair the template routing and token-budget failures, then evaluate a newly frozen version against a fresh, untouched held-out set. This v1 test partition must now be treated as consumed for tuning purposes.

## Artifacts

- `generation-test-benchmark-v1_report.json`: full summary, latency distributions, configuration, machine and integrity details.
- `generation-test-benchmark-v1_examples.jsonl`: all 879 prompts, accepted references, generated commands, checks and per-request timings.
- `generation-test-benchmark-v1_semantic_review.csv`: 801 non-matches and generation failures for manual review.
- `generation-test-benchmark-v1_summary.md`: this human-readable summary.
