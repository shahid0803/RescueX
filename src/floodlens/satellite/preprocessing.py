from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

S2_CLOUD_CLASSES = (3, 8, 9, 10)
S2_INVALID_CLASSES = (1, 7, 11)


@dataclass
class PreprocessingConfig:
    analysis_crs: str = "auto"
    target_resolution: float | None = None
    clip_to_aoi: bool = True
    sentinel1_backscatter: str = "source_calibrated"
    sentinel1_terrain_correction: bool = False
    sentinel1_speckle_filter_enabled: bool = False
    sentinel2_bands: list[str] = field(default_factory=lambda: ["B02", "B03", "B04", "B08"])
    sentinel2_cloud_mask: bool = True
    sentinel2_scl_classes_to_mask: tuple[int, ...] = S2_CLOUD_CLASSES + S2_INVALID_CLASSES
    nodata_value: float = -9999.0
    resampling: str = "bilinear"


def sentinel1_metadata(config: PreprocessingConfig) -> dict[str, Any]:
    return {
        "backscatter_representation": config.sentinel1_backscatter,
        "terrain_correction": config.sentinel1_terrain_correction,
        "speckle_filter": {"enabled": config.sentinel1_speckle_filter_enabled},
        "limitation": "No calibration or terrain correction is claimed by the baseline reader.",
    }


def sentinel2_cloud_mask(scl: np.ndarray, classes: tuple[int, ...] = S2_CLOUD_CLASSES + S2_INVALID_CLASSES) -> np.ndarray:
    return np.isin(scl, classes)


def sentinel2_scale_reflectance(values: np.ndarray, scale_factor: float = 10000.0) -> np.ndarray:
    if scale_factor <= 0:
        raise ValueError("scale factor must be positive")
    output = values.astype("float32") / scale_factor
    output[~np.isfinite(output)] = np.nan
    return output


class PreparedRasterRef(BaseModel):
    path: str
    scene_id: str
    sensor: str
    role: str
    crs: str
    resolution: tuple[float, float]
    transform: tuple[float, ...]
    bounds: tuple[float, float, float, float]
    processing_version: str


class BeforeAfterRasterPair(BaseModel):
    before: PreparedRasterRef
    after: PreparedRasterRef
    alignment: dict[str, Any]
    processing: dict[str, Any]
    provenance: dict[str, Any]
