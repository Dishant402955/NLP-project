# Command-Generation Development Evaluation

**Evaluation date:** 2026-11-17  
**Prompt version:** `qwen-bash-json-v6`  
**Model:** Qwen2.5-1.5B-Instruct Q4_K_M GGUF  
**Runtime:** llama-cpp-python 0.3.37, CPU, four threads, 4,096-token context, temperature 0.0, 512-token output limit

## Method

A seeded sample of 10 requests was selected from the confirmed development annotation partition, with one example per available intent label. Seed: `20261117`. Each request was evaluated under two conditions:

1. **Request-only:** the generator receives only the original natural-language request.
2. **NLP context:** the generator receives the original request, frozen intent prediction, and deterministic extracted entities and extraction issues.

The paired reference Bash command is used only after generation to score exact string match. It is never passed into either generation prompt. No test partition, test request, or test label was loaded. The experiment records command-generation success, exact match, Bash syntax validity, selected explicit-constraint preservation, high-risk warnings, and latency.

## Results

| Metric | Request-only | NLP context |
|---|---:|---:|
| Generation success | 10 / 10 (100%) | 10 / 10 (100%) |
| Bash syntax valid | 9 / 10 (90%) | 9 / 10 (90%) |
| Selected explicit constraints preserved | 8 / 10 (80%) | 10 / 10 (100%) |
| Exact reference-command match | 0 / 10 (0%) | 0 / 10 (0%) |
| High-risk warnings | 1 | 1 |
| Mean generation latency | 10.02 s | 11.22 s |
| Median generation latency | 9.88 s | 12.22 s |

The observed sample suggests that supplying the intent/entity context improved the selected constraint checks on these ten requests, while syntax validity was equal. NLP context took about 2.3 seconds longer at the median. These small-sample results do not establish general superiority or semantic correctness.

## Interpretation and limitations

- Exact command matching was zero in both conditions. The generated commands are not textually identical to their references.
- Bash syntax validity establishes only that Bash accepts the syntax; it does not establish that a command performs the requested task.
- Entity grounding checks only selected explicit constraints. They are not a semantic-equivalence checker and can miss incorrect or incomplete behavior.
- A high-risk count is based on heuristics. A zero warning count would not prove safety.
- No human semantic-correctness ratings were collected.
- The sample has only ten requests, one per intent category. It is an engineering comparison, not a population-level performance estimate.
- The development annotations were initially AI-assisted and then reviewed by the project owner. They are not an inter-annotator agreement study.

Representative errors include inaccurate process selection, incomplete `find -prune` expressions, and model-invented identifiers for operations that require a process ID or database credentials. Treat all output as a proposal that requires human inspection.

## Frozen generation configuration

The selected CLI generation mode is NLP context because it preserved the selected explicit constraints on all ten sample requests, compared with eight of ten in request-only mode. This selection is a limited engineering choice, not a claim of semantic superiority.

`artifacts/evaluation/frozen_generation_config.json` binds:

- The local Qwen GGUF file SHA-256 and Hugging Face model revision.
- llama-cpp-python version and CPU generation settings.
- Prompt version and prompt source checksum.
- Intent classifier artifact and manifest checksums.
- Frozen development confidence threshold checksum and value.
- Checksums of the pipeline, extractor, grounding checker, validator, CLI, evaluation code, package configuration, and lockfile.
- The development report checksum and the fact that no test data was used.

The end-to-end CLI verifies these values before generation and fails closed if a frozen component, model, threshold, or runtime setting changes. The model file itself is stored outside Git; its checksum and retrieval instructions are versioned.

## Reproduction

From the repository root, after installing the optional local model dependency and downloading the model as described in [Local Model Setup](LOCAL_MODEL_SETUP.md):

```bash
uv run nl2bash evaluate-generation-dev \
  --llm-model "$HOME/.cache/nl2bash/models/qwen2.5-1.5b-instruct-q4_k_m.gguf" \
  --sample-size 10 \
  --seed 20261117 \
  --output artifacts/evaluation/generation_dev_v6_report.json
```

The CLI refuses to overwrite an existing report. The committed report is the recorded run; rerunning the experiment should use a new output path and be documented as a separate run.
