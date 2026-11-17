"""End-to-end NL2Bash command-line interface."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Sequence

from nl2bash.bash_validation import validate_bash_command
from nl2bash.command_generation import (
    DEFAULT_CONTEXT_SIZE, DEFAULT_MODEL_PATH, CommandGenerationError,
    generate_bash_command, load_local_generator,
)
from nl2bash.entity_extraction import extract_entities
from nl2bash.entity_validation import validate_entity_grounding
from nl2bash.evaluation import EvaluationError, load_frozen_development_threshold
from nl2bash.intent_prediction import ModelLoadError, load_intent_classifier, predict_intent
from nl2bash.generation_evaluation import evaluate_generation_on_development
from nl2bash.generation_configuration import (
    GenerationConfigurationError, verify_frozen_generation_configuration,
)
from nl2bash.preprocessing import InvalidRequestError, normalize_request

DEFAULT_MODEL_FILE = Path("models/intent_classifier.joblib")
DEFAULT_MODEL_MANIFEST = Path("models/intent_classifier_manifest.json")
DEFAULT_FROZEN_THRESHOLD = Path("artifacts/evaluation/frozen_dev_threshold.json")
DEFAULT_GENERATION_CONFIG = Path("artifacts/evaluation/frozen_generation_config.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nl2bash",
        description="Translate a natural-language Linux request into a validated Bash command (never executes it).",
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    generate = subparsers.add_parser("generate", help="run the complete NLP-to-Bash pipeline")
    generate.add_argument("--request", required=True, help="natural-language Linux task")
    generate.add_argument("--intent-model", type=Path, default=DEFAULT_MODEL_FILE)
    generate.add_argument("--intent-manifest", type=Path, default=DEFAULT_MODEL_MANIFEST)
    generate.add_argument("--frozen-threshold", type=Path, default=DEFAULT_FROZEN_THRESHOLD)
    generate.add_argument("--llm-model", type=Path, default=DEFAULT_MODEL_PATH)
    generate.add_argument("--context-size", type=int, default=DEFAULT_CONTEXT_SIZE)
    generate.add_argument("--threads", type=int)
    generate.add_argument("--max-tokens", type=int, default=512)
    generate.add_argument("--generation-config", type=Path, default=DEFAULT_GENERATION_CONFIG)
    generate.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    validate = subparsers.add_parser("validate", help="check Bash syntax and known safety risks without execution")
    validate.add_argument("--command", required=True, help="Bash command to parse")
    validate.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    experiment = subparsers.add_parser(
        "evaluate-generation-dev",
        help="compare request-only and NLP-context generation on a seeded development sample",
    )
    experiment.add_argument("--llm-model", type=Path, default=DEFAULT_MODEL_PATH)
    experiment.add_argument("--sample-size", type=int, default=10)
    experiment.add_argument("--seed", type=int, default=20261117)
    experiment.add_argument("--output", type=Path, default=Path("artifacts/evaluation/generation_dev_report.json"))
    return parser


def _run_validate(args: argparse.Namespace) -> int:
    result = validate_bash_command(args.command)
    output = {
        "syntax_valid": result.syntax_valid,
        "parser": result.parser,
        "risk_level": result.risk_level,
        "review_required": result.review_required,
        "syntax_error": result.syntax_error,
        "findings": [asdict(item) for item in result.findings],
        "executed": False,
    }
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Syntax: {'valid' if result.syntax_valid else 'invalid'} ({result.parser})")
        print(f"Risk: {result.risk_level}; manual review required: {'yes' if result.review_required else 'no known heuristic findings'}")
        for finding in result.findings:
            print(f"- [{finding.severity}] {finding.code}: {finding.message}")
        print("Execution: never performed")
    return 0 if result.syntax_valid and not result.review_required else 3


def _run_generate(args: argparse.Namespace) -> int:
    request = normalize_request(args.request)
    model = load_intent_classifier(args.intent_model, args.intent_manifest)
    _frozen, threshold, threshold_sha256 = load_frozen_development_threshold(model, args.frozen_threshold)
    generation_config_sha256 = verify_frozen_generation_configuration(
        args.generation_config,
        model_path=args.llm_model,
        classifier_model_path=args.intent_model,
        classifier_manifest_path=args.intent_manifest,
        frozen_threshold_path=args.frozen_threshold,
        context_size=args.context_size,
        threads=args.threads,
        max_tokens=args.max_tokens,
    )
    prediction = predict_intent(model, request, confidence_threshold=threshold)
    extraction = extract_entities(request)
    generator = load_local_generator(args.llm_model, context_size=args.context_size, threads=args.threads)
    generated = generate_bash_command(
        request, prediction, extraction, generator=generator, max_tokens=args.max_tokens,
    )
    validation = validate_bash_command(generated.command)
    grounding_findings = validate_entity_grounding(generated.command, extraction)

    output = {
        "request": request,
        "intent": {
            "label": prediction.intent_label,
            "raw_top_label": prediction.raw_top_label,
            "confidence": prediction.confidence,
            "confidence_interpretation": "uncalibrated model probability estimate",
            "low_confidence": prediction.low_confidence,
            "threshold": prediction.confidence_threshold,
            "threshold_sha256": threshold_sha256,
        },
        "entities": [asdict(item) for item in extraction.entities],
        "extraction_issues": [asdict(item) for item in extraction.issues],
        "generation": {
            "model": generated.model,
            "prompt_version": generated.prompt_version,
            "generation_config_sha256": generation_config_sha256,
            "command": generated.command,
            "explanation": generated.explanation,
            "assumptions": list(generated.assumptions),
        },
        "constraint_check": {
            "passed": not grounding_findings,
            "findings": [asdict(item) for item in grounding_findings],
        },
        "review_required": validation.review_required or bool(grounding_findings),
        "validation": {
            "syntax_valid": validation.syntax_valid,
            "parser": validation.parser,
            "risk_level": validation.risk_level,
            "review_required": validation.review_required,
            "syntax_error": validation.syntax_error,
            "findings": [asdict(item) for item in validation.findings],
        },
        "executed": False,
    }
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Intent: {prediction.intent_label} (confidence {prediction.confidence:.3f})")
        if extraction.entities:
            print("Entities:")
            for item in extraction.entities:
                print(f"  - {item.entity_type}: {item.value}")
        for issue in extraction.issues:
            print(f"Extraction note: {issue.message}")
        print("\nGenerated Bash command:")
        print(generated.command)
        print(f"\nExplanation: {generated.explanation}")
        for assumption in generated.assumptions:
            print(f"Assumption: {assumption}")
        print(f"\nSyntax: {'valid' if validation.syntax_valid else 'invalid'}")
        print(f"Risk level: {validation.risk_level}")
        for finding in validation.findings:
            print(f"Warning [{finding.severity}]: {finding.message}")
        for finding in grounding_findings:
            print(f"Constraint warning: {finding.message}")
        print("\nThe command was displayed only and was not executed.")
    return 0 if validation.syntax_valid and not validation.review_required and not grounding_findings else 3


def _run_generation_experiment(args: argparse.Namespace) -> int:
    report = evaluate_generation_on_development(
        model_path=args.llm_model,
        sample_size=args.sample_size,
        seed=args.seed,
        output_path=args.output,
    )
    print(json.dumps({
        "operation": "evaluate-generation-dev",
        "report_file": str(args.output),
        "sample_size": report["sample_size"],
        "test_data_used": report["test_data_used"],
        "metrics": report["metrics"],
    }, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.operation == "generate":
            return _run_generate(args)
        if args.operation == "validate":
            return _run_validate(args)
        if args.operation == "evaluate-generation-dev":
            return _run_generation_experiment(args)
    except (CommandGenerationError, ModelLoadError, EvaluationError, GenerationConfigurationError,
            InvalidRequestError, OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
