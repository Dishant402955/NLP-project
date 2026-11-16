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

Performs lightweight normalization and tokenization where useful. Preprocessing must preserve meaningful shell-related details, including paths, file extensions, numbers, flags, and technical terms. It must not remove information required for command generation.

### 3.3 Intent classification

Predicts the operation category represented by the request. Initial categories may include file search, file inspection, text processing, process inspection, directory operations, and system information.

The initial classifier will use TF-IDF features and a Scikit-learn Logistic Regression model. The category set and training examples will be defined as part of the dataset preparation work.

### 3.4 Entity and parameter extraction

Extracts values that constrain the requested operation. Examples include:
- File extensions, names, and paths.
- Numeric values and size units.
- Ports and process names.
- Dates and time ranges.
- Comparison conditions such as greater than or smaller than.

The first implementation will use explicit patterns and rules. The extracted values will be represented in a structured form so that they can be inspected and passed to the generation component.

### 3.5 LLM command generation

Receives the original request, predicted intent, and extracted parameters. It generates:
- A Bash command.
- A short explanation of the command.
- Any assumptions or missing details that affect the result.

The planned local model is Qwen2.5 1.5B Instruct served through Ollama. Model suitability and hardware requirements will be checked before finalizing this choice.

### 3.6 Validation

Checks the generated command using a Bash parser such as bashlex and applies additional rules to identify known dangerous patterns. Validation results should distinguish syntax errors from safety warnings.

A parser can identify syntax problems, but neither parsing nor a basic rule set can prove that a command is safe or produces the intended result.

### 3.7 Output

Displays the generated command, explanation, and validation findings. The user remains responsible for deciding whether to run the command.

## 4. Example data flow

Input:

> Find all Python files larger than 10 MB in the current directory.

Illustrative NLP output:

```json
{
  "intent": "file_search",
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
find . -type f -name "*.py" -size +10M
```

The validator checks the command syntax and applies the configured safety rules. The application then displays the result without executing it.

## 5. Design principles

- Keep intent classification, parameter extraction, generation, and validation as separate components.
- Keep the original natural-language request available throughout the pipeline.
- Make intermediate NLP results inspectable for debugging and evaluation.
- Do not treat model output as trusted shell input.
- Do not execute generated commands automatically.
- Report uncertainty and missing information instead of silently inventing parameters.
