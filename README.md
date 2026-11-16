# Natural Language to Bash Command Generator

A hybrid NLP system that translates natural-language instructions into Bash commands. It combines traditional NLP techniques for understanding requests with a lightweight instruction-tuned language model for command generation.

The system displays the generated command, explains what it does, and checks its syntax and basic safety properties. It does not execute commands automatically.

## Project status

The Python package foundation, reproducible NL2Bash dataset preparation, annotation workflow, and TF-IDF plus Logistic Regression intent-classifier implementation are in place. The 500-row training pilot and the 375-row blind development and test worklists are generated locally, but all labels are still pending human review. No project model has been trained and no accuracy result is available yet. Entity extraction, LLM command generation, Bash validation, and the end-to-end command-generation CLI remain planned.

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
find . -type f -name "*.py" -size +10M
```

## Planned technology stack

| Area | Planned technology |
|---|---|
| Programming language | Python |
| Text preprocessing | Python standard library and custom utilities |
| Intent classification | Scikit-learn, TF-IDF, Logistic Regression |
| Entity and parameter extraction | Rule-based extraction |
| Command generation | Qwen2.5 1.5B Instruct through Ollama |
| Bash syntax parsing | bashlex |
| Verification | Temporary scripts outside the repository; no test source is committed |
| Initial interface | Command-line interface |

The stack is a project plan and may be adjusted after environment checks and initial experiments.

## Documentation

Detailed project documentation is maintained in the [docs](docs/) directory.

- [Project Plan](docs/PROJECT_PLAN.md): scope, objectives, requirements, deliverables, and exclusions.
- [System Architecture](docs/ARCHITECTURE.md): component responsibilities and the end-to-end data flow.
- [Technical Design](docs/TECHNICAL_DESIGN.md): planned modules, technology choices, and implementation boundaries.
- [Dataset and Evaluation](docs/DATASET_AND_EVALUATION.md): dataset audit, licensing, split strategy, metrics, and experiments.
- [Intent Taxonomy](docs/INTENT_TAXONOMY.md): intent labels, definitions, boundary examples, and taxonomy rules.
- [Annotation Guide](docs/ANNOTATION_GUIDE.md): commands and instructions for reviewing, confirming, and validating the training and held-out annotation worklists.
- [Intent Classifier](docs/INTENT_CLASSIFIER.md): TF-IDF and Logistic Regression training contract, prediction behavior, and evaluation rules.
- [Implementation Roadmap](docs/IMPLEMENTATION_ROADMAP.md): ordered development steps, acceptance criteria, verification protocol, and commit strategy.

## Project evaluation

The system will be evaluated at both component and end-to-end levels.

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

The NL2Bash dataset license and structure have been audited. Raw data and annotations remain outside Git; see the dataset documentation for the audit findings and limitations.
