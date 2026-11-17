# Technical Design

## 1. Implemented technology stack

| Component | Technology | Purpose |
|---|---|---|
| Core application | Python | Application logic and component integration |
| Preprocessing | Python standard library and custom utilities | Input validation and removal of surrounding whitespace while preserving internal text and Unicode code points |
| Feature extraction | Scikit-learn TF-IDF | Convert text into features for classification |
| Intent classifier | Scikit-learn Logistic Regression | Predict the requested operation category |
| Parameter extraction | Python rules and regular expressions | Extract paths, extensions, file names, sizes, ports, process names, dates, and comparison conditions |
| Language model | Qwen2.5-1.5B-Instruct Q4_K_M GGUF | Local command generation |
| Model runtime | llama-cpp-python | CPU inference from the local GGUF file |
| Bash syntax | `bash -n` plus bashlex | Parse-only syntax check and supplementary AST analysis |
| Constraint check | Deterministic entity grounding | Flag selected explicit request constraints missing from generated command text |

The base package installs without the optional inference binding. The local runtime and model were installed and exercised on the agent host; the small development experiment and its limitations are recorded in [Command-Generation Evaluation](GENERATION_EVALUATION.md).

## 2. Application modules

The implementation is organized around the following responsibilities:

- Input and CLI: collect requests and display results.
- Preprocessing: validate string input and remove surrounding whitespace while preserving all internal content.
- Dataset preparation: validate the parallel corpus, group duplicate-linked records, assign deterministic partitions, and write JSONL files with a manifest.
- Annotation workflow: produce a training-only review worklist, validate explicit human decisions, and export only confirmed labels through the nl2bash-annotations CLI.
- Intent classifier: fit and run a TF-IDF and Logistic Regression pipeline using only confirmed training annotations and the categories in [Intent Taxonomy](INTENT_TAXONOMY.md).
- Entity extractor: identify supported values and conditions while preserving exact source spans and reporting incomplete or contradictory cues.
- Entity evaluation: compute exact-span micro and per-type precision, recall, and F1 against an adjudicated entity sample.
- Command generator: construct the model prompt and obtain generated output.
- Validator: parse commands and apply safety rules.
- Evaluation: select a confidence threshold using confirmed development labels, then evaluate once on the blind-reviewed test partition with provenance and a one-time run guard.

## 3. Model interaction

The generation component sends the original request and, in the context-aware condition, the predicted intent and structured entity metadata to a local Qwen GGUF model through llama-cpp-python. A second request-only condition is retained for development experiments. The model must return a JSON object containing a Bash command, explanation, and assumptions. The adapter validates the schema and never invokes a shell.

The application handles unavailable local models, malformed structured responses, empty output, and invalid generation settings. Local inference runs synchronously; a hard per-request wall-clock timeout is not currently enforced.

The rule-based entity extractor preserves exact values and source spans and reports incomplete or contradictory parameters; see [Entity Extraction](ENTITY_EXTRACTION.md).

The model is a generation component, not the sole source of intent understanding. The separately implemented classifier and extractor provide measurable NLP components and additional context for generation.

## 4. Validation boundaries

Validation includes:
- Parsing the generated command to identify syntax errors.
- Applying explicit rules to flag selected risky command patterns.
- Reporting syntax status and safety warnings separately.

The validator is not a sandbox and does not establish that a command is harmless. It runs only `bash -n` (syntax-only mode) plus bashlex parsing and deterministic text/AST heuristics; it never runs the generated command itself. The application has no generated-command execution path.

## 5. Runtime and configuration

The target is a local Linux environment with Python. The base package does not require a model runtime; install the optional `local-llm` dependency to enable generation. The GGUF model is stored outside the repository under `~/.cache/nl2bash/models/` by default. Context length, CPU thread count, and model path are configurable. See [Local Model Setup](LOCAL_MODEL_SETUP.md).

## 6. Implementation constraints

- Prefer small, testable modules.
- Keep dependencies limited to those required by the project.
- Version the licensed raw dataset, processed partitions, annotation worklists/exports, model artifacts, and evaluation configuration with their provenance manifests.
- Keep test source code, temporary fixtures, generated caches, virtual environments, and secrets out of Git.
- Record model version and experiment configuration for reproducibility.
- Do not store secrets or machine-specific configuration in source control.

## 7. Verification policy

Executable checks are required for each implementation step. By project requirement, test source and fixtures will be created only in temporary locations outside the repository and will not be committed. See the [Implementation Roadmap](IMPLEMENTATION_ROADMAP.md) for the mandatory ten-pass review and adversarial-review procedure.

## 8. Dataset boundary

The NL2Bash source contains paired natural-language requests and Bash commands, but no project-specific intent labels or entity annotations. The dataset preparation CLI creates duplicate-aware partitions and a checksum manifest. The licensed raw dataset, annotation artifacts, and processed train/dev/test splits are versioned in Git with checksums and provenance manifests. See [Dataset and Evaluation](DATASET_AND_EVALUATION.md).

## 9. Annotation data boundary

Training intent suggestions are generated from request-text rules and remain separate from confirmed labels. Reviewers edit the versioned training CSV worklist; the importer validates source identity, group identity, suggestion metadata, review status, and taxonomy labels. Only explicitly confirmed rows are exported for classifier training. Development and test have separate partition-specific worklists with no in-file heuristic suggestions. The test labels were proposed in a separate request-only AI suggestion artifact, then all 375 were accepted by the project owner without corrections. Reference commands and classifier predictions were not used for the proposals. This is AI-assisted owner-approved annotation, not independent adjudication; the export manifest records that limitation.
