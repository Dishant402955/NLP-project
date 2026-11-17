# System Architecture

## 1. Overview

The application follows a pipeline architecture. Traditional NLP components identify the user's intended operation and extract relevant parameters. A language model then generates a Bash command using this information. A final validation stage checks the generated command before it is shown to the user.

## 2. Architecture flow

```text
Natural-language request
          |
          v
Text preprocessing
          |
          v
Intent classification
          |
          v
Entity and parameter extraction
          |
          v
LLM command generation
          |
          v
Bash syntax and safety checks
          |
          v
Command, explanation, and validation result
```

## 3. Component responsibilities

### 3.1 Input

Receives a natural-language instruction from the command-line interface. The original request is retained and passed to the generation component.

### 3.2 Text preprocessing

Validates the input and removes only surrounding whitespace. Later NLP components may create derived token or feature representations, but the original request remains unchanged and available to the generator. Paths, file extensions, numbers, flags, punctuation, quotes, and internal whitespace must be preserved.

### 3.3 Intent classification

Predicts the operation category represented by the request. The initial intent labels cover file discovery, text search and processing, file and directory management, permissions and ownership, process and job management, system information, network and remote operations, archive and compression, shell and session operations, and an other/ambiguous fallback.

The implemented classifier uses TF-IDF features and a Scikit-learn Logistic Regression model. The project-defined categories and annotation rules are documented in the [Intent Taxonomy](INTENT_TAXONOMY.md).

### 3.4 Entity and parameter extraction

Extracts values that constrain the requested operation. The deterministic extractor supports file extensions, paths, file names, sizes, ports, process names, process metrics, date/time phrases, comparison conditions, programming-language mentions, and explicit case-sensitivity requirements. It preserves each exact source value and character span, with optional normalized values for sizes, ports, extensions, and comparison operators.

Incomplete or contradictory cues are represented as structured extraction issues rather than guessed values. The implementation and current limitations are documented in [Entity Extraction](ENTITY_EXTRACTION.md). Rule-based extraction is intentionally separate from intent classification and language-model generation.

### 3.5 LLM command generation

Receives the original request, predicted intent, and extracted parameters. It generates:
- A Bash command.
- A short explanation of the command.
- Any assumptions or missing details that affect the result.

The implemented local model is Qwen2.5-1.5B-Instruct Q4_K_M in GGUF format, loaded through llama-cpp-python for CPU inference. The model file is downloaded separately to the user cache and is not committed to Git. The exact model revision and setup process are documented in [Local Model Setup](LOCAL_MODEL_SETUP.md).

### 3.6 Validation

Checks syntax in parse-only mode with `bash -n`, uses bashlex for supplementary AST analysis, and applies conservative rules for known high-impact patterns. A separate entity-grounding check flags selected explicit constraints that are missing from the generated text. Syntax errors, safety warnings, and dropped constraints are reported separately.

Neither parsing, entity grounding, nor a basic rule set can prove that a command is safe or semantically correct. The checks are warning mechanisms, not a sandbox or formal guarantee.

### 3.7 Output

Displays the generated command, explanation, and validation findings. The user remains responsible for deciding whether to run the command.

## 4. Example data flow

Input:

> Find all Python files larger than 10 MB in the current directory.

Illustrative NLP output:

```json
{
  "intent": "file_discovery",
  "entities": {
    "file_extension": ".py",
    "size_value": 10,
    "size_unit": "MB",
    "size_condition": "greater_than",
    "directory": "."
  }
}
```

Illustrative generated command:

```bash
find . -type f -name "*.py" -size +10000000c
```

The validator checks the command syntax and applies configured safety and explicit-constraint rules. For GNU `find -size`, normalized byte thresholds must use the `c` suffix and the comparison direction must agree with the request. The application then displays the result without executing it.

## 5. Design principles

- Keep intent classification, parameter extraction, generation, and validation as separate components.
- Keep the original natural-language request available throughout the pipeline.
- Make intermediate NLP results inspectable for debugging and evaluation.
- Treat explicit entities as constraints to preserve, and flag a generated command when selected constraints disappear.
- Do not treat model output as trusted shell input.
- Do not execute generated commands automatically.
- Report uncertainty and missing information instead of silently inventing parameters.


## 6. Source-module map

| Stage | Main source files | Responsibility |
|---|---|---|
| End-to-end CLI | `src/nl2bash/cli.py` | Defines `generate`, `validate`, and `evaluate-generation-dev`; orchestrates the application |
| Input normalization | `preprocessing.py` | Validates requests and trims surrounding whitespace without altering internal text |
| Intent prediction | `intent_prediction.py`, `intent_classifier.py` | Loads the checksum-verified model and returns label/confidence information |
| Classifier data and commands | `classifier_data.py`, `classifier_cli.py` | Validates confirmed labels, trains the pipeline, selects the development threshold, predicts, and evaluates |
| Entity extraction | `entity_extraction.py` | Extracts supported parameter types, exact source spans, normalized values, and extraction issues |
| Entity grounding | `entity_validation.py` | Checks selected explicit constraints against the generated command text |
| Model prompt and generation | `command_generation.py` | Loads the local GGUF model, constructs prompts, validates structured output, and returns command/explanation/assumptions |
| Frozen configuration | `generation_configuration.py` | Verifies model, runtime, prompt, classifier, threshold, package, and pipeline hashes/settings |
| Bash validation | `bash_validation.py` | Runs syntax-only Bash parsing, bashlex analysis, and heuristic risk checks |
| Corpus and splits | `corpus.py`, `dataset_builder.py`, `grouping.py`, `splitting.py`, `dataset_cli.py` | Loads parallel data, groups duplicate-linked rows, creates splits and manifests |
| Annotation | `annotations.py`, `annotation_validation.py`, `review_import.py`, `annotation_cli.py` | Creates review worklists, validates human decisions, imports test decisions, and exports confirmed labels |
| Classifier evaluation | `evaluation.py` | Selects the development threshold and implements the guarded one-time test evaluation |
| Entity evaluation | `entity_evaluation.py`, `entity_benchmark_cli.py` | Computes exact type/value/span metrics and enforces the one-time guard |
| Generation experiment | `generation_evaluation.py` | Runs paired request-only/NLP-context development evaluation and records automated metrics |

The pipeline is deliberately staged: classifier and extractor outputs are structured inputs to generation; the generator does not receive the paired reference command; validation inspects the generated text but does not execute it.
