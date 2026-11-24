"""End-to-end NL2Bash command-line interface."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
import time
from typing import Any, Sequence

from nl2bash.bash_validation import validate_bash_command
from nl2bash.command_generation import (
    DEFAULT_BATCH_SIZE, DEFAULT_CONTEXT_SIZE, DEFAULT_GPU_LAYERS, DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL_PATH, CommandGenerationError, generate_bash_command, load_local_generator,
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


@dataclass(slots=True)
class LoadedRuntime:
    classifier: Any
    threshold: float
    threshold_sha256: str
    generation_config_sha256: str
    generator: Any
    startup_timings: dict[str, float]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nl2bash",
        description="Translate a natural-language Linux request into a validated Bash command (never executes it).",
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    generate = subparsers.add_parser("generate", help="run the complete NLP-to-Bash pipeline")
    generate.add_argument("--request", help="natural-language Linux task")
    generate.add_argument("--interactive", action="store_true", help="keep the local model loaded for multiple requests")
    generate.add_argument("--intent-model", type=Path, default=DEFAULT_MODEL_FILE)
    generate.add_argument("--intent-manifest", type=Path, default=DEFAULT_MODEL_MANIFEST)
    generate.add_argument("--frozen-threshold", type=Path, default=DEFAULT_FROZEN_THRESHOLD)
    generate.add_argument("--llm-model", type=Path, default=DEFAULT_MODEL_PATH)
    generate.add_argument("--context-size", type=int, default=DEFAULT_CONTEXT_SIZE)
    generate.add_argument("--threads", type=int)
    generate.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    generate.add_argument("--gpu-layers", type=int, default=DEFAULT_GPU_LAYERS)
    generate.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    generate.add_argument("--generation-config", type=Path, default=DEFAULT_GENERATION_CONFIG)
    generate.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    generate.add_argument("--timings", action="store_true", help="show startup, pipeline, prompt, and token-generation timings")

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
    experiment.add_argument("--threads", type=int)
    experiment.add_argument("--context-size", type=int, default=DEFAULT_CONTEXT_SIZE)
    experiment.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    experiment.add_argument("--gpu-layers", type=int, default=DEFAULT_GPU_LAYERS)
    experiment.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    experiment.add_argument("--output", type=Path, default=Path("artifacts/evaluation/generation_dev_report.json"))
    return parser


def _load_runtime(args: argparse.Namespace) -> LoadedRuntime:
    timings: dict[str, float] = {}
    started = time.perf_counter()
    stage = time.perf_counter()
    model = load_intent_classifier(args.intent_model, args.intent_manifest)
    timings["classifier_load_seconds"] = round(time.perf_counter() - stage, 6)

    stage = time.perf_counter()
    _frozen, threshold, threshold_sha256 = load_frozen_development_threshold(model, args.frozen_threshold)
    timings["threshold_load_seconds"] = round(time.perf_counter() - stage, 6)

    stage = time.perf_counter()
    generation_config_sha256 = verify_frozen_generation_configuration(
        args.generation_config,
        model_path=args.llm_model,
        classifier_model_path=args.intent_model,
        classifier_manifest_path=args.intent_manifest,
        frozen_threshold_path=args.frozen_threshold,
        context_size=args.context_size,
        threads=args.threads,
        batch_size=args.batch_size,
        gpu_layers=args.gpu_layers,
        max_tokens=args.max_tokens,
    )
    timings["configuration_verification_seconds"] = round(time.perf_counter() - stage, 6)

    stage = time.perf_counter()
    generator = load_local_generator(
        args.llm_model, context_size=args.context_size, threads=args.threads,
        batch_size=args.batch_size, gpu_layers=args.gpu_layers,
    )
    timings["llm_model_load_seconds"] = round(time.perf_counter() - stage, 6)
    timings["total_startup_seconds"] = round(time.perf_counter() - started, 6)
    return LoadedRuntime(model, threshold, threshold_sha256, generation_config_sha256, generator, timings)


def _generate_one(request_text: str, args: argparse.Namespace, runtime: LoadedRuntime) -> dict[str, Any]:
    total_started = time.perf_counter()
    timings: dict[str, float] = {}

    stage = time.perf_counter()
    request = normalize_request(request_text)
    timings["request_normalization_seconds"] = round(time.perf_counter() - stage, 6)

    stage = time.perf_counter()
    prediction = predict_intent(runtime.classifier, request, confidence_threshold=runtime.threshold)
    timings["intent_prediction_seconds"] = round(time.perf_counter() - stage, 6)

    stage = time.perf_counter()
    extraction = extract_entities(request)
    timings["entity_extraction_seconds"] = round(time.perf_counter() - stage, 6)

    stage = time.perf_counter()
    generated = generate_bash_command(
        request, prediction, extraction, generator=runtime.generator, max_tokens=args.max_tokens,
    )
    timings["generation_total_seconds"] = round(time.perf_counter() - stage, 6)

    stage = time.perf_counter()
    validation = validate_bash_command(generated.command)
    grounding_findings = validate_entity_grounding(generated.command, extraction)
    timings["validation_seconds"] = round(time.perf_counter() - stage, 6)
    timings["request_total_seconds"] = round(time.perf_counter() - total_started, 6)

    output = {
        "request": request,
        "intent": {
            "label": prediction.intent_label,
            "raw_top_label": prediction.raw_top_label,
            "confidence": prediction.confidence,
            "confidence_interpretation": "uncalibrated model probability estimate",
            "low_confidence": prediction.low_confidence,
            "threshold": prediction.confidence_threshold,
            "threshold_sha256": runtime.threshold_sha256,
        },
        "entities": [asdict(item) for item in extraction.entities],
        "extraction_issues": [asdict(item) for item in extraction.issues],
        "generation": {
            "model": generated.model,
            "prompt_version": generated.prompt_version,
            "generation_config_sha256": runtime.generation_config_sha256,
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
    if args.timings:
        output["timings"] = {
            "startup_seconds": runtime.startup_timings,
            "request_seconds": timings,
            "llm_inference": generated.inference_metrics,
        }
    return output


def _print_generate_output(output: dict[str, Any], args: argparse.Namespace) -> None:
    if args.json:
        json_options = {"ensure_ascii": False, "sort_keys": True}
        if not args.interactive:
            json_options["indent"] = 2
        else:
            json_options["separators"] = (",", ":")
        print(json.dumps(output, **json_options), flush=True)
        return
    generated = output["generation"]
    validation = output["validation"]
    print(f"Intent: {output['intent']['label']} (confidence {output['intent']['confidence']:.3f})")
    if output["entities"]:
        print("Entities:")
        for item in output["entities"]:
            print(f"  - {item['entity_type']}: {item['value']}")
    for issue in output["extraction_issues"]:
        print(f"Extraction note: {issue['message']}")
    print("\nGenerated Bash command:")
    print(generated["command"])
    print(f"\nExplanation: {generated['explanation']}")
    for assumption in generated["assumptions"]:
        print(f"Assumption: {assumption}")
    print(f"\nSyntax: {'valid' if validation['syntax_valid'] else 'invalid'}")
    print(f"Risk level: {validation['risk_level']}")
    for finding in validation["findings"]:
        print(f"Warning [{finding['severity']}]: {finding['message']}")
    for finding in output["constraint_check"]["findings"]:
        print(f"Constraint warning: {finding['message']}")
    if args.timings:
        print("\nPerformance timings (seconds):")
        for section, values in output["timings"].items():
            print(f"  {section}:")
            for key, value in values.items():
                print(f"    {key}: {value}")
    print("\nThe command was displayed only and was not executed.")


def _run_generate(args: argparse.Namespace) -> int:
    if not args.interactive and not args.request:
        raise InvalidRequestError("--request is required unless --interactive is used")
    runtime = _load_runtime(args)

    if args.interactive:
        if not args.json:
            print(
                f"Local model ready in {runtime.startup_timings['total_startup_seconds']:.2f}s. "
                "Enter a Linux task; type 'exit' or 'quit' to stop.",
                flush=True,
            )
        if args.request:
            output = _generate_one(args.request, args, runtime)
            _print_generate_output(output, args)
        while True:
            if not args.json:
                print("nl2bash> ", end="", file=sys.stderr, flush=True)
            line = sys.stdin.readline()
            if not line:
                break
            request_text = line.strip()
            if not request_text:
                continue
            if request_text.lower() in {"exit", "quit"}:
                break
            try:
                output = _generate_one(request_text, args, runtime)
                _print_generate_output(output, args)
            except (CommandGenerationError, ModelLoadError, EvaluationError, GenerationConfigurationError,
                    InvalidRequestError, OSError, TypeError, ValueError, RuntimeError) as exc:
                print(f"error: {exc}", file=sys.stderr, flush=True)
        return 0

    output = _generate_one(args.request, args, runtime)
    _print_generate_output(output, args)
    return 0 if output["validation"]["syntax_valid"] and not output["review_required"] else 3


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


def _run_generation_experiment(args: argparse.Namespace) -> int:
    report = evaluate_generation_on_development(
        model_path=args.llm_model,
        sample_size=args.sample_size,
        seed=args.seed,
        output_path=args.output,
        context_size=args.context_size,
        threads=args.threads,
        batch_size=args.batch_size,
        gpu_layers=args.gpu_layers,
        max_tokens=args.max_tokens,
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
