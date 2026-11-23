# Reproducibility Guide

**Repository:** Dishant402955/NLP-project  
**Default branch:** main  
**Environment:** Linux x86-64, Python 3.10 or later  
**Dependency lock:** uv.lock

This is the operational guide for reproducing the project from a clean clone. It separates safe, repeatable development commands from held-out test evaluations that have already been run once and must not be repeated.

## 1. Repository contents and reproducibility boundary

The repository versions the software, source dataset, processed data, annotation files and manifests, trained intent classifier, frozen configuration, and evaluation reports.

| Path | Contents |
|---|---|
| `src/nl2bash/` | CLI, preprocessing, classifier, entity extraction, local generation, validation, annotation, data preparation, evaluation |
| `data/raw/nl2bash/` | Original NL2Bash request and command corpus plus its MIT license notice |
| `data/processed/nl2bash/` | Duplicate-aware train/dev/test JSONL and source/checksum manifest |
| `data/annotations/` | Intent/entity review sheets, confirmed exports, manifests, semantic review records |
| `models/` | Committed TF-IDF/Logistic Regression model and provenance manifest |
| `artifacts/evaluation/` | Frozen threshold/configuration, reports, and one-time test guards |
| `docs/` | Design, taxonomy, annotation, evaluation, audit, and reproduction guides |
| `.github/workflows/` | CI smoke checks and recorded experiment workflows |

The large Qwen GGUF model, local virtual environment, build outputs, caches, and temporary test fixtures are deliberately not versioned. The model must be downloaded using the pinned revision and checksum below. Secrets and machine-specific configuration must never be committed.

The source corpus is NL2Bash from upstream revision `d6b9f5bdff45621d190134e31ab63b7bf7002190`. The dataset files included here have their own MIT license notice. Refer to [Dataset and Evaluation](DATASET_AND_EVALUATION.md) before redistributing the data.

## 2. Clean clone and base installation

Install Git, Bash, Python 3.10+, and uv, then run:

```bash
git clone https://github.com/Dishant402955/NLP-project.git
cd NLP-project
uv sync --locked
```

The locked base environment includes the Python dependencies needed for preprocessing, data preparation, annotation validation, classifier use, entity extraction, and Bash validation. Local Qwen generation needs the additional native inference runtime in section 4.

Check the installed entry points:

```bash
uv run nl2bash --help
uv run nl2bash-prepare-dataset --help
uv run nl2bash-annotations --help
uv run nl2bash-classifier --help
uv run python -m nl2bash.entity_benchmark_cli --help
```

The entity evaluation is exposed as a Python module CLI rather than a separate installed console script.

## 3. Run the validator without the model

The standalone validator can be used immediately after the base installation:

```bash
uv run nl2bash validate \
  --command 'find . -type f -name "*.py" -size +10000000c'
```

For JSON output:

```bash
uv run nl2bash validate \
  --command 'sudo rm -rf /' \
  --json
```

The second command is deliberately destructive if executed. The application only parses it and should flag it for manual review. **Do not run the example as a shell command.** The validator returns syntax validity, parser information, risk level, and findings; it does not prove safety.

## 4. Install local Qwen command generation

### 4.1 Install native build prerequisites

On Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake python3-dev curl
```

Install the pinned llama.cpp Python binding. The build flags disable host-native CPU tuning and enable OpenMP, matching the recorded CPU-oriented setup:

```bash
CMAKE_ARGS="-DGGML_NATIVE=OFF -DGGML_OPENMP=ON" \
CMAKE_BUILD_PARALLEL_LEVEL=2 FORCE_CMAKE=1 \
uv pip install --python .venv/bin/python llama-cpp-python==0.3.37
```

A working C/C++ compiler, CMake, Python development headers, and build toolchain are required. This is an optional addition; it is not necessary for the classifier and validation CLI.

### 4.2 Download and verify the GGUF model

- Model: Qwen2.5-1.5B-Instruct Q4_K_M GGUF
- Source repository: Qwen/Qwen2.5-1.5B-Instruct-GGUF
- Pinned model revision: `91cad51170dc346986eccefdc2dd33a9da36ead9`
- Expected SHA-256: `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`
- Approximate file size: 1.12 GB
- Default local path: `~/.cache/nl2bash/models/qwen2.5-1.5b-instruct-q4_k_m.gguf`

```bash
mkdir -p "$HOME/.cache/nl2bash/models"
curl -fL --retry 4 \
  'https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf' \
  -o "$HOME/.cache/nl2bash/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"

echo "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e  $HOME/.cache/nl2bash/models/qwen2.5-1.5b-instruct-q4_k_m.gguf" | sha256sum --check
```

Do not continue if the checksum fails or the download is incomplete. Normal generation uses local inference and does not send prompts to a hosted inference API. Downloading packages and the model requires network access.

The CLI accepts an explicit model path through `--llm-model`. The default model path is under the user cache. The frozen generation configuration also verifies the model, classifier, manifest, threshold, prompt, source files, and selected runtime settings before inference.

## 5. Run the end-to-end application

With the base environment, pinned runtime, and verified model available:

```bash
uv run nl2bash generate \
  --request 'Find all Python files larger than 10 MB in the current directory.'
```

Machine-readable output:

```bash
uv run nl2bash generate \
  --request 'List listening TCP ports.' \
  --json
```

The output contains the original request, predicted intent and confidence, extracted entities and extraction issues, generated command, explanation, assumptions, selected-constraint findings, syntax status, heuristic risk findings, and an explicit `executed: false` field. A non-zero status indicates that generation or validation needs attention. Review the structured output; do not treat a generated command as ready to execute.

## 6. Reproduce the dataset preparation

The raw corpus is already in `data/raw/nl2bash/`. Its audited upstream revision is `d6b9f5bdff45621d190134e31ab63b7bf7002190`.

To reproduce the partitions without overwriting the committed files, send the output to `/tmp`:

```bash
uv run nl2bash-prepare-dataset \
  --requests data/raw/nl2bash/all.nl \
  --commands data/raw/nl2bash/all.cm \
  --output-dir /tmp/nl2bash-reproduction \
  --source-revision d6b9f5bdff45621d190134e31ab63b7bf7002190 \
  --seed 42
```

The committed partition summary is:

| Partition | Records | Duplicate groups |
|---|---:|---:|
| Train | 10,085 | 8,701 |
| Development | 1,261 | 375 |
| Test | 1,261 | 375 |
| **Total** | **12,607** | **9,451** |

The splitter groups records linked by identical trimmed natural-language requests or identical trimmed commands before assigning whole groups to partitions. The manifest stores the source revision, raw checksums, split algorithm, random seed, ratios, record/group counts, output checksums, and cross-partition overlap checks. Compare the output under `/tmp/nl2bash-reproduction/` with `data/processed/nl2bash/`. Never use the canonical output directory for a reproduction dry run.

## 7. Understand and reproduce annotation worklists

The repository includes confirmed intent exports for 500 training, 375 development, and 375 test examples, as well as partition worklists and provenance manifests. The test intent suggestions were generated from request text only and approved by the project owner. They are AI-assisted and owner-approved, not independently adjudicated ground truth.

Inspect annotation commands:

```bash
uv run nl2bash-annotations --help
uv run nl2bash-annotations create --help
uv run nl2bash-annotations validate --help
uv run nl2bash-annotations apply-test-review --help
```

The `create` operation creates a CSV review worklist plus a manifest. Training defaults to a suggested-balanced pilot; development/test default to manual selection across duplicate groups. The `validate` operation validates source IDs, group IDs, taxonomy labels, review states, source checksums, and reviewer decisions before exporting confirmed labels. `apply-test-review` imports decisions from a blind request-only test review sheet.

Example of a new training review worklist written outside the repository:

```bash
uv run nl2bash-annotations create \
  --partition train \
  --selection-mode suggested_balanced \
  --per-label 50 \
  --seed 42 \
  --output-csv /tmp/nl2bash-train-review.csv \
  --pilot-manifest /tmp/nl2bash-train-review-manifest.json
```

Follow [Annotation Guide](ANNOTATION_GUIDE.md) to edit and validate a new review file. Do not overwrite the committed confirmed exports or manifests used by the reported results.

## 8. Reproduce classifier training and threshold selection safely

The committed classifier is `models/intent_classifier.joblib`; its source and version information is in `models/intent_classifier_manifest.json`. It uses confirmed training annotations. The decision threshold is selected using development labels and a minimum-coverage rule; the frozen value is `0.1361115729921777`.

For a reproduction, write new artifacts to temporary paths:

```bash
uv run nl2bash-classifier train \
  --model-file /tmp/nl2bash-intent-classifier.joblib \
  --model-manifest /tmp/nl2bash-intent-classifier-manifest.json

uv run nl2bash-classifier select-threshold \
  --model-file /tmp/nl2bash-intent-classifier.joblib \
  --model-manifest /tmp/nl2bash-intent-classifier-manifest.json \
  --output /tmp/nl2bash-frozen-dev-threshold.json
```

The default annotation, partition, and manifest paths are defined by the CLI. Use `uv run nl2bash-classifier train --help` and `uv run nl2bash-classifier select-threshold --help` for overrides.

A prediction can be reproduced against those temporary model files:

```bash
uv run nl2bash-classifier predict \
  --request 'Find all Python files under the current directory' \
  --model-file /tmp/nl2bash-intent-classifier.joblib \
  --model-manifest /tmp/nl2bash-intent-classifier-manifest.json \
  --frozen-threshold /tmp/nl2bash-frozen-dev-threshold.json
```

Do not overwrite the committed classifier or threshold during reproduction. The saved model and threshold are the frozen artifacts associated with the reported test results.

## 9. Reproduce the v7 development generation comparison

The committed v7 experiment uses a seeded sample of 40 development requests and evaluates two conditions on the same requests:

- **Request-only:** the generator receives the original natural-language request.
- **NLP context:** the generator receives the original request, the frozen intent prediction, and the deterministic extracted entities/issues.

Paired reference commands are used only after generation for scoring. They are not placed in either generation prompt. The test partition is not used. The workflow `.github/workflows/generation-development-evaluation.yml` records the pinned model, checksum, locked environment, native build flags, four CPU threads, 4,096-token context, 512-token output limit, sample size, and seed.

To run a separate local development reproduction, use a new output file:

```bash
uv run nl2bash evaluate-generation-dev \
  --llm-model "$HOME/.cache/nl2bash/models/qwen2.5-1.5b-instruct-q4_k_m.gguf" \
  --sample-size 40 \
  --seed 20261117 \
  --output /tmp/nl2bash-generation-dev-reproduction.json
```

The CLI refuses to overwrite an existing report. Results may vary with hardware and native build settings. The committed report remains the canonical result of the recorded run. This is a development engineering experiment, not a held-out generation test estimate.

## 10. Completed evaluations and safeguards

| Evaluation | Canonical report | Guard/status |
|---|---|---|
| Intent classifier held-out test, 375 examples | `artifacts/evaluation/test_report.json` | `test_evaluation.lock`; complete, do not rerun |
| Entity exact-span held-out test, 66 targeted requests | `artifacts/evaluation/entity_test_report.json` | `entity_test_evaluation.lock`; complete, do not rerun |
| Generation v7 development comparison, 40 requests | `artifacts/evaluation/generation_dev_v7_report.json` | Complete; dev-only, with frozen configuration verification |

**Do not run the one-time classifier test evaluation or entity test benchmark again on the canonical checkout.** Do not delete, reset, or bypass their guards. For these test evaluations, reproducibility means inspecting committed reports, source manifests, checksums, and CI integrity assertions, not generating a second test result.

The entity benchmark CLI help can be inspected using `uv run python -m nl2bash.entity_benchmark_cli --help`. Do not invoke the evaluator on the canonical test sample again.

## 11. Human semantic-review completion record

The project owner confirmed completion of human semantic review for all 80 generated candidates in the v7 worksheet (two candidates for each of 40 development requests). The attestation is `data/annotations/generation_dev_v7_human_review_attestation.json`; the package-smoke CI workflow validates that it covers the same 80 item IDs as the candidate worksheet.

The original candidate worksheet is retained in its blinded A/B format. Its `semantic_rating` and `reviewer_note` fields remain blank because the completion confirmation did not include row-level score values or comments for import. Consequently:

- The human-review milestone is marked complete.
- No aggregate human correctness percentage, ordinal score, or A/B condition comparison is published.
- The separate assistant-only review in `data/annotations/generation_dev_v7_assistant_semantic_review.csv` is not substituted for human results.
- Automated generation, syntax, selected-constraint, exact-match, warning, and latency measures are not semantic correctness metrics.

This keeps the repository auditable without fabricating observations.

## 12. Continuous integration

The workflows in `.github/workflows/` serve distinct purposes:

| Workflow | Purpose |
|---|---|
| `package-smoke.yml` | Locked package install, CLI/import checks, safe/high-risk/invalid Bash parse-only checks, entity annotation/report/guard integrity, and v7 human-review attestation |
| `generation-development-evaluation.yml` | Optional pinned CPU Qwen setup, frozen configuration verification, and paired development generation evaluation |
| `final-test-evaluation.yml` | Historical one-time classifier test validation/evaluation; do not manually dispatch again |

The package smoke workflow runs on GitHub-hosted Ubuntu for relevant changes on `main` or by manual dispatch. It installs with `uv sync --locked` and runs inline Python/shell integrity checks. The repository intentionally does not contain a standalone `tests/` directory; ad hoc test scripts and fixtures are kept outside Git.

The generation workflow performs a CPU build of the pinned runtime, downloads the model at the pinned revision, verifies its SHA-256, verifies the frozen component hashes, and evaluates 40 development requests. It is not the one-time classifier/entity test workflow.

## 13. Recorded end-to-end results

The project-level quantitative results are from the paired v7 development comparison: 40 requests evaluated in both conditions, producing 80 candidates. The raw LLM baseline receives only the natural-language request; the final system also receives the frozen intent prediction and deterministic entity context.

| Automated metric | Raw LLM (request-only) | Final system (NLP context) |
|---|---:|---:|
| Generation success | 39/40 (97.5%) | 40/40 (100%) |
| Bash syntax valid | 39/40 (97.5%) | 40/40 (100%) |
| Selected explicit constraints passed | 33/40 (82.5%) | 34/40 (85.0%) |
| Strict exact reference-command match | 2/40 (5.0%) | 2/40 (5.0%) |
| High-risk warnings | 3 | 2 |
| Mean latency | 5.52 s | 6.21 s |
| Median latency | 4.57 s | 5.82 s |

These are automated, development-only engineering diagnostics, not semantic-accuracy estimates. Syntax validity and selected-constraint preservation do not prove that a command is semantically correct or safe. Exact string matching can also penalise semantically equivalent commands.

The project owner confirmed that all 80 candidates received human semantic review. The completion attestation did not include row-level ratings or reviewer notes, so no human semantic score or A/B win rate is claimed.

## 14. Known limitations

- The 1.5B-parameter generator is a small model chosen for local CPU inference, not production-grade command reliability.
- Syntax parsing does not establish semantic correctness or safety.
- Safety checks are heuristic, can miss dangerous behaviour, and can flag legitimate commands.
- Entity grounding checks selected explicit constraints only; it does not prove semantic equivalence or cover every utility-specific syntax.
- Known gaps include some unrequested case-insensitive filters, concrete invented process IDs, omitted date/time constraints, and incomplete checks of comparison, ownership, depth, interface-selection, and utility-specific semantics.
- Local inference is synchronous and does not currently enforce a hard per-request wall-clock timeout.
- NL2Bash covers a subset of Bash syntax; it does not represent every shell construct or arbitrary scripts.
- AI-assisted owner-approved annotation provenance and the targeted entity sample constrain interpretation of the classifier/entity metrics.

Any post-freeze model, prompt, classifier, threshold, extractor, or validator change is a new development configuration. Evaluate changes on separate development/challenge data. Do not tune using the one-time held-out classifier/entity test results. Generated commands remain proposals and must never be executed automatically.
