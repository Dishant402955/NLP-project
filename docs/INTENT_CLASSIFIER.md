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

The generated model and its JSON manifest live under the versioned `models/` directory. The manifest records the source dataset revision, training-partition checksum, confirmed-annotation checksum, label counts, feature settings, classifier settings, and Scikit-learn version. The current model is committed for reproducibility. The training annotations were AI-assisted initially and then reviewed by the project owner; see [Annotation Review Status](ANNOTATION_REVIEW_STATUS.md) and [Human Review Attestation](HUMAN_REVIEW_ATTESTATION.md).

The serialized joblib file must be treated as a trusted project artifact; do not load model files from untrusted sources because joblib uses Python object serialization.

The trainer must fail before writing model artifacts when the confirmed training data is empty, invalid, or below the per-label minimum. The data loader enforces this contract before any Scikit-learn component is called.

## 5. Prediction behavior

Prediction accepts one non-empty natural-language request. It returns:

- The highest-scoring predicted label.
- The model's highest class-probability estimate.
- A low-confidence indicator.
- The configured confidence threshold.

The probability is a model score, not a calibrated probability that the answer is correct. The model manifest retains 0.45 as a provisional fallback. The end-to-end CLI uses the separate, checksum-bound threshold selected and frozen from development data (currently 0.1361115729921777).

When the score is below the threshold, the prediction is marked low confidence and the public intent result is other_or_ambiguous. The underlying top-scoring label remains available for diagnostics. If the request contains no terms in the fitted TF-IDF vocabulary, the predictor returns other_or_ambiguous with a score of 0.0 and no raw top label.

The classifier never executes a command. Model loading checks the model checksum, pipeline structure, taxonomy, and exact Scikit-learn, NumPy, and joblib versions recorded at training time.

## 6. Evaluation protocol

The classifier must not use development or test examples during fitting. The implementation validates each held-out export against its own partition checksum and requires the canonical held-out worklist to contain no heuristic suggestion labels. The training and development labels were AI-assisted and then reviewed by the project owner. The 375 test labels were proposed by an AI assistant from request text only; the paired reference commands and classifier predictions were not used to produce the proposals. The project owner accepted all 375 suggestions without corrections. This is AI-assisted, owner-approved annotation, not independent ground truth, and test metrics must be interpreted accordingly.

- Training partition: fit TF-IDF and Logistic Regression using confirmed training annotations.
- Development partition: select the confidence threshold using confirmed development labels only.
- Test partition: perform one final evaluation after the threshold is frozen. A project-level guard prevents a second run, even when a different report filename is supplied.

Held-out evaluation labels must be explicitly confirmed and validated against the corresponding source partition. Record whether any AI-proposed labels were shown to the reviewer. The test label proposals in this project were request-only and did not use reference commands or classifier predictions, but the owner did see and approve the proposals. Do not describe them as independently adjudicated labels.

The threshold-selection rule maximizes development macro-F1 subject to at least 80% prediction coverage. Ties are resolved by higher coverage, then by the lower threshold. Coverage is the fraction of examples not marked low-confidence. The selected threshold, development metrics, source checksums, and model checksum are written to a frozen JSON artifact.

Report accuracy, macro and weighted precision/recall/F1, per-class precision/recall/F1, class support, and a confusion matrix. Macro averages include only classes with at least one confirmed example in that evaluation partition; macro_label_count records how many classes contributed. Classes with zero support remain in the per-class report and confusion matrix with zero support. Include the selected threshold, prediction coverage, and low-confidence count.

Low-confidence and zero-known-feature requests are mapped to other_or_ambiguous for the public classifier result. The separate coverage and low-confidence fields make abstention visible in the report.

The test annotations were confirmed, the project annotation validator passed, and the one-time held-out test evaluation completed successfully. Its report and one-time guard are committed under artifacts/evaluation/. The evaluated configuration is frozen; do not rerun the test evaluation or reset its guard. The report discloses the AI-assisted, owner-approved label provenance.

## 7. CLI usage

Install the locked project dependencies and package:

    uv sync --locked

Train the model after the confirmed training export meets the per-label minimum:

    .venv/bin/nl2bash-classifier train

The command validates the confirmed export against the training partition and writes the model and manifest under the versioned `models/` directory. Commit the updated model and manifest together after training.

Select and freeze a confidence threshold using the confirmed development partition:

    .venv/bin/nl2bash-classifier select-threshold

The default output is artifacts/evaluation/frozen_dev_threshold.json. It records the chosen threshold, development metrics, model checksum, and development annotation checksums. The minimum prediction coverage defaults to 80%.

Use the frozen threshold for ordinary prediction:

    .venv/bin/nl2bash-classifier predict --request "Find all Python files under the current directory" --frozen-threshold artifacts/evaluation/frozen_dev_threshold.json

The prediction command prints JSON with the public intent label, diagnostic top label, uncalibrated score, threshold, and low-confidence flag. The frozen threshold must belong to the loaded model.

## Final test evaluation (completed)

The one-time final evaluation ran successfully in the clean Python 3.10 GitHub Actions environment after the development threshold was frozen. It produced `artifacts/evaluation/test_report.json` and the completed one-time guard `artifacts/evaluation/test_evaluation.lock`. Results: accuracy 0.6853, macro-F1 0.6400, weighted-F1 0.6793, macro precision 0.7854, macro recall 0.6186, and prediction coverage 0.9947 (373/375) at threshold 0.1361115729921777. Test labels are AI-assisted and owner-approved, not independent ground truth.

**Do not run `nl2bash-classifier evaluate-test` again, delete/reset the guard, or overwrite the report.**

The classifier CLI also provides --help for each command and options for alternate input and artifact paths. It never generates or executes a Bash command.

## 8. Current model and annotation status

The project owner reports completing a final review of all 500 training and 375 development intent annotations with zero further label changes. The original AI-assisted label provenance remains recorded in the CSV row notes; the final human review is attested in [Human Review Attestation](HUMAN_REVIEW_ATTESTATION.md). This is one human review pass after AI-assisted initial annotation, not an inter-annotator agreement study.

A fresh model training run in a temporary directory reproduced all 375 development class predictions and probability values exactly compared with the committed model. Threshold reselection reproduced the committed threshold exactly. The existing model and threshold artifacts therefore remain valid for the current reviewed CSV and export checksums. The model manifest retains its training-artifact status field; the separate one-time test report and guard record the completed final evaluation. The classifier test evaluation has completed and must not be repeated.

The current development diagnostics are 0.6880 accuracy, 0.6709 macro-F1, 0.6801 weighted-F1, and 0.9893 prediction coverage at threshold 0.1361115729921777. These are development metrics only. The class imbalance and AI-assisted annotation history must be disclosed; do not present these numbers as final test performance.

The end-to-end command-generation component and development-only request-versus-NLP-context experiment are documented separately. All 375 test labels are approved and exported. The one-time classifier test evaluation is complete: accuracy 0.6853, macro-F1 0.6400, weighted-F1 0.6793, and coverage 0.9947 (373/375) at the frozen development threshold 0.1361115729921777. These results measure agreement with AI-assisted, owner-approved labels, not independent gold-standard accuracy. Do not rerun the test evaluation or use its results to tune the evaluated system.
