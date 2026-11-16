# Technical Design

## 1. Planned technology stack

| Component | Technology | Purpose |
|---|---|---|
| Core application | Python | Application logic and component integration |
| Preprocessing | Python standard library and custom utilities | Input validation and removal of surrounding whitespace while preserving internal text and Unicode code points |
| Feature extraction | Scikit-learn TF-IDF | Convert text into features for classification |
| Intent classifier | Scikit-learn Logistic Regression | Predict the requested operation category |
| Parameter extraction | Python rules and regular expressions | Extract paths, extensions, file names, sizes, ports, process names, dates, and comparison conditions |
| Language model | Qwen2.5 1.5B Instruct | Generate Bash commands and explanations |
| Model serving | Ollama | Run the selected model locally |
| Bash parsing | bashlex | Parse generated Bash syntax |

These are planned choices, not claims that the environment has already been configured or that the model has been benchmarked.

## 2. Application modules

The implementation is expected to be organized around the following responsibilities. The exact file layout may evolve as the code is developed.

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

The generation component will send the original request and structured NLP results to the locally served model. The prompt will specify that the model must return a Bash command and a concise explanation, and must not execute anything.

The application should handle unavailable model services, malformed model responses, empty output, and generation timeouts.

The rule-based entity extractor preserves exact values and source spans and reports incomplete or contradictory parameters; see [Entity Extraction](ENTITY_EXTRACTION.md).

The model is a generation component, not the sole source of intent understanding. The separately implemented classifier and extractor provide measurable NLP components and additional context for generation.

## 4. Validation boundaries

Validation will include:
- Parsing the generated command to identify syntax errors.
- Applying explicit rules to flag selected risky command patterns.
- Reporting syntax status and safety warnings separately.

The validator is not a sandbox and does not establish that a command is harmless. The application will not execute generated commands as part of normal operation.

## 5. Runtime and configuration

The initial target is a local Linux environment with Python. Ollama and the selected model will be required for local LLM generation. Model configuration should be kept separate from application logic so that the model can be changed without rewriting the NLP pipeline.

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

Intent suggestions are generated from request-text rules only and remain separate from confirmed labels. Reviewers edit the versioned training CSV worklist; the importer validates source identity, group identity, suggestion metadata, review status, and taxonomy labels. Only explicitly confirmed rows are exported for classifier training. Development and test use separate blind worklists with no suggested labels and partition-specific confirmed exports. Raw data, worklists, confirmed annotations, and manifests are versioned in Git; the test worklist remains unlabelled until the final evaluation is ready.
