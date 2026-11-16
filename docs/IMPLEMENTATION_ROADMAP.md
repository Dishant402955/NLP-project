# Implementation Roadmap

## 1. Purpose

This document is the execution plan for the Natural Language to Bash Command Generator. It defines the implementation order, deliverables, acceptance criteria, verification process, and repository boundaries. Work must follow this plan unless an implementation finding requires a documented change.

The application will be built incrementally. Each step has its own scope and acceptance criteria. A step is not complete merely because code has been written or a command exits successfully.

## 2. Final product boundary

The finished application will accept a natural-language Linux request and return:
- A predicted operation category.
- Extracted entities and parameters.
- A generated Bash command.
- A concise explanation.
- Syntax-validation status and any safety warnings.

Generated commands are displayed only. The application will not execute them.

The initial interface is a Python command-line application. The initial generation model is planned to run locally through Ollama. Model choice and quantization may be adjusted only after checking actual machine resources and testing model availability.

## 3. Planned architecture

The main processing flow is:
1. Input boundary and preprocessing.
2. Intent classification.
3. Entity and parameter extraction.
4. LLM-based command generation.
5. Bash syntax and safety validation.
6. Result formatting and CLI output.

The original request must remain available through the pipeline. NLP output must be represented as structured data and passed to the generator without losing the original wording.

## 4. Ordered implementation steps

### Step 0: Repository and project-plan baseline

**Status:** Completed.

**Delivered:**
- Project scope and objectives.
- High-level architecture.
- Technical design.
- Dataset and evaluation plan.
- This implementation roadmap.

**Completion evidence:** These documents are committed in the repository before application implementation begins.

### Step 1: Application foundation and request preprocessing

**Status:** Completed.

**Delivered:**
- Python package metadata and src-layout package.
- Repository ignore rules for local environments, caches, secrets, datasets, and model artifacts.
- Request validation and conservative whitespace trimming in the preprocessing module.

**Work:**
- Create a minimal Python package using a src layout.
- Declare the minimum supported Python version and build configuration.
- Add repository ignore rules for generated environments, caches, secrets, raw datasets, and model artifacts.
- Define a small, stable request-preprocessing API.
- Remove only leading and trailing whitespace from the request.
- Reject inputs that are not strings or contain no meaningful text.
- Preserve all internal whitespace and Unicode code points, including case, punctuation, shell-like tokens, paths, quotes, and numeric values. Preprocessing must not rewrite the request into a different meaning.

**Acceptance criteria:**
- The package can be installed in editable mode on the target Python version.
- The preprocessing module imports without optional ML or LLM dependencies.
- Valid input is normalized predictably.
- Empty and invalid input produces a clear, documented error.
- Inputs containing quotes, paths, punctuation, mixed case, internal whitespace, and Unicode are preserved apart from trimming surrounding whitespace.
- No generated command is executed.
- No test source, test directory, test fixture, model weight, or raw dataset is committed.

**Verification:** Run isolated checks from a temporary directory outside the repository. Review installation, import behavior, input cases, error paths, and package contents before committing.

### Step 2: Dataset audit and NLP data specification

**Status:** Completed.

**Delivered:**
- Audited the current NL2Bash source files, data shape, duplicates, utility distribution, and dataset-specific MIT license.
- Recorded the difference between the published filtered split counts and the output of the current upstream filtering script.
- Documented why the legacy split script could not be reproduced unmodified in the available environment.
- Defined the project intent labels and annotation rules in [Intent Taxonomy](INTENT_TAXONOMY.md).
- Specified a deterministic, duplicate-aware 80:10:10 split strategy.

**Implementation findings:**
- The audited source snapshot contains 12,607 aligned request/command records.
- The current upstream filtering script produced 11,546 filtered records, while the upstream paper/README reports 9,305 filtered records and split sizes of 8,090/609/606.
- The legacy split routine failed in its spell-correction code in the available environment. These upstream counts are not treated as reproduced project results.
- A preliminary exact-text duplicate-link analysis found 9,451 connected groups, with a largest group of 45 records.

**Work completed:**
- Inspect the NL2Bash source, format, license, and data files.
- Define a project intent taxonomy from the command and request patterns.
- Define a representation for utterances, reference commands, intent labels, and extracted entities.
- Define duplicate-aware, deterministic data partitioning.
- Keep raw and processed dataset files outside Git.

**Acceptance criteria:**
- Dataset source, revision, license, and citation are recorded.
- Source fields and alignment are documented.
- Intent labels have written definitions, examples, and annotation rules.
- Split strategy keeps duplicate requests and duplicate commands in a single partition.
- Filtering and split discrepancies are documented rather than hidden.
- Raw data, annotations, and split outputs are excluded from Git.

### Step 3: Intent classification

This stage is divided into small implementation commits. Do not train a classifier on unreviewed heuristic labels.

#### Step 3.1: Reproducible dataset preparation

**Status:** Completed.

**Delivered:**
- Aligned UTF-8 corpus loading, row validation, stable IDs, and source checksums.
- Transitive duplicate grouping by exact request or reference command after trimming surrounding whitespace.
- Seeded, duplicate-safe train/dev/test partition allocation.
- JSONL partition writing and a checksum/provenance manifest.
- A command-line entry point named nl2bash-prepare-dataset.
- A verified local run against the audited NL2Bash revision.

**Verified run:** 12,607 records, 9,451 duplicate groups, largest group 45; train 10,085, dev 1,261, test 1,261. Request and command overlap across partitions were independently verified as zero.

**Substep 3.1.a: aligned corpus loader**

Implemented in src/nl2bash/corpus.py: paired UTF-8 files are read line by line, aligned counts and blank records are validated, source text is preserved, stable row IDs are assigned, and source SHA-256 checksums are calculated.

**Substep 3.1.b: duplicate grouping**

Implemented in src/nl2bash/grouping.py: records are connected when they share an exact request or reference command after trimming surrounding whitespace. Transitive links form one group, and group ordering is deterministic.

**Substep 3.1.c: deterministic group splitting**

Implemented in src/nl2bash/splitting.py: a seeded greedy allocator assigns whole groups to train/dev/test, validates that duplicate requests and commands do not cross groups, and returns records in stable group order.

**Substep 3.1.d: partition files and manifest**

Implemented in src/nl2bash/dataset_builder.py: deterministic JSONL partitions are written atomically per file, and a manifest records source revision/checksums, split configuration, record/group counts, output checksums, and zero-overlap checks.

**Substep 3.1.e: dataset preparation CLI**

Implemented in src/nl2bash/dataset_cli.py and exposed as nl2bash-prepare-dataset. It validates that output paths are separate from raw inputs, orchestrates loading/grouping/splitting/writing, and returns a non-zero status with a concise error on invalid inputs.

**Work:**
- Implement a standard-library dataset loader for aligned NL2Bash request and command files.
- Validate row counts, empty records, encoding, and source checksums.
- Link rows that share an exact request or exact command after trimming surrounding whitespace.
- Assign entire duplicate-linked groups to train, development, or test using a fixed seed and 80:10:10 target ratios.
- Write JSONL partitions and a manifest under ignored local data directories.
- Record source revision, checksums, seed, ratios, group counts, record counts, and verified cross-partition overlap.

**Acceptance criteria:**
- Misaligned or malformed source files fail with actionable errors.
- The same inputs and seed produce byte-for-byte identical partitions and manifest data.
- No request or command duplicate crosses partitions.
- Group sizes, split counts, checksums, and source revision appear in the manifest.
- Raw and processed files remain outside Git.

#### Step 3.2: Annotation workflow and pilot

This stage is divided into three small implementation commits.

##### Step 3.2.a: training-only pilot worklist generator

**Status:** Completed.

**Delivered:**
- Request-text-only weak intent suggestions with explicit suggestion reasons.
- A deterministic 50-per-label pilot selected from the training partition.
- A one-example-per-duplicate-group constraint across the entire pilot.
- A CSV review worklist with blank confirmed labels and pending statuses.
- A pilot manifest containing source checksums, seed, category quotas, and selected IDs.
- Spreadsheet-safe escaping for formula-leading source text, with reversible handling during annotation import.
- A reviewer guide in [Annotation Guide](ANNOTATION_GUIDE.md).

**Verified pilot:** 500 rows, 50 per each of the ten labels, 500 distinct duplicate groups, zero confirmed labels, all statuses pending, and no shortages.

**Work:**
- Verify the training JSONL checksum against the dataset manifest before selecting candidates.
- Apply request-text heuristics only to propose a label and record a reason; do not infer a confirmed label from the reference command.
- Select approximately 50 distinct duplicate groups per taxonomy label using a fixed seed.
- Keep one row per duplicate group in the pilot.
- Write a CSV with source IDs, request, reference command, suggested label, blank confirmed label, pending status, and reviewer note.
- Write a pilot manifest with source checksum, seed, quotas, and actual category counts.

**Acceptance criteria:**
- Only the manifest-declared training partition is accepted.
- Every pilot record belongs to the training partition and is source-identical.
- Pilot group IDs are unique across all selected labels.
- Suggestions and confirmed labels are separate fields; all new records start pending.
- Category shortages are reported instead of filled with fabricated records.

##### Step 3.2.b: reviewed annotation validator and importer

**Status:** Completed.

**Delivered:**
- Strict validation of the pilot manifest and reviewer-edited CSV.
- Source and suggestion integrity checks against the original training partition and pilot metadata.
- Explicit review-status validation for pending, confirmed, ambiguous, and rejected rows.
- Confirmed-only JSONL export with reviewer notes and a checksum manifest.
- Spreadsheet-formula escaping is reversed before source comparison and export.
- Failure-safe manifest handling so incomplete imports are not marked complete.

**Verification:** Valid and invalid annotation cases, all-pending export, malformed metadata, source edits, suggestion edits, missing/duplicate rows, formula-leading values, and interrupted export were tested outside the repository.

**Work:**
- Validate reviewer-edited CSV headers, IDs, group IDs, source text, statuses, and labels.
- Allow only pending, confirmed, ambiguous, or rejected statuses.
- Require a valid taxonomy label for confirmed rows and a reviewer note for ambiguous/rejected rows.
- Reject duplicate IDs, duplicate groups, changed source text, unknown labels, and inconsistent status/label combinations.
- Export only confirmed rows to a separate local JSONL artifact.

**Acceptance criteria:**
- Pending, ambiguous, and rejected rows never enter the confirmed training artifact.
- Every exported label was explicitly confirmed by a reviewer.
- The export is deterministic and retains source IDs and reviewer notes.
- Invalid annotations fail with actionable errors.

##### Step 3.2.c: annotation CLI and pilot generation

**Status:** Completed.

**Delivered:**
- Installed nl2bash-annotations console command with create and validate subcommands.
- Machine-readable summaries and non-zero error status for invalid inputs.
- Default CSV, manifests, and confirmed export under the Git-ignored data/annotations/ directory.
- Reviewer instructions and reproducible command examples in the Annotation Guide.

**Verified current state:** The local pilot contains 500 rows, 50 suggested examples per taxonomy label, 500 unique duplicate groups, 500 pending statuses, and zero confirmed labels. The confirmed export is therefore empty until a reviewer completes and validates the worklist.

**Completion note:** The annotation tooling is implemented. Human review of the pilot is still outstanding, and classifier training must wait until confirmed labels exist.

#### Step 3.3: TF-IDF and Logistic Regression baseline

The implementation is divided into small commits. See [Intent Classifier](INTENT_CLASSIFIER.md) for the model contract and evaluation protocol.

##### Step 3.3.a: confirmed training-data contract

**Status:** Completed.

**Delivered:**
- Training-only annotation loader with checksum and manifest provenance validation.
- Source-record checks for example IDs, request text, reference command, and duplicate-group IDs.
- Explicit confirmed-status and taxonomy-label validation.
- Configurable per-label minimum, defaulting to two examples per taxonomy label.
- Clear refusal when the confirmed export is empty or insufficient.

**Verification:** Valid fixture data and adversarial cases for changed checksums, changed source rows, duplicate IDs/groups, pending status, unknown labels, missing taxonomy coverage, path traversal, and invalid configuration were checked outside the repository. The actual local zero-label export was refused with the expected actionable error.

**Work:**
- Validate the confirmed annotation export and both source manifests.
- Verify annotation IDs, requests, groups, labels, checksums, and explicit review status against the training partition.
- Require a minimum number of confirmed examples for every taxonomy label.
- Refuse to train when the confirmed dataset is empty or incomplete.

**Acceptance criteria:**
- Only confirmed annotations from the training partition are accepted.
- Heuristic suggestions and reference commands never become classifier labels or input features.
- Invalid or insufficient data fails before any model artifact is written.

##### Step 3.3.b: TF-IDF and Logistic Regression pipeline

**Status:** Completed.

**Delivered:**
- Scikit-learn 1.7.2 dependency pinned to the supported 1.7 series for the Python 3.10 project environment.
- One Scikit-learn Pipeline containing TfidfVectorizer and LogisticRegression.
- Explicit and reproducible TF-IDF, regularization, solver, iteration, and random-seed settings.
- Training data and provenance validation at the fit boundary.
- Atomic local model serialization and a JSON manifest with source checksums, class counts, library versions, settings, and model checksum.
- Model manifest marks the artifact as not evaluated until held-out evaluation is implemented.

**Verification:** A temporary balanced fixture outside the repository was used to fit and reload the model, inspect ten-class scores, verify artifact checksums, and exercise invalid configuration, insufficient labels, duplicate groups, invalid provenance, and interrupted manifest writes. This is an implementation smoke test, not a project accuracy result.

**Acceptance criteria:**
- The pipeline fits only the validated confirmed training subset.
- The fitted vectorizer is reused unchanged during prediction.
- Model artifacts record the training source, label counts, settings, and library version.

##### Step 3.3.c: prediction and low-confidence handling

**Work:**
- Load the locally generated pipeline and validate its manifest.
- Normalize one natural-language request and return the predicted label and top-class score.
- Expose a configurable low-confidence threshold.
- Return other_or_ambiguous when the top-class score is below the threshold while retaining the raw top label for diagnostics.

**Acceptance criteria:**
- Empty or invalid input is rejected.
- Prediction never executes shell commands.
- The score is described as an uncalibrated model estimate, not a guarantee of correctness.
- The threshold is recorded and can later be selected on development data.

##### Step 3.3.d: held-out annotations and evaluation

**Work:**
- Extend the annotation workflow to support development and test partitions without changing the existing training pilot.
- Generate separate review worklists and confirmed exports for held-out partitions.
- Validate every held-out annotation against its own source partition and checksum.
- Implement evaluation using development data for configuration selection and test data once after the configuration is frozen.

**Acceptance criteria:**
- No development or test annotation enters model fitting.
- No duplicate-linked group appears across partitions.
- Metrics include accuracy, macro/weighted and per-class precision, recall, F1, support, and confusion matrix.
- Test evaluation fails closed when labels are missing, unconfirmed, or inconsistent.

**Current limitation:** The training pilot contains 500 pending rows and zero confirmed labels. The classifier can be implemented and tested with temporary fixtures outside the repository, but no real model training or performance result is possible until human annotations are confirmed.

### Step 4: Entity and parameter extraction

**Work:**
- Implement rule-based extraction for the selected supported entities.
- Initial entity types may include file extensions, paths, file names, sizes, ports, process names, dates, and comparison conditions.
- Preserve the exact extracted value and its type.
- Detect conflicting or incomplete values rather than guessing.

**Acceptance criteria:**
- Each supported entity has examples and extraction rules documented.
- Overlapping matches and quoted values are handled deterministically.
- Missing and ambiguous parameters are represented explicitly.
- Precision, recall, and F1 can be measured against annotated examples.

### Step 5: LLM command-generation adapter

**Work:**
- Implement a small adapter for the local Ollama HTTP API.
- Keep the model name, endpoint, timeout, and generation settings configurable.
- Pass the original request, intent, and extracted entities to the model.
- Require structured output containing a command, explanation, and assumptions.
- Parse and validate the response structure; handle malformed, empty, timed-out, and unavailable responses.
- Do not invoke a shell or execute model output.

**Acceptance criteria:**
- The adapter fails clearly when Ollama is unavailable.
- Model output is treated as untrusted text.
- Malformed model responses are rejected or reported, never executed.
- Timeouts and response errors are surfaced cleanly.
- Model choice is based on a successful smoke test on the available hardware.

### Step 6: Bash syntax and safety validation

**Work:**
- Parse command text using bashlex or another justified parser.
- Report syntax validity separately from safety findings.
- Add conservative checks for selected destructive or high-impact command patterns.
- Handle parser errors and unsupported syntax without crashing.

**Acceptance criteria:**
- Valid and invalid syntax examples are distinguished.
- Safety warnings include reasons and do not claim to prove safety.
- Validation never executes the command.
- Parser limitations are documented.

### Step 7: End-to-end CLI

**Work:**
- Add the command-line entry point.
- Connect preprocessing, classifier, entity extraction, generation, validation, and output formatting.
- Support one-shot input and an interactive mode if the implementation remains simple.
- Provide useful errors for missing model services, unknown intent, ambiguous input, and validation failures.

**Acceptance criteria:**
- The end-to-end flow works with the configured local model.
- Every stage can be inspected in diagnostic output without exposing secrets.
- The CLI exits with appropriate status codes on input and service failures.
- No command execution path exists.

### Step 8: Evaluation and experiments

**Work:**
- Build a repeatable evaluation procedure using the agreed data splits.
- Measure intent classification and entity extraction independently.
- Compare generation with the original request alone against generation with NLP-derived context.
- Measure command exact match, syntax validity, semantic correctness on a reviewed sample, and latency.
- Record limitations and representative failures.

**Acceptance criteria:**
- Evaluation results are reproducible from recorded configuration.
- Test examples are not used for training or prompt tuning.
- Exact match is not presented as the only measure of correctness.
- Semantic checks use reviewed examples in an isolated environment, never the user's normal shell.

### Step 9: Final integration review and documentation

**Work:**
- Review the full application against the scope and architecture.
- Update README and technical documentation to match actual behavior.
- Document installation, model setup, usage, limitations, and reproducibility.
- Remove generated caches and local artifacts from the working tree.
- Verify a clean clone can be installed and run using the documented procedure.

**Acceptance criteria:**
- Documentation matches the implementation.
- A clean environment can follow the setup instructions.
- No secrets, model weights, raw datasets, test source, or temporary artifacts are tracked.
- The final Git history contains small, meaningful commits.

## 5. Per-step engineering and review protocol

Every implementation step must follow this sequence:

1. Read the relevant project documents and inspect the current Git state.
2. Confirm the step's scope and acceptance criteria before changing files.
3. Make the smallest implementation that satisfies that scope.
4. Run executable checks from outside the repository. Test source files and temporary fixtures must live outside the repository and must never be staged.
5. Perform ten separate review passes:
   1. Requirements traceability: every change maps to an approved requirement.
   2. Architecture consistency: module boundaries and data flow remain correct.
   3. Correctness: normal inputs produce the intended result.
   4. Edge cases: empty, malformed, Unicode, long, and boundary inputs are considered as relevant.
   5. Failure handling: dependency, filesystem, network, parsing, and timeout failures are handled as relevant.
   6. Security: untrusted input and generated output are never treated as executable instructions.
   7. Compatibility: supported Python and dependency versions are respected.
   8. Maintainability: names, interfaces, complexity, and error messages are reviewed.
   9. Regression: existing behavior and previously completed acceptance criteria are rechecked.
   10. Repository hygiene: documentation, staged diff, generated artifacts, and commit scope are checked.
6. Perform a separate adversarial review. Try malformed and hostile inputs, unexpected dependency responses, and attempts to cross the documented safety boundary. The attack cases must be appropriate to the step.
7. Fix every confirmed issue and repeat the relevant checks and all ten review passes for the corrected version.
8. Review the final staged diff and commit only the files belonging to that step.
9. Confirm the commit, remote push, and clean working tree before proceeding.

A review pass is not a claim of independent human review. It is a distinct, deliberate inspection against the corresponding checklist item. Never report a check as passed unless it was actually performed.

## 6. Test and repository policy

The user requires that no tests appear in the Git repository. Therefore:
- Do not create a tests directory.
- Do not commit test modules, test fixtures, test datasets, or test reports.
- Write temporary test scripts and fixtures under a location such as /tmp/nl2bash-verification/.
- Use installed test tools or Python's standard library from that external location.
- Keep only production application code and project documentation in the repository.
- Report the commands and outcomes of verification without adding test code to Git.

This policy does not mean the project should be left untested. Every implementation step still requires executable checks.

## 7. Commit strategy

Use small commits with one clear purpose. Planned commit subjects include:
- Document implementation roadmap
- Add application foundation
- Add dataset specification
- Implement intent classification
- Implement parameter extraction
- Add local LLM generation adapter
- Add Bash command validation
- Build command-line workflow
- Add evaluation workflow
- Complete project documentation

Commit subjects may be adjusted to accurately describe the changes actually made. Do not create a commit for unfinished or failing work.

## 8. Current environment observations

The initial remote workspace inspection found:
- Linux x86_64.
- Python 3.10.12.
- 4 logical CPU cores.
- Approximately 7.5 GiB RAM.
- Ollama not installed.
- Scikit-learn, NLTK, bashlex, and pytest not installed.
- The repository was clean at the start of implementation.

These are environment observations, not permanent assumptions. Recheck before installing dependencies or downloading model weights. The first implementation step is intentionally independent of an LLM runtime.
