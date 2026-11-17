# Final Engineering Audit

**Audit date:** 2026-11-17
**Execution host:** local Ubuntu 22.04.5 LTS, x86_64, 4 CPU threads
**Checkout:** isolated fresh clone at /tmp/NLP-project-final-20261117
**Repository state at checkout:** main at the generation v7 commit; pre-existing user workspace was not modified

## Checks completed

- uv sync --locked completed successfully in a fresh local virtual environment.
- Python compileall completed successfully.
- The nl2bash, dataset-preparation, annotations, classifier, and entity-evaluation module CLI help entry points all returned successfully.
- Malformed model JSON, empty commands, unexpected JSON fields, and Markdown-fenced command output were rejected.
- A missing model path was rejected with setup guidance.
- A missing llama-cpp-python import was simulated and the local generator failed closed with an install message. No remote inference fallback exists. The fresh locked base environment does not include llama-cpp-python; the host has the frozen 1.1 GB Qwen GGUF model cached separately.
- Entity grounding detected an omitted explicit file-extension constraint, an unresolved PID placeholder, and an unrequested file-size filter. A command retaining the requested .py pattern passed the visibility check.
- A tampered copy of the frozen-generation manifest was rejected when a component checksum differed.
- Bash parse-only checks accepted a safe command, flagged sudo rm -rf / for manual review, and rejected invalid Bash syntax. All three reports stated executed = false.
- Twelve adversarial assertions passed. Zero generated commands were executed. Temporary fixtures were kept outside the repository.

## Known limitations found

The frozen validator is deliberately heuristic and does not detect every semantic error:

1. It does not report an unrequested case-insensitive find option such as -iname when the request contains no explicit case-sensitivity entity.
2. It does not flag a concrete invented process identifier such as kill 4242 when the request supplies no PID. It does detect several obvious placeholder forms such as <PID>.
3. It rejects time filters when no date/time entity is extracted, but it does not verify that every extracted date/time constraint is actually preserved in the generated command.
4. It does not prove semantic equivalence or validate all comparison, ownership, depth, interface-selection, or utility-specific constraints.

These gaps are recorded rather than silently patched because the command-generation configuration is frozen and its checksums include the relevant pipeline and validator source. A post-freeze code change would be a new development configuration and would require a separate development evaluation and updated provenance. The held-out classifier and entity test evaluations must not be rerun or used for tuning.

## Overall status

The clean install, entry-point smoke checks, malformed-output checks, fail-closed missing-model/runtime checks, selected grounding checks, frozen-component tamper detection, and parse-only safety checks passed. The project is not yet semantically complete: generation candidates have a preliminary assistant review, but the original owner-facing blind semantic worksheet is still unrated. The engineering audit also records the validator limitations above for the final report.
