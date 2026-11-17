"""Deterministic extraction of selected entities from Bash requests."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
import re

from nl2bash.preprocessing import normalize_request

ENTITY_TYPES = (
    "file_extension", "path", "file_name", "size", "port",
    "process_name", "process_metric", "date_time", "comparison_condition", "programming_language", "case_sensitivity",
)


@dataclass(frozen=True, slots=True)
class ExtractedEntity:
    """An exact entity mention with offsets and an optional normalized value."""
    entity_type: str
    value: str
    start: int
    end: int
    normalized_value: str | None = None

    def __post_init__(self) -> None:
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError(f"unsupported entity type: {self.entity_type}")
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("entity value must be non-empty text")
        if (isinstance(self.start, bool) or not isinstance(self.start, int)
                or isinstance(self.end, bool) or not isinstance(self.end, int)
                or self.start < 0 or self.end <= self.start):
            raise ValueError("entity span must be a non-empty, non-negative range")
        if self.normalized_value is not None and not isinstance(self.normalized_value, str):
            raise TypeError("normalized_value must be a string or None")


@dataclass(frozen=True, slots=True)
class ExtractionIssue:
    """A missing or contradictory parameter detected without inventing a value."""
    code: str
    message: str
    start: int | None = None
    end: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code:
            raise ValueError("issue code must be non-empty text")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("issue message must be non-empty text")
        if (self.start is None) != (self.end is None):
            raise ValueError("issue start and end must either both be set or both be None")
        if self.start is not None and (
            isinstance(self.start, bool) or not isinstance(self.start, int)
            or isinstance(self.end, bool) or not isinstance(self.end, int)
            or self.start < 0 or self.end <= self.start
        ):
            raise ValueError("issue span must be a non-empty, non-negative range")


@dataclass(frozen=True, slots=True)
class EntityExtractionResult:
    """Structured extraction output; offsets refer to the normalized request."""
    request: str
    entities: tuple[ExtractedEntity, ...]
    issues: tuple[ExtractionIssue, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.request, str) or not self.request:
            raise ValueError("result request must be non-empty text")
        for entity in self.entities:
            if not isinstance(entity, ExtractedEntity):
                raise TypeError("entities must contain ExtractedEntity values")
            if entity.end > len(self.request) or self.request[entity.start:entity.end] != entity.value:
                raise ValueError("entity value does not match its request span")
        for issue in self.issues:
            if not isinstance(issue, ExtractionIssue):
                raise TypeError("issues must contain ExtractionIssue values")
            if issue.end is not None and issue.end > len(self.request):
                raise ValueError("issue span exceeds the request length")

    def by_type(self, entity_type: str) -> tuple[ExtractedEntity, ...]:
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"unsupported entity type: {entity_type}")
        return tuple(item for item in self.entities if item.entity_type == entity_type)


_QUOTED_RE = re.compile(r"(?P<q>['\"`])(?P<v>[^'\"`]*)(?P=q)")
_FILE_QUOTED_RE = re.compile(
    r"\b(?:files?|filenames?)\s+(?:(?:named|called)\s+)?"
    r"(?P<q>['\"`])(?P<v>[^'\"`]+)(?P=q)", re.I,
)
_FILE_BARE_RE = re.compile(
    r"\b(?:files?|filenames?)\s+(?:named|called)\s+(?P<v>[\w$*?.@+-]+"
    r"(?:\.[\w_*+-]+)*)", re.I,
)
_EXTENSION_RE = re.compile(
    r"(?<![A-Za-z0-9_.])\*?(?P<v>\.\w[\w-]*(?:\.\w[\w-]*)*)\b"
)
_SIZE_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<n>\d+(?:\.\d+)?)\s*(?P<u>bytes?|B|kB|KB|KiB|MB|MiB|GB|GiB|TB|TiB)\b", re.I
)
_SIZE_MULTIPLIER = {
    "b": 1, "byte": 1, "bytes": 1, "kb": 1_000, "kib": 1_024,
    "mb": 1_000_000, "mib": 1_048_576, "gb": 1_000_000_000,
    "gib": 1_073_741_824, "tb": 1_000_000_000_000,
    "tib": 1_099_511_627_776,
}
_PORT_PATTERNS = (
    re.compile(r"\bport(?:\s+(?:number|no\.?))?\s*(?:=|:|is)?\s*(?P<v>\d+)\b", re.I),
    re.compile(r"--port(?:=|\s+)(?P<v>\d+)\b", re.I),
)
_SSH_PORT_RE = re.compile(r"(?<!\w)-p\s+(?P<v>\d+)\b", re.I)
_PORT_CUE_RE = re.compile(r"\bport(?:\s+(?:number|no\.?))?\b", re.I)
_PROCESS_AFTER_QUOTED_RE = re.compile(
    r"\bprocess(?:es)?(?:\s+(?:named|called|with\s+name|name))?(?:\s+is)?\s+(?P<q>['\"])(?P<v>.*?)(?P=q)",
    re.I,
)
_PROCESS_AFTER_BARE_RE = re.compile(
    r"\bprocess(?:es)?(?:\s+(?:named|called|with\s+name|name))?(?:\s+is)?\s+(?P<v>[\w.-]+)",
    re.I,
)
_PROCESS_BEFORE_RE = re.compile(r"\b(?P<v>[\w.-]+)\s+process(?:es)?\b", re.I)
_PROCESS_STOP = {
    "a", "an", "the", "all", "any", "newest", "current", "running", "listening",
    "using", "with", "whose", "belonging", "owned", "under", "on", "at", "for",
    "by", "from", "to", "of", "it", "this", "that", "and", "or", "named", "called", "name", "find", "show",
    "list", "get", "monitor", "identify", "terminate", "kill", "stop", "start",
    "inspect", "search", "check", "display", "print", "is",
}
_DATE_PATTERNS = (
    re.compile(r"\b(?:within\s+the\s+last|in\s+the\s+last|more\s+than|less\s+than|newer\s+than|older\s+than|last|past|exactly|within|over|under|after|before)\s+\d+(?:\.\d+)?\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|wks?|months?|years?)\b", re.I),
    re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:,?\s+\d{4})?)\b", re.I),
    re.compile(r"\b\d{1,2}:\d{2}(?:\s*[AP]M)?\b", re.I),
    re.compile(r"\b(?:yesterday|today|tomorrow)\b", re.I),
)
_COMPARISONS = (
    ("greater_than_or_equal", r"at least|no less than|not less than|not smaller than|greater than or equal to"),
    ("less_than_or_equal", r"at most|no more than|not greater than|less than or equal to"),
    ("greater_than", r"greater than|larger than|bigger than|more than|above(?=\s+\d)|over(?=\s+\d)"),
    ("less_than", r"less than|smaller than|fewer than|below(?=\s+\d)|under(?=\s+\d)"),
    ("equal_to", r"equal to|equals?|exactly"),
    ("newer_than", r"newer than"), ("older_than", r"older than"),
    ("after", r"after"), ("before", r"before"),
)
_COMPARISON_RE = re.compile(r"\b(?P<v>" + "|".join(f"(?:{p})" for _, p in _COMPARISONS) + r")\b", re.I)
_COMPARISON_MAP = {part.lower(): label for label, phrases in _COMPARISONS for part in phrases.split("|")}
_COMPARISON_MAP["equal"] = "equal_to"
_COMPARISON_MAP["equals"] = "equal_to"
_COMPARISON_MAP["above"] = "greater_than"
_COMPARISON_MAP["over"] = "greater_than"
_COMPARISON_MAP["below"] = "less_than"
_COMPARISON_MAP["under"] = "less_than"
_COMPOUND_EXT = (".tar.bz2", ".tar.gz", ".tar.xz", ".tar.zst", ".sql.gz", ".tar.lz")
_LANGUAGE_EXTENSIONS = {
    "python": ".py", "javascript": ".js", "typescript": ".ts",
    "java": ".java", "rust": ".rs", "go": ".go", "golang": ".go",
    "ruby": ".rb", "php": ".php", "perl": ".pl", "bash": ".sh",
    "shell": ".sh", "sql": ".sql", "yaml": ".yaml", "yml": ".yml",
    "golang": ".go",
}
_LANGUAGE_FILE_RE = re.compile(
    r"\b(?P<language>Python|JavaScript|TypeScript|Java|Rust|Golang|Go|Ruby|PHP|Perl|Bash|Shell|SQL|YAML|YML)"
    r"\s+(?:source\s+)?(?:files?|scripts?|programs?|code)\b",
    re.I,
)
_PROCESS_METRICS = (
    ("virtual_memory", r"virtual(?:\s+private)?\s+memory|virtual\s+size|\bVSZ\b|\bVPRVT\b"),
    ("resident_memory", r"resident(?:\s+set)?\s+memory|\bRSS\b|\bRES\b"),
    ("cpu_usage", r"CPU\s+(?:usage|use|utili[sz]ation)|\b%CPU\b"),
)
_PROCESS_METRIC_RES = tuple(
    (name, re.compile(pattern, re.I), normalized)
    for name, pattern, normalized in (
        ("virtual_memory", _PROCESS_METRICS[0][1], "vsz"),
        ("resident_memory", _PROCESS_METRICS[1][1], "rss"),
        ("cpu_usage", _PROCESS_METRICS[2][1], "%cpu"),
    )
)


def _add(entities: list[ExtractedEntity], request: str, entity_type: str, start: int, end: int, normalized: str | None = None) -> None:
    if 0 <= start < end <= len(request):
        item = ExtractedEntity(entity_type, request[start:end], start, end, normalized)
        if item not in entities:
            entities.append(item)


_SLASH_PHRASES = {
    "files/directories", "file/directory", "and/or", "or/and", "input/output",
    "output/input", "read/write", "write/read", "yes/no", "no/yes", "true/false",
    "on/off", "off/on", "up/down", "down/up", "client/server", "server/client",
}


def _looks_like_path(value: str) -> bool:
    lowered = value.strip().lower()
    return (
        "/" in value
        and lowered not in _SLASH_PHRASES
        and not lowered.startswith(("http://", "https://", "ftp://"))
    )


def _trim_end(request: str, start: int, end: int) -> tuple[int, int]:
    while end > start and request[end - 1] in ".,;:!?)]}":
        end -= 1
    return start, end


def _extract_paths(request: str, entities: list[ExtractedEntity]) -> None:
    quoted = []
    for match in _QUOTED_RE.finditer(request):
        quoted.append(match.span())
        if _looks_like_path(match.group("v")):
            _add(entities, request, "path", *match.span("v"))
    absolute_or_rooted = re.compile(
        r"(?<![A-Za-z0-9_:/])(?P<v>(?:/(?!/)|~/|\.\.?/|\$\{[A-Za-z_]\w*\}/|\$[A-Za-z_]\w*/)[\w.@%+~*?\[\]-]+(?:/[\w.@%+~*?\[\]-]+)*/?)"
    )
    relative = re.compile(r"(?<![A-Za-z0-9_$/.:])(?P<v>[\w.-]+/[\w.-]+(?:/[\w.-]+)*/?)")
    for match in absolute_or_rooted.finditer(request):
        start, end = _trim_end(request, *match.span("v"))
        if not any(start < q_end and end > q_start for q_start, q_end in quoted):
            _add(entities, request, "path", start, end)

    # A single slash between ordinary words is often prose (files/directories,
    # input/output), not a path. Keep it only with path context or a filename
    # suffix; multi-component relative paths are sufficiently distinctive.
    path_cue = re.compile(r"\b(?:in|under|from|into|at|path|directory|folder|location)\s*$", re.I)
    for match in relative.finditer(request):
        start, end = _trim_end(request, *match.span("v"))
        value = request[start:end]
        if any(start < q_end and end > q_start for q_start, q_end in quoted):
            continue
        if not _looks_like_path(value):
            continue
        before = request[max(0, start - 40):start]
        has_context = bool(path_cue.search(before))
        has_suffix = bool(re.search(r"\.[A-Za-z0-9_-]+/?$", value))
        has_multiple_components = value.count("/") >= 2
        if has_context or has_suffix or has_multiple_components:
            _add(entities, request, "path", start, end)
    variable_root = re.compile(r"(?<![A-Za-z0-9_])(?P<v>\$\{[A-Za-z_]\w*\}|\$[A-Za-z_]\w*|~|\.{1,2})(?![A-Za-z0-9_/])")
    for match in variable_root.finditer(request):
        prefix = request[max(0, match.start() - 28):match.start()]
        if re.search(r"\b(?:in|under|from|into|at|path)\s+$", prefix, re.I):
            _add(entities, request, "path", *match.span("v"))


def _extract_file_names(request: str, entities: list[ExtractedEntity]) -> None:
    for pattern in (_FILE_QUOTED_RE, _FILE_BARE_RE):
        for match in pattern.finditer(request):
            value = match.group("v")
            if _looks_like_path(value) or value.lower() in {"in", "under", "to", "from", "with", "that", "which", "and"}:
                continue
            _add(entities, request, "file_name", *match.span("v"))


def _extension_for(value: str) -> tuple[int, str] | None:
    base_start = value.rfind("/") + 1
    basename = value[base_start:]
    if not basename or (basename.startswith(".") and basename.count(".") == 1):
        return None
    lower = basename.lower()
    for ext in _COMPOUND_EXT:
        if lower.endswith(ext) and len(basename) > len(ext):
            return base_start + len(basename) - len(ext), basename[-len(ext):]
    dot = basename.rfind(".")
    if dot <= 0 or dot == len(basename) - 1:
        return None
    ext = basename[dot:]
    if re.fullmatch(r"\.\w[\w-]*", ext):
        return base_start + dot, ext
    return None


def _extract_extensions(request: str, entities: list[ExtractedEntity]) -> None:
    for item in tuple(entities):
        if item.entity_type in {"path", "file_name"}:
            derived = _extension_for(item.value)
            if derived:
                offset, ext = derived
                start = item.start + offset
                _add(entities, request, "file_extension", start, start + len(ext), ext.lower())
    for match in _EXTENSION_RE.finditer(request):
        start, end = match.span("v")
        value = match.group("v")
        is_explicit_dotfile = any(
            item.entity_type == "file_name"
            and item.start == start and item.end == end
            and item.value.startswith(".") and item.value.count(".") == 1
            for item in entities
        )
        has_wildcard = start > 0 and request[start - 1] == "*"
        before = request[max(0, start - 32):start]
        after = request[end:end + 16]
        has_extension_context = bool(
            re.search(r"\b(?:extension|suffix|ending(?:\s+with)?)\s*$", before, re.I)
            or re.match(r"\s+files?\b", after, re.I)
            or re.search(r"\bfiles?\s+(?:with|matching|ending(?:\s+with)?)\s*$", before, re.I)
        )
        if value.count(".") == 1 and not (has_wildcard or has_extension_context):
            continue
        if not is_explicit_dotfile:
            _add(entities, request, "file_extension", start, end, value.lower())


def _extract_sizes(request: str, entities: list[ExtractedEntity]) -> None:
    for match in _SIZE_RE.finditer(request):
        try:
            raw_number = match.group("n")
            multiplier = _SIZE_MULTIPLIER[match.group("u").lower()]
            with localcontext() as context:
                context.prec = max(28, len(raw_number.replace(".", "")) + len(str(multiplier)) + 2)
                count = Decimal(raw_number) * multiplier
            normalized = f"{int(count)} bytes" if count == count.to_integral_value() else None
        except (InvalidOperation, KeyError, ValueError):
            normalized = None
        _add(entities, request, "size", *match.span(), normalized)


def _extract_ports(
    request: str,
    entities: list[ExtractedEntity],
    issues: list[ExtractionIssue],
) -> None:
    matches = [match for pattern in _PORT_PATTERNS for match in pattern.finditer(request)]
    if re.search(r"\bssh\b", request, re.I):
        matches.extend(_SSH_PORT_RE.finditer(request))
    unique_matches = {match.span("v"): match for match in matches}
    for match in sorted(unique_matches.values(), key=lambda item: item.start("v")):
        raw = match.group("v")
        normalized = raw.lstrip("0") or "0"
        start, end = match.span("v")
        _add(entities, request, "port", start, end, normalized)
        out_of_range = len(normalized) > 5 or (
            len(normalized) == 5 and int(normalized) > 65535
        ) or normalized == "0"
        if out_of_range:
            issues.append(ExtractionIssue(
                "port_out_of_range",
                f"port {raw} is outside the valid range 1-65535",
                start,
                end,
            ))

    for cue in _PORT_CUE_RE.finditer(request):
        remainder = request[cue.end():]
        if re.match(r"\s*(?:=|:|is)?\s*\d+\b", remainder, re.I):
            continue
        issues.append(ExtractionIssue(
            "missing_port_value",
            "the request mentions a port but does not provide a numeric value",
            cue.start(),
            cue.end(),
        ))


def _extract_process_names(
    request: str,
    entities: list[ExtractedEntity],
    issues: list[ExtractionIssue],
) -> None:
    for match in _PROCESS_AFTER_QUOTED_RE.finditer(request):
        _add(entities, request, "process_name", *match.span("v"))
    for match in _PROCESS_AFTER_BARE_RE.finditer(request):
        name = match.group("v")
        if name.lower() not in _PROCESS_STOP:
            _add(entities, request, "process_name", *match.span("v"))
    for match in _PROCESS_BEFORE_RE.finditer(request):
        name = match.group("v")
        if name.lower() not in _PROCESS_STOP:
            _add(entities, request, "process_name", *match.span("v"))

    cue_pattern = re.compile(
        r"\bprocess(?:es)?\s+(?:named|called|with\s+name|name)(?:\s+is)?\b", re.I
    )
    for cue in cue_pattern.finditer(request):
        has_value = any(
            entity.entity_type == "process_name"
            and cue.end() <= entity.start <= cue.end() + 5
            for entity in entities
        )
        if not has_value:
            issues.append(ExtractionIssue(
                "missing_process_name",
                "a process name was requested but not supplied",
                cue.start(),
                cue.end(),
            ))


_CASE_INSENSITIVE_RE = re.compile(
    r"\b(?:case[- ]insensitive|ignore\s+(?:the\s+)?case|any[- ]cased|regardless\s+of\s+case|case[- ]agnostic)\b",
    re.I,
)
_CASE_SENSITIVE_RE = re.compile(r"\bcase[- ]sensitive\b|\bmatch\s+case\b", re.I)


def _extract_case_sensitivity(request: str, entities: list[ExtractedEntity]) -> None:
    """Capture explicit case-matching requirements; absence means default semantics."""
    matches = [(m, "insensitive") for m in _CASE_INSENSITIVE_RE.finditer(request)]
    matches.extend((m, "sensitive") for m in _CASE_SENSITIVE_RE.finditer(request))
    for match, normalized in matches:
        _add(entities, request, "case_sensitivity", *match.span(), normalized)


def _extract_process_metrics(request: str, entities: list[ExtractedEntity]) -> None:
    """Extract explicit process resource metrics without guessing a process."""
    for _name, pattern, normalized in _PROCESS_METRIC_RES:
        for match in pattern.finditer(request):
            _add(entities, request, "process_metric", *match.span(), normalized)


def _extract_programming_languages(request: str, entities: list[ExtractedEntity]) -> None:
    """Recognize common language/file types and their conventional suffixes."""
    for match in _LANGUAGE_FILE_RE.finditer(request):
        name = match.group("language")
        extension = _LANGUAGE_EXTENSIONS.get(name.lower())
        if extension:
            _add(entities, request, "programming_language", *match.span("language"), extension)


def _extract_dates(request: str, entities: list[ExtractedEntity]) -> None:
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(request):
            _add(entities, request, "date_time", *match.span(), match.group(0).lower())


def _extract_comparisons(request: str, entities: list[ExtractedEntity]) -> None:
    for match in _COMPARISON_RE.finditer(request):
        value = match.group("v")
        normalized = _COMPARISON_MAP[value.lower()]
        _add(entities, request, "comparison_condition", *match.span("v"), normalized)


def _detect_size_conflicts(entities: list[ExtractedEntity], issues: list[ExtractionIssue]) -> None:
    sizes = sorted((e for e in entities if e.entity_type == "size"), key=lambda e: e.start)
    comps = [e for e in entities if e.entity_type == "comparison_condition"]
    lower, upper = [], []
    for size in sizes:
        near = [c for c in comps if c.end <= size.start and size.start - c.end <= 32]
        if not near or not size.normalized_value:
            continue
        comp = near[-1].normalized_value
        amount = int(size.normalized_value.split()[0])
        if comp in {"greater_than", "greater_than_or_equal"}:
            lower.append((amount, comp == "greater_than_or_equal", size))
        elif comp in {"less_than", "less_than_or_equal"}:
            upper.append((amount, comp == "less_than_or_equal", size))
    if not lower or not upper:
        return
    low = max(lower, key=lambda x: x[0])
    high = min(upper, key=lambda x: x[0])
    conflict = low[0] > high[0] or (low[0] == high[0] and not (low[1] and high[1]))
    if conflict:
        issues.append(ExtractionIssue(
            "conflicting_size_constraints",
            "the request contains incompatible lower and upper size limits",
            min(low[2].start, high[2].start), max(low[2].end, high[2].end),
        ))


def _detect_incomplete_size(
    request: str,
    entities: list[ExtractedEntity],
    issues: list[ExtractionIssue],
) -> None:
    if any(entity.entity_type == "size" for entity in entities):
        return
    unit = r"(?:bytes?|B|kB|KB|KiB|MB|MiB|GB|GiB|TB|TiB)"
    comparator = (
        r"(?:greater|larger|bigger|less|smaller|more)(?:\s+than)?|"
        r"at\s+least|at\s+most|above|below|over|under"
    )
    numeric_cue = re.search(
        rf"\b(?:files?|size)\b[^.?!]{{0,48}}\b(?:{comparator})\s+\d+(?!\s*{unit}\b)",
        request,
        re.I,
    )
    if numeric_cue:
        issues.append(ExtractionIssue(
            "missing_size_unit",
            "a numeric file-size limit is present but its unit is missing",
            numeric_cue.start(),
            numeric_cue.end(),
        ))
        return

    missing_value_cue = re.search(
        r"\b(?:files?|(?:file\s+)?size)\b[^.?!]{0,48}\b(?:"
        r"greater(?:\s+than)?|larger(?:\s+than)?|bigger(?:\s+than)?|"
        r"less(?:\s+than)?|smaller(?:\s+than)?|more\s+than|"
        r"at\s+least|at\s+most|equal(?:\s+to)?|above|below)\b",
        request,
        re.I,
    )
    if missing_value_cue:
        issues.append(ExtractionIssue(
            "missing_size_value",
            "the request describes a size condition but no explicit size value and unit were found",
            missing_value_cue.start(),
            missing_value_cue.end(),
        ))


def extract_entities(request: str) -> EntityExtractionResult:
    """Extract supported entities; do not normalize away their original values.

    Entity spans are offsets into ``result.request``. Overlapping spans are
    intentional when, for example, an extension occurs within a full path.
    Ambiguous or incomplete cues are reported in ``issues`` rather than filled
    with inferred values.
    """
    normalized = normalize_request(request)
    entities: list[ExtractedEntity] = []
    issues: list[ExtractionIssue] = []
    _extract_paths(normalized, entities)
    _extract_file_names(normalized, entities)
    _extract_extensions(normalized, entities)
    _extract_sizes(normalized, entities)
    _extract_ports(normalized, entities, issues)
    _extract_process_names(normalized, entities, issues)
    _extract_dates(normalized, entities)
    _extract_comparisons(normalized, entities)
    _extract_programming_languages(normalized, entities)
    _extract_process_metrics(normalized, entities)
    _extract_case_sensitivity(normalized, entities)
    _detect_size_conflicts(entities, issues)
    _detect_incomplete_size(normalized, entities, issues)
    entities.sort(key=lambda e: (e.start, e.end, e.entity_type))
    issues.sort(key=lambda i: ((i.start if i.start is not None else -1), i.code))
    return EntityExtractionResult(normalized, tuple(entities), tuple(issues))
