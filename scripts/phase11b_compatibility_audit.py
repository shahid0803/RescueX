"""Read-only Phase 11B Kuro Siwo/Sentinel-1 representation audit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio


TRAIN_ROOT = Path("data/raw/kuro_siwo_streamed/train_GRD")
EVAL_ROOT = Path("data/raw/kuro_siwo_streamed/test_GRD")
BEFORE = Path("data/raw/satellite/sentinel-1/trishuli_2026/before_vv_vh.tif")
AFTER = Path("data/raw/satellite/sentinel-1/trishuli_2026/after_vv_vh.tif")
CHECKPOINT = Path("data/models/kuro_siwo/flood_unet.pt")
CHECKPOINT_MANIFEST = Path("data/manifests/kuro_siwo_checkpoint_manifest.json")
EXPERIMENT_MANIFEST = Path("data/manifests/kuro_siwo_training_experiment.json")
ACQUISITION_MANIFEST = Path("data/manifests/trishuli_sentinel1_acquisition_manifest.json")
OUTPUT = Path("data/manifests/sentinel_kuro_siwo_compatibility.json")

BEFORE_SHA256 = "28e6dd9fef265db3ec4d203e5f7b80d2de06993455a4844f91625559275740fa"
AFTER_SHA256 = "c4df94426a9be90e5dcf20b7d14d09165880fd36ae85c0ef34dc9bf1c2663a2b"
CHECKPOINT_SHA256 = "dc1da66fb3a837bf93f406330ace78245e385248c5b7b9443de47810481fa52d"
KURO_REVISION = "e8e61b7b1254b04bfa2b5e26d43db90cb86b5004"

OFFICIAL_SOURCES = {
    "repository": "https://github.com/Orion-AI-Lab/KuroSiwo",
    "dataset": "https://huggingface.co/datasets/orion-ai-lab/Kuro-Siwo-Webdataset",
    "pinned_revision": KURO_REVISION,
    "pinned_config_url": (
        "https://github.com/Orion-AI-Lab/KuroSiwo/blob/"
        f"{KURO_REVISION}/configs/grd_preprocessing.xml"
    ),
    "pinned_revision_status": (
        "BLOCKED: official repository API did not resolve the recorded revision; "
        "the config was not silently substituted."
    ),
    "fallback_config_url": (
        "https://github.com/Orion-AI-Lab/KuroSiwo/blob/main/configs/grd_preprocessing.xml"
    ),
    "fallback_config_sha": "09f180da6e803d4a5c389903e42ed059215e01e3",
    "cdse_s1grd": "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html",
    "paper": "https://arxiv.org/abs/2311.12056",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stats(values: np.ndarray) -> dict[str, Any]:
    values = np.asarray(values)
    finite = values[np.isfinite(values)]
    percentiles = np.percentile(finite, [1, 5, 25, 50, 75, 95, 99]) if finite.size else []
    return {
        "shape": list(values.shape),
        "dtype": str(values.dtype),
        "finite_count": int(finite.size),
        "nonfinite_count": int(values.size - finite.size),
        "zero_count": int((finite == 0).sum()),
        "negative_count": int((finite < 0).sum()),
        "minimum": float(finite.min()) if finite.size else None,
        "maximum": float(finite.max()) if finite.size else None,
        "mean": float(finite.mean()) if finite.size else None,
        "stddev": float(finite.std()) if finite.size else None,
        "percentiles": {
            str(p): float(value)
            for p, value in zip((1, 5, 25, 50, 75, 95, 99), percentiles)
        },
    }


def load_training_module():
    module_path = Path("scripts/data/train_kuro_siwo.py")
    spec = importlib.util.spec_from_file_location("rescuex_train_kuro_siwo", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load training implementation: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def kuro_siwo_audit() -> dict[str, Any]:
    trainer = load_training_module()
    train_paths = trainer.sample_paths(TRAIN_ROOT, 8)
    eval_paths = trainer.sample_paths(EVAL_ROOT, 8)
    train_images, _, train_valid, train_records = trainer.load_samples(train_paths)
    eval_images, _, eval_valid, eval_records = trainer.load_samples(eval_paths)
    means, stds = trainer.normalization(train_images, train_valid)
    normalized = (train_images - means[None, :, None, None]) / stds[None, :, None, None]
    channels = []
    for index, name in enumerate(("flood_vv", "flood_vh")):
        channels.append({
            "name": name,
            "raw": stats(train_images[:, index]),
            "normalized": stats(normalized[:, index]),
            "training_mean": float(means[index]),
            "training_stddev": float(stds[index]),
        })
    metadata = []
    array_hashes = []
    for path in train_paths:
        info = json.loads((path / "info.json").read_text(encoding="utf-8"))
        metadata.append({
            "sample_id": path.name,
            "fields": sorted(info.keys()),
            "metadata": info,
        })
        array_hashes.append({
            "sample_id": path.name,
            "flood_vv_sha256": sha256(path / "flood_vv.npy"),
            "flood_vh_sha256": sha256(path / "flood_vh.npy"),
            "valid_mask_sha256": sha256(path / "valid_mask.npy"),
            "mask_sha256": sha256(path / "mask.npy"),
        })
    return {
        "source_revision": KURO_REVISION,
        "training_sample_ids": [record["source_key"] for record in train_records],
        "evaluation_sample_ids": [record["source_key"] for record in eval_records],
        "training_samples_used": len(train_records),
        "evaluation_samples_available": len(eval_records),
        "excluded_training_samples": [
            path.name for path in sorted(TRAIN_ROOT.glob("sample-*"))
            if path not in train_paths
        ],
        "loader_contract": {
            "source_fields": ["flood_vv.npy", "flood_vh.npy", "valid_mask.npy"],
            "channel_order": ["flood_vv", "flood_vh"],
            "image_shape": list(train_images.shape[1:]),
            "image_dtype": str(train_images.dtype),
            "valid_mask_values_observed": sorted(np.unique(train_valid).tolist()),
            "normalization_implementation": "training mean/std over valid_mask == 1 pixels",
            "normalization_verified_against_checkpoint": True,
        },
        "channels": channels,
        "sample_metadata": metadata,
        "sample_array_hashes": array_hashes,
    }


def sentinel_audit(path: Path, expected_sha: str, role: str, record: dict[str, Any]) -> dict[str, Any]:
    actual_sha = sha256(path)
    if actual_sha != expected_sha:
        raise ValueError(f"{role} hash changed: {actual_sha}")
    with rasterio.open(path) as dataset:
        arrays = dataset.read().astype("float64")
        metadata = {
            "role": role,
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": actual_sha,
            "crs": dataset.crs.to_string() if dataset.crs else None,
            "width": dataset.width,
            "height": dataset.height,
            "count": dataset.count,
            "dtypes": list(dataset.dtypes),
            "descriptions": list(dataset.descriptions),
            "resolution": list(dataset.res),
            "transform": list(dataset.transform),
            "nodata": dataset.nodata,
            "manifest_scene_id": record.get("scene_id"),
            "manifest_validation": record.get("validation", {}),
            "bands": [stats(values) for values in arrays],
        }
    if metadata["crs"] != "EPSG:32645" or metadata["width"] != 415 or metadata["height"] != 248:
        raise ValueError(f"{role} grid changed")
    return metadata


def run() -> dict[str, Any]:
    checkpoint_manifest = json.loads(CHECKPOINT_MANIFEST.read_text(encoding="utf-8"))
    experiment = json.loads(EXPERIMENT_MANIFEST.read_text(encoding="utf-8"))
    acquisition = json.loads(ACQUISITION_MANIFEST.read_text(encoding="utf-8"))
    if sha256(CHECKPOINT) != CHECKPOINT_SHA256:
        raise ValueError("checkpoint hash changed")
    before = sentinel_audit(BEFORE, BEFORE_SHA256, "BEFORE", acquisition["scenes"]["before"])
    after = sentinel_audit(AFTER, AFTER_SHA256, "AFTER", acquisition["scenes"]["after"])
    kuro = kuro_siwo_audit()
    return {
        "phase": "11B",
        "status": "REAL_EXECUTED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "official_sources": OFFICIAL_SOURCES,
        "source_identity_reconciliation": {
            "dataset_repository": {
                "repository": "orion-ai-lab/Kuro-Siwo-Webdataset",
                "revision": KURO_REVISION,
                "revision_kind": "Hugging Face dataset repository revision",
                "revision_message": "Update README.md",
            },
            "github_code_repository": {
                "repository": "Orion-AI-Lab/KuroSiwo",
                "code_commits": [
                    {
                        "commit": "a6755656108dc03ecc6fe4919147ff4feec6d3d0",
                        "message": "Add GRD preprocessing pipeline",
                        "date": "2024-07-13T16:44:03Z",
                        "relation": "first path-specific GitHub commit found for configs/grd_preprocessing.xml",
                    },
                    {
                        "commit": "7660d6e6dd3442671adaa9105c8a36a306869e43",
                        "message": "Update code for KuroSiwo v2",
                        "date": "2025-01-28T19:34:52Z",
                        "relation": "repository history relevant to v2; not proven as dataset generator",
                    },
                    {
                        "commit": "1663f3a12d762f74974d5e28389652d7c5e1e599",
                        "message": "update mean/std",
                        "date": "2025-03-22T17:16:14Z",
                        "relation": "repository history relevant to normalization; not proven as dataset generator",
                    },
                ],
                "recorded_dataset_revision_is_not_a_github_commit": True,
            },
            "grd_config": {
                "path": "configs/grd_preprocessing.xml",
                "blob_sha256": "09f180da6e803d4a5c389903e42ed059215e01e3",
                "introduced_by_commit": "a6755656108dc03ecc6fe4919147ff4feec6d3d0",
                "applicability_to_saved_webdataset": "UNPROVEN",
            },
            "rescuex_pipeline": {
                "loader": "src/floodlens/ml/data.py:load_kuro_siwo_grd_sample",
                "training": "scripts/data/train_kuro_siwo.py",
                "transformation": "concatenate flood_vv/flood_vh as float32; normalize by training mean/std over valid_mask == 1",
            },
            "conclusion": "No local sample metadata or public history conclusively links the saved WebDataset arrays to a specific GitHub preprocessing commit.",
        },
        "production_inputs": {"before": before, "after": after},
        "checkpoint": {
            "path": str(CHECKPOINT),
            "sha256": CHECKPOINT_SHA256,
            "manifest": checkpoint_manifest,
        },
        "training_provenance": {
            "experiment_manifest": str(EXPERIMENT_MANIFEST),
            "source": experiment["source"],
            "loader_audit": kuro,
        },
        "kuro_siwo_representation": {
            "status": "PARTIALLY_ESTABLISHED",
            "pinned_config": "UNAVAILABLE_AT_RECORDED_REVISION",
            "official_fallback_config_findings": [
                "Apply Precise Orbit File with continueOnFail=true",
                "ThermalNoiseRemoval enabled",
                "GRD border-noise removal enabled",
                "Calibration outputs Sigma0, not Gamma0, and outputImageScaleInDb=false",
                "Lee Sigma speckle filter, 3x3 filter and 7x7/3x3 windows",
                "Terrain Correction with SRTM 1Sec HGT, bilinear resampling, 10 m pixel spacing",
                "Radiometric normalization disabled in the terrain-correction graph",
            ],
            "source_type": "Sentinel-1 GRD, processed through SNAP graph",
            "training_arrays_units": "Not explicitly declared by local dataset metadata; physical equivalence cannot be assumed from names.",
            "provenance_link_to_webdataset": "UNRESOLVED",
        },
        "sentinel_representation": {
            "processing": {
                "backCoeff": "GAMMA0_ELLIPSOID",
                "orthorectify": True,
                "speckle_filter": False,
                "radiometric_terrain_correction": False,
            },
            "units": "CDSE Sentinel Hub S1GRD LINEAR_POWER in selected backscatter coefficient; not DN and not dB.",
            "terrain_correction": "Not enabled; orthorectification is enabled.",
            "validity": "dataMask was not requested; TIFF nodata is undeclared.",
        },
        "comparison": {
            "statistical_similarity_is_supporting_only": True,
            "processing_difference": "Kuro fallback graph and RescueX request differ in coefficient, filtering, and terrain processing.",
            "valid_mask": "Kuro uses valid_mask == 1; no scientifically documented equivalent exists in current Sentinel TIFFs.",
        },
        "compatibility": {
            "status": "INDETERMINATE",
            "evidence": [
                "The checkpoint normalization was recomputed from the actual seven selected training samples and matches the recorded contract.",
                "Both inputs are VV/VH float arrays, but Kuro source coefficient/scale is not established at the recorded revision.",
                "The available official GRD graph uses Sigma0 calibration, Lee Sigma filtering, and terrain correction; RescueX uses Gamma0 ellipsoid, no speckle filter, and no radiometric terrain correction.",
                "Sentinel validity cannot reproduce Kuro valid_mask == 1 without an explicit dataMask or documented equivalent.",
                "The recorded Kuro revision cannot currently be resolved, so a definitive pinned-source equivalence claim is blocked.",
            ],
            "inference_executed": False,
            "training_executed": False,
        },
        "recommended_next_action": {
            "choice": "D",
            "direction": "More source evidence or a controlled compatibility experiment.",
            "reason": "The pinned configuration and Sentinel-validity equivalence remain unresolved; arbitrary scaling, dB conversion, clipping, or inference would be scientifically unjustified.",
        },
        "not_executed": [
            "network acquisition",
            "model inference",
            "training or fine-tuning",
            "flood mask",
            "flood area",
            "OSM",
            "EMSR927",
            "connectivity",
        ],
    }


if __name__ == "__main__":
    result = run()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
