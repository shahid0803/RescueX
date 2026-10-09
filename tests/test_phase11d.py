import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from affine import Affine
from rasterio.io import MemoryFile

from floodlens.satellite.process_api import (
    AcquisitionGrid,
    build_candidate_process_payload,
    build_grid,
    validate_candidate_raster,
)


AOI = {
    "type": "Polygon",
    "coordinates": [[[85.11, 27.88], [85.19, 27.88], [85.19, 27.91],
                     [85.11, 27.91], [85.11, 27.88]]],
}
SCENE = "S1D_IW_GRDH_1SDV_20260816T122141_20260816T122206_004151_007980_B091_COG"
START = datetime(2026, 8, 16, 12, 21, 41, tzinfo=timezone.utc)
END = datetime(2026, 8, 16, 12, 22, 6, tzinfo=timezone.utc)


def _candidate_bytes(grid):
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff", width=grid.width, height=grid.height, count=3,
            dtype="float32", crs=grid.crs, transform=Affine(*grid.transform),
        ) as dataset:
            dataset.write(np.ones((3, grid.height, grid.width), dtype="float32"))
            dataset.set_band_description(1, "VV")
            dataset.set_band_description(2, "VH")
            dataset.set_band_description(3, "dataMask")
        return memory.read()


def test_candidate_payload_pins_sigma0_lee_and_datamask():
    grid = AcquisitionGrid(
        "EPSG:32645", 10.0, 830, 496,
        (313843.864892112, 3084291.802767885, 322143.864892112, 3089251.802767885),
    )
    payload = build_candidate_process_payload(SCENE, AOI, grid, START, END)
    data = payload["input"]["data"][0]
    assert data["processing"] == {
        "backCoeff": "SIGMA0_ELLIPSOID",
        "orthorectify": True,
        "speckleFilter": {"type": "LEE", "windowSize": 3},
    }
    assert payload["output"]["width"] == 830
    assert payload["output"]["height"] == 496
    assert "dataMask" in payload["evalscript"]
    assert data["processing"]["speckleFilter"]["type"] == "LEE"


def test_candidate_validator_requires_vv_vh_datamask(tmp_path: Path):
    grid = AcquisitionGrid(
        "EPSG:32645", 10.0, 830, 496,
        (313843.864892112, 3084291.802767885, 322143.864892112, 3089251.802767885),
    )
    path = tmp_path / "candidate.tif"
    path.write_bytes(_candidate_bytes(grid))
    result = validate_candidate_raster(path, AOI, SCENE, grid)
    assert result["valid"] is True
    assert result["data_mask_values"] == [1.0]


def test_candidate_dry_run_reads_manifest_scene_ids_without_network(tmp_path: Path, monkeypatch):
    script_path = Path(__file__).parents[1] / "scripts" / "phase11d_candidate_acquire.py"
    spec = importlib.util.spec_from_file_location("phase11d", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    acquisition = tmp_path / "acquisition.json"
    acquisition.write_text(json.dumps({
        "scenes": {"before": {"scene_id": "before-id"}, "after": {"scene_id": "after-id"}}
    }))
    monkeypatch.setattr(module, "ACQUISITION_MANIFEST", acquisition)
    manifest = module.run(Path("configs/case_studies/trishuli_2026_aoi.geojson"),
                          tmp_path / "candidate", execute=False)
    assert manifest["status"] == "CANDIDATE_PROFILE_IMPLEMENTED"
    assert manifest["network_request_performed"] is False
    assert manifest["scenes"]["after"]["scene_id"] == "after-id"
