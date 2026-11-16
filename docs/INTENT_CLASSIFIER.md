# Intent Classifier

## 1. Goal

Implement a measurable NLP baseline that predicts one primary intent from a natural-language Bash request.

The baseline uses a Scikit-learn TF-IDF vectorizer followed by Logistic Regression. It is separate from the LLM command generator: the classifier predicts the operation category, while the LLM is responsible for producing Bash syntax.

## 2. Input contract

Training uses only explicitly confirmed annotations from the training partition.

The loader is implemented in src/nl2bash/classifier_data.py. It returns request text, labels, example IDs, duplicate-group IDs, class counts, and source checksums only after all checks pass.

Before fitting, the trainer must verify:

- The dataset manifest identifies the training partition and its SHA-256 checksum.
- The confirmed-annotation manifest refers to the same training checksum.
- The annotation JSONL checksum and record count match its manifest.
- Every annotation has annotation_status=confirmed and a valid taxonomy label.
- Each example ID, request, and duplicate-group ID match the original training record.
- Example IDs and duplicate groups are unique in the labelled subset.
- Every taxonomy label has enough confirmed examples for the configured minimum.

Heuristic suggestions, pending rows, ambiguous rows, rejected rows, and reference commands are not training labels or classifier input.

## 3. Baseline configuration

Scikit-learn is constrained to the 1.7 series because the configured project environment uses Python 3.10. The dependency and transitive versions are recorded in uv.lock.

Initial, explicit settings:

| Component | Initial setting |
|---|---|
| Text feature extraction | TfidfVectorizer |
| Token features | Word unigrams and bigrams |
| Lowercasing | Enabled |
| Sublinear term frequency | Enabled |
| Maximum vocabulary | 50,000 features |
| Classifier | LogisticRegression |
| Solver | lbfgs |
| Maximum iterations | 2,000 |
| Random seed | 42 |

These are baseline settings, not claimed optimal hyperparameters. Changes must be recorded with their development-set results.

## 4. Training and model artifacts

Training fits one Scikit-learn pipeline so that inference always uses the exact same fitted TF-IDF vocabulary and Logistic Regression parameters.

The generated model and its JSON manifest live under the ignored models/ directory. The manifest records the source dataset revision, training-partition checksum, confirmed-annotation checksum, label counts, feature settings, classifier settings, and Scikit-learn version.

Model files are generated locally and are not committed to Git. The serialized joblib file must be treated as a trusted local artifact; do not load model files from untrusted sources because joblib uses Python object serialization.

The trainer must fail before writing model artifacts when the confirmed training data is empty, invalid, or below the per-label minimum. The data loader enforces this contract before any Scikit-learn component is called.

## 5. Prediction behavior

Prediction accepts one non-empty natural-language request. It returns:

- The highest-scoring predicted label.
- The model's highest class-probability estimate.
- A low-confidence indicator.
- The configured confidence threshold.

The probability is a model score, not a calibrated probability that the answer is correct. The current default threshold is 0.45, a provisional placeholder only; it must be selected using confirmed development data before final evaluation.

When the score is below the threshold, the prediction is marked low confidence and the public intent result is other_or_ambiguous. The underlying top-scoring label remains available for diagnostics. If the request contains no terms in the fitted TF-IDF vocabulary, the predictor returns other_or_ambiguous with a score of 0.0 and no raw top label.

The classifier never executes a command. Model loading checks the model checksum, pipeline structure, taxonomy, and exact Scikit-learn, NumPy, and joblib versions recorded at training time.

## 6. Evaluation protocol

The classifier must not use development or test examples during fitting.

- Training partition: fit TF-IDF and Logistic Regression using confirmed training annotations.
- Development partition: compare documented configurations and select the confidence threshold.
- Test partition: perform one final evaluation after the configuration is frozen.

Held-out evaluation labels must be explicitly confirmed by a reviewer and must be validated against the corresponding source partition. They must never be inferred from request-text heuristics or reference commands.

Report accuracy, macro and weighted precision/recall/F1, per-class precision/recall/F1, class support, and a confusion matrix. Include the selected threshold and the number of low-confidence predictions.

No test result is valid until the test annotations are confirmed and the final configuration is frozen.

## 7. CLI usage

Install the locked project dependencies and package:

    uv sync --locked
    uv pip install --python .venv/bin/python -e .

Train the model after the confirmed training export meets the per-label minimum:

    .venv/bin/nl2bash-classifier train

The command reads the confirmed annotation export and its manifest, validates every row against the training partition, and writes the model and manifest under models/.

Predict one request using the verified local model:

    .venv/bin/nl2bash-classifier predict --request "Find all Python files under the current directory"

The prediction command prints JSON with the public intent label, diagnostic top label, score, threshold, and low-confidence flag. It does not generate or execute a Bash command.

At the current project state, the train command intentionally exits with an error because the confirmed annotation export is empty. Complete and validate the human-reviewed pilot first.

## 8. Current limitation

The annotation workflow currently has a 500-example training pilot. All 500 rows are pending and the confirmed export contains zero rows. Therefore no real classifier can be fitted or evaluated yet.

Implementation and offline verification may use temporary synthetic fixtures outside the repository. Such fixtures must never be committed, must never be added to the project's annotation data, and must never be presented as model results.
