"""Deterministic train, development, and test splitting."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from collections.abc import Sequence

from nl2bash.corpus import CorpusRecord
from nl2bash.grouping import DuplicateGroup


@dataclass(frozen=True, slots=True)
class DatasetSplits:
    """Records assigned to partitions and the group-level assignments."""

    train: tuple[CorpusRecord, ...]
    dev: tuple[CorpusRecord, ...]
    test: tuple[CorpusRecord, ...]
    group_assignments: tuple[tuple[str, str], ...]

    def records_by_split(self) -> dict[str, tuple[CorpusRecord, ...]]:
        """Return a new mapping in the canonical train/dev/test order."""
        return {"train": self.train, "dev": self.dev, "test": self.test}


def _validate_groups(groups: Sequence[DuplicateGroup]) -> None:
    group_ids: set[str] = set()
    example_ids: set[str] = set()
    request_owner: dict[str, str] = {}
    command_owner: dict[str, str] = {}

    for group in groups:
        if not group.records:
            raise ValueError(f"duplicate group {group.group_id} is empty")
        if group.group_id in group_ids:
            raise ValueError(f"duplicate group ID: {group.group_id}")
        group_ids.add(group.group_id)

        for record in group.records:
            if record.example_id in example_ids:
                raise ValueError(f"duplicate example ID: {record.example_id}")
            example_ids.add(record.example_id)

            request_key = record.request.strip()
            command_key = record.reference_command.strip()
            prior_group = request_owner.setdefault(request_key, group.group_id)
            if prior_group != group.group_id:
                raise ValueError(
                    "duplicate request appears in multiple groups: "
                    f"{record.example_id}"
                )
            prior_group = command_owner.setdefault(command_key, group.group_id)
            if prior_group != group.group_id:
                raise ValueError(
                    "duplicate reference command appears in multiple groups: "
                    f"{record.example_id}"
                )


def split_duplicate_groups(
    groups: Sequence[DuplicateGroup],
    *,
    seed: int = 42,
    train_ratio: float = 0.8,
    dev_ratio: float = 0.1,
    test_ratio: float = 0.1,
) -> DatasetSplits:
    """Assign whole duplicate groups to deterministic data partitions.

    Groups are shuffled with a private seeded random generator, then stably
    ordered from largest to smallest. Each group is assigned to the split
    that most reduces the normalized squared deviation from its target record
    count. Output records retain the input group order and each group's
    internal record order.

    Split percentages are approximate because duplicate groups are
    indivisible. Group integrity takes priority over exact percentages.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")

    ratios = {"train": train_ratio, "dev": dev_ratio, "test": test_ratio}
    for name, ratio in ratios.items():
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
            raise TypeError(f"{name}_ratio must be a number")
        if not math.isfinite(ratio) or ratio <= 0:
            raise ValueError(f"{name}_ratio must be finite and greater than zero")
    if not math.isclose(sum(ratios.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("train_ratio, dev_ratio, and test_ratio must sum to 1.0")

    items = tuple(groups)
    _validate_groups(items)
    if not items:
        raise ValueError("at least one duplicate group is required")

    total_records = sum(len(group.records) for group in items)
    targets = {
        name: total_records * ratio for name, ratio in ratios.items()
    }
    assigned_records = {name: 0 for name in ratios}

    shuffled_groups = list(items)
    random.Random(seed).shuffle(shuffled_groups)
    shuffled_groups.sort(key=lambda group: len(group.records), reverse=True)

    assignment: dict[str, str] = {}
    split_order = tuple(ratios)
    for group in shuffled_groups:
        group_size = len(group.records)

        def incremental_cost(split_name: str) -> float:
            target = targets[split_name]
            current = assigned_records[split_name]
            before = ((current - target) / target) ** 2
            after = ((current + group_size - target) / target) ** 2
            return after - before

        destination = min(split_order, key=incremental_cost)
        assignment[group.group_id] = destination
        assigned_records[destination] += group_size

    records_by_split: dict[str, list[CorpusRecord]] = {
        name: [] for name in ratios
    }
    for group in items:
        destination = assignment[group.group_id]
        records_by_split[destination].extend(group.records)

    return DatasetSplits(
        train=tuple(records_by_split["train"]),
        dev=tuple(records_by_split["dev"]),
        test=tuple(records_by_split["test"]),
        group_assignments=tuple(
            (group.group_id, assignment[group.group_id]) for group in items
        ),
    )
