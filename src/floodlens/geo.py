"""Small geometry helpers with an optional Shapely acceleration path."""

from typing import Any


def shape(geometry: dict[str, Any]) -> Any:
    try:
        from shapely.geometry import shape as shapely_shape
    except ImportError as exc:
        raise RuntimeError(
            "Shapely is required for GeoJSON analysis; install the geospatial extra."
        ) from exc
    return shapely_shape(geometry)


def overlap_ratio(feature_geometry: dict[str, Any], zones: list[dict[str, Any]]) -> float:
    feature = shape(feature_geometry)
    if feature.is_empty or feature.area <= 0:
        return 0.0
    union = None
    for geometry in zones:
        zone = shape(geometry)
        union = zone if union is None else union.union(zone)
    return 0.0 if union is None else float(feature.intersection(union).area / feature.area)


def line_overlap_ratio(feature_geometry: dict[str, Any], zones: list[dict[str, Any]]) -> float:
    feature = shape(feature_geometry)
    if feature.is_empty or feature.length <= 0:
        return 0.0
    union = None
    for geometry in zones:
        zone = shape(geometry)
        union = zone if union is None else union.union(zone)
    return 0.0 if union is None else float(feature.intersection(union).length / feature.length)
