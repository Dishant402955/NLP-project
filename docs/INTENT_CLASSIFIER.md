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

The generated model and its JSON manifest live under the versioned `models/` directory. The manifest records the source dataset revision, training-partition checksum, confirmed-annotation checksum, label counts, feature settings, classifier settings, and Scikit-learn version. The current model is committed for reproducibility but remains provisional because its training annotations are AI-assisted; see [Annotation Review Status](ANNOTATION_REVIEW_STATUS.md).

The serialized joblib file must be treated as a trusted project artifact; do not load model files from untrusted sources because joblib uses Python object serialization.

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

The classifier must not use development or test examples during fitting. The implementation validates each held-out export against its own partition checksum and requires the export manifest to identify blind manual review.

- Training partition: fit TF-IDF and Logistic Regression using confirmed training annotations.
- Development partition: select the confidence threshold using confirmed development labels only.
- Test partition: perform one final evaluation after the threshold is frozen. A project-level guard prevents a second run, even when a different report filename is supplied.

Held-out evaluation labels must be explicitly confirmed by a reviewer and must be validated against the corresponding source partition. They must never be inferred from request-text heuristics or reference commands.

The threshold-selection rule maximizes development macro-F1 subject to at least 80% prediction coverage. Ties are resolved by higher coverage, then by the lower threshold. Coverage is the fraction of examples not marked low-confidence. The selected threshold, development metrics, source checksums, and model checksum are written to a frozen JSON artifact.

Report accuracy, macro and weighted precision/recall/F1, per-class precision/recall/F1, class support, and a confusion matrix. Macro averages include only classes with at least one confirmed example in that evaluation partition; macro_label_count records how many classes contributed. Classes with zero support remain in the per-class report and confusion matrix with zero support. Include the selected threshold, prediction coverage, and low-confidence count.

Low-confidence and zero-known-feature requests are mapped to other_or_ambiguous for the public classifier result. The separate coverage and low-confidence fields make abstention visible in the report.

No test result is valid until the test annotations are confirmed and the final configuration is frozen.

## 7. CLI usage

Install the locked project dependencies and package:

    uv sync --locked

Train the model after the confirmed training export meets the per-label minimum:

    .venv/bin/nl2bash-classifier train

The command validates the confirmed export against the training partition and writes the model and manifest under the versioned `models/` directory. Commit the updated model and manifest together after training.

Select and freeze a confidence threshold using the confirmed, blind-reviewed development partition:

    .venv/bin/nl2bash-classifier select-threshold

The default output is artifacts/evaluation/frozen_dev_threshold.json. It records the chosen threshold, development metrics, model checksum, and development annotation checksums. The minimum prediction coverage defaults to 80%.

Use the frozen threshold for ordinary prediction:

    .venv/bin/nl2bash-classifier predict --request "Find all Python files under the current directory" --frozen-threshold artifacts/evaluation/frozen_dev_threshold.json

The prediction command prints JSON with the public intent label, diagnostic top label, uncalibrated score, threshold, and low-confidence flag. The frozen threshold must belong to the loaded model.

Run the final test evaluation only after the development threshold has been frozen:

    .venv/bin/nl2bash-classifier evaluate-test

The report is written to artifacts/evaluation/test_report.json. A separate test_evaluation.lock guard prevents another test evaluation in the same project workspace, including attempts that use a different output filename. A guard left in in_progress state after an interrupted process requires manual inspection before any reset.

The classifier CLI also provides --help for each command and options for alternate input and artifact paths. It never generates or executes a Bash command.

## 8. Current limitation and provisional run

The current local annotation state is: 500 AI-assisted training labels, 375 AI-assisted blind development labels, and zero test labels. The training and development labels were assigned from the natural-language requests without using paired commands or classifier predictions. However, both partitions were reviewed by the same AI annotator. They are not independent human ground truth and may share systematic annotation bias.

A project-specific baseline has been fitted and a development threshold has been selected from these provisional labels. Its metrics are engineering diagnostics only, not final academic results. A human reviewer should independently adjudicate the training and development annotations, with particular attention to category boundaries and the `other_or_ambiguous` class, before finalizing claims. The test partition must remain untouched until the taxonomy, model, and threshold are frozen.

Implementation and offline verification may use temporary synthetic fixtures outside the repository. Such fixtures must never be committed, must never be added to the project's annotation data, and must never be presented as model results.
