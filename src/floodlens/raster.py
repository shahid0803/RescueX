"""Georeferenced raster inspection, clipping, reprojection, alignment, and QC.

This module intentionally performs geometric preparation only. It does not
produce flood masks or claim image-to-image co-registration.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, transform_bounds
from shapely.geometry import mapping, shape

from .satellite.errors import IntegrityError

PIPELINE_VERSION = "0.2.0"


@dataclass(frozen=True)
class RasterMetadata:
    path: str
    width: int
    height: int
    count: int
    dtype: str
    crs: str
    transform: tuple[float, ...]
    bounds: tuple[float, float, float, float]
    resolution: tuple[float, float]
    nodata: float | int | None
    driver: str
    warnings: list[str]


@dataclass(frozen=True)
class QCReport:
    scene_id: str | None
    sensor: str | None
    crs: str
    bounds: tuple[float, float, float, float]
    resolution: tuple[float, float]
    width: int
    height: int
    bands: int
    nodata_fraction: float
    valid_pixel_fraction: float
    processing_steps: list[str]
    warnings: list[str]


def _require_rasterio() -> None:
    if rasterio is None:
        raise RuntimeError("rasterio is required for raster processing")


def inspect_raster(path: Path) -> RasterMetadata:
    with rasterio.open(path) as dataset:
        warnings: list[str] = []
        if dataset.crs is None:
            warnings.append("missing CRS")
        if dataset.nodata is None:
            warnings.append("nodata is not declared")
        if not dataset.transform:
            warnings.append("missing transform")
        return RasterMetadata(
            path=str(path),
            width=dataset.width,
            height=dataset.height,
            count=dataset.count,
            dtype=dataset.dtypes[0],
            crs=dataset.crs.to_string() if dataset.crs else "",
            transform=tuple(dataset.transform),
            bounds=tuple(dataset.bounds),
            resolution=tuple(dataset.res),
            nodata=dataset.nodata,
            driver=dataset.driver,
            warnings=warnings,
        )


def validate_raster_metadata(metadata: RasterMetadata) -> dict[str, Any]:
    errors = []
    if metadata.width <= 0 or metadata.height <= 0:
        errors.append("raster dimensions must be positive")
    if metadata.count <= 0:
        errors.append("raster must have at least one band")
    if not metadata.crs:
        errors.append("CRS is required")
    if any(not math.isfinite(value) for value in metadata.bounds):
        errors.append("bounds must be finite")
    if any(value <= 0 or not math.isfinite(value) for value in metadata.resolution):
        errors.append("resolution must be finite and positive")
    if not all(math.isfinite(value) for value in metadata.transform):
        errors.append("transform must be finite")
    return {
        "valid": not errors,
        "warnings": metadata.warnings,
        "errors": errors,
        "crs": metadata.crs,
        "bounds": metadata.bounds,
        "resolution": metadata.resolution,
        "width": metadata.width,
        "height": metadata.height,
        "bands": metadata.count,
    }


def clip_to_aoi(input_path: Path, output_path: Path, aoi_geometry: dict[str, Any]) -> RasterMetadata:
    with rasterio.open(input_path) as source:
        geometries = [mapping(shape(aoi_geometry))]
        clipped, transform = mask(source, geometries, crop=True, filled=True, nodata=source.nodata)
        profile = source.profile.copy()
        if not profile.get("tiled", False):
            for key in ("blockxsize", "blockysize"):
                profile.pop(key, None)
        profile.update(height=clipped.shape[1], width=clipped.shape[2], transform=transform)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".part")
        with rasterio.open(temporary, "w", **profile) as destination:
            destination.write(clipped)
            for index in range(1, source.count + 1):
                destination.set_band_description(index, source.descriptions[index - 1] or f"band_{index}")
        temporary.replace(output_path)
    return inspect_raster(output_path)


def reproject_raster(
    input_path: Path,
    output_path: Path,
    target_crs: str,
    resolution: float | None = None,
    resampling: Resampling = Resampling.bilinear,
) -> RasterMetadata:
    with rasterio.open(input_path) as source:
        transform, width, height = calculate_default_transform(
            source.crs, target_crs, source.width, source.height, *source.bounds,
            resolution=resolution,
        )
        profile = source.profile.copy()
        profile.update(crs=target_crs, transform=transform, width=width, height=height)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".part")
        with rasterio.open(temporary, "w", **profile) as destination:
            for band in range(1, source.count + 1):
                reproject(
                    source=rasterio.band(source, band),
                    destination=rasterio.band(destination, band),
                    src_transform=source.transform,
                    src_crs=source.crs,
                    dst_transform=transform,
                    dst_crs=target_crs,
                    resampling=resampling,
                    src_nodata=source.nodata,
                    dst_nodata=source.nodata,
                )
        temporary.replace(output_path)
    return inspect_raster(output_path)


def align_before_after(
    before_path: Path,
    after_path: Path,
    before_output: Path,
    after_output: Path,
    target_crs: str | None = None,
    resolution: float | None = None,
    categorical: bool = False,
) -> dict[str, Any]:
    before = inspect_raster(before_path)
    after = inspect_raster(after_path)
    if not before.crs or not after.crs:
        raise ValueError("both rasters must have CRS metadata")
    target_crs = target_crs or before.crs
    before_bounds = transform_bounds(before.crs, target_crs, *before.bounds)
    after_bounds = transform_bounds(after.crs, target_crs, *after.bounds)
    overlap = (
        max(before_bounds[0], after_bounds[0]),
        max(before_bounds[1], after_bounds[1]),
        min(before_bounds[2], after_bounds[2]),
        min(before_bounds[3], after_bounds[3]),
    )
    if overlap[0] >= overlap[2] or overlap[1] >= overlap[3]:
        raise ValueError("before and after rasters have no spatial overlap")
    with rasterio.open(before_path) as source:
        target_resolution = resolution or abs(source.res[0])
    from rasterio.transform import from_origin
    from rasterio.windows import from_bounds
    width = max(1, int(math.ceil((overlap[2] - overlap[0]) / target_resolution)))
    height = max(1, int(math.ceil((overlap[3] - overlap[1]) / target_resolution)))
    grid_transform = from_origin(overlap[0], overlap[3], target_resolution, target_resolution)
    resampling_method = Resampling.nearest if categorical else Resampling.bilinear
    for input_path, output_path in ((before_path, before_output), (after_path, after_output)):
        with rasterio.open(input_path) as source:
            profile = source.profile.copy()
            profile.update(
                crs=target_crs, transform=grid_transform, width=width, height=height,
                tiled=False,
            )
            profile.pop("blockxsize", None)
            profile.pop("blockysize", None)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = output_path.with_suffix(output_path.suffix + ".part")
            with rasterio.open(temporary, "w", **profile) as destination:
                for band in range(1, source.count + 1):
                    reproject(
                        source=rasterio.band(source, band),
                        destination=rasterio.band(destination, band),
                        src_transform=source.transform,
                        src_crs=source.crs,
                        dst_transform=grid_transform,
                        dst_crs=target_crs,
                        dst_width=width,
                        dst_height=height,
                        resampling=resampling_method,
                        src_nodata=source.nodata,
                        dst_nodata=source.nodata,
                    )
            temporary.replace(output_path)
    aligned_before = inspect_raster(before_output)
    aligned_after = inspect_raster(after_output)
    if aligned_before.transform != aligned_after.transform or (
        aligned_before.width, aligned_before.height
    ) != (aligned_after.width, aligned_after.height):
        raise ValueError("reprojected outputs do not share a common grid")
    return {
        "same_crs": aligned_before.crs == aligned_after.crs,
        "same_resolution": aligned_before.resolution == aligned_after.resolution,
        "same_transform": aligned_before.transform == aligned_after.transform,
        "same_dimensions": (aligned_before.width, aligned_before.height)
        == (aligned_after.width, aligned_after.height),
        "overlap_bounds": aligned_before.bounds,
        "resampling": "nearest" if categorical else "bilinear",
        "target_crs": target_crs,
        "target_resolution": target_resolution,
    }


def choose_analysis_crs(aoi_geometry: dict[str, Any], source_crs: str = "EPSG:4326") -> str:
    """Choose a UTM CRS from an AOI centroid; never assumes a country or zone."""
    geometry = shape(aoi_geometry)
    if source_crs.upper() != "EPSG:4326":
        return source_crs
    centroid = geometry.centroid
    zone = max(1, min(60, int((centroid.x + 180) / 6) + 1))
    epsg = 32600 + zone if centroid.y >= 0 else 32700 + zone
    return f"EPSG:{epsg}"


def qc_report(path: Path, scene_id: str | None = None, sensor: str | None = None,
              processing_steps: list[str] | None = None) -> QCReport:
    metadata = inspect_raster(path)
    with rasterio.open(path) as dataset:
        values = dataset.read(masked=True)
        total = values.size
        invalid = int(np.ma.count_masked(values))
        finite = np.isfinite(values.data).all(axis=0)
        valid = max(0, int(total - invalid - np.size(finite) + int(finite.sum())))
        nodata_fraction = invalid / total if total else 1.0
        valid_fraction = (total - invalid) / total if total else 0.0
        warnings = list(metadata.warnings)
        if valid_fraction == 0:
            warnings.append("zero valid pixels")
        if not np.isfinite(values.data).all():
            warnings.append("NaN or infinite values present")
    return QCReport(scene_id, sensor, metadata.crs, metadata.bounds, metadata.resolution,
                    metadata.width, metadata.height, metadata.count, nodata_fraction,
                    valid_fraction, processing_steps or [], warnings)


def write_qc(path: Path, report: QCReport) -> Path:
    output = path.with_suffix(path.suffix + ".qc.json")
    output.write_text(json.dumps(asdict(report), indent=2, default=str), encoding="utf-8")
    return output


def write_preview(path: Path, output_path: Path, band: int = 1) -> Path:
    with rasterio.open(path) as dataset:
        values = dataset.read(band, masked=True).filled(np.nan).astype("float32")
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise IntegrityError("cannot preview raster with no finite pixels")
    low, high = np.percentile(finite, [2, 98])
    scaled = np.clip((values - low) / max(high - low, 1e-12) * 255, 0, 255)
    Image.fromarray(np.nan_to_num(scaled, nan=0).astype("uint8")).save(output_path)
    return output_path
