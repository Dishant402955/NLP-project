"""Bash syntax checks and conservative, non-executing safety heuristics."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

import bashlex


@dataclass(frozen=True, slots=True)
class SafetyFinding:
    code: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class BashValidationResult:
    syntax_valid: bool
    parser: str
    risk_level: str
    findings: tuple[SafetyFinding, ...]
    syntax_error: str | None = None

    @property
    def review_required(self) -> bool:
        return bool(self.findings) or not self.syntax_valid


def _walk(node: Any):
    seen: set[int] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if id(current) in seen or not hasattr(current, "kind"):
            continue
        seen.add(id(current))
        yield current
        for attr in ("parts", "list", "command", "output", "input"):
            child = getattr(current, attr, None)
            if isinstance(child, (list, tuple)):
                stack.extend(reversed(child))
            elif hasattr(child, "kind"):
                stack.append(child)


def _command_words(node: Any) -> list[str]:
    return [str(part.word) for part in getattr(node, "parts", ())
            if getattr(part, "kind", None) == "word" and isinstance(getattr(part, "word", None), str)]


def _effective_command(words: list[str]) -> tuple[str, list[str], bool]:
    index = 0
    elevated = False
    wrappers = {"command", "builtin", "nohup", "time", "nice", "timeout", "setsid", "stdbuf", "sudo", "env"}
    while index < len(words):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[index]):
            index += 1
            continue
        name = Path(words[index]).name
        if name == "sudo":
            elevated = True
            index += 1
            while index < len(words) and words[index].startswith("-"):
                flag = words[index]
                index += 1
                if flag in {"-u", "-g", "-h", "-p", "-C", "--user", "--group", "--host", "--prompt", "--close-from"} and index < len(words):
                    index += 1
            continue
        if name == "env":
            index += 1
            while index < len(words) and (words[index].startswith("-") or "=" in words[index]):
                index += 1
            continue
        if name in wrappers:
            index += 1
            while index < len(words) and words[index].startswith("-"):
                flag = words[index]
                index += 1
                if flag in {"-n", "-u", "-g", "-p", "-o", "-e", "--signal", "--kill-after"} and index < len(words):
                    index += 1
            # timeout has a mandatory duration before its wrapped command.
            if name == "timeout" and index < len(words) and not words[index].startswith("-"):
                index += 1
            # nice accepts an optional priority after -n; handled above.
            continue
        break
    return (Path(words[index]).name, words[index + 1:], elevated) if index < len(words) else ("", [], elevated)


def _has_recursive_force(args: list[str]) -> bool:
    recursive = force = False
    for arg in args:
        if arg == "--recursive":
            recursive = True
        elif arg == "--force":
            force = True
        elif arg.startswith("-") and not arg.startswith("--"):
            flags = arg[1:].replace("-", "")
            recursive = recursive or "r" in flags or "R" in flags
            force = force or "f" in flags
    return recursive and force


def _is_dangerous_root_target(value: str) -> bool:
    target = value.strip("\"'")
    return target in {"/", "/*", "~", "$HOME", "${HOME}", ".", ".."} or bool(
        re.match(r"^/(?:dev|sys|proc|boot)(?:/|$)", target)
    )


def _collect_findings(roots: list[Any], *, depth: int = 0, seen_scripts: set[str] | None = None) -> tuple[SafetyFinding, ...]:
    findings: dict[str, SafetyFinding] = {}
    seen_scripts = seen_scripts if seen_scripts is not None else set()

    def add(code: str, severity: str, message: str) -> None:
        findings.setdefault(code, SafetyFinding(code, severity, message))

    nodes = [node for root in roots for node in _walk(root)]
    commands = [node for node in nodes if node.kind == "command"]
    nested_scripts: list[str] = []
    for node in commands:
        words = _command_words(node)
        executable, args, elevated = _effective_command(words)
        if elevated:
            add("elevated_privileges", "medium", "The command requests elevated privileges. Review every target and option before running it.")
        if executable == "rm" and _has_recursive_force(args):
            add("recursive_forced_delete", "high", "Recursive forced deletion can permanently remove large directory trees.")
            if any(_is_dangerous_root_target(arg) for arg in args if not arg.startswith("-")):
                add("broad_delete_target", "high", "The recursive delete target is a root, home, or system directory.")
        if executable.startswith("mkfs") or executable in {"fdisk", "sfdisk", "parted", "wipefs", "blkdiscard"}:
            add("disk_modification", "high", "This utility can repartition, format, or discard storage devices.")
        if executable == "dd" and any(arg.startswith("of=") for arg in args):
            add("raw_device_write", "high", "dd writes directly to an output target and can destroy data or overwrite a device.")
        if executable in {"shutdown", "reboot", "poweroff", "halt", "init"}:
            add("system_state_change", "high", "This command can shut down or change the state of the operating system.")
        if executable == "find":
            if "-delete" in args:
                add("find_delete", "high", "find -delete removes every matching path; verify the search scope carefully.")
            for marker in ("-exec", "-execdir"):
                if marker in args:
                    marker_index = args.index(marker)
                    nested = args[marker_index + 1:]
                    if nested and nested[0] != "sh":
                        nested_words = nested[:]
                        if nested_words[0] == "bash" or nested_words[0] in {"rm", "mkfs", "dd", "chmod", "chown"}:
                            nested_exec, nested_args, nested_elevated = _effective_command(nested_words)
                            if nested_exec == "rm" and _has_recursive_force(nested_args):
                                add("recursive_forced_delete", "high", "find -exec invokes recursive forced deletion for each match.")
                            if nested_exec.startswith("mkfs") or nested_exec in {"dd", "wipefs", "blkdiscard"}:
                                add("disk_modification", "high", "find -exec invokes a disk-modifying utility.")
        if executable == "eval":
            add("dynamic_shell_evaluation", "high", "eval interprets generated text as shell code and can hide additional commands.")
        if executable in {"chmod", "chown"} and any(arg in {"-R", "--recursive"} for arg in args):
            if executable == "chown" or any("777" in arg for arg in args):
                add("recursive_permission_change", "high", "A recursive ownership or broadly permissive mode change can affect many files.")
        if executable == "git" and args:
            if args[0] == "reset" and "--hard" in args:
                add("destructive_git_reset", "high", "git reset --hard discards uncommitted working-tree changes.")
            if args[0] == "clean" and any(arg.startswith("-f") for arg in args[1:]):
                add("destructive_git_clean", "high", "git clean with force removes untracked files and directories.")
        if executable == "docker" and args[:2] == ["system", "prune"] and any("a" in arg for arg in args[2:] if arg.startswith("-")):
            add("broad_container_prune", "medium", "This can remove unused images, containers, networks, and build cache.")

        # Parse shell -c payloads recursively, including wrappers such as
        # find -exec sh -c '...' and xargs bash -c '...'.
        for word_index, word in enumerate(words[:-1]):
            shell = Path(word).name
            if shell not in {"bash", "sh", "dash", "zsh", "ksh"}:
                continue
            flag_index = next((j for j in range(word_index + 1, min(len(words) - 1, word_index + 4))
                               if words[j] in {"-c", "--command"} or (words[j].startswith("-") and "c" in words[j][1:])), None)
            if flag_index is not None:
                script_index = flag_index + 1
                script = words[script_index]
                if script and script not in seen_scripts:
                    nested_scripts.append(script)
                    seen_scripts.add(script)

    for node in nodes:
        if node.kind == "pipeline":
            parts = [part for part in getattr(node, "parts", ()) if getattr(part, "kind", None) == "command"]
            if len(parts) >= 2:
                left, right = _command_words(parts[0]), _command_words(parts[-1])
                left_name = Path(left[0]).name if left else ""
                right_name = Path(right[0]).name if right else ""
                if left_name in {"curl", "wget"} and right_name in {"bash", "sh", "dash", "zsh"}:
                    add("remote_script_execution", "high", "Downloaded network content is piped directly into a shell interpreter.")
        elif node.kind == "redirect":
            target = getattr(getattr(node, "output", None), "word", "")
            redirect_type = getattr(node, "type", "")
            if isinstance(target, str) and re.match(r"^/dev/(?:sd[a-z]|nvme\d|vd[a-z]|mapper/|loop\d|mmcblk)", target):
                add("device_redirection", "high", "Shell redirection targets a block device and may overwrite storage.")
            if isinstance(target, str) and re.match(r"^/(?:etc|boot|sys|proc)/", target) and redirect_type in {">", ">|", "<>"}:
                add("critical_path_write", "high", "Shell redirection writes to a critical operating-system path.")

    if depth < 4:
        for script in nested_scripts:
            try:
                nested_roots = bashlex.parse(script)
            except (bashlex.errors.ParsingError, NotImplementedError, ValueError):
                add("incomplete_nested_shell_analysis", "medium", "A nested shell command could not be fully analysed; inspect it manually.")
                continue
            for item in _collect_findings(nested_roots, depth=depth + 1, seen_scripts=seen_scripts):
                findings.setdefault(item.code, item)
    elif nested_scripts:
        add("nested_shell_depth_limit", "medium", "Nested shell analysis reached its depth limit; inspect the command manually.")

    return tuple(sorted(findings.values(), key=lambda item: (item.severity != "high", item.code)))


def validate_bash_command(command: str, *, timeout_seconds: float = 3.0) -> BashValidationResult:
    """Parse Bash without executing it and flag known risky patterns."""
    if not isinstance(command, str):
        raise TypeError("command must be a string")
    if not command.strip():
        raise ValueError("command must contain non-whitespace text")
    if "\x00" in command:
        raise ValueError("command must not contain NUL bytes")
    if len(command) > 20_000:
        raise ValueError("command exceeds the 20000-character validation limit")
    bash_path = shutil.which("bash")
    if not bash_path:
        raise RuntimeError("bash is required for syntax-only validation but was not found on PATH")
    try:
        check = subprocess.run([bash_path, "-n"], input=command, text=True,
                               capture_output=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Bash syntax check exceeded its time limit") from exc
    syntax_valid = check.returncode == 0
    syntax_error = None if syntax_valid else (check.stderr.strip() or "Bash rejected the command syntax")[:1000]

    roots: list[Any] = []
    ast_error: str | None = None
    try:
        roots = bashlex.parse(command)
    except (bashlex.errors.ParsingError, NotImplementedError, ValueError) as exc:
        ast_error = str(exc)[:500]
    findings = list(_collect_findings(roots)) if roots else []
    if ast_error and syntax_valid:
        findings.append(SafetyFinding("incomplete_ast_analysis", "medium", "Bash accepted the syntax, but the supplementary safety parser could not fully analyse this construct; inspect it manually."))
    if not syntax_valid:
        findings.append(SafetyFinding("invalid_bash_syntax", "high", syntax_error or "Invalid Bash syntax."))
    unique = {item.code: item for item in findings}
    result_findings = tuple(sorted(unique.values(), key=lambda item: (item.severity != "high", item.code)))
    risk = "high" if any(item.severity == "high" for item in result_findings) else "medium" if result_findings else "none"
    return BashValidationResult(syntax_valid, "bash -n + bashlex" if not ast_error else "bash -n (bashlex analysis incomplete)", risk, result_findings, syntax_error)
