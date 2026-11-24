# Natural Language to Bash Command Generator

[![Open in Google Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Dishant402955/NLP-project/blob/main/notebooks/NL2Bash_Colab.ipynb)


A hybrid NLP system that translates natural-language Linux requests into Bash command proposals. Traditional NLP predicts the requested operation and extracts explicit parameters. Common, well-specified patterns use deterministic Bash templates; other requests use a local instruction-tuned language model. Deterministic checks inspect syntax, selected constraints, and known risky patterns.

**Project repository:** [Dishant402955/NLP-project](https://github.com/Dishant402955/NLP-project)

**Safety boundary: generated commands are displayed only. The application does not execute them.**

## Project status

**Core implementation, recorded evaluations, selected engineering audit, human semantic-review milestone, and presentation review are complete.** The project owner confirmed that all 80 generated candidates from the 40-request v7 development comparison received human semantic review. The completion record is `data/annotations/generation_dev_v7_human_review_attestation.json`. The completion confirmation did not include per-candidate scores or reviewer notes, so no human semantic accuracy score or A/B win rate is claimed. The original worksheet remains unchanged rather than being populated with invented ratings.

The project owner has also approved the presentation. Any college-specific cover-page fields or required formatting are administrative submission details, not outstanding technical work.

## How it works

1. The CLI accepts a natural-language Linux task and preserves its original wording.
2. Preprocessing validates the request and trims surrounding whitespace only.
3. A Scikit-learn TF-IDF + Logistic Regression model predicts an intent category and confidence.
4. A deterministic rule-based extractor finds supported parameters such as extensions, paths, file names, sizes, ports, process names, dates, comparison conditions, programming languages, and case-sensitivity requirements. It preserves exact values and source spans, and reports incomplete or conflicting cues.
5. The generator first checks a conservative set of deterministic templates for common Linux tasks. If no template matches, it loads the local Qwen2.5-1.5B-Instruct model on demand and asks it for one Bash command only. Both paths work offline.
6. The validator runs Bash syntax parsing in parse-only mode, applies heuristic risk checks, and checks selected explicit constraints against the generated text.
7. The CLI displays the command and all findings. It never invokes a shell to execute generated text.

See [System Architecture](docs/ARCHITECTURE.md), [Technical Design](docs/TECHNICAL_DESIGN.md), and [Reproducibility Guide](docs/REPRODUCIBILITY.md).

## Domain extensibility and design trade-off

The pipeline pattern can be adapted to other CLI ecosystems such as Docker or AWS, but support is not plug-and-play. Each domain needs its own intent taxonomy and labelled examples, entity schema and extractor, generation prompt and command examples, and syntax, risk, and constraint validators. The shared preprocessing, orchestration, model adapter, and output contract can be reused. Domain-specific components are prepared and versioned as a coherent pipeline configuration rather than dynamically loading or hot-reloading a heavyweight stack for every request. This keeps the runtime lighter and more predictable while preserving domain-specific behaviour. Docker and AWS support are proposed extensions, not implemented or evaluated features.

## Technology

| Area | Implementation |
|---|---|
| Language | Python 3.10+ |
| Packaging/environment | setuptools, uv, locked dependencies |
| Intent classification | Scikit-learn TF-IDF word unigrams/bigrams + Logistic Regression |
| Entity extraction | Deterministic Python rules and regular expressions |
| Generation | Qwen2.5-1.5B-Instruct Q4_K_M GGUF |
| Inference | llama-cpp-python 0.3.37, local CPU inference (2 threads, batch 128, context 1,024, 48-token output cap) |
| Bash parsing | `bash -n` parse-only mode and bashlex AST analysis |
| Interfaces | `nl2bash`, `nl2bash-classifier`, `nl2bash-annotations`, `nl2bash-prepare-dataset` CLIs |

The base package works without the optional LLM runtime. The model binary is installed separately, not committed to Git, and pinned by SHA-256. Deterministic routes do not load the model; unsupported requests use the local Qwen fallback. After the model and dependencies are present locally, normal generation makes no network requests and uses no hosted inference service. Setup instructions are in [Local Model Setup](docs/LOCAL_MODEL_SETUP.md).

## Quick start

Prerequisites: Linux, Bash, Python 3.10+, and uv.

```bash
git clone https://github.com/Dishant402955/NLP-project.git
cd NLP-project
uv sync --locked

uv run nl2bash --help
uv run nl2bash validate --command 'find . -type f -name "*.py" -size +10000000c'
```

The last command checks syntax and heuristic risks without executing it.

### Enable local generation

On Debian/Ubuntu, install build tools, then install the pinned inference runtime:

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake python3-dev curl

CMAKE_ARGS="-DGGML_NATIVE=OFF -DGGML_OPENMP=ON" \
CMAKE_BUILD_PARALLEL_LEVEL=2 FORCE_CMAKE=1 \
uv pip install --python .venv/bin/python llama-cpp-python==0.3.37
```

Download the pinned GGUF model and verify its checksum:

```bash
mkdir -p "$HOME/.cache/nl2bash/models"
curl -fL --retry 4 \
  'https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf' \
  -o "$HOME/.cache/nl2bash/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"

echo "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e  $HOME/.cache/nl2bash/models/qwen2.5-1.5b-instruct-q4_k_m.gguf" | sha256sum --check
```

Run an example:

```bash
uv run nl2bash generate --request 'Find all Python files larger than 10 MB in the current directory.'
```

For repeated requests, keep one local model instance in memory with the interactive mode. It accepts requests until `exit` or `quit` and does not reload the 1.1 GB model between them:

```bash
uv run nl2bash generate --interactive --timings
```

The timing output separates startup, classifier, entity extraction, prompt evaluation, token generation, and validation. The model is loaded only when a request needs the LLM fallback. The runtime can be tuned with `--threads`, `--batch-size`, `--context-size`, `--gpu-layers`, and `--max-tokens`; the frozen configuration accepts only its recorded settings unless it is deliberately re-evaluated and re-frozen.

For full reproduction instructions, including safe data preparation and evaluation commands, see [Reproducibility Guide](docs/REPRODUCIBILITY.md).

## Latency optimization results (2026-11-24)

The current hybrid path was measured on the tested Intel Core i3-1005G1 (2 physical cores / 4 logical CPUs) using a 20-request development sample. With NLP context, mean generation-plus-validation latency was **0.73s**, median **0.80s**, and maximum **1.92s**. All 20 requests generated a command and passed Bash syntax checks; 19/20 passed the selected explicit-constraint checks. Seven requests used deterministic templates and thirteen used the local LLM fallback. This is a development-only sample, not a universal latency guarantee or semantic-accuracy estimate.

Cold one-shot CLI runs, including Python process startup and with the local integrity sidecar present, were measured at **0.98s** for a deterministic request, **1.02s** for a filename-sort template, **0.98s** for a primary-interface lookup template, and **3.35s** for a local LLM fallback. After simulating a fresh model install by deleting the sidecar, the first LLM fallback also performed the one-time full SHA-256 check and completed in **4.32s**. These representative runs met the 5-second target. Arbitrary unsupported requests and other hardware are not guaranteed to meet a hard 5-second deadline; the LLM has a 48-token cap and fails closed when it reaches that cap.

The previous 0.6B model experiment was not adopted because its speed did not come with acceptable command quality on the sampled requests. The stronger 1.5B local model remains the fallback while deterministic templates handle common patterns.

The detailed current report is [generation_dev_v17_report.json](artifacts/evaluation/generation_dev_v17_report.json). The frozen runtime configuration is `artifacts/evaluation/frozen_generation_config.json`.

## Recorded end-to-end results

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

## Documentation map

- [Google Colab Notebook](notebooks/NL2Bash_Colab.ipynb): runnable notebook for setup, classifier, entity extraction, safety validation, saved reports, and optional local Qwen generation.
- [Reproducibility Guide](docs/REPRODUCIBILITY.md): clean clone, environment setup, model download, CLI, data preparation, annotation workflow, safe evaluation, artifacts, and CI.
- [System Architecture](docs/ARCHITECTURE.md): end-to-end flow and source-module map.
- [Technical Design](docs/TECHNICAL_DESIGN.md): module responsibilities, technology choices, runtime, and validation boundaries.
- [Project Plan](docs/PROJECT_PLAN.md): objectives, scope, requirements, and deliverables.
- [Dataset and Evaluation](docs/DATASET_AND_EVALUATION.md): NL2Bash provenance/licensing, data audit, duplicate-aware split, annotations, and methodology.
- [Intent Taxonomy](docs/INTENT_TAXONOMY.md): intent categories and definitions.
- [Annotation Guide](docs/ANNOTATION_GUIDE.md): worklist creation, review, validation, and exports.
- [Annotation Review Status](docs/ANNOTATION_REVIEW_STATUS.md): intent/entity annotation status, provenance, and classifier results.
- [Intent Classifier](docs/INTENT_CLASSIFIER.md): TF-IDF, Logistic Regression, training, prediction, threshold selection, and test evaluation.
- [Entity Extraction](docs/ENTITY_EXTRACTION.md): entity types, rules, exact spans, normalized values, and limitations.
- [Entity Evaluation](docs/ENTITY_EVALUATION.md): targeted sample, exact-span metrics, per-type support, and caveats.
- [Command-Generation Evaluation](docs/GENERATION_EVALUATION.md): historical v7 comparison, current hybrid latency results, and semantic-review status.
- [Held-Out Generation Benchmark](docs/GENERATION_TEST_BENCHMARK.md): full held-out correctness and latency protocol, reproducible runner, metrics, and semantic-review worksheet.
- [Owner Review Attestation](data/annotations/generation_dev_v7_human_review_attestation.json): completion record for all 80 v7 candidates.
- [Assistant Semantic Review](docs/GENERATION_V7_ASSISTANT_REVIEW.md): separate preliminary assistant assessment, not human labels.
- [Engineering Audit](docs/ENGINEERING_AUDIT.md): clean-install, adversarial, grounding, checksum, and parse-only checks; known gaps.
- [Implementation Roadmap](docs/IMPLEMENTATION_ROADMAP.md): implementation history and acceptance evidence.
- [Project Completion Status](docs/FINAL_REMAINING_WORK.md): final handoff status and administrative notes.
- [Local Model Setup](docs/LOCAL_MODEL_SETUP.md): optional CPU inference runtime and model installation.
- [Human Review Attestation](docs/HUMAN_REVIEW_ATTESTATION.md): review of intent annotations.

## Repository layout

- `src/nl2bash/`: application, data, annotation, classifier, generation, validation, and evaluation modules.
- `data/raw/nl2bash/`: licensed original corpus files and dataset notice.
- `data/processed/nl2bash/`: duplicate-aware train/dev/test JSONL and checksum manifest.
- `data/annotations/`: worklists, confirmed exports, provenance manifests, and review records.
- `models/`: committed classifier and manifest.
- `artifacts/evaluation/`: frozen configuration/threshold, reports, and one-time guards.
- `docs/`: project, methodology, implementation, evaluation, audit, and reproducibility documentation.
- `tests/`: offline regression tests for prompt, deterministic templates, lazy model loading, runtime configuration, and interactive mode.
- `.github/workflows/`: package smoke and experiment workflows.

Temporary test fixtures, caches, virtual environments, model binaries, and secrets are not committed. Regression tests use Python's standard `unittest` framework and require no network access.

## Limitations and safety

- Syntax validity does not prove that a command is semantically correct or safe.
- Safety rules and entity grounding are heuristic checks, not a sandbox or formal guarantee.
- The model can omit constraints, invent values, or generate an incorrect command.
- Known validator gaps are listed in [Engineering Audit](docs/ENGINEERING_AUDIT.md).
- NL2Bash covers only a subset of Bash syntax.
- Intent and entity test labels are AI-assisted and owner-approved; the entity sample is targeted and not prevalence-representative.
- Generation v7 is a small development experiment, not held-out generation test accuracy.

Generated commands must always be reviewed by a person before any use.
