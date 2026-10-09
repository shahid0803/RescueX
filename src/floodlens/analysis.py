from __future__ import annotations

from typing import Any

from .geo import line_overlap_ratio, overlap_ratio
from .models import Feature, Road
from .network import connectivity_analysis


def infrastructure_impact(
    zones: list[dict[str, Any]],
    buildings: list[Feature],
    roads: list[Road],
    bridges: list[Feature],
    building_threshold: float,
    road_threshold: float,
) -> dict[str, Any]:
    affected_buildings = []
    for feature in buildings:
        ratio = overlap_ratio(feature.geometry, zones)
        if ratio >= building_threshold:
            affected_buildings.append({"id": feature.id, "overlap_ratio": ratio})

    affected_roads = []
    for road in roads:
        geometry = {"type": "LineString", "coordinates": [[p.x, p.y] for p in road.geometry]}
        ratio = line_overlap_ratio(geometry, zones)
        if ratio >= road_threshold:
            affected_roads.append(
                {"id": road.id, "affected_length_m": road.length_m * ratio, "overlap_ratio": ratio}
            )

    affected_bridges = []
    for feature in bridges:
        ratio = overlap_ratio(feature.geometry, zones)
        if ratio > 0:
            affected_bridges.append({"id": feature.id, "overlap_ratio": ratio})

    return {
        "affected_buildings": affected_buildings,
        "affected_roads": affected_roads,
        "affected_bridges": affected_bridges,
        "method": "geometry overlap with configurable thresholds",
    }


def run_analysis(request: Any) -> dict[str, Any]:
    impact = infrastructure_impact(
        request.flood_zones,
        request.buildings,
        request.roads,
        request.bridges,
        request.building_overlap_threshold,
        request.road_block_threshold,
    )
    blocked = {item["id"] for item in impact["affected_roads"]}
    network = connectivity_analysis(request.roads, request.settlements, request.destinations, blocked)
    return {
        "flood_zone_count": len(request.flood_zones),
        "infrastructure": impact,
        "network": network,
    }
