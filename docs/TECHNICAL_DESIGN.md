# Technical Design

## 1. Planned technology stack

| Component | Technology | Purpose |
|---|---|---|
| Core application | Python | Application logic and component integration |
| Preprocessing | NLTK and custom utilities | Tokenization and lightweight text normalization |
| Feature extraction | Scikit-learn TF-IDF | Convert text into features for classification |
| Intent classifier | Scikit-learn Logistic Regression | Predict the requested operation category |
| Parameter extraction | Python rules and regular expressions | Extract paths, extensions, sizes, ports, dates, and related values |
| Language model | Qwen2.5 1.5B Instruct | Generate Bash commands and explanations |
| Model serving | Ollama | Run the selected model locally |
| Bash parsing | bashlex | Parse generated Bash syntax |
| Tests | pytest | Unit and integration tests |

These are planned choices, not claims that the environment has already been configured or that the model has been benchmarked.

## 2. Application modules

The implementation is expected to be organized around the following responsibilities. The exact file layout may evolve as the code is developed.

- Input and CLI: collect requests and display results.
- Preprocessing: normalize and tokenize text where appropriate.
- Intent classifier: train, load, and run the intent model.
- Entity extractor: identify relevant values and conditions.
- Command generator: construct the model prompt and obtain generated output.
- Validator: parse commands and apply safety rules.
- Evaluation: calculate metrics and run repeatable experiments.

## 3. Model interaction

The generation component will send the original request and structured NLP results to the locally served model. The prompt will specify that the model must return a Bash command and a concise explanation, and must not execute anything.

The application should handle unavailable model services, malformed model responses, empty output, and generation timeouts.

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
- Keep datasets and model weights out of Git unless their size and licensing make inclusion appropriate.
- Record model version and experiment configuration for reproducibility.
- Do not store secrets or machine-specific configuration in source control.
