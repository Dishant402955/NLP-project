# Held-Out Command-Generation Benchmark

## Purpose

This benchmark measures the current frozen hybrid NL-to-Bash generator on the complete project-held-out NL2Bash test partition. It records latency and several independent correctness signals. It does not equate syntactically valid Bash with semantically correct Bash.

## Dataset and test population

- Source corpus: [TellinaTool/NL2Bash](https://github.com/TellinaTool/nl2bash), described in Lin et al., [NL2Bash: A Corpus and Semantic Parser for Natural Language Interface to the Linux Operating System](https://lrec.elra.info/lrec2018-main-491).
- The source data directory has a separate MIT license notice, as documented by the upstream project.
- This repository's audited raw corpus contains 12,607 paired request/command records.
- Its project-generated duplicate-aware held-out test partition contains 1,261 rows and 879 distinct natural-language requests.
- The benchmark runs the generator once for each of those 879 distinct requests. It groups identical request text and accepts any reference command paired with that exact request. This prevents duplicate prompts from artificially weighting the accuracy denominator.
- The train, development, and test partitions are verified before execution. The script checks the raw-file hashes, test-partition checksum, row counts, and zero request/command overlap across partitions. The test references are read only after generation for scoring; they are not present in model prompts.

The project's 1,261-row split is not the same as the upstream README's published 8,090/609/606 split. The project created a reproducible duplicate-aware split from the audited raw source; the report identifies the exact revision and file checksums.

## Latency protocol

1. Load the same classifier, frozen configuration, model, prompt version, and runtime settings used by the application.
2. Run three fresh CLI processes using the same simple development-only LLM-fallback request. Each outer process timer includes Python/CLI startup, classifier/config loading, local model loading, generation, and static validation. The operating-system file cache is not forced cold.
3. Run five distinct LLM-fallback warm-up requests from the development partition. None are part of the test population.
4. Run all 879 distinct test requests in one process with the model already loaded. For each request, measure wall latency around normalization, intent prediction, entity extraction, generation, and static validation. One-time process/model loading and output serialization are excluded from this warm latency distribution.
5. Report minimum, maximum, arithmetic mean, median, p90, p95, p99, quartiles, interquartile range, total range, population standard deviation, population variance, coefficient of variation, throughput, and the share completed under five seconds. Latency distributions are also separated by deterministic-template and local-LLM route.

Percentiles use linear interpolation over sorted observations. Standard deviation and variance are population statistics because the benchmark processes the complete chosen test population.

## Correctness and safety metrics

- **Generation success:** a command was returned rather than a generation exception.
- **Strict reference exact match:** output text exactly matches at least one reference command for the request.
- **Whitespace-normalized match:** the same command text after collapsing whitespace.
- **Shell-token match:** the same sequence of shell words and operators after shell-style tokenization. This is a lexical proxy only, not a semantic-equivalence proof.
- **Bash syntax validity:** the existing `bash -n` plus `bashlex` validation accepts the generated text.
- **Explicit entity/constraint pass:** the project's current entity-grounding checker reports no finding for the entities it extracted from the request.
- **Static risk flags and review-required count:** the existing non-executing Bash safety heuristics.

The denominator for each rate is all 879 unique requests; generation failures count as failures. The report also gives route-specific and predicted-intent breakdowns.

Semantic correctness still requires human judgement. Every generated output with no shell-token reference match, plus every generation failure, is placed in the accompanying CSV worksheet. A reviewer can mark `semantic_correctness_review` as `correct`, `partially_correct`, or `incorrect` and add notes. No human semantic-accuracy percentage is claimed until that worksheet is completed.

**No generated command is executed.** Validation uses parsing/static inspection only. A syntax pass or zero risk flags is not a guarantee that a command is correct or safe to run.

## Reproduction

The classifier was serialized with NumPy 2.2.6, scikit-learn 1.7.2, and joblib 1.6.0. The project now pins NumPy to 2.2.6 because the loader intentionally rejects an environment whose versions differ from the model manifest.

```bash
uv sync --locked
uv pip install --python .venv/bin/python llama-cpp-python==0.3.37

.venv/bin/python scripts/run_generation_test_benchmark.py
```

The runner checkpoint-writes completed requests. If an execution is interrupted, rerun the same command with `--resume`; it verifies the code commit, test-data checksum, frozen configuration checksum, and seed before skipping already completed records. Do not edit the benchmark inputs or frozen configuration between the original run and a resume.

The local Qwen2.5-1.5B-Instruct Q4_K_M model must be installed at the documented default path, or the script must be adjusted to pass a configured model path through the benchmark runtime. Inference is local; no hosted LLM service is used.

The runner refuses to overwrite a report or any companion artifact with the same versioned name. The benchmark's report, per-example JSONL, and semantic-review CSV are stored under `artifacts/evaluation/`.

## Artifacts

- `artifacts/evaluation/generation-test-benchmark-v1_report.json`: summary, correctness, latency distributions, cold-start probes, configuration, hardware, and integrity checks.
- `artifacts/evaluation/generation-test-benchmark-v1_examples.jsonl`: every unique request, all paired references, generated output, validation, checks, and per-request latency.
- `artifacts/evaluation/generation-test-benchmark-v1_semantic_review.csv`: all non-matching outputs and generation failures for human semantic review.
- `artifacts/evaluation/frozen_generation_config_v14.json`: versioned frozen configuration after the NumPy pin and lockfile update.

## Interpretation limits

The NL2Bash task is a benchmark of concise Linux command translation, not arbitrary multi-line scripts, interactive shell state, or every distribution-specific command. A command can be syntactically valid but perform the wrong operation. Reference commands may not enumerate every semantically valid solution. Exact and token matches therefore provide conservative reproducible signals, not a complete semantic judgement. Results apply to the recorded Intel i3-1005G1 CPU-only environment and this local quantized model; latency on other hardware will differ.
