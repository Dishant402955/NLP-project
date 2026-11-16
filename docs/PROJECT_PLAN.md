# Project Plan

## 1. Project title

Natural Language to Bash Command Generator

## 2. Problem statement

Linux users often need to translate an instruction expressed in ordinary language into a valid shell command. Users who do not know the relevant command, options, or syntax may find this difficult. Even experienced users can spend time looking up less familiar command combinations.

This project aims to build a system that accepts a natural-language request and generates a corresponding Bash command. It also provides an explanation and performs basic syntax and safety checks before presenting the result.

## 3. Project goal

Develop and evaluate a hybrid NLP system that translates natural-language instructions into Bash commands by combining traditional NLP techniques with a lightweight instruction-tuned language model.

## 4. Objectives

1. Accept command requests in plain English.
2. Preprocess input text for downstream language-processing tasks.
3. Classify requests into the project-defined intent categories using a labelled subset that will receive independent human review before final evaluation.
4. Extract useful entities and parameters from requests.
5. Generate Bash commands using a language model.
6. Explain the generated command.
7. Validate Bash syntax and flag potentially dangerous command patterns.
8. Evaluate each major component and the end-to-end system.

## 5. Scope

The initial system will:
- Target Bash commands on Linux.
- Support a selected set of common command-operation categories.
- Use a traditional machine-learning classifier for intent classification, with labels defined in the [Intent Taxonomy](INTENT_TAXONOMY.md).
- Use rule-based methods for extracting selected entities and parameters.
- Use an instruction-tuned language model for command generation.
- Display generated commands and explanations.
- Perform syntax checks and basic safety checks.
- Provide a command-line interface.

## 6. Out of scope

The initial project will not:
- Execute generated commands automatically.
- Operate as an autonomous terminal agent.
- Support PowerShell, Windows CMD, or other shells.
- Train a large language model from scratch.
- Learn automatically from arbitrary command manuals.
- Guarantee that every generated command is harmless or semantically correct.

## 7. Example use cases

| Natural-language request | Expected operation |
|---|---|
| Find all Python files | Search for files by extension |
| Show the ten largest files | Find and sort files by size |
| Find processes using port 8080 | Inspect processes associated with a port |
| Count lines in Python files | Find files and count their lines |
| Find files modified in the last 24 hours | Search by modification time |

These examples illustrate the intended scope. The categories are documented in the [Intent Taxonomy](INTENT_TAXONOMY.md) and will be checked against the dataset during annotation.

## 8. Research question

How effectively can a hybrid NLP and language-model-based system translate natural-language instructions into syntactically valid Bash commands?

## 9. Expected deliverables

- A working Python application with a command-line interface.
- An intent-classification component and its evaluation.
- An entity and parameter extraction component and its evaluation.
- An LLM-based Bash command-generation component.
- A command-validation component.
- A repeatable external verification procedure; verification scripts will not be stored in the repository.
- A documented evaluation dataset and experiment results.
- Project and technical documentation.

## 10. Development approach

Implementation will proceed incrementally according to the [Implementation Roadmap](IMPLEMENTATION_ROADMAP.md). Each step has explicit acceptance criteria and is reviewed before a small commit is created.

The project is verified, but test source code and temporary fixtures are kept outside the Git repository by project requirement. No test source directory, test script, or temporary test fixture will be committed. The dataset, model, and runtime environment will be checked before committing to implementation details that depend on them.
