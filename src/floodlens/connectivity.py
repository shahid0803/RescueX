"""Road-network connectivity analysis for Phase 5.

This module deliberately models *potentially blocked* edges, not confirmed
damage.  It uses the pre-event graph as the immutable baseline and derives an
event graph by disabling matched edges.
"""

from __future__ import annotations

import heapq
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field

from .models import Point, Road


class BlockedRoad(BaseModel):
    segment_id: str | None = None
    osm_id: str | None = None
    reason: str = "Phase 4 potentially blocked road"
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str = "phase4"
    provenance: dict[str, Any] = Field(default_factory=dict)


class BlockedRoadSet(BaseModel):
    roads: list[BlockedRoad] = Field(default_factory=list)
    match_failures: list[str] = Field(default_factory=list)


class Phase4RoadImpactAdapter:
    """Adapt common Phase 4 impact dictionaries without weakening provenance."""

    @staticmethod
    def adapt(impact: dict[str, Any] | Iterable[dict[str, Any]]) -> BlockedRoadSet:
        items = impact.get("potentially_blocked_roads", impact.get("affected_roads", [])) if isinstance(impact, dict) else impact
        blocked = []
        for item in items:
            if item.get("potentially_blocked", True):
                blocked.append(BlockedRoad(
                    segment_id=item.get("segment_id") or item.get("id"),
                    osm_id=item.get("osm_id"),
                    reason=item.get("reason", "Phase 4 potentially blocked road"),
                    confidence=item.get("confidence"),
                    source=item.get("source", "phase4"),
                    provenance=item.get("provenance", {}),
                ))
        return BlockedRoadSet(roads=blocked)


class ConnectivityConfig(BaseModel):
    event_date: date
    osm_snapshot_date: date
    aoi: dict[str, Any] = Field(default_factory=dict)
    snap_tolerance_m: float = Field(default=25, gt=0)
    settlement_access_tolerance_m: float = Field(default=250, gt=0)
    destination_access_tolerance_m: float = Field(default=250, gt=0)
    access_degraded_enabled: bool = False
    access_degraded_threshold_percent: float = Field(default=50, ge=0)
    use_bridge_blocking: bool = True
    road_class_policy: list[str] = Field(default_factory=list)
    buffer_m: float = Field(default=1000, ge=0)

    def validate_snapshot(self) -> None:
        if self.osm_snapshot_date >= self.event_date:
            raise ValueError("OSM snapshot date must be earlier than event date")


class SettlementConnectivityResult(BaseModel):
    settlement_id: str
    name: str | None = None
    nearest_town_id: str | None = None
    nearest_town_distance_before_m: float | None = None
    nearest_town_distance_after_m: float | None = None
    town_connected_before: bool = False
    town_connected_after: bool = False
    cut_off_from_town: bool = False
    nearest_hospital_id: str | None = None
    nearest_hospital_distance_before_m: float | None = None
    nearest_hospital_distance_after_m: float | None = None
    hospital_connected_before: bool = False
    hospital_connected_after: bool = False
    cut_off_from_hospital: bool = False
    cut_off_from_both: bool = False
    access_degraded: bool = False
    blocked_segments: list[str] = Field(default_factory=list)
    path_before: list[str] | None = None
    path_after: list[str] | None = None
    status: str
    reason: str
    provenance: dict[str, Any] = Field(default_factory=dict)


class ConnectivityAnalysisResult(BaseModel):
    run_id: str
    status: str
    settlements: list[SettlementConnectivityResult]
    summary: dict[str, int]
    diagnostics: dict[str, Any]
    provenance: dict[str, Any]
    configuration: dict[str, Any]

    def geojson(self, points: list[Point]) -> dict[str, Any]:
        by_id = {point.id: point for point in points}
        features = []
        for result in self.settlements:
            point = by_id.get(result.settlement_id)
            if point is None:
                continue
            properties = result.model_dump(exclude={"provenance"})
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [point.x, point.y]},
                "properties": properties,
            })
        return {"type": "FeatureCollection", "features": features}


def _edge_key(road: Road) -> str:
    return road.id


def _graph(roads: list[Road], disabled: set[str]) -> dict[str, list[tuple[str, float, str]]]:
    graph: dict[str, list[tuple[str, float, str]]] = {}
    for road in roads:
        if road.id in disabled:
            continue
        graph.setdefault(road.start, []).append((road.end, road.length_m, road.id))
        graph.setdefault(road.end, []).append((road.start, road.length_m, road.id))
    return graph


def _shortest(graph: dict[str, list[tuple[str, float, str]]], start: str, targets: set[str]) -> tuple[float, list[str], str | None]:
    queue = [(0.0, start, [])]
    visited: set[str] = set()
    while queue:
        distance, node, path = heapq.heappop(queue)
        if node in visited:
            continue
        visited.add(node)
        if node in targets:
            return distance, path, node
        for neighbor, weight, edge_id in graph.get(node, []):
            if neighbor not in visited:
                heapq.heappush(queue, (distance + weight, neighbor, path + [edge_id]))
    return math.inf, [], None


def _attach(points: list[Point], roads: list[Road], tolerance: float) -> tuple[dict[str, str], list[str]]:
    attached: dict[str, str] = {}
    unresolved = []
    endpoint_points: dict[str, Point] = {}
    for road in roads:
        if road.geometry:
            endpoint_points.setdefault(road.start, road.geometry[0])
            endpoint_points.setdefault(road.end, road.geometry[-1])
    for point in points:
        candidates = [
            (math.hypot(point.x - endpoint.x, point.y - endpoint.y), endpoint_id)
            for endpoint_id, endpoint in endpoint_points.items()
        ]
        if not candidates:
            unresolved.append(point.id)
            continue
        distance, endpoint_id = min(candidates)
        if distance <= tolerance:
            attached[point.id] = endpoint_id
        else:
            unresolved.append(point.id)
    return attached, unresolved


def analyze_connectivity(
    roads: list[Road],
    settlements: list[Point],
    towns: list[Point],
    hospitals: list[Point],
    blocked: BlockedRoadSet,
    config: ConnectivityConfig,
    *,
    run_id: str | None = None,
    phase4_source: str = "fixture",
) -> ConnectivityAnalysisResult:
    config.validate_snapshot()
    road_ids = {road.id for road in roads}
    blocked_ids = {item.segment_id for item in blocked.roads if item.segment_id in road_ids}
    match_failures = [item.segment_id or item.osm_id or "unknown" for item in blocked.roads if item.segment_id not in road_ids]
    before = _graph(roads, set())
    after = _graph(roads, blocked_ids)
    town_attach, unmapped_towns = _attach(towns, roads, config.destination_access_tolerance_m)
    hospital_attach, unmapped_hospitals = _attach(hospitals, roads, config.destination_access_tolerance_m)
    settlement_attach, unmapped_settlements = _attach(settlements, roads, config.settlement_access_tolerance_m)
    results = []
    for settlement in settlements:
        start = settlement_attach.get(settlement.id)
        common = {"settlement_id": settlement.id, "name": settlement.id, "blocked_segments": sorted(blocked_ids)}
        if not start:
            results.append(SettlementConnectivityResult(**common, status="UNMAPPED_SETTLEMENT", reason="Settlement is outside the configured road access tolerance"))
            continue
        town_targets = set(town_attach.values())
        hospital_targets = set(hospital_attach.values())
        town_before, town_path_before, town_id_node = _shortest(before, start, town_targets)
        town_after, town_path_after, _ = _shortest(after, start, town_targets)
        hospital_before, hospital_path_before, hospital_id_node = _shortest(before, start, hospital_targets)
        hospital_after, hospital_path_after, _ = _shortest(after, start, hospital_targets)
        town_id = next((key for key, value in town_attach.items() if value == town_id_node), None)
        hospital_id = next((key for key, value in hospital_attach.items() if value == hospital_id_node), None)
        town_connected_before = math.isfinite(town_before)
        hospital_connected_before = math.isfinite(hospital_before)
        town_connected_after = math.isfinite(town_after)
        hospital_connected_after = math.isfinite(hospital_after)
        cut_town = town_connected_before and not town_connected_after
        cut_hospital = hospital_connected_before and not hospital_connected_after
        no_baseline_route = not town_connected_before and not hospital_connected_before
        degraded = config.access_degraded_enabled and any(
            before_distance > 0 and math.isfinite(after_distance)
            and (after_distance - before_distance) / before_distance * 100 >= config.access_degraded_threshold_percent
            for before_distance, after_distance in ((town_before, town_after), (hospital_before, hospital_after))
        )
        status = (
            "CUT_OFF_FROM_BOTH" if cut_town and cut_hospital else
            "CUT_OFF" if cut_town or cut_hospital else
            "NO_BASELINE_ROUTE" if no_baseline_route else
            "ACCESS_DEGRADED" if degraded else "CONNECTED"
        )
        reason = (
            "Connectivity lost under modeled blockage assumptions" if status.startswith("CUT_OFF")
            else "No baseline road route to an available destination" if no_baseline_route
            else "Road-network route remains available"
        )
        results.append(SettlementConnectivityResult(
            **common, nearest_town_id=town_id, nearest_town_distance_before_m=None if not town_connected_before else town_before,
            nearest_town_distance_after_m=None if not town_connected_after else town_after, town_connected_before=town_connected_before,
            town_connected_after=town_connected_after, cut_off_from_town=cut_town, nearest_hospital_id=hospital_id,
            nearest_hospital_distance_before_m=None if not hospital_connected_before else hospital_before,
            nearest_hospital_distance_after_m=None if not hospital_connected_after else hospital_after,
            hospital_connected_before=hospital_connected_before, hospital_connected_after=hospital_connected_after,
            cut_off_from_hospital=cut_hospital, cut_off_from_both=cut_town and cut_hospital, access_degraded=degraded,
            path_before=town_path_before or hospital_path_before or None, path_after=town_path_after or hospital_path_after or None,
            status=status, reason=reason,
        ))
    provenance = {
        "osm_snapshot_date": config.osm_snapshot_date.isoformat(),
        "event_date": config.event_date.isoformat(),
        "phase4_road_impact_source": phase4_source,
        "blocked_road_semantics": "potentially blocked; unavailable only for this connectivity simulation",
        "processing_version": "phase5-connectivity-v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    summary = {
        "total_settlements": len(results),
        "connected_before": sum(r.town_connected_before or r.hospital_connected_before for r in results),
        "connected_after": sum(r.town_connected_after or r.hospital_connected_after for r in results),
        "cut_off": sum(r.status.startswith("CUT_OFF") for r in results),
        "cut_off_from_town": sum(r.cut_off_from_town for r in results),
        "cut_off_from_hospital": sum(r.cut_off_from_hospital for r in results),
        "cut_off_from_both": sum(r.cut_off_from_both for r in results),
        "access_degraded": sum(r.access_degraded for r in results),
        "unresolved": sum(r.status.startswith("UNMAPPED") for r in results),
    }
    return ConnectivityAnalysisResult(
        run_id=run_id or str(uuid4()), status="WARNING" if match_failures or unmapped_settlements else "VALID",
        settlements=results, summary=summary,
        diagnostics={"nodes_before": len(before), "edges_before": len(roads), "nodes_after": len(after),
                     "edges_after": len(roads) - len(blocked_ids), "blocked_edges": sorted(blocked_ids),
                     "blocked_match_failures": match_failures, "unmapped_towns": unmapped_towns,
                     "unmapped_hospitals": unmapped_hospitals, "unmapped_settlements": unmapped_settlements},
        provenance=provenance, configuration=config.model_dump(mode="json"),
    )
