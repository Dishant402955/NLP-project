# Final Remaining Work

**Status date:** 2026-11-17

## Completed and committed

- Core Python package, TF-IDF/Logistic Regression intent classifier, rule-based entity extractor, local Qwen command generator, Bash syntax/risk checks, and end-to-end CLI.
- Duplicate-aware NL2Bash partitions and source/checksum manifests.
- 500 training and 375 development intent annotations; the project owner reported zero further corrections after AI-assisted annotation.
- Frozen classifier, development-selected confidence threshold, generation prompt/model/runtime, and validation configuration.
- Ten-request development-only command-generation comparison.
- 375 test intent decisions: request-only AI suggestions were reviewed and all accepted by the project owner without correction. The canonical test worklist, confirmed JSONL export, checksums, and AI-assisted provenance manifest are committed.

The test intent labels are AI-assisted and owner-approved, not independently adjudicated ground truth. Any classifier test metrics must state that limitation.

## Remaining work

### 1. Classifier test evaluation

<badge color="success">Completed</badge>

The workflow at `.github/workflows/final-test-evaluation.yml` completed successfully in GitHub Actions. It installed the locked Python 3.10 environment, passed the project's test annotation validator on 375 records, ran the one-time frozen classifier evaluation, verified the provenance/metrics, and committed the report and guard. The lockfile's Python-version-specific NumPy references were also repaired and `uv sync --locked` passed.

Results: accuracy 0.6853, macro-F1 0.6400, weighted-F1 0.6793, macro precision 0.7854, macro recall 0.6186, prediction coverage 0.9947, and two low-confidence requests. The development-selected threshold was 0.1361115729921777.

Report: `artifacts/evaluation/test_report.json`. Completed guard: `artifacts/evaluation/test_evaluation.lock`. The evaluation must not be rerun. Test annotation was AI-assisted and owner-approved, not independently adjudicated, and that caveat is embedded in the report.

The test evaluator must not be rerun after its report/guard are produced.

### 2. Build an entity-extraction benchmark

The extractor supports eleven entity types and the exact-span metric implementation exists, but no reviewed entity gold set exists. Create an annotation schema that captures entity type, exact source text, normalized value, and start/end character offsets. Have a human adjudicate a development sample for rule refinement and a separate held-out sample for final scoring. Calculate exact-span micro and per-type precision, recall, and F1. Do not present functional smoke tests as accuracy metrics.

### 3. Run a larger command-generation evaluation

The existing comparison has ten development requests only. Run a larger representative sample with the frozen Qwen model, prompt, runtime, classifier, extractor, and validator. Compare request-only and NLP-context generation on the same requests. Report exact match, syntax validity, selected constraint preservation, warnings, and latency.

Add blinded human semantic-correctness ratings for generated commands. A valid Bash parse is not evidence that the command does the right thing. Do not execute generated commands as part of the normal evaluation.

### 4. Complete the final engineering audit

- Verify `uv sync --locked` from a clean Python 3.10 environment.
- Verify the optional `llama-cpp-python==0.3.37` installation and the Qwen GGUF SHA-256.
- Run the annotation validator, classifier CLI, generation CLI, and standalone Bash validator after installing from the lockfile.
- Recheck malformed inputs, dangerous command patterns, missing model/runtime cases, and frozen-configuration rejection.
- Inspect the final Git diff and verify that no test source, temporary fixtures, caches, virtual environments, or secrets are committed.

The remote coding-agent workspace is currently unreachable. GitHub repository reads and commits are available, but they do not execute Python commands. The final runtime audit therefore remains unverified.

### 5. Finish the academic submission

After the outstanding evaluations, prepare the final report, presentation, and live demonstration. The report must include dataset provenance/licensing, annotation methodology, the AI-assisted test-label caveat, frozen model details, per-class metrics, entity benchmark results, command-generation semantic ratings, failure analysis, safety limitations, and reproducibility instructions. Do not fill missing results with estimates.
