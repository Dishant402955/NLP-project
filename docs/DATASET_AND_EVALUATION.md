# Dataset and Evaluation Plan

## 1. Dataset source

The primary candidate dataset is NL2Bash:

- Upstream repository: [TellinaTool/nl2bash](https://github.com/TellinaTool/nl2bash)
- Research paper: [NL2Bash: A Corpus and Semantic Parser for Natural Language Interface to the Linux Operating System](https://arxiv.org/abs/1802.08979)
- Dataset files: `data/bash/all.nl` and `data/bash/all.cm` in the upstream repository.

The corpus contains one-line Linux shell commands paired line by line with expert-written natural-language descriptions. It is suitable for command-generation experiments. It does not include project-specific intent labels or entity annotations; those must be created separately.

## 2. Source audit

The audit was performed against upstream commit `d6b9f5bdff45621d190134e31ab63b7bf7002190` (2026-04-18). The current source files contained:

| Observation | Audited value |
|---|---:|
| Natural-language records in `all.nl` | 12,607 |
| Command records in `all.cm` | 12,607 |
| Empty natural-language records | 0 |
| Empty command records | 0 |
| Unique exact natural-language descriptions | 11,348 |
| Unique exact commands | 10,624 |
| Repeated natural-language rows beyond first occurrences | 1,259 |
| Repeated command rows beyond first occurrences | 1,983 |
| Average description length | 13.16 words |
| Longest description | 56 words |
| Descriptions longer than 50 words | 3 |

The two source files have matching line counts and are aligned by row. There are no duplicate exact natural-language/command pairs in the audited files, although descriptions and commands recur across different pairs.

The upstream parser's utility-counting code reports frequent utilities including:

| Utility | Command records containing utility |
|---|---:|
| `find` | 6,651 |
| `xargs` | 1,190 |
| `grep` | 1,100 |
| `rm` | 598 |
| `sort` | 477 |
| `echo` | 451 |
| `ls` | 450 |
| `chmod` | 341 |
| `cat` | 272 |
| `wc` | 272 |
| `cut` | 262 |
| `head` | 223 |
| `mv` | 191 |
| `chown` | 179 |
| `tr` | 174 |

These are command-record incidences reported by the upstream Bash parser, not counts of natural-language intents. A pipeline can contain several utilities, and one utility can support multiple user goals. The intent taxonomy is therefore based on the requested outcome rather than a direct utility-to-label mapping.

## 3. Licensing and attribution

The upstream repository's root code is marked GPL-3.0. The dataset directory `data/bash` has its own MIT license, and the upstream README explicitly identifies it as separately licensed.

This project uses the separately licensed dataset files and cites the NL2Bash paper. It does not copy the upstream parser, model, or training implementation into this repository. The raw dataset files and their MIT license notice are included under `data/raw/nl2bash/`; the project-generated partitions and checksum manifest are included under `data/processed/nl2bash/`. Any redistribution of dataset material must retain the dataset's MIT notice.

## 4. Filtering and split reproducibility findings

The upstream documentation reports 9,305 filtered pairs, split into 8,090 training, 609 development, and 606 test examples. The current checkout contains 12,607 raw pairs.

During this audit, the upstream filtering script was run against the current raw files in a temporary clone. It produced 11,546 filtered pairs. This does not match the 9,305-pair figure in the published documentation. The legacy split script also failed during its spell-correction routine in the available environment after its older dependencies were supplied.

Because these results do not reproduce the published counts, this project will not silently treat the documented split sizes as verified current outputs. We will create and document our own deterministic split from the audited source records.

## 5. Dataset syntax limitations

The NL2Bash paper studies one-line Bash commands rather than arbitrary shell scripts. Its stated grammar includes single commands, selected logical connectives, pipelines, parentheses, command substitution, and process substitution. It excludes input redirection and here-documents, variable assignments, compound control statements, shell functions, and embedded non-Bash program strings such as scripts passed to language interpreters.

These exclusions limit what the dataset can demonstrate. The project will report benchmark results as results on the NL2Bash-supported subset, not as coverage of all Bash syntax. Additional examples for excluded syntax may be added to a separate, clearly identified challenge set only if they fit the project schedule; they will not be mixed into the NL2Bash benchmark results.

## 6. Project data preparation and split strategy

The planned preparation process is:

1. Download or clone the upstream dataset into `data/raw/`; preserve the source files and MIT license notice in version control.
2. Preserve the raw source files unchanged and record their upstream revision and checksums.
3. Check line alignment, blank records, malformed records, and parser compatibility.
4. Apply project-specific scope filters and record every filtering decision.
5. Group records before splitting to prevent exact duplicate natural-language requests or exact duplicate commands from appearing in multiple partitions.
6. Assign whole groups to train, development, and test partitions using a fixed random seed and an approximate 80:10:10 ratio.
7. Record the final record counts, group counts, and overlap checks.

A preliminary duplicate-link analysis over the raw corpus connected rows that shared the same request text or the same command text (after trimming surrounding whitespace). It produced 9,451 connected groups; the largest group contained 45 records. This indicates that group-aware splitting is practical for this corpus. Final counts will be recalculated by the project data-preparation implementation.

All rows in a duplicate-linked group must remain in one partition. Group integrity takes precedence over an exact percentage target.

The project record format will retain the source pair and keep new annotations explicit:

```json
{
  "example_id": "nl2bash-000001",
  "request": "Find Python files in the current directory.",
  "reference_command": "find . -type f -name '*.py'",
  "intent_label": null,
  "entities": [],
  "source": {
    "dataset": "NL2Bash",
    "revision": "d6b9f5bdff45621d190134e31ab63b7bf7002190",
    "partition": null
  }
}
```

The null fields are populated only after annotation and split assignment. The source pair is not rewritten during annotation.

## 7. Reproducible preparation run

The project provides the command-line entry point nl2bash-prepare-dataset. Install the package in the project's Python environment, then run the following from the repository root:

```bash
uv pip install --python .venv/bin/python -e .

.venv/bin/nl2bash-prepare-dataset \
  --requests data/raw/nl2bash/all.nl \
  --commands data/raw/nl2bash/all.cm \
  --output-dir data/processed/nl2bash \
  --source-revision d6b9f5bdff45621d190134e31ab63b7bf7002190 \
  --seed 42
```

The current audited run produced:

| Partition | Records | Duplicate groups |
|---|---:|---:|
| Train | 10,085 | 8,701 |
| Development | 1,261 | 375 |
| Test | 1,261 | 375 |
| **Total** | **12,607** | **9,451** |

The tracked manifest records the upstream revision, SHA-256 checksums of the raw files, split algorithm, seed, target ratios, record and group counts, output-file checksums, and zero cross-partition request/command overlap checks.

Generated JSONL files and the manifest are stored under `data/processed/nl2bash/` and are committed alongside the raw source files. This lets a clean clone reproduce the model-training and evaluation inputs without downloading the corpus again. Re-running the command with the same source files, revision, and settings produces byte-identical partition files and manifest.

## 8. Intent labels and annotation

NL2Bash does not provide the intent labels needed to train our classifier. The project will use the [Intent Taxonomy](INTENT_TAXONOMY.md), which defines nine primary operation categories and an `other_or_ambiguous` fallback.

Begin with a manually reviewed pilot of approximately 50 examples per label. Review the pilot for unclear category boundaries before expanding it. The natural-language request is the classifier input; the paired command is supporting context for annotators, not a replacement for the request.

The labelled data must use the same duplicate-aware partitions described above. The classifier is trained only on confirmed training examples, its confidence threshold is selected using separately confirmed and blind-reviewed development examples, and it is evaluated once on blind-reviewed test examples after the threshold is frozen. The default threshold-selection rule maximizes macro-F1 subject to at least 80% coverage; see Intent Classifier for the full protocol.

Raw data, annotations, and generated split files are project research artifacts and are committed to Git with their license, source revision, and checksums.

## 9. Intent annotation pilot

The first pilot is generated from the training partition only. It contains 50 candidate examples per taxonomy label, for 500 rows total. Each row comes from a distinct duplicate group, so the pilot does not contain multiple near-duplicate records from the same group.

The pilot generator uses request-text rules only to suggest labels. It does not use the paired Bash command to assign a suggestion. Every row starts with a blank confirmed label and a pending review status. The suggestions are deliberately not treated as ground truth.

The local worklist, its manifest, and the confirmed-only export are stored under `data/annotations/` and are versioned in Git. Generate it with .venv/bin/nl2bash-annotations create and validate reviewer decisions with .venv/bin/nl2bash-annotations validate. See the [Annotation Guide](ANNOTATION_GUIDE.md) for the full review procedure and CSV field definitions. The initial AI-assisted annotation pass labelled all 500 training rows and all 375 development rows. The project owner subsequently reviewed all 875 rows and reported zero further corrections; see [Human Review Attestation](HUMAN_REVIEW_ATTESTATION.md). Retain and disclose the AI-assisted annotation provenance; this is not an inter-annotator agreement study.

Separate blind worklists are generated for development and test using one source record per duplicate group. These worklists contain no heuristic label suggestions. Their confirmed exports are tagged with the matching partition name and checksum. The classifier training loader rejects either held-out export. The development labels have been reviewed by the project owner. The test worklist remains untouched and its confirmed export is empty. The test partition and pending worklist are tracked as data, but no test labels have been created.

## 10. Evaluation metrics

### Intent classification

- Accuracy.
- Precision, recall, and F1-score.
- Per-class precision, recall, and F1-score to expose class imbalance.
- Macro averages over classes with confirmed support in the evaluated partition; the report records the number of contributing labels.
- Confusion matrix to identify category overlap, retaining all taxonomy labels including zero-support classes.
- Prediction coverage and low-confidence count after the development-selected confidence threshold is applied.

### Entity extraction

- Precision, recall, and F1-score for entity type and value.
- Separate reporting for each supported entity type where sample counts permit.

### Command generation

- Exact-match accuracy against the reference command.
- Bash syntax-validity rate.
- Human-reviewed semantic correctness on a documented sample, because semantically equivalent commands may have different text.

Exact string matching alone is not a complete measure of correctness.

### Runtime

Measure generation latency under a recorded hardware, model, and configuration setup. Report the number of examples and the measurement method.

## 11. Experiments

1. Train an intent-classification baseline using TF-IDF and Logistic Regression.
2. Evaluate entity extraction on annotated examples.
3. Generate commands using the original request alone.
4. Generate commands using the original request together with predicted intent and extracted parameters.
5. Compare command quality and syntax-validity results to determine whether the NLP understanding components improve generation.
6. Review representative failures and record limitations.

Any functional or semantic command checks must run only in a controlled, isolated environment with reviewed examples. The normal application must never execute generated commands.

### Command-generation development experiment

The end-to-end CLI provides `nl2bash evaluate-generation-dev`, which performs a seeded, label-stratified sample from the confirmed development partition. It compares two conditions on the same requests: the original request alone, and the original request plus the intent prediction and deterministic entity context. Paired Bash reference commands are used only as evaluation targets and are never included in generation prompts. The report records exact string match, Bash syntax validity, selected explicit-constraint preservation, high-risk warnings, and latency. This is a small engineering experiment, not a final test estimate. It does not claim human-rated semantic correctness. The report and its model/data checksums are stored under `artifacts/evaluation/`.

The test partition is excluded from this experiment. The evaluated prompt/model/runtime configuration is frozen in `artifacts/evaluation/frozen_generation_config.json` before the test worklist review. The recorded ten-request results and their limitations are documented in [Command-Generation Evaluation](GENERATION_EVALUATION.md).

## 12. Reporting

The final experiment report should include:
- Dataset source, upstream revision, license, checksums, filtering decisions, and final split sizes.
- Intent definitions and annotation procedure.
- Model name, version, and generation settings.
- Evaluation metrics and per-class results.
- Representative successful and unsuccessful examples.
- Limitations, including ambiguous requests, unsupported syntax, and semantically incorrect commands.

## 13. Citation

Lin, Xi Victoria, Chenglong Wang, Luke Zettlemoyer, and Michael D. Ernst. 2018. “NL2Bash: A Corpus and Semantic Parser for Natural Language Interface to the Linux Operating System.” Proceedings of LREC 2018.

BibTeX:

```bibtex
@inproceedings{LinWZE2018:NL2Bash,
  author = {Xi Victoria Lin and Chenglong Wang and Luke Zettlemoyer and Michael D. Ernst},
  title = {NL2Bash: A Corpus and Semantic Parser for Natural Language Interface to the Linux Operating System},
  booktitle = {Proceedings of the Eleventh International Conference on Language Resources and Evaluation},
  year = {2018}
}
```
