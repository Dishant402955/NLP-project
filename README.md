# Natural Language to Bash Command Generator

A hybrid NLP system that translates natural-language instructions into Bash commands. It combines traditional NLP techniques for understanding requests with a lightweight instruction-tuned language model for command generation.

The system displays the generated command, explains what it does, and checks its syntax and basic safety properties. It does not execute commands automatically. Safety checks are heuristic warnings, not proof of safety.

## Project status

The Python package foundation, reproducible dataset preparation, intent classifier, deterministic entity extractor, local Qwen command-generation adapter, Bash syntax/safety validation, and end-to-end CLI are implemented. The project owner reviewed the 500 training and 375 development annotations after AI-assisted labelling and reported zero further corrections. The 375 test labels have also been approved without corrections from request-only AI proposals and are now present in the confirmed test export. This test annotation is AI-assisted and owner-approved, not independent ground truth; see [Annotation Review Status](docs/ANNOTATION_REVIEW_STATUS.md). The classifier, threshold, generator, prompt, and validation configuration are frozen from development work. The development generation comparison is recorded under `artifacts/evaluation/`. Final test classifier metrics, a reviewed entity benchmark, a larger generation evaluation with semantic ratings, and the final engineering audit remain outstanding.

## Versioned research artifacts

The repository includes the licensed NL2Bash raw source files, reproducibly generated partitions, train/development/test annotation worklists and exports, the classifier, and its frozen development threshold. Source revisions, checksums, and annotation provenance are recorded in manifests, the [Annotation Review Status](docs/ANNOTATION_REVIEW_STATUS.md), and the [Intent Audit Log](docs/INTENT_AUDIT_LOG.md). The test decision worksheet contains no reference commands or classifier predictions; its separate AI proposal file is retained for transparency. The test export includes explicit AI-assisted, owner-approved provenance. Test scripts, temporary fixtures, caches, virtual environments, and secrets are not committed.

## Project objectives

- Accept Linux command requests written in plain English.
- Identify the operation the user wants to perform.
- Extract relevant parameters such as file extensions, paths, sizes, ports, dates, and process names.
- Generate an appropriate Bash command.
- Explain the generated command in understandable language.
- Validate Bash syntax and flag potentially dangerous commands.
- Evaluate the performance of the individual components and the complete system.

## How it works

1. **Input:** The user enters a natural-language request.
2. **NLP understanding:** The system preprocesses the text, classifies the intent, and extracts relevant entities and parameters.
3. **Command generation:** A language model uses the original request and extracted information to generate a Bash command and explanation.
4. **Validation:** The generated command is checked for Bash syntax and against basic safety rules.
5. **Output:** The system displays the command, explanation, and validation result. It does not run the command.

For example, the request:

> Find all Python files larger than 10 MB in the current directory.

Could produce:

```bash
find . -type f -name "*.py" -size +10000000c
```

## Implemented technology stack

| Area | Technology |
|---|---|
| Programming language | Python |
| Text preprocessing | Python standard library and custom utilities |
| Intent classification | Scikit-learn, TF-IDF, Logistic Regression |
| Entity and parameter extraction | Rule-based extraction |
| Command generation | Qwen2.5-1.5B-Instruct Q4_K_M GGUF through llama-cpp-python (local CPU inference) |
| Bash syntax parsing | `bash -n` parse-only mode plus bashlex AST analysis |
| Verification | Temporary scripts outside the repository; no test source is committed |
| Initial interface | Command-line interface |

The generation runtime and quantization were selected after inspecting the agent host (4 logical CPU cores, approximately 7.5 GiB RAM, no detected NVIDIA GPU). Model weights are downloaded separately and are not committed to Git. See [Local Model Setup](docs/LOCAL_MODEL_SETUP.md).

## Documentation

Detailed project documentation is maintained in the [docs](docs/) directory.

- [Project Plan](docs/PROJECT_PLAN.md): scope, objectives, requirements, deliverables, and exclusions.
- [System Architecture](docs/ARCHITECTURE.md): component responsibilities and the end-to-end data flow.
- [Technical Design](docs/TECHNICAL_DESIGN.md): implemented modules, technology choices, and validation boundaries.
- [Dataset and Evaluation](docs/DATASET_AND_EVALUATION.md): dataset audit, licensing, split strategy, metrics, and experiments.
- [Intent Taxonomy](docs/INTENT_TAXONOMY.md): intent labels, definitions, boundary examples, and taxonomy rules.
- [Annotation Guide](docs/ANNOTATION_GUIDE.md): commands and instructions for reviewing, confirming, and validating the training and held-out annotation worklists.
- [Intent Classifier](docs/INTENT_CLASSIFIER.md): TF-IDF and Logistic Regression training, prediction, threshold selection, and one-time test evaluation commands.
- [Annotation Review Status](docs/ANNOTATION_REVIEW_STATUS.md): annotation provenance, partition counts, development metrics, approved test-label distribution, and remaining evaluation steps.
- [Entity Extraction](docs/ENTITY_EXTRACTION.md): supported entity types, extraction rules, structured output, uncertainty findings, and exact-span evaluation.
- [Implementation Roadmap](docs/IMPLEMENTATION_ROADMAP.md): ordered development steps, acceptance criteria, verification protocol, and commit strategy.
- [Local Model Setup](docs/LOCAL_MODEL_SETUP.md): local GGUF model installation, runtime setup, and CLI usage.
- [Command-Generation Evaluation](docs/GENERATION_EVALUATION.md): development-only comparison of request-only and NLP-context generation, with limitations and frozen configuration.
- [Final Test Review](docs/ANNOTATION_GUIDE.md#10-final-test-review-outcome): completed test annotation outcome, provenance, and validation/evaluation commands.
- [Test Review Protocol](docs/TEST_PRELIMINARY_ANNOTATION_PROTOCOL.md): completed owner-approved test annotation, provenance, and one-time evaluation protocol.
- [Human Review Attestation](docs/HUMAN_REVIEW_ATTESTATION.md): final human review of the AI-assisted training and development intent labels.

## Quick start

Install the base package and run the syntax/risk validator:

```bash
uv sync
uv run nl2bash validate --command 'find . -type f -name "*.py" -size +10000000c'
```

To enable local generation, install the optional local inference runtime separately and download the model as described in [Local Model Setup](docs/LOCAL_MODEL_SETUP.md), then run:

```bash
uv sync --locked
uv pip install --python .venv/bin/python llama-cpp-python==0.3.37
uv run nl2bash generate --request 'Find all Python files larger than 10 MB in the current directory.'
```

The CLI prints the proposed command, explanation, assumptions, syntax result, and risk warnings. It never executes the command.

## Project evaluation

The project has a development-only classifier and generation evaluation. The final test classifier evaluation, entity gold benchmark, and larger generation evaluation remain to be completed.

- Intent classification: accuracy, precision, recall, and F1-score.
- Entity extraction: precision, recall, and F1-score.
- Command generation: exact-match accuracy.
- Syntax validation: proportion of generated commands accepted by the Bash parser.
- Runtime: command-generation latency.

Exact command matching is useful for comparison but does not capture every semantically equivalent command. Evaluation will account for this limitation where practical.

## Safety boundary

Generated commands are shown to the user and are not executed automatically. Syntax validity does not establish that a command is safe or that it will have the intended effect. Safety checks are intended to flag known risks, not to provide a formal guarantee.

## Development verification

The application is verified at every implementation step. Test scripts and temporary fixtures are kept outside this repository; no test source or test directory is committed. The review and verification process is defined in [Implementation Roadmap](docs/IMPLEMENTATION_ROADMAP.md).

## Initial scope

The first version targets Bash commands on Linux. Support for other shells, automatic execution, autonomous terminal operation, and model training from scratch are outside the initial project scope.

## Reference

The project will investigate the NL2Bash dataset and the associated research:

- [NL2Bash: A Corpus and Semantic Parser for Natural Language Interface to the Linux Operating System](https://arxiv.org/abs/1802.08979)
- [NL2Bash repository](https://github.com/TellinaTool/nl2bash)

The NL2Bash dataset license and structure have been audited. The licensed raw data, processed splits, annotations, and provenance manifests are included in Git; see the dataset documentation for the audit findings and limitations.
