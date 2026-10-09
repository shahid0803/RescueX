from __future__ import annotations

import random
from dataclasses import dataclass

from .data import SampleRecord


@dataclass(frozen=True)
class DatasetSplit:
    train: list[SampleRecord]
    validation: list[SampleRecord]
    test: list[SampleRecord]
    split_version: str = "scene-region-v1"


def geographic_split(
    samples: list[SampleRecord], seed: int = 42, train_fraction: float = 0.7, validation_fraction: float = 0.15
) -> DatasetSplit:
    groups: dict[str, list[SampleRecord]] = {}
    for sample in samples:
        groups.setdefault(sample.region or sample.scene_id, []).append(sample)
    regions = list(groups)
    random.Random(seed).shuffle(regions)
    train_count = max(1, int(len(regions) * train_fraction)) if regions else 0
    val_count = max(0, int(len(regions) * validation_fraction))
    train_regions = set(regions[:train_count])
    val_regions = set(regions[train_count:train_count + val_count])
    return DatasetSplit(
        train=[s for s in samples if (s.region or s.scene_id) in train_regions],
        validation=[s for s in samples if (s.region or s.scene_id) in val_regions],
        test=[s for s in samples if (s.region or s.scene_id) not in train_regions | val_regions],
    )
