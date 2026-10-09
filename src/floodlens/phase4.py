"""Phase 4 integration helpers with explicit real-vs-fixture provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .analysis import infrastructure_impact
from .models import Feature, Point, Road
from .network import connectivity_analysis

DEVELOPMENT_FIXTURE_LABEL = "DEVELOPMENT FIXTURE — NOT REAL SATELLITE RESULT"


def classify_phase3_artifacts(root: Path) -> dict[str, Any]:
    """Inspect local Phase 3 artifacts without creating or interpreting them."""
    checkpoints = sorted(
        path for path in root.rglob("*") if path.is_file() and path.suffix in {".pt", ".pth", ".ckpt"}
    ) if root.exists() else []
    masks = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".tif", ".tiff"}
        and ("mask" in path.stem.lower() or "prob" in path.stem.lower())
    ) if root.exists() else []
    checkpoint_records = []
    for checkpoint in checkpoints:
        manifest = checkpoint.with_suffix(".json")
        record: dict[str, Any] = {"path": str(checkpoint), "classification": "unclassified"}
        if manifest.exists():
            try:
                metadata = json.loads(manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                metadata = {}
            record["dataset"] = metadata.get("dataset")
            record["classification"] = (
                "synthetic fixture"
                if metadata.get("dataset") == "development-fixture"
                else "real trained model" if metadata.get("dataset") else "unclassified"
            )
        checkpoint_records.append(record)
    return {
        "real_checkpoint_exists": any(item["classification"] == "real trained model" for item in checkpoint_records),
        "real_georeferenced_mask_exists": False,
        "checkpoints": checkpoint_records,
        "candidate_masks": [{"path": str(path), "classification": "requires provenance"} for path in masks],
        "conclusion": (
            "No genuine Phase 3 flood mask is available."
            if not any(item["classification"] == "real trained model" for item in checkpoint_records)
            else "A trained checkpoint exists; mask provenance still requires an inference manifest."
        ),
    }


def run_development_fixture(
    zones: list[dict[str, Any]],
    buildings: list[Feature],
    roads: list[Road],
    bridges: list[Feature],
    settlements: list[Point],
    destinations: list[Point],
    *,
    building_threshold: float = 0.1,
    road_threshold: float = 0.5,
) -> dict[str, Any]:
    """Run Phase 4 analysis on caller-supplied synthetic geometry only."""
    impact = infrastructure_impact(
        zones, buildings, roads, bridges, building_threshold, road_threshold
    )
    network = connectivity_analysis(
        roads, settlements, destinations, {item["id"] for item in impact["affected_roads"]}
    )
    return {
        "execution_classification": "synthetic fixture",
        "label": DEVELOPMENT_FIXTURE_LABEL,
        "results": {"flood_zone_count": len(zones), "infrastructure": impact, "network": network},
        "real_satellite_result": False,
        "real_data_execution_pending": True,
    }
