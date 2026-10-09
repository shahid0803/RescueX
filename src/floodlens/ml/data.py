from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np


ALLOWED_TRAINING_DATASETS = {"kuro-siwo", "sen1floods11", "development-fixture"}
FORBIDDEN_DATASET_TOKENS = {"emsr", "unosat", "damage-map", "published-damage"}


def assert_training_dataset_is_allowed(dataset: str) -> None:
    normalized = dataset.lower().replace("_", "-")
    if any(token in normalized for token in FORBIDDEN_DATASET_TOKENS):
        raise ValueError(f"forbidden validation/damage source cannot be training data: {dataset}")
    if normalized not in ALLOWED_TRAINING_DATASETS:
        raise ValueError(f"training dataset is not registered: {dataset}")


@dataclass(frozen=True)
class SampleRecord:
    sample_id: str
    image_path: str
    mask_path: str
    scene_id: str
    region: str
    sensor: str = "sentinel-1"


@dataclass(frozen=True)
class DatasetManifest:
    name: str
    official_url: str
    source_revision: str | None
    license: str | None
    citation: str | None
    sensor: str
    local_path: str
    enabled: bool
    notes: str = ""

    def validate(self) -> None:
        assert_training_dataset_is_allowed(self.name)
        if self.enabled and not Path(self.local_path).exists():
            raise FileNotFoundError(f"enabled dataset path does not exist: {self.local_path}")


def dataset_manifest(name: str, local_path: str, enabled: bool = False) -> DatasetManifest:
    if name == "kuro-siwo":
        return DatasetManifest(
            name=name,
            official_url="https://github.com/Orion-AI-Lab/KuroSiwo",
            source_revision="main (inspected 2026-10-03)",
            license="CC BY (dataset statement); repository code LICENSE is MIT",
            citation="Bountos et al., NeurIPS 2024, Kuro Siwo",
            sensor="Sentinel-1 GRD",
            local_path=local_path,
            enabled=enabled,
            notes="No raw data is redistributed by RescueX.",
        )
    if name == "sen1floods11":
        return DatasetManifest(
            name=name,
            official_url="https://github.com/cloudtostreet/Sen1Floods11",
            source_revision="v1.1",
            license=None,
            citation="Bonafilia et al., CVPR Workshops 2020",
            sensor="Sentinel-1",
            local_path=local_path,
            enabled=enabled,
            notes="Optional and not enabled for the baseline.",
        )
    return DatasetManifest(
        name=name, official_url="internal", source_revision="fixture",
        license="internal", citation=None, sensor="synthetic",
        local_path=local_path, enabled=enabled,
    )


def write_manifest(path: Path, manifest: DatasetManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")


def inspect_samples(samples: Iterable[SampleRecord]) -> dict:
    records = list(samples)
    return {
        "sample_count": len(records),
        "scene_ids": sorted({record.scene_id for record in records}),
        "regions": sorted({record.region for record in records}),
        "missing_images": [r.sample_id for r in records if not Path(r.image_path).exists()],
        "missing_masks": [r.sample_id for r in records if not Path(r.mask_path).exists()],
        "label_semantics": {"0": "non-flood/background", "1": "flood/water target", "ignore": 255},
        "inspection_timestamp": datetime.now(timezone.utc).isoformat(),
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_kuro_siwo_grd_sample(sample_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load one official GRD sample into the Phase 3 array contract.

    The source mask is preserved with values 0/1/2.  The returned binary
    target is an explicit adapter view where only source class 2 is flood.
    """
    required = (
        "flood_vv.npy", "flood_vh.npy", "mask.npy", "valid_mask.npy",
        "info.json",
    )
    missing = [name for name in required if not (sample_path / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Kuro Siwo sample is missing fields: {missing}")
    vv = np.load(sample_path / "flood_vv.npy", allow_pickle=False)
    vh = np.load(sample_path / "flood_vh.npy", allow_pickle=False)
    source_mask = np.load(sample_path / "mask.npy", allow_pickle=False)
    valid_mask = np.load(sample_path / "valid_mask.npy", allow_pickle=False)
    if vv.shape != vh.shape or vv.shape != source_mask.shape or vv.shape != valid_mask.shape:
        raise ValueError("Kuro Siwo image, mask, and valid-mask shapes do not align")
    image = np.concatenate((vv, vh), axis=0).astype("float32", copy=False)
    binary_target = ((source_mask == 2) & (valid_mask == 1)).astype("float32", copy=False)
    return image, source_mask, binary_target
