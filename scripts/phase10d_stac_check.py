"""Verify the public STAC candidates without CDSE credentials or raster access."""

from __future__ import annotations

import json
from pathlib import Path

from floodlens.satellite.errors import CatalogUnavailableError
from floodlens.satellite.process_api import verify_stac_candidate
from phase10d_acquire import AFTER_ID, BEFORE_ID, SCENE_WINDOWS, extract_geometry


AOI_PATH = Path("configs/case_studies/trishuli_2026_aoi.geojson")


def main() -> int:
    geometry = extract_geometry(json.loads(AOI_PATH.read_text(encoding="utf-8")))
    exit_code = 0
    for role, scene_id in (("before", BEFORE_ID), ("after", AFTER_ID)):
        start, end = SCENE_WINDOWS[role]
        try:
            result = verify_stac_candidate(geometry, scene_id, start, end)
            print(json.dumps({
                "role": role,
                "matching_item_count": 1,
                "metadata_verification": result["status"],
                "scene_id": scene_id,
                "datetime": result["query"]["datetime"],
            }))
        except CatalogUnavailableError as exc:
            print(json.dumps({
                "role": role,
                "matching_item_count": getattr(exc, "item_count", None),
                "metadata_verification": "FAILED",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }))
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
