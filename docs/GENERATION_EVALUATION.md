# Command-Generation Development Evaluation

**Evaluation date:** 2026-11-17  
**Current comparison:** generation v7  
**Model:** Qwen2.5-1.5B-Instruct Q4_K_M GGUF  
**Runtime:** llama-cpp-python 0.3.37, CPU, four threads, 4,096-token context, temperature 0.0, 512-token output limit

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

The selected CLI generation mode is NLP context. The frozen configuration binds:

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
  --sample-size 40 \
  --seed 20261117 \
  --output /tmp/nl2bash-generation-dev-reproduction.json
```

The CLI refuses to overwrite an existing report. Results may vary with hardware and native build settings. The committed report remains the canonical result of the recorded run. Keep the evaluation development-only and do not tune the frozen configuration against held-out test data.

## Historical pilot and human-review record

The earlier ten-request v6 pilot is retained as a historical artifact and superseded by the v7 comparison. It is not used as the headline project result.

The v7 blinded worksheet is `data/annotations/generation_dev_v7_semantic_review.csv`; it contains 80 candidates, two for each of the 40 requests. The owner-completion attestation is `data/annotations/generation_dev_v7_human_review_attestation.json`. The original worksheet remains in its blinded A/B format. Its semantic-rating and reviewer-note fields remain blank because individual score values and comments were not included in the completion confirmation.

The supplementary assistant-only review in `data/annotations/generation_dev_v7_assistant_semantic_review.csv` is not human ground truth and is not substituted for the owner review.
