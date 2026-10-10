"""Bounded, exact-scene Sentinel-1 acquisition through the CDSE Process API."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

import rasterio
import numpy as np
from rasterio.warp import transform_bounds
from rasterio.warp import transform_geom
from shapely.geometry import shape

from .auth import CopernicusAuthenticator
from .errors import (
    CatalogAmbiguousError,
    CatalogNoMatchError,
    CatalogUnavailableError,
    CatalogValidationError,
    DownloadError,
    IntegrityError,
    ProcessAPIAuthError,
    ProcessAPIRequestError,
)
from ..raster import inspect_raster, qc_report, validate_raster_metadata

PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"
PROCESS_CRS_URI = "http://www.opengis.net/def/crs/EPSG/0/{epsg}"
STAC_SEARCH_URL = "https://stac.dataspace.copernicus.eu/v1/search"
MAX_STORAGE_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class AcquisitionGrid:
    crs: str
    resolution_m: float
    width: int
    height: int
    bounds: tuple[float, float, float, float]

    @property
    def expected_bytes(self) -> int:
        return self.width * self.height * 2 * 4

    @property
    def transform(self) -> tuple[float, ...]:
        from rasterio.transform import from_bounds

        return tuple(from_bounds(*self.bounds, self.width, self.height))


def build_grid(aoi_geometry: dict[str, Any], crs: str = "EPSG:32645", resolution_m: float = 20.0) -> AcquisitionGrid:
    if resolution_m <= 0:
        raise ValueError("resolution must be positive")
    source = shape(aoi_geometry)
    bounds = transform_bounds("EPSG:4326", crs, *source.bounds, densify_pts=21)
    width = max(1, int((bounds[2] - bounds[0] + resolution_m - 1e-9) // resolution_m))
    height = max(1, int((bounds[3] - bounds[1] + resolution_m - 1e-9) // resolution_m))
    bounded = (bounds[0], bounds[1], bounds[0] + width * resolution_m, bounds[1] + height * resolution_m)
    return AcquisitionGrid(crs, resolution_m, width, height, bounded)


def _crs_uri(crs: str) -> str:
    return PROCESS_CRS_URI.format(epsg=crs.split(":")[-1])


def build_process_payload(
    scene_id: str,
    aoi_geometry: dict[str, Any],
    grid: AcquisitionGrid,
    acquisition_start: datetime,
    acquisition_end: datetime,
) -> dict[str, Any]:
    if acquisition_start.tzinfo is None or acquisition_end.tzinfo is None:
        raise ValueError("acquisition window must be timezone-aware")
    if acquisition_start >= acquisition_end:
        raise ValueError("acquisition window must be ordered")
    # The AOI determines the grid in build_grid; request the complete grid
    # bounds so the service cannot fit the fixed dimensions to the AOI extent.
    bounds = grid.bounds
    return {
        "input": {
            "bounds": {"bbox": list(bounds), "properties": {"crs": _crs_uri(grid.crs)}},
            "data": [{
                "type": "sentinel-1-grd",
                "dataFilter": {
                    "timeRange": {
                        "from": acquisition_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "to": acquisition_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    },
                    "acquisitionMode": "IW",
                    "orbitDirection": "ASCENDING",
                    "polarization": "DV",
                },
                "processing": {"backCoeff": "GAMMA0_ELLIPSOID", "orthorectify": True},
            }],
        },
        "output": {
            "width": grid.width,
            "height": grid.height,
            "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
            "parameters": {"crs": _crs_uri(grid.crs)},
        },
        "evalscript": """//VERSION=3
function setup() {
  return {input: [{bands: ["VV", "VH"]}], output: {bands: 2, sampleType: "FLOAT32"}};
}
function evaluatePixel(sample) { return [sample.VV, sample.VH]; }
""",
    }


def build_candidate_process_payload(
    scene_id: str,
    aoi_geometry: dict[str, Any],
    grid: AcquisitionGrid,
    acquisition_start: datetime,
    acquisition_end: datetime,
) -> dict[str, Any]:
    """Build the isolated Phase 11D Sigma0/LEE candidate request.

    CDSE's Process API ``LEE`` filter is intentionally recorded as distinct
    from Kuro Siwo's SNAP Lee Sigma graph; this payload does not claim they
    are equivalent.
    """
    payload = build_process_payload(
        scene_id, aoi_geometry, grid, acquisition_start, acquisition_end
    )
    data = payload["input"]["data"][0]
    data["processing"] = {
        "backCoeff": "SIGMA0_ELLIPSOID",
        "orthorectify": True,
        "speckleFilter": {"type": "LEE", "windowSizeX": 3, "windowSizeY": 3},
    }
    payload["evalscript"] = """//VERSION=3
function setup() {
  return {
    input: [{bands: ["VV", "VH", "dataMask"]}],
    output: {bands: 3, sampleType: "FLOAT32"}
  };
}
function evaluatePixel(sample) {
  return [sample.VV, sample.VH, sample.dataMask];
}
"""
    return payload


def validate_candidate_raster(
    path: Path,
    aoi_geometry: dict[str, Any],
    scene_id: str,
    grid: AcquisitionGrid,
) -> dict[str, Any]:
    """Validate VV, VH and dataMask candidate output without touching production."""
    metadata = inspect_raster(path)
    result = validate_raster_metadata(metadata)
    with rasterio.open(path) as dataset:
        values = dataset.read()
        finite = values[np.isfinite(values)] if values.size else values
        aoi_projected = shape(transform_geom("EPSG:4326", dataset.crs, aoi_geometry))
        raster_bounds = shape({
            "type": "Polygon",
            "coordinates": [[
                [dataset.bounds.left, dataset.bounds.bottom],
                [dataset.bounds.right, dataset.bounds.bottom],
                [dataset.bounds.right, dataset.bounds.top],
                [dataset.bounds.left, dataset.bounds.top],
                [dataset.bounds.left, dataset.bounds.bottom],
            ]],
        })
        result.update({
            "scene_id": scene_id,
            "path": str(path),
            "dtype": list(dataset.dtypes),
            "band_descriptions": list(dataset.descriptions),
            "nodata": dataset.nodata,
            "finite_pixel_count": int(finite.size),
            "data_mask_values": sorted(np.unique(values[2]).tolist()) if dataset.count == 3 else [],
            "aoi_intersects": bool(raster_bounds.intersects(aoi_projected)),
            "coverage_fraction": float(
                raster_bounds.intersection(aoi_projected).area / max(aoi_projected.area, 1e-12)
            ),
            "expected_grid": {
                "crs": grid.crs,
                "resolution_m": grid.resolution_m,
                "width": grid.width,
                "height": grid.height,
            },
        })
        if dataset.count != 3 or list(dataset.descriptions) != ["VV", "VH", "dataMask"]:
            result["valid"] = False
            result["errors"].append("expected VV, VH, dataMask bands in that order")
        expected_transform = grid.transform
        actual_transform = tuple(dataset.transform)
        if dataset.width != grid.width or dataset.height != grid.height:
            result["valid"] = False
            result["errors"].append(
                f"expected {grid.width}x{grid.height} raster dimensions"
            )
        if dataset.crs is None or dataset.crs.to_string() != grid.crs:
            result["valid"] = False
            result["errors"].append(f"expected CRS {grid.crs}")
        if (
            not math.isclose(abs(dataset.res[0]), grid.resolution_m, rel_tol=0, abs_tol=1e-6)
            or not math.isclose(abs(dataset.res[1]), grid.resolution_m, rel_tol=0, abs_tol=1e-6)
        ):
            result["valid"] = False
            result["errors"].append(f"expected {grid.resolution_m} m pixel size")
        if any(
            not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-6)
            for actual, expected in zip(actual_transform, expected_transform)
        ):
            result["valid"] = False
            result["errors"].append("raster transform does not match expected grid")
        if any(dtype != "float32" for dtype in dataset.dtypes):
            result["valid"] = False
            result["errors"].append("expected three FLOAT32 bands")
        if dataset.count == 3 and np.any(~np.isin(values[2], [0.0, 1.0])):
            result["valid"] = False
            result["errors"].append("dataMask contains values other than 0 and 1")
        if finite.size == 0:
            result["valid"] = False
            result["errors"].append("candidate contains no finite pixels")
        if not result["aoi_intersects"]:
            result["valid"] = False
            result["errors"].append("candidate does not intersect the AOI")
    return result


def verify_stac_candidate(
    aoi_geometry: dict[str, Any],
    expected_scene_id: str,
    acquisition_start: datetime,
    acquisition_end: datetime,
    opener: Callable[..., Any] = urlopen,
    endpoint: str = STAC_SEARCH_URL,
) -> dict[str, Any]:
    """Require one matching public STAC acquisition before Process API use."""
    target = shape(aoi_geometry)
    query = {
        "collections": ["sentinel-1-grd"],
        "bbox": list(target.bounds),
        "datetime": (
            acquisition_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            + "/"
            + acquisition_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "limit": 100,
    }
    request = Request(
        endpoint,
        data=json.dumps(query).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/geo+json"},
        method="POST",
    )
    try:
        with opener(request, timeout=60) as response:
            document = json.loads(response.read())
    except Exception as exc:
        raise CatalogUnavailableError("CDSE STAC catalogue transport failed") from exc
    if not isinstance(document, dict) or not isinstance(document.get("features"), list):
        raise CatalogUnavailableError("CDSE STAC response was not a FeatureCollection")
    features = document["features"]
    expected_datetime = acquisition_start.astimezone(timezone.utc).replace(microsecond=0)
    distinct_acquisitions = {
        feature.get("properties", {}).get("datetime")
        for feature in features
        if feature.get("properties", {}).get("datetime")
    }
    if not features:
        error = CatalogNoMatchError("STAC catalogue returned zero items")
        error.item_count = 0
        raise error
    if len(features) > 1:
        error = CatalogAmbiguousError(
            f"STAC catalogue returned {len(features)} items for the narrow window"
        )
        error.item_count = len(features)
        raise error
    feature = features[0]
    properties = feature.get("properties", {})
    assets = feature.get("assets", {})
    footprint = feature.get("geometry")
    actual_datetime = properties.get("datetime")
    try:
        actual_datetime_value = datetime.fromisoformat(actual_datetime.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        error = CatalogValidationError("STAC item has an invalid acquisition timestamp")
        error.item_count = 1
        raise error from exc
    actual_datetime_value = actual_datetime_value.astimezone(timezone.utc)
    matches = []
    if (
        feature.get("id") == expected_scene_id
        and actual_datetime_value.replace(microsecond=0) == expected_datetime
        and properties.get("platform") == "sentinel-1d"
        and properties.get("sar:instrument_mode") == "IW"
        and properties.get("sat:orbit_state") == "ascending"
        and properties.get("sat:relative_orbit") == 85
        and set(properties.get("sar:polarizations", [])) >= {"VV", "VH"}
        and footprint
        and shape(footprint).intersects(target)
        and all(name.lower() in {key.lower() for key in assets} for name in ("VV", "VH"))
    ):
        matches.append(feature)
    if len(matches) != 1:
        error = CatalogValidationError("STAC item failed expected scene metadata validation")
        error.item_count = 1
        raise error
    return {
        "status": "VERIFIED_UNIQUE",
        "expected_scene_id": expected_scene_id,
        "returned_scene_ids": [feature.get("id") for feature in features],
        "distinct_acquisition_count": len(distinct_acquisitions),
        "query": query,
    }


def validate_acquired_raster(
    path: Path,
    aoi_geometry: dict[str, Any],
    scene_id: str,
    grid: AcquisitionGrid,
) -> dict[str, Any]:
    metadata = inspect_raster(path)
    result = validate_raster_metadata(metadata)
    with rasterio.open(path) as dataset:
        values = dataset.read(masked=True)
        finite = values.compressed()
        aoi_projected = shape(transform_geom("EPSG:4326", dataset.crs, aoi_geometry))
        raster_bounds = shape({
            "type": "Polygon",
            "coordinates": [[
                [dataset.bounds.left, dataset.bounds.bottom],
                [dataset.bounds.right, dataset.bounds.bottom],
                [dataset.bounds.right, dataset.bounds.top],
                [dataset.bounds.left, dataset.bounds.top],
                [dataset.bounds.left, dataset.bounds.bottom],
            ]],
        })
        coverage = raster_bounds.intersection(aoi_projected).area / max(aoi_projected.area, 1e-12)
        result.update({
            "scene_id": scene_id,
            "path": str(path),
            "dtype": list(dataset.dtypes),
            "band_descriptions": list(dataset.descriptions),
            "nodata": dataset.nodata,
            "finite_pixel_count": int(finite.size),
            "aoi_intersects": bool(raster_bounds.intersects(aoi_projected)),
            "coverage_fraction": float(coverage),
            "expected_grid": {
                "crs": grid.crs,
                "resolution_m": grid.resolution_m,
                "width": grid.width,
                "height": grid.height,
            },
        })
        expected_transform = grid.transform
        actual_transform = tuple(dataset.transform)
        if dataset.width != grid.width or dataset.height != grid.height:
            result["valid"] = False
            result["errors"].append(
                f"expected {grid.width}x{grid.height} raster dimensions"
            )
        if dataset.crs is None or dataset.crs.to_string() != grid.crs:
            result["valid"] = False
            result["errors"].append(f"expected CRS {grid.crs}")
        if (
            not math.isclose(abs(dataset.res[0]), grid.resolution_m, rel_tol=0, abs_tol=1e-6)
            or not math.isclose(abs(dataset.res[1]), grid.resolution_m, rel_tol=0, abs_tol=1e-6)
        ):
            result["valid"] = False
            result["errors"].append(f"expected {grid.resolution_m} m pixel size")
        if list(dataset.descriptions) != ["VV", "VH"]:
            result["valid"] = False
            result["errors"].append("expected VV/VH band descriptions")
        if any(
            not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-6)
            for actual, expected in zip(actual_transform, expected_transform)
        ):
            result["valid"] = False
            result["errors"].append("raster transform does not match expected grid")
        if dataset.count != 2 or any(dtype != "float32" for dtype in dataset.dtypes):
            result["valid"] = False
            result["errors"].append("expected two FLOAT32 VV/VH bands")
        if finite.size == 0:
            result["valid"] = False
            result["errors"].append("raster contains no finite pixels")
        if not result["aoi_intersects"]:
            result["valid"] = False
            result["errors"].append("raster does not intersect the AOI")
    return result


class ProcessAPIClient:
    def __init__(self, authenticator: CopernicusAuthenticator, endpoint: str = PROCESS_URL,
                 opener: Callable[..., Any] = urlopen):
        self.authenticator = authenticator
        self.endpoint = endpoint
        self.opener = opener

    def request_raster(self, scene_id: str, payload: dict[str, Any]) -> bytes:
        token = self.authenticator.get_token()
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=180) as response:
                self.last_response_content_type = getattr(response, "headers", {}).get("Content-Type")
                content = response.read()
        except Exception as exc:
            diagnostics = _request_failure_diagnostics(exc, self.endpoint)
            if getattr(exc, "code", None) in (401, 403):
                error = ProcessAPIAuthError(f"Process API authorization failed (HTTP {exc.code})")
                error.diagnostics = diagnostics
                raise error from exc
            raise ProcessAPIRequestError(
                f"Process API acquisition failed for {scene_id}", diagnostics
            ) from exc
        if not content:
            raise IntegrityError(f"Process API returned an empty raster for {scene_id}")
        return content


def _request_failure_diagnostics(exc: Exception, endpoint: str) -> dict[str, Any]:
    """Return bounded, credential-free diagnostics for an HTTP/request failure."""
    diagnostics: dict[str, Any] = {
        "stage": "http_submission_or_response",
        "endpoint": endpoint,
        "http_status": getattr(exc, "code", None),
        "http_reason": _sanitize_text(str(getattr(exc, "reason", ""))[:200]),
        "content_type": None,
        "response_body_received": False,
        "error_type": type(exc).__name__,
    }
    headers = getattr(exc, "headers", None)
    if headers:
        diagnostics["content_type"] = headers.get("Content-Type")
    reader = getattr(exc, "read", None)
    if not callable(reader):
        return diagnostics
    try:
        raw = reader(8192)
        diagnostics["response_body_received"] = bool(raw)
        if not raw:
            return diagnostics
        text = raw.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            diagnostics["body_preview"] = _sanitize_text(text[:1000])
        else:
            if isinstance(parsed, dict):
                safe_keys = ("error", "error_description", "message", "detail", "code", "status")
                diagnostics["error_fields"] = {
                    key: _sanitize_text(str(parsed[key])[:1000])
                    for key in safe_keys
                    if key in parsed
                }
            else:
                diagnostics["body_type"] = type(parsed).__name__
    except (OSError, UnicodeError, TypeError):
        diagnostics["response_body_read_error"] = True
    return diagnostics


def _sanitize_text(value: str) -> str:
    return re.sub(
        r"(?i)(access[_-]?token|client[_-]?secret|authorization|cookie)\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        value,
    )


def acquire_scene(
    client: ProcessAPIClient,
    scene_id: str,
    aoi_geometry: dict[str, Any],
    grid: AcquisitionGrid,
    destination: Path,
    acquisition_start: datetime,
    acquisition_end: datetime,
    existing_bytes: int = 0,
    preserve_invalid_diagnostic: Path | None = None,
) -> dict[str, Any]:
    expected = grid.expected_bytes
    if existing_bytes + expected > MAX_STORAGE_BYTES:
        raise DownloadError("512 MiB Sentinel-1 storage budget would be exceeded")
    destination.parent.mkdir(parents=True, exist_ok=True)
    free_before = shutil.disk_usage(destination.parent).free
    payload = build_process_payload(
        scene_id, aoi_geometry, grid, acquisition_start, acquisition_end
    )
    content = client.request_raster(scene_id, payload)
    if len(content) > MAX_STORAGE_BYTES - existing_bytes:
        raise DownloadError("Process API response exceeds the remaining Sentinel-1 storage budget")
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(content)
    validation: dict[str, Any] | None = None
    try:
        enrichment = enrich_band_descriptions(temporary)
        validation = validate_acquired_raster(temporary, aoi_geometry, scene_id, grid)
        validation["metadata_enrichment"] = enrichment
        if not validation["valid"]:
            raise IntegrityError(f"invalid Process API raster for {scene_id}: {validation['errors']}")
        temporary.replace(destination)
    except Exception as exc:
        if preserve_invalid_diagnostic is not None:
            diagnostic = _preserve_invalid_raster_diagnostic(
                preserve_invalid_diagnostic,
                content,
                validation,
                getattr(client, "last_response_content_type", None),
                grid,
                existing_bytes,
                exc,
            )
            if diagnostic is not None:
                setattr(exc, "diagnostics", diagnostic)
        temporary.unlink(missing_ok=True)
        raise
    return {
        "scene_id": scene_id,
        "file_size": destination.stat().st_size,
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "free_disk_before": free_before,
        "free_disk_after": shutil.disk_usage(destination.parent).free,
        "validation": validation,
        "request": payload,
        "qc": qc_report(destination, scene_id, "sentinel-1").__dict__,
    }


def enrich_band_descriptions(path: Path) -> dict[str, Any]:
    """Add contract-derived labels without changing raster samples or grid."""
    with rasterio.open(path, "r+") as dataset:
        if dataset.count != 2:
            return {"applied": False, "reason": "expected exactly two bands"}
        before = list(dataset.descriptions)
        dataset.set_band_description(1, "VV")
        dataset.set_band_description(2, "VH")
        return {
            "applied": True,
            "source": "RescueX evalscript output order: VV, VH",
            "before": before,
            "after": list(dataset.descriptions),
        }


def _preserve_invalid_raster_diagnostic(
    path: Path,
    content: bytes,
    validation: dict[str, Any] | None,
    content_type: str | None,
    grid: AcquisitionGrid,
    existing_bytes: int,
    error: Exception,
) -> dict[str, Any] | None:
    """Preserve only a bounded, TIFF-signature response outside production data."""
    remaining = MAX_STORAGE_BYTES - existing_bytes
    signature = content[:4]
    is_tiff = signature in (b"II*\x00", b"MM\x00*")
    content_type_ok = not content_type or content_type.split(";", 1)[0].strip().lower() in {
        "image/tiff",
        "application/octet-stream",
    }
    report: dict[str, Any] = {
        "artifact_type": "rejected_process_api_raster_diagnostic",
        "production_output": False,
        "response_content_type": content_type,
        "file_size": len(content),
        "tiff_signature": signature.hex(),
        "tiff_signature_valid": is_tiff,
        "within_remaining_budget": len(content) <= remaining,
        "expected_grid": {
            "crs": grid.crs,
            "width": grid.width,
            "height": grid.height,
            "resolution_m": grid.resolution_m,
            "transform": list(grid.transform),
        },
        "validation": validation,
        "failure": str(error)[:2000],
    }
    if not is_tiff or not content_type_ok or len(content) > remaining:
        report["preserved"] = False
        return report
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    report_path = path.with_suffix(".json")
    report["preserved"] = True
    temporary.write_bytes(content)
    temporary.replace(path)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {**report, "path": str(path), "report_path": str(report_path)}


def compare_raster_grids(before_path: Path, after_path: Path) -> dict[str, Any]:
    before = inspect_raster(before_path)
    after = inspect_raster(after_path)
    comparison = {
        "same_crs": before.crs == after.crs,
        "same_resolution": before.resolution == after.resolution,
        "same_dimensions": (before.width, before.height) == (after.width, after.height),
        "same_transform": before.transform == after.transform,
    }
    comparison["aligned"] = all(comparison.values())
    return comparison
