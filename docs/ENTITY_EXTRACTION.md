# Entity and Parameter Extraction

## 1. Purpose

The extractor identifies values in a natural-language Bash request that constrain command generation. It is a deterministic NLP component, separate from intent classification and LLM generation.

The first implementation uses Python regular expressions and explicit rules. It does not call an LLM, interpret a request as executable code, or execute a command.

## 2. Supported entity types

| Type | Example source value | Normalized value |
|---|---|---|
| `file_extension` | `.PY` | `.py` |
| `path` | `$HOME/projects/` | Not changed |
| `file_name` | `report.final.csv` | Not changed |
| `size` | `10 MB` | `10000000 bytes` |
| `port` | `08080` | `8080` |
| `process_name` | `nginx` | Not changed |
| `date_time` | `within the last 7 days` | Lowercase source phrase |
| `comparison_condition` | `larger than` | `greater_than` |

Size conversion uses decimal multipliers for KB/MB/GB/TB and binary multipliers for KiB/MiB/GiB/TiB. The original text is always retained in `value`; normalization is additional metadata, not a replacement.

Comparison labels include `greater_than`, `greater_than_or_equal`, `less_than`, `less_than_or_equal`, `equal_to`, `newer_than`, `older_than`, `after`, and `before`.

## 3. Python API

```python
from nl2bash.entity_extraction import extract_entities

result = extract_entities(
    'Find Python files larger than 10 MB under "/home/user/projects"'
)

for entity in result.entities:
    print(entity.entity_type, entity.value, entity.normalized_value)

for issue in result.issues:
    print(issue.code, issue.message)
```

`EntityExtractionResult` contains the trimmed request, ordered entity tuple, and issue tuple. Each `ExtractedEntity` has:

- `entity_type`: one of the eight supported types.
- `value`: exact characters from the request.
- `start` and `end`: Python string offsets, with an exclusive end.
- `normalized_value`: optional machine-friendly representation.

Offsets refer to `result.request`, which has only had surrounding whitespace removed by the standard preprocessing function. Internal whitespace, case, quotes, Unicode, punctuation, and path contents are not rewritten. Overlapping entities are intentional, for example a file extension inside a file name or path.

Use `result.by_type("path")` to retrieve one entity type.

## 4. Uncertainty and validation issues

The extractor reports incomplete or invalid cues instead of inventing missing values. Current issue codes are:

| Code | Meaning |
|---|---|
| `missing_port_value` | The request mentions a port but supplies no numeric value. |
| `port_out_of_range` | The extracted port is outside 1-65535. |
| `missing_process_name` | The request explicitly asks for a named process but supplies no name. |
| `missing_size_value` | A size condition is present but no explicit size value and unit are found. |
| `missing_size_unit` | A numeric file-size limit is present but its unit is missing. |
| `conflicting_size_constraints` | Lower and upper size conditions cannot both be satisfied. |

An issue is not a generated clarification question. It is structured evidence for the later CLI and generation stages to handle.

## 5. Extraction rules and boundaries

- Quoted and unquoted absolute, home-relative, variable-based, and relative paths are recognized when the request provides a path-like form. URL strings are not treated as filesystem paths.
- File extensions may be extracted from explicit patterns and from recognized paths or file names. Compound suffixes such as `.tar.gz` are kept together.
- When explicitly identified as a filename, a single-dot hidden file such as `.env` is not treated as an extension.
- Sizes require a recognized unit. SI and IEC units are distinguished during byte conversion.
- Ports are extracted from explicit `port` and `--port` forms. `-p` is interpreted as a port option only when the request mentions SSH.
- Process names are extracted from explicit `process named`, `process name`, and `<name> process` forms. Generic phrases such as `all processes` do not create a process name.
- Date/time rules cover common relative intervals, calendar dates, times, and relative days. They preserve the source phrase and do not resolve a date relative to the current clock.
- Comparison rules normalize common textual operators. The original condition phrase remains available.
- Conflicting size constraints are flagged when they are explicit and locally associated with their size values.

## 6. Evaluation

`nl2bash.entity_evaluation.evaluate_entity_extraction` computes micro and macro precision, recall, and F1, plus per-entity-type metrics. Macro averages exclude entity types with zero gold support in the evaluated sample. A match requires exact entity type, value, and character span. Partial overlaps do not receive credit. Gold annotations use `ExtractedEntity` values whose offsets refer to the normalized request.

The metric implementation is separate from annotation creation. The repository does not currently contain a reviewed entity gold dataset. Final entity scores require a manually adjudicated entity sample, partition-aware provenance, and an evaluation split that is not used to tune extraction rules.

## 7. Known limitations

The rule set is intentionally conservative and supports common forms rather than every possible way of mentioning a value. It does not fully parse shell syntax, infer implicit paths such as `the current directory`, resolve variables, interpret arbitrary date expressions, or infer process names from surrounding context. A false negative is preferable to silently fabricating an argument. Extraction rules must be expanded only with examples and measured against a reviewed benchmark.
