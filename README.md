# Natural Language to Bash Command Generator

A hybrid NLP system that translates natural-language Linux requests into Bash command proposals. Traditional NLP predicts the requested operation and extracts explicit parameters; a local instruction-tuned language model generates a command; deterministic checks inspect syntax, selected constraints, and known risky patterns.

**Safety boundary: generated commands are displayed only. The application does not execute them.**

## Project status

**Core implementation, recorded evaluations, selected engineering audit, human semantic-review milestone, and presentation review are complete.** The project owner confirmed that all 80 generated candidates from the 40-request v7 development comparison received human semantic review. The completion record is `data/annotations/generation_dev_v7_human_review_attestation.json`. The completion confirmation did not include per-candidate scores or reviewer notes, so no human semantic accuracy score or A/B win rate is claimed. The original worksheet remains unchanged rather than being populated with invented ratings.

The project owner has also approved the presentation. Any college-specific cover-page fields or required formatting are administrative submission details, not outstanding technical work.

## How it works

1. The CLI accepts a natural-language Linux task and preserves its original wording.
2. Preprocessing validates the request and trims surrounding whitespace only.
3. A Scikit-learn TF-IDF + Logistic Regression model predicts an intent category and confidence.
4. A deterministic rule-based extractor finds supported parameters such as extensions, paths, file names, sizes, ports, process names, dates, comparison conditions, programming languages, and case-sensitivity requirements. It preserves exact values and source spans, and reports incomplete or conflicting cues.
5. The generation adapter sends the original request and structured NLP context to a local Qwen2.5-1.5B-Instruct model. The model must return structured JSON containing a Bash command, explanation, and assumptions.
6. The validator runs Bash syntax parsing in parse-only mode, applies heuristic risk checks, and checks selected explicit constraints against the generated text.
7. The CLI displays the command and all findings. It never invokes a shell to execute generated text.

See [System Architecture](docs/ARCHITECTURE.md), [Technical Design](docs/TECHNICAL_DESIGN.md), and [Reproducibility Guide](docs/REPRODUCIBILITY.md).

## Technology

| Area | Implementation |
|---|---|
| Language | Python 3.10+ |
| Packaging/environment | setuptools, uv, locked dependencies |
| Intent classification | Scikit-learn TF-IDF word unigrams/bigrams + Logistic Regression |
| Entity extraction | Deterministic Python rules and regular expressions |
| Generation | Qwen2.5-1.5B-Instruct Q4_K_M GGUF |
| Inference | llama-cpp-python 0.3.37, local CPU inference |
| Bash parsing | `bash -n` parse-only mode and bashlex AST analysis |
| Interfaces | `nl2bash`, `nl2bash-classifier`, `nl2bash-annotations`, `nl2bash-prepare-dataset` CLIs |

The base package works without the optional LLM runtime. The model binary is downloaded separately, not committed to Git, and verified using a pinned SHA-256. Setup instructions are in [Local Model Setup](docs/LOCAL_MODEL_SETUP.md).

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

For full reproduction instructions, including safe data preparation and evaluation commands, see [Reproducibility Guide](docs/REPRODUCIBILITY.md).

## Recorded results

| Component | Result | Interpretation |
|---|---|---|
| Intent classifier | 375-example one-time test: accuracy 0.6853, macro-F1 0.6400, weighted-F1 0.6793, coverage 0.9947 | Test labels were AI-assisted and owner-approved, not independently adjudicated |
| Entity extraction | 66 targeted requests / 113 gold spans: micro precision 0.8588, recall 0.6460, F1 0.7374; macro-F1 0.7517 | Targeted sample, not prevalence-representative; some entity types have sparse or zero support |
| Command generation | 40-request paired development comparison (80 candidates): request-only generated 39/40; NLP context 40/40; both had 2/40 exact string matches | Development-only experiment; automated syntax/constraint checks are not semantic accuracy |
| Human semantic review | Owner confirmed all 80 v7 candidates reviewed | Completion is attested; no per-row ratings were provided for computing a human aggregate score |

Detailed reports and per-class/per-type metrics are committed under `artifacts/evaluation/`. The classifier and entity test evaluations are one-time guarded runs. **Do not rerun them, remove their guards, or use held-out test results for tuning.**

## Documentation map

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
- [Command-Generation Evaluation](docs/GENERATION_EVALUATION.md): v6/v7 development comparisons and semantic-review status.
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
- `.github/workflows/`: package smoke and experiment workflows.

Temporary test fixtures, caches, virtual environments, model binaries, and secrets are not committed. Project policy keeps standalone test source outside the repository; CI uses inline smoke and integrity checks.

## Limitations and safety

- Syntax validity does not prove that a command is semantically correct or safe.
- Safety rules and entity grounding are heuristic checks, not a sandbox or formal guarantee.
- The model can omit constraints, invent values, or generate an incorrect command.
- Known validator gaps are listed in [Engineering Audit](docs/ENGINEERING_AUDIT.md).
- NL2Bash covers only a subset of Bash syntax.
- Intent and entity test labels are AI-assisted and owner-approved; the entity sample is targeted and not prevalence-representative.
- Generation v7 is a small development experiment, not held-out generation test accuracy.

Generated commands must always be reviewed by a person before any use.
