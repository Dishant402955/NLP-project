"""Duplicate-aware grouping for parallel corpus records."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from nl2bash.corpus import CorpusRecord


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """Records connected by a shared request or reference command."""

    group_id: str
    records: tuple[CorpusRecord, ...]


def group_duplicate_records(
    records: Iterable[CorpusRecord],
) -> tuple[DuplicateGroup, ...]:
    """Group records sharing an exact request or command.

    Leading and trailing whitespace is ignored only when comparing duplicate
    keys. Internal whitespace, case, punctuation, and the stored source text
    are preserved. Duplicate links are transitive: if A shares a request with
    B and B shares a command with C, all three records belong to one group.

    Groups and records within each group retain first-occurrence input order.
    Every example ID must be unique so that group membership is auditable.
    """
    items = tuple(records)
    if not items:
        return ()

    seen_ids: set[str] = set()
    for record in items:
        if record.example_id in seen_ids:
            raise ValueError(f"duplicate example ID: {record.example_id}")
        seen_ids.add(record.example_id)

    parents = list(range(len(items)))
    sizes = [1] * len(items)

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if sizes[left_root] < sizes[right_root]:
            left_root, right_root = right_root, left_root
        parents[right_root] = left_root
        sizes[left_root] += sizes[right_root]

    first_request: dict[str, int] = {}
    first_command: dict[str, int] = {}

    for index, record in enumerate(items):
        request_key = record.request.strip()
        command_key = record.reference_command.strip()

        previous_request = first_request.setdefault(request_key, index)
        if previous_request != index:
            union(index, previous_request)

        previous_command = first_command.setdefault(command_key, index)
        if previous_command != index:
            union(index, previous_command)

    members_by_root: dict[int, list[CorpusRecord]] = {}
    for index, record in enumerate(items):
        members_by_root.setdefault(find(index), []).append(record)

    # Dict insertion order follows the first input occurrence of each group.
    ordered_groups = members_by_root.values()
    return tuple(
        DuplicateGroup(
            group_id=f"group-{group[0].example_id}",
            records=tuple(group),
        )
        for group in ordered_groups
    )
