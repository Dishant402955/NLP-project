# Dataset and Evaluation Plan

## 1. Purpose

The project requires examples that connect natural-language requests with their intended operation, relevant parameters, and reference Bash commands. These examples will support intent-classifier training, entity-extraction development, and command-generation evaluation.

## 2. Candidate dataset

The initial candidate is NL2Bash:

- Paper: [NL2Bash: A Corpus and Semantic Parser for Natural Language Interface to the Linux Operating System](https://arxiv.org/abs/1802.08979)
- Repository: [TellinaTool/nl2bash](https://github.com/TellinaTool/nl2bash)

Before using the dataset, inspect its license, format, command coverage, and train/test split. Record any filtering or transformations. Do not assume that the dataset can be redistributed with this project.

A small, clearly documented set of additional examples may be created to cover project-specific intents and parameters that are missing from the candidate dataset.

## 3. Data preparation

The planned preparation process is:

1. Inspect the source dataset and its licensing terms.
2. Identify natural-language and command fields.
3. Normalize examples without removing meaningful paths, extensions, numbers, or command options.
4. Assign intent labels for the selected operation categories.
5. Annotate entities and parameters needed by the extraction component.
6. Create training, validation, and test splits.
7. Keep test examples separate from training and prompt-development examples.

Dataset versions, filtering decisions, and split details will be documented so experiments can be repeated.

## 4. Evaluation metrics

### Intent classification

- Accuracy
- Precision
- Recall
- F1-score

Report per-class results as well as an overall score where appropriate.

### Entity extraction

- Precision
- Recall
- F1-score

Evaluate extracted values and their associated entity types against annotated examples.

### Command generation

- Exact-match accuracy against reference commands.
- Syntax-validity rate using the Bash parser.
- Manual or controlled semantic assessment for a representative sample, since different commands can produce equivalent results.

Exact string matching alone is not a complete measure of command correctness.

### Runtime

Measure generation latency under a documented hardware and model configuration. Report the number of examples and the measurement method.

## 5. Experiments

The planned experiments are:

1. Establish an intent-classification baseline using TF-IDF and Logistic Regression.
2. Evaluate entity extraction on annotated examples.
3. Evaluate command generation using the original request as input.
4. Evaluate command generation using the original request together with predicted intent and extracted parameters.
5. Compare the results to understand whether the NLP understanding components improve generation quality.

Any semantic or functional testing must use a controlled, isolated test environment and a reviewed set of commands. Generated commands must not be executed on the user's normal system.

## 6. Reporting

The final report should include:
- Dataset source, license, size, and split details.
- Intent categories and annotation procedure.
- Model name and version.
- Evaluation metrics and results.
- Representative successful and unsuccessful examples.
- Limitations, including ambiguity, unsupported operations, and semantically incorrect commands.
