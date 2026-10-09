"""Read-only QA and model-input compatibility audit for the real Sentinel-1 pair."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from PIL import Image, ImageDraw

from floodlens.satellite.process_api import build_grid, compare_raster_grids, validate_acquired_raster
from floodlens.satellite.models import AOI
from phase10d_acquire import AFTER_ID, BEFORE_ID, DEFAULT_AOI, DEFAULT_OUTPUT, MANIFEST, extract_geometry

PAIR_MANIFEST = Path("data/manifests/trishuli_sentinel1_pair_qa.json")
QA_IMAGE = Path("data/qa/sentinel1_trishuli_pair_qa.png")
REPORT = Path("PHASE11A_IMPLEMENTATION_REPORT.md")
BEFORE_SHA256 = "28e6dd9fef265db3ec4d203e5f7b80d2de06993455a4844f91625559275740fa"
AFTER_SHA256 = "c4df94426a9be90e5dcf20b7d14d09165880fd36ae85c0ef34dc9bf1c2663a2b"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def raster_stats(path: Path) -> dict[str, Any]:
    with rasterio.open(path) as dataset:
        arrays = dataset.read().astype("float64")
        result: dict[str, Any] = {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
            "crs": dataset.crs.to_string() if dataset.crs else None,
            "width": dataset.width,
            "height": dataset.height,
            "count": dataset.count,
            "dtypes": list(dataset.dtypes),
            "descriptions": list(dataset.descriptions),
            "resolution": list(dataset.res),
            "transform": list(dataset.transform),
            "bounds": list(dataset.bounds),
            "nodata": dataset.nodata,
            "bands": [],
        }
        for index, values in enumerate(arrays):
            finite = values[np.isfinite(values)]
            percentiles = np.percentile(finite, [1, 5, 25, 50, 75, 95, 99]).tolist() if finite.size else []
            histogram = None
            if finite.size:
                counts, edges = np.histogram(finite, bins=10)
                histogram = {
                    "edges": edges.tolist(),
                    "counts": counts.tolist(),
                }
            result["bands"].append({
                "band": index + 1,
                "label": dataset.descriptions[index] or f"band_{index + 1}",
                "finite_count": int(finite.size),
                "nonfinite_count": int(values.size - finite.size),
                "zero_count": int((finite == 0).sum()),
                "negative_count": int((finite < 0).sum()),
                "minimum": float(finite.min()) if finite.size else None,
                "maximum": float(finite.max()) if finite.size else None,
                "mean": float(finite.mean()) if finite.size else None,
                "stddev": float(finite.std()) if finite.size else None,
                "percentiles": {
                    str(p): float(v) for p, v in zip((1, 5, 25, 50, 75, 95, 99), percentiles)
                },
                "histogram_10_bins": histogram,
            })
        return result


def _preview(values: np.ndarray, size: tuple[int, int]) -> Image.Image:
    finite = values[np.isfinite(values)]
    if not finite.size:
        scaled = np.zeros(values.shape, dtype="uint8")
    else:
        low, high = np.percentile(finite, [1, 99])
        scaled = np.clip((values - low) / max(high - low, 1e-12) * 255, 0, 255)
        scaled[~np.isfinite(scaled)] = 0
        scaled = scaled.astype("uint8")
    return Image.fromarray(scaled, mode="L").resize(size)


def write_qa_image(paths: list[Path], output: Path) -> None:
    with rasterio.open(paths[0]) as before, rasterio.open(paths[1]) as after:
        arrays = [before.read(1), before.read(2), after.read(1), after.read(2)]
    tile = (480, 300)
    canvas = Image.new("RGB", (tile[0] * 2, (tile[1] + 24) * 2), "white")
    draw = ImageDraw.Draw(canvas)
    for index, (label, values) in enumerate(zip(("BEFORE VV", "BEFORE VH", "AFTER VV", "AFTER VH"), arrays)):
        x = (index % 2) * tile[0]
        y = (index // 2) * (tile[1] + 24)
        canvas.paste(_preview(values, tile).convert("RGB"), (x, y + 24))
        draw.text((x + 8, y + 5), label, fill="black")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG")


def model_contract() -> dict[str, Any]:
    checkpoint_manifest = Path("data/manifests/kuro_siwo_checkpoint_manifest.json")
    experiment_manifest = Path("data/manifests/kuro_siwo_training_experiment.json")
    checkpoint = json.loads(checkpoint_manifest.read_text(encoding="utf-8"))
    experiment = json.loads(experiment_manifest.read_text(encoding="utf-8"))
    sample_stats: dict[str, Any] = {}
    sample_root = Path("data/raw/kuro_siwo_streamed/train_GRD")
    samples = sorted(sample_root.glob("sample-*"))[:7]
    if samples:
        channels = []
        for name in ("flood_vv.npy", "flood_vh.npy"):
            values = np.concatenate([
                np.load(sample / name, allow_pickle=False).astype("float64").ravel()
                for sample in samples
            ])
            channels.append({
                "name": name,
                "minimum": float(values.min()),
                "maximum": float(values.max()),
                "mean": float(values.mean()),
                "stddev": float(values.std()),
            })
        sample_stats = {"sample_count": len(samples), "channels": channels}
    return {
        "architecture": checkpoint["model"]["architecture"],
        "input_channels": checkpoint["model"]["input_channels"],
        "channels": checkpoint["preprocessing"]["channels"],
        "normalization_mean": checkpoint["preprocessing"]["normalization_mean"],
        "normalization_std": checkpoint["preprocessing"]["normalization_std"],
        "checkpoint_sha256": checkpoint["sha256"],
        "training_dataset": experiment["source"],
        "training_sample_count": experiment["samples"]["training_count"],
        "evaluation_sample_count": experiment["samples"]["evaluation_count"],
        "label_conversion": experiment["label_conversion"],
        "valid_mask_required": "valid_mask==1" in checkpoint["label_conversion"],
        "sample_stats": sample_stats,
        "output_semantics": "one flood logit per pixel; sigmoid probability; threshold 0.5 in evaluation",
    }


def run() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    geometry = extract_geometry(json.loads(DEFAULT_AOI.read_text(encoding="utf-8")))
    aoi = AOI(geometry=geometry)
    grid = build_grid(aoi.geometry)
    paths = {
        "before": DEFAULT_OUTPUT / "before_vv_vh.tif",
        "after": DEFAULT_OUTPUT / "after_vv_vh.tif",
    }
    expected = {
        "before": (BEFORE_ID, BEFORE_SHA256),
        "after": (AFTER_ID, AFTER_SHA256),
    }
    rasters = {}
    for role, path in paths.items():
        scene_id, digest = expected[role]
        record = manifest["scenes"][role]
        if record.get("scene_id") != scene_id:
            raise ValueError(f"{role} scene provenance mismatch")
        if record.get("sha256") != digest:
            raise ValueError(f"{role} manifest hash mismatch")
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f"{role} production artifact hash mismatch")
        validation = validate_acquired_raster(path, aoi.geometry, scene_id, grid)
        if not validation["valid"]:
            raise ValueError(f"{role} strict validation failed: {validation['errors']}")
        rasters[role] = raster_stats(path)
    pair = compare_raster_grids(paths["before"], paths["after"])
    with rasterio.open(paths["before"]) as before, rasterio.open(paths["after"]) as after:
        before_data = before.read().astype("float64")
        after_data = after.read().astype("float64")
    difference = after_data - before_data
    pair["finite_consistency"] = int(np.isfinite(before_data).all(axis=0).sum())
    pair["either_nonfinite_pixels"] = int((~np.isfinite(before_data).all(axis=0) | ~np.isfinite(after_data).all(axis=0)).sum())
    pair["band_differences"] = [{
        "band": i + 1,
        "mean_change": float(np.nanmean(difference[i])),
        "stddev_change": float(np.nanstd(difference[i])),
        "mean_absolute_change": float(np.nanmean(np.abs(difference[i]))),
    } for i in range(2)]
    model = model_contract()
    # The checkpoint stores normalization for Kuro Siwo arrays, but no project
    # contract proves the Process API values share those units or scale.
    compatibility = {
        "status": "INDETERMINATE",
        "evidence": [
            "Band count/order and spatial dimensions match the two-channel FloodUNet contract.",
            "Kuro Siwo training used flood_vv/flood_vh arrays with checkpoint normalization means/stds.",
            "Phase 10D Sentinel values are Process API GAMMA0_ELLIPSOID FLOAT32 values; project code does not establish unit/scale equivalence to Kuro Siwo arrays.",
            "No valid-mask mapping for the Sentinel TIFF is established; nodata is undeclared.",
            "The checkpoint was trained on only 7 training and 5 held-out Kuro Siwo samples.",
        ],
        "inference_executed": False,
    }
    output = {
        "phase": "11A",
        "status": "REAL_EXECUTED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {"manifest": str(MANIFEST), "aoi": str(DEFAULT_AOI), "rasters": rasters},
        "pair": pair,
        "model_contract": model,
        "input_compatibility": compatibility,
        "qa_artifact": str(QA_IMAGE),
        "warnings": [
            "Nodata is undeclared; zero was not treated as nodata.",
            "Difference statistics are exploratory and not flood classification.",
        ],
        "not_executed": ["inference", "flood mask", "flood area", "OSM", "EMSR927", "connectivity"],
    }
    write_qa_image(list(paths.values()), QA_IMAGE)
    PAIR_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    PAIR_MANIFEST.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
