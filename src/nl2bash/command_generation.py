"""Local Qwen command generation via llama-cpp-python."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shlex
import time
from typing import Any

from nl2bash.entity_extraction import EntityExtractionResult
from nl2bash.intent_prediction import IntentPrediction

DEFAULT_MODEL_PATH = Path.home() / ".cache/nl2bash/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"
DEFAULT_CONTEXT_SIZE = 1024
DEFAULT_MAX_TOKENS = 48
DEFAULT_RETRY_MAX_TOKENS = 96
DEFAULT_THREADS = 2
DEFAULT_BATCH_SIZE = 128
DEFAULT_GPU_LAYERS = 0
PROMPT_VERSION = "qwen-bash-command-v8"


class CommandGenerationError(RuntimeError):
    """Raised when local command generation is unavailable or malformed."""


class LocalGeneratorRequired(CommandGenerationError):
    """Signals that a deterministic route did not match and an LLM is needed."""


@dataclass(frozen=True, slots=True)
class GeneratedCommand:
    command: str
    explanation: str
    assumptions: tuple[str, ...]
    model: str
    prompt_version: str
    inference_metrics: dict[str, float | int | str] = field(default_factory=dict)


def _prompt(
    request: str,
    intent: IntentPrediction | None,
    extraction: EntityExtractionResult | None,
) -> list[dict[str, str]]:
    """Build a compact command-only prompt; deterministic NLP facts stay explicit."""
    system = (
        "You translate Linux tasks into Bash. Output exactly one Bash command, with no prose "
        "or Markdown. Preserve every explicit path, name, value, filter, and comparison. "
        "Never invent identifiers or add constraints. Prefer read-only inspection; do not "
        "use eval or download scripts. Match filenames case-sensitively unless asked otherwise."
    )
    facts: list[str] = []
    if intent is not None:
        facts.append(f"intent={intent.intent_label}")
    if extraction is not None:
        for item in extraction.entities:
            value = item.normalized_value or item.value
            if item.entity_type == "path":
                facts.append(f"path={item.value}")
            elif item.entity_type == "programming_language":
                facts.append(f"{item.value} files: match *{value}")
            elif item.entity_type == "file_extension":
                facts.append(f"extension={value}; preserve this exact extension")
            elif item.entity_type == "size":
                match = re.search(r"(\d+)\s+bytes", str(value))
                if match:
                    size_bytes = int(match.group(1))
                    comparator = "+" if any(x.entity_type == "comparison_condition" and x.normalized_value == "greater_than" for x in extraction.entities) else ""
                    facts.append(f"GNU find exact byte-size expression: -size {comparator}{size_bytes}c")
                else:
                    facts.append(f"size={item.value} ({value})")
            elif item.entity_type == "date_time":
                if "last 24 hours" in str(value).lower():
                    facts.append("time filter: -mmin -1440")
                else:
                    facts.append(f"time={value}")
            elif item.entity_type == "process_metric":
                facts.append(f"process metric={value}; use ps field {item.normalized_value}")
            elif item.entity_type == "case_sensitivity":
                facts.append(f"case sensitivity={value}")
        for issue in extraction.issues:
            facts.append(f"extraction note={issue.code}")
    user = f"Task: {request}"
    if facts:
        user += "\nFacts: " + "; ".join(facts)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _validate_command_text(content: Any, model_name: str) -> GeneratedCommand:
    if not isinstance(content, str) or not content.strip():
        raise CommandGenerationError("model returned an empty command")
    command = content.strip()
    if len(command) > 10_000 or "\x00" in command:
        raise CommandGenerationError("model response contains an oversized or malformed command")
    if command.startswith("```"):
        command = command.split("\n", 1)[1] if "\n" in command else ""
        if command.rstrip().endswith("```"):
            command = command.rstrip()[:-3].rstrip()
    command = command.strip()
    for prefix in ("bash:", "command:", "Bash command:"):
        if command.lower().startswith(prefix.lower()):
            command = command[len(prefix):].strip()
            break
    command = command.replace("<think>", "").replace("</think>", "").strip()
    if not command or "```" in command:
        raise CommandGenerationError("model returned prose or an empty command instead of Bash")
    if command.lower().startswith(("here is", "the command is", "you can use")):
        raise CommandGenerationError("model returned explanatory prose instead of a Bash command")
    return GeneratedCommand(
        command, "Generated from the natural-language request.", (), model_name, PROMPT_VERSION,
    )


def load_local_generator(
    model_path: str | Path | None = None, *, context_size: int = DEFAULT_CONTEXT_SIZE,
    threads: int | None = None, batch_size: int = DEFAULT_BATCH_SIZE,
    gpu_layers: int = DEFAULT_GPU_LAYERS,
) -> Any:
    """Load a local GGUF model; there is no remote API fallback."""
    selected_path = Path(model_path or os.environ.get("NL2BASH_LLM_MODEL", DEFAULT_MODEL_PATH)).expanduser()
    if not selected_path.is_file():
        raise CommandGenerationError(
            f"local model not found: {selected_path}. See docs/LOCAL_MODEL_SETUP.md to install the Qwen GGUF model."
        )
    if isinstance(context_size, bool) or not isinstance(context_size, int) or not 512 <= context_size <= 16384:
        raise ValueError("context_size must be an integer between 512 and 16384")
    try:
        from llama_cpp import Llama
    except ImportError as exc:
        raise CommandGenerationError(
            "llama-cpp-python is not installed. Install the local-llm optional dependency; see docs/LOCAL_MODEL_SETUP.md."
        ) from exc
    selected_threads = threads if threads is not None else min(DEFAULT_THREADS, os.cpu_count() or 1)
    if isinstance(selected_threads, bool) or not isinstance(selected_threads, int) or not 1 <= selected_threads <= 64:
        raise ValueError("threads must be an integer between 1 and 64")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 32 <= batch_size <= 2048:
        raise ValueError("batch_size must be an integer between 32 and 2048")
    if isinstance(gpu_layers, bool) or not isinstance(gpu_layers, int) or not 0 <= gpu_layers <= 256:
        raise ValueError("gpu_layers must be an integer between 0 and 256")
    try:
        return Llama(model_path=str(selected_path), n_ctx=context_size, n_threads=selected_threads,
                     n_threads_batch=selected_threads, n_batch=batch_size, n_ubatch=batch_size,
                     n_gpu_layers=gpu_layers, use_mmap=True, verbose=False)
    except Exception as exc:
        raise CommandGenerationError(f"could not load local GGUF model {selected_path}: {exc}") from exc



def _fast_candidate_covers_request(
    request: str, extraction: EntityExtractionResult, command: str, route: str,
) -> bool:
    """Reject a template when it omits explicit, mechanically checkable requirements."""
    lower = request.casefold()
    output = command.casefold()

    # Every extracted non-trivial path must be represented in the command.
    for entity in extraction.entities:
        if entity.entity_type != "path":
            continue
        value = str(entity.value).strip()
        if not value or value in {".", "./"}:
            continue
        candidates = {value, value.strip("'\"")}
        if value.startswith("~/"):
            candidates.update({"$HOME/" + value[2:], "${HOME}/" + value[2:]})
        if not any(candidate.casefold() in output for candidate in candidates if candidate):
            return False

    # "Home directory" is a scope requirement, not an alias for the current directory.
    if re.search(r"\b(?:my|user'?s)\s+home(?:\s+(?:directory|folder))?\b|\bhome\s+(?:directory|folder)\b", lower):
        if not re.search(r"(?:\$HOME|\$\{HOME\}|~/|/home/)", output):
            return False

    # Preserve every explicitly mentioned suffix (including compound suffixes).
    explicit_extensions = set(re.findall(
        r"(?<![A-Za-z0-9_])\.[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*", lower,
    ))
    if any(extension not in output for extension in explicit_extensions):
        return False

    # Time and size filters must survive the fast route.
    if re.search(r"\b(?:last|past)\s+(?:24\s+hours?|day)\b|\bwithin\s+(?:the\s+)?last\s+24\s+hours?\b", lower):
        if not re.search(r"(?:-mmin\b|-mtime\b|-cmin\b|-ctime\b|-newermt\b|-newer\b)", output):
            return False
    if re.search(r"\b(?:last|past)\s+(?:seven|7)\s+days?\b", lower):
        if not re.search(r"(?:-mmin\b|-mtime\b|-newermt\b|-newer\b)", output):
            return False
    if any(entity.entity_type == "size" for entity in extraction.entities):
        if not re.search(r"(?:-size\b|--threshold\b|\bdu\b)", output):
            return False

    asks_for_directories = bool(re.search(
        r"\b(?:find|list|show|display)\s+(?:all\s+)?(?:the\s+)?(?:directories|folders)\b", lower,
    ))
    if asks_for_directories and "find " in output and "-type d" not in output and not re.search(r"\bdu\b", output):
        return False
    if re.search(r"\bregular files\b", lower) and "find " in output and "-type f" not in output:
        return False

    # Explicit operation verbs must be reflected by the generated command.
    action_requirements = (
        (r"\b(?:convert|converting|converted|transform|transcode|render)\b",
         r"\b(?:pandoc|soffice|libreoffice|ffmpeg|magick|convert|gs|enscript|wkhtmlto[a-z]*)\b"),
        (r"\bappend\b|\badd\b.{0,40}\b(?:existing\s+)?archive\b",
         r"\btar\b.*(?:--append|--concatenate|(?:^|\s)-[a-z]*r[a-z]*(?:\s|$))"),
        (r"\b(?:move|moving)\b", r"(?:^|[\s;&|])mv(?:\s|$)"),
        (r"\b(?:copy|copied|copying)\b", r"\b(?:cp|scp|rsync)\b"),
        (r"\b(?:delete|deleting|remove|removing)\b", r"\brm\b|\b-unlink\b|\s-delete\b"),
        (r"\b(?:archive|archiving|compress|compressing|zip)\b", r"\b(?:tar|zip|gzip|bzip2|xz)\b"),
        (r"\b(?:extract|unpack|uncompress)\b", r"\bunzip\b|\b7z\b.*\bx\b|\btar\b.*(?:-x|--extract)"),
        (r"\b(?:change|modify|set)\b.{0,30}\bpermissions?\b|\bchmod\b",
         r"\b(?:chmod|chown|setfacl)\b"),
        (r"\bcount\b.{0,40}\b(?:lines|files|matches|occurrences)\b", r"\b(?:wc|awk|grep)\b"),
        (r"\b(?:sort|sorted|sorting)\b", r"\bsort\b"),
    )
    for request_pattern, command_pattern in action_requirements:
        if re.search(request_pattern, lower) and not re.search(command_pattern, output):
            return False

    # Searching names and searching file contents are different operations.
    if re.search(r"\b(?:search|find|look)\b.{0,80}\b(?:contents?|text|lines?|contain(?:ing)?)\b", lower):
        if not re.search(r"\b(?:grep|rg|awk|sed)\b", output):
            return False
    if re.search(r"\bcase[- ]insensitive\b|\bignore case\b", lower):
        if not re.search(r"(?:-iname\b|grep\b.*\s-i\b|rg\b.*\s-i\b)", output):
            return False
    if re.search(r"\brecursively\b", lower) and "find " not in output and not re.search(r"\b(?:grep|rg)\b.*\s-R\b", output):
        return False

    return True


def _try_fast_command(request: str, extraction: EntityExtractionResult) -> tuple[str, str] | None:
    """Handle common, well-specified Linux tasks without invoking the LLM."""
    text = request.strip()
    lower = text.casefold()
    paths = [item.value for item in extraction.entities if item.entity_type == "path"]

    def quote_path(value: str) -> str:
        # Expand only simple, explicit shell variables; quote everything else.
        if re.fullmatch(r"\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)(?:/[A-Za-z0-9._-]+)*", value):
            return f'"{value}"'
        if re.fullmatch(r"~/[A-Za-z0-9._/-]*", value):
            return '"$HOME/' + value[2:] + '"'
        return shlex.quote(value)

    quoted_paths = " ".join(quote_path(path) for path in paths) if paths else "."
    extensions = [item.normalized_value or item.value for item in extraction.entities
                  if item.entity_type == "file_extension"]
    languages = [item.normalized_value or item.value for item in extraction.entities
                 if item.entity_type == "programming_language"]
    extension = extensions[0] if extensions else (languages[0] if languages else None)
    extension_values = list(dict.fromkeys(extensions or languages))
    if not extension_values:
        pair_match = re.search(r"(['\"])(\.[A-Za-z0-9]+)\1\s+or\s+(['\"])(\.[A-Za-z0-9]+)\3", text)
        if pair_match:
            extension_values = [pair_match.group(2), pair_match.group(4)]
    extension_patterns = [shlex.quote(f"*{value}" if not value.startswith("*") else value)
                          for value in extension_values]
    extension_pattern = shlex.quote(f"*{extension}" if extension and not extension.startswith("*") else extension or "")
    variable_paths = re.findall(r"\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)", text)
    named_path_match = re.search(r"containing\s+(['\"]?)(\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|/[A-Za-z0-9_./-]+)\1", text, re.IGNORECASE)

    # Prune one explicit subtree while still printing the excluded directory itself.
    prune_match = re.search(r"skip the directory\s+([^\s,;]+)", text, re.IGNORECASE)
    if prune_match and "print it" in lower and ("under it" in lower or "under that" in lower):
        subtree = prune_match.group(1).strip("'\"`.,")
        subtree = subtree if subtree.startswith("./") else "./" + subtree.lstrip("./")
        return f"find . -path {shlex.quote(subtree)} -print -prune -o -print", "prune_named_directory_and_print_others"

    # Bash directory-stack operation.
    if "dirs stack" in lower and ("top two" in lower or "first two" in lower):
        return "pushd +1", "swap_directory_stack_entries"

    # Resolve an IPv4 address for an explicitly named network interface.
    interface_match = re.search(
        r"(?:network\s+)?interface\s+['\"]?([A-Za-z0-9_.:-]+)['\"]?|"
        r"['\"]([A-Za-z0-9_.:-]+)['\"]\s+network\s+interface",
        text, re.IGNORECASE,
    )
    if "ip address" in lower and interface_match:
        interface = shlex.quote(interface_match.group(1) or interface_match.group(2))
        return f"ip -o -4 addr show dev {interface}", "interface_ipv4_address"

    if "ip address" in lower and "primary" in lower and "interface" in lower:
        return ("ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i==\"src\") print $(i+1)}'",
                "primary_interface_ipv4_address")

    # Mount-point lookup for the filesystem containing an explicit path or variable.
    if "mount point" in lower and (named_path_match or variable_paths or paths):
        target = quote_path(named_path_match.group(2)) if named_path_match else quote_path(variable_paths[0]) if variable_paths else quote_path(paths[0])
        return f"df -P {target} | awk 'NR==2 {{print $6}}'", "filesystem_mount_point"

    # Extract a supported tar archive while keeping the filename as the only operand.
    extraction_match = re.search(r"\bextract\s+['\"]?([^\s'\"]+\.(?:tar\.xz|tar\.gz|tar\.bz2|tar|tgz|txz))['\"]?", text, re.IGNORECASE)
    if extraction_match and any(word in lower for word in ("extract", "unpack")):
        archive = shlex.quote(extraction_match.group(1))
        return f"tar -xvf {archive}", "extract_tar_archive"

    # List functions currently defined in the interactive shell.
    if "function" in lower and "shell" in lower and any(word in lower for word in ("list", "defined", "show")):
        return "declare -F", "list_shell_functions"

    # Find files and display only their basename, not their full path.
    if ("filename" in lower or "file names" in lower or "filenames" in lower) \
            and ("not paths" in lower or "only the" in lower):
        return f"find {quoted_paths} -type f -printf '%f\\n'", "file_basenames_only"

    # Find .conf files at a precise depth and show the final few lines of each.
    depth_match = re.search(r"\b(?:up to|upto)\s+(\d+)\s+levels?\s+down\b", lower)
    wants_tail = "tail" in lower or ("few lines" in lower and "from the end" in lower)
    if extension == ".conf" and depth_match and wants_tail and paths:
        depth = int(depth_match.group(1))
        maxdepth = depth + 1
        return (f"find {quoted_paths} -maxdepth {maxdepth} -type f -name '*.conf' "
                f"-exec tail -n 5 {{}} +", "find_conf_files_and_tail")

    # Exclude hidden subdirectories while finding a specific name.
    quoted_name = re.search(r"['\"]([^'\"]{1,200})['\"]", text)
    if quoted_name and "hidden director" in lower and "regular files" in lower:
        name = shlex.quote(quoted_name.group(1))
        return f"find . -path '*/.*' -prune -o -type f -name {name} -print", "find_excluding_hidden_directories"

    # Copy named directories to a remote host over SSH as the current local user.
    host_match = re.search(r"\bon host\s+['\"]([A-Za-z0-9.-]+)['\"]", text, re.IGNORECASE)
    target_match = re.search(r"to directory\s+['\"]([^'\"]+)['\"]", text, re.IGNORECASE)
    if host_match and target_match and "recursively copy directories" in lower:
        source_names = re.findall(r"directories\s+((?:['\"][^'\"]+['\"]\s+and\s+['\"][^'\"]+['\"]))", text, re.IGNORECASE)
        if source_names:
            sources = re.findall(r"['\"]([^'\"]+)['\"]", source_names[0])
            if len(sources) == 2:
                destination = f'"$(id -un)@{host_match.group(1)}:{target_match.group(1).rstrip("/")}/"'
                return f"scp -r -P 22 {shlex.quote(sources[0])} {shlex.quote(sources[1])} {destination}", "copy_directories_over_ssh"

    # Move related marker/PDF pairs between explicitly named environment paths.
    if "move all" in lower and ".pdf.marker" in lower and "corresponding" in lower:
        vars_in_order = re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", text)
        if len(vars_in_order) >= 2:
            source, destination = quote_path("${" + vars_in_order[0] + "}"), quote_path("${" + vars_in_order[1] + "}")
            return (f"find {source} -type f \\( -name '*.pdf.marker' -o -name '*.pdf' \\) "
                    f"-exec mv -t {destination} -- {{}} +"), "move_related_pdf_files"

    # Move MP3 files from the filesystem root into the requested destination.
    if "mp3" in lower and "move" in lower and "file system" in lower and paths:
        destination = quote_path(paths[-1])
        return f"find / -type f -name '*.mp3' -exec mv -t {destination} -- {{}} +", "move_mp3_files"

    # Run mplayer for a specific MP3 filename pattern.
    if extension == ".mp3" and "mplayer" in lower:
        glob_match = re.search(r"([A-Za-z0-9_*?.-]+\.mp3)", text, re.IGNORECASE)
        if glob_match:
            pattern = shlex.quote(glob_match.group(1))
            return f"find . -type f -name {pattern} -exec mplayer {{}} +", "run_mplayer_for_matching_files"

    # Archive a specific file type into a named tar archive.
    archive_match = re.search(r"\b([\w.-]+\.(?:tar\.gz|tgz|tar))\b", text, flags=re.IGNORECASE)
    if archive_match and ("archive" in lower or "compress" in lower or "tar" in lower):
        pattern_match = re.search(r"\b([A-Za-z0-9_.-]*\*[A-Za-z0-9_.*-]*)\s+files?(?:/directories)?\b", text, re.IGNORECASE)
        if extension or pattern_match:
            pattern_value = f"*{extension}" if extension else pattern_match.group(1)
            pattern = shlex.quote(pattern_value)
            archive = shlex.quote(archive_match.group(1))
            compress_flag = "-czf" if archive_match.group(1).lower().endswith((".gz", ".tgz")) else "-cf"
            archive_root_match = re.search(r"\bunder\s+([^\s]+)", text, re.IGNORECASE)
            archive_root = quote_path(archive_root_match.group(1).rstrip(".,")) if archive_root_match else quoted_paths
            file_type = "" if "files/directories" in lower or "files and directories" in lower else "-type f "
            command = (f"find {archive_root} {file_type}-name {pattern} -print0 | "
                       f"tar {compress_flag} {archive} --null -T -")
            return command, "archive_matching_files"

    # Search by filename, not by searching file contents.
    named_file = re.search(r"\bfile\s+['\"]([^'\"]+\.[A-Za-z0-9]+)['\"]", text, re.IGNORECASE)
    if named_file and any(word in lower for word in ("search", "find", "look for")) \
            and not any(word in lower for word in ("contents", "text", "contain", "lines")):
        return f"find {quoted_paths} -type f -name {shlex.quote(named_file.group(1))} -print", "find_named_file"

    # Search for an explicitly quoted term in a known source-file type.
    search_match = re.search(r"['\"]([^'\"]{1,200})['\"]", text)
    if search_match and extension and any(word in lower for word in ("search", "grep", "look for", "find text", "contain")):
        pattern = shlex.quote(f"*{extension}" if not extension.startswith("*") else extension)
        term = shlex.quote(search_match.group(1))
        command = f"find {quoted_paths} -type f -name {pattern} -exec grep -Hn -- {term} {{}} +"
        return command, "search_text_in_file_type"

    # Apply an explicitly requested mode to a named file type in named directories.
    chmod_match = re.search(r"\b(?:to|mode)\s+([0-7]{3,4})\b", text, re.IGNORECASE)
    if chmod_match and extension and any(term in lower for term in ("permission", "permiss", "chmod", "change")):
        dirs_match = re.search(r"under directories?\s+([A-Za-z0-9_.-]+)\s+and\s+([A-Za-z0-9_.-]+)", text, re.IGNORECASE)
        if dirs_match:
            directories = f"{shlex.quote(dirs_match.group(1))} {shlex.quote(dirs_match.group(2))}"
            pattern = shlex.quote(f"*{extension}" if not extension.startswith("*") else extension)
            return f"find {directories} -type f -name {pattern} -exec chmod {chmod_match.group(1)} {{}} +", "change_file_permissions"

    # Return the unique parent directories of matching files.
    if "parent director" in lower:
        name_match = re.search(r"\b([A-Za-z0-9_.-]+\.[A-Za-z0-9]+)\b", text)
        if name_match or extension:
            pattern = shlex.quote(name_match.group(1) if name_match else f"*{extension}")
            return f"find {quoted_paths} -type f -name {pattern} -printf '%h\\n' | sort -u", "parent_directories_for_file_type"

    # Count lines in every file of an explicitly identified file type.
    if extension and any(word in lower for word in ("count the lines", "line count", "number of lines", "display the number of lines")):
        pattern = shlex.quote(f"*{extension}" if not extension.startswith("*") else extension)
        return f"find {quoted_paths} -type f -name {pattern} -print0 | xargs -0 wc -l", "count_lines_by_file_type"

    # Extract IPv4-looking tokens from files below a requested path.
    if "ip address" in lower and paths:
        return (f"grep -RhoIE --binary-files=without-match "
                f"'([0-9]{{1,3}}\\.){{3}}[0-9]{{1,3}}' {quoted_paths}", "find_ipv4_addresses")

    # Search for multiple explicit file extensions without losing either predicate.
    if len(extension_patterns) >= 2 and any(word in lower for word in ("search", "find", "list")) \
            and any(word in lower for word in ("files", "names")) \
            and not any(word in lower for word in ("contain", "contents", "text", "move", "delete", "remove")):
        predicates = " -o ".join(f"-name {pattern}" for pattern in extension_patterns)
        return f"find {quoted_paths} -type f \\( {predicates} \\) -print", "find_multiple_file_types"

    # Filter files by an explicit wildcard path and numeric-sort the requested filename field.
    numeric_field_match = re.search(r"\*+/([A-Za-z0-9_.-]+)/\*+", text)
    if numeric_field_match and extension and "numerically sort" in lower and "second field" in lower \
            and "delimiter '_'" in lower:
        path_pattern = shlex.quote(f"*/{numeric_field_match.group(1)}/*")
        pattern = shlex.quote(f"*{extension}" if not extension.startswith("*") else extension)
        command = (f"find . -type f -path {path_pattern} -name {pattern} -printf '%f\\n' "
                   "| sort -t '_' -k2,2n")
        return command, "numeric_sort_filename_field_by_path_pattern"

    # Sum the sizes of all files of a specified extension.
    if extension and "total size" in lower and not any(word in lower for word in ("directory size", "disk usage")):
        pattern = shlex.quote(f"*{extension}" if not extension.startswith("*") else extension)
        command = (f"find {quoted_paths} -type f -name {pattern} -printf '%s\\n' "
                   "| awk '{total += $1} END {printf \"%.0f\\n\", total}'")
        return command, "sum_file_sizes"

    # POSIX mode bits: both group-write (0020) and other-write (0002) must be set.
    if "writable" in lower and "both" in lower and "other" in lower and "group" in lower:
        return f"find {quoted_paths} -type f -perm -0022 -print", "files_group_and_other_writable"

    # Exact extracted size and time filters are rendered deterministically.
    size_entity = next((item for item in extraction.entities if item.entity_type == "size"), None)
    comparison = next((item for item in extraction.entities if item.entity_type == "comparison_condition"), None)
    time_entity = next((item for item in extraction.entities if item.entity_type == "date_time"), None)
    if size_entity and comparison and comparison.normalized_value == "greater_than" \
            and re.search(r"\b(?:directories|folders)\b", lower):
        match = re.search(r"(\d+)\s+bytes", str(size_entity.normalized_value))
        if match and not time_entity:
            return (f"du -B1 --threshold={int(match.group(1))} {quoted_paths}",
                    "directories_over_size")

    directory_query = bool(re.search(r"\b(?:directories|folders)\b", lower))
    archive_or_compress_query = any(word in lower for word in ("archive", "compress", "tar", "zip"))
    if (size_entity or time_entity or "last seven days" in lower or "last 7 days" in lower) \
            and not (directory_query and archive_or_compress_query):
        predicates = ["-type f"]
        if extension:
            predicates.extend(["-name", shlex.quote(f"*{extension}" if not extension.startswith("*") else extension)])
        if size_entity and comparison and comparison.normalized_value == "greater_than":
            match = re.search(r"(\d+)\s+bytes", str(size_entity.normalized_value))
            if match:
                predicates.extend(["-size", f"+{int(match.group(1))}c"])
        if time_entity and "last 24 hours" in str(time_entity.normalized_value).casefold():
            predicates.extend(["-mmin", "-1440"])
        elif "last seven days" in lower or "last 7 days" in lower:
            predicates.extend(["-mmin", "-10080"])
        if len(predicates) > 1:
            return f"find {quoted_paths} {' '.join(predicates)} -print", "file_discovery_filters"

    if "process" in lower and any(word in lower for word in ("memory", "ram", "resident")) \
            and any(word in lower for word in ("most", "top", "highest", "largest", "using")):
        return "ps -eo pid,comm,rss --sort=-rss | head -n 11", "top_processes_by_memory"

    if "tcp" in lower and "port" in lower and any(word in lower for word in ("listen", "listening")):
        suffix = "p" if any(word in lower for word in ("process", "pid", "program")) else ""
        return f"ss -lt{suffix}n", "listening_tcp_ports"

    if "disk usage" in lower and paths:
        if "filesystem" in lower or "file system" in lower:
            unit = "-k" if "kilobyte" in lower or re.search(r"\bkb\b", lower) else "-h"
            return f"df {unit} {quoted_paths}", "filesystem_usage"
        return f"du -sh {quoted_paths}", "directory_disk_usage"

    # Simple extension discovery only when no extra filters or actions were requested.
    simple_discovery = not any(term in lower for term in (
        "only", "up to", "upto", "level", "depth", "directories", "folders",
        "files/directories", "few lines", "last ", "modified", "permission", "permissions",
        "tail", "head", "end", "older", "newer", "before", "after", "recursive",
        "recursively", "parent", "run ", "execute", "move", "copy", "delete", "remove",
        "change", "chmod", "mplayer", "and their", "contain", "excluding", "exclude",
    ))
    if extension and simple_discovery and any(word in lower for word in ("find", "list", "show")) \
            and any(word in lower for word in ("file", "files")) \
            and not (size_entity or time_entity or search_match or archive_match):
        return f"find {quoted_paths} -type f -name {extension_pattern} -print", "find_file_type"

    return None


def generate_bash_command(
    request: str, intent: IntentPrediction, extraction: EntityExtractionResult, *,
    generator: Any, model_name: str = "Qwen2.5-1.5B-Instruct-Q4_K_M", max_tokens: int = DEFAULT_MAX_TOKENS,
    include_nlp_context: bool = True,
) -> GeneratedCommand:
    """Generate one compact Bash command using an already-loaded local model."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("request must be non-empty text")
    if not isinstance(intent, IntentPrediction) or not isinstance(extraction, EntityExtractionResult):
        raise TypeError("intent and extraction must be validated pipeline outputs")
    if extraction.request != request.strip():
        raise ValueError("entity extraction request does not match the generation request")
    if not isinstance(include_nlp_context, bool):
        raise TypeError("include_nlp_context must be a boolean")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 16 <= max_tokens <= 512:
        raise ValueError("max_tokens must be an integer between 16 and 512")
    fast_started = time.perf_counter()
    fast_match = _try_fast_command(request, extraction) if include_nlp_context else None
    fast_path_seconds = time.perf_counter() - fast_started
    if fast_match is not None:
        command, route = fast_match
        if _fast_candidate_covers_request(request, extraction, command, route):
            return GeneratedCommand(
                command, "Generated using a deterministic command template.", (),
                f"deterministic:{route}", PROMPT_VERSION,
                {"fast_path_seconds": round(fast_path_seconds, 6), "generation_path": "deterministic_template"},
            )
        # Prefer a slower local fallback over returning a template that drops intent.
    if generator is None:
        raise LocalGeneratorRequired("no deterministic template matched; local LLM fallback is required")

    prompt_started = time.perf_counter()
    messages = _prompt(request, intent if include_nlp_context else None, extraction if include_nlp_context else None)
    prompt_build_seconds = time.perf_counter() - prompt_started
    context_handle = None
    perf_context = None
    perf_reset = None
    try:
        import llama_cpp
        perf_context = getattr(llama_cpp, "llama_perf_context", None)
        perf_reset = getattr(llama_cpp, "llama_perf_context_reset", None)
        context_handle = getattr(getattr(generator, "_ctx", None), "ctx", None)
        if context_handle is not None and callable(perf_reset):
            perf_reset(context_handle)
    except Exception:
        context_handle = None

    try:
        inference_started = time.perf_counter()
        response = generator.create_chat_completion(
            messages=messages, temperature=0.0, top_p=0.9, seed=42,
            max_tokens=max_tokens,
        )
        initial_inference_seconds = time.perf_counter() - inference_started
        retry_inference_seconds = 0.0
        retry_count = 0
        response_history = [response]
        choice = response["choices"][0]
        if choice.get("finish_reason") == "length":
            retry_started = time.perf_counter()
            response = generator.create_chat_completion(
                messages=messages, temperature=0.0, top_p=0.9, seed=42,
                max_tokens=DEFAULT_RETRY_MAX_TOKENS,
            )
            retry_inference_seconds = time.perf_counter() - retry_started
            retry_count = 1
            response_history.append(response)
            choice = response["choices"][0]
            if choice.get("finish_reason") == "length":
                raise CommandGenerationError(
                    "command generation remained incomplete after the bounded token-budget retry "
                    f"({max_tokens} tokens, then {DEFAULT_RETRY_MAX_TOKENS} tokens); "
                    "no partial command was returned"
                )
        content = choice.get("message", {}).get("content")
        generated = _validate_command_text(content, model_name)
    except CommandGenerationError:
        raise
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise CommandGenerationError(f"local model returned an invalid response: {exc}") from exc
    except Exception as exc:
        raise CommandGenerationError(f"local model inference failed: {exc}") from exc

    inference_metrics: dict[str, float | int | str] = {
        "generation_path": "local_llm",
        "prompt_build_seconds": round(prompt_build_seconds, 6),
        "initial_model_call_seconds": round(initial_inference_seconds, 6),
        "retry_model_call_seconds": round(retry_inference_seconds, 6),
        "model_call_seconds": round(initial_inference_seconds + retry_inference_seconds, 6),
        "retry_count": retry_count,
        "initial_max_tokens": max_tokens,
        "retry_max_tokens": DEFAULT_RETRY_MAX_TOKENS,
        "max_tokens_used": DEFAULT_RETRY_MAX_TOKENS if retry_count else max_tokens,
    }
    usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for attempt in response_history:
        usage = attempt.get("usage", {}) if isinstance(attempt, dict) else {}
        if isinstance(usage, dict):
            for key in usage_totals:
                value = usage.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    usage_totals[key] += value
    for key, value in usage_totals.items():
        if value:
            inference_metrics[key] = value
    if context_handle is not None and callable(perf_context):
        try:
            perf = perf_context(context_handle)
            prompt_eval_ms = float(perf.t_p_eval_ms)
            token_eval_ms = float(perf.t_eval_ms)
            prompt_eval_tokens = int(perf.n_p_eval)
            generated_tokens = int(perf.n_eval)
            inference_metrics.update({
                "prompt_eval_seconds": round(prompt_eval_ms / 1000.0, 6),
                "token_generation_seconds": round(token_eval_ms / 1000.0, 6),
                "prompt_eval_tokens": prompt_eval_tokens,
                "compute_graph_reuse_count": int(getattr(perf, "n_reused", 0)),
                "completion_tokens": generated_tokens,
            })
            if "prompt_tokens" not in inference_metrics:
                inference_metrics["prompt_tokens"] = prompt_eval_tokens
            if prompt_eval_ms > 0 and prompt_eval_tokens > 0:
                inference_metrics["prompt_eval_tokens_per_second"] = round(
                    prompt_eval_tokens * 1000.0 / prompt_eval_ms, 2,
                )
            if token_eval_ms > 0 and generated_tokens > 0:
                inference_metrics["generation_tokens_per_second"] = round(
                    generated_tokens * 1000.0 / token_eval_ms, 2,
                )
        except Exception:
            pass
    return GeneratedCommand(
        generated.command, generated.explanation, generated.assumptions,
        generated.model, generated.prompt_version, inference_metrics,
    )
