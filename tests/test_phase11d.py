import importlib.util
import hashlib
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
from floodlens.satellite.errors import ProcessAPIRequestError


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


def _candidate_bytes_without_descriptions(grid, count=3, transform=None):
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff", width=grid.width, height=grid.height, count=count,
            dtype="float32", crs=grid.crs,
            transform=Affine(*(transform or grid.transform)),
        ) as dataset:
            dataset.write(np.ones((count, grid.height, grid.width), dtype="float32"))
        return memory.read()


def _write_recovery_inputs(module, tmp_path, grid, content, descriptions):
    aoi_path = tmp_path / "aoi.json"
    aoi_path.write_text(json.dumps(AOI))
    acquisition_path = tmp_path / "acquisition.json"
    acquisition_path.write_text(json.dumps({
        "scenes": {"before": {"scene_id": SCENE}, "after": {"scene_id": "after-id"}}
    }))
    quarantine = tmp_path / "before_rejected.tif"
    quarantine.write_bytes(content)
    diagnostic = {
        "sha256": hashlib.sha256(content).hexdigest(),
        "role": "before",
        "validation": {
            "band_descriptions": descriptions,
            "scene_id": SCENE,
        },
    }
    quarantine.with_suffix(".json").write_text(json.dumps(diagnostic))
    module.ACQUISITION_MANIFEST = acquisition_path
    return aoi_path, acquisition_path, quarantine


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
        "speckleFilter": {"type": "LEE", "windowSizeX": 3, "windowSizeY": 3},
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


def test_resume_reuses_before_and_requests_only_after(tmp_path: Path, monkeypatch):
    script_path = Path(__file__).parents[1] / "scripts" / "phase11d_candidate_acquire.py"
    spec = importlib.util.spec_from_file_location("phase11d_resume", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    grid = AcquisitionGrid(
        "EPSG:32645", 10.0, 830, 496,
        (313843.864892112, 3084291.802767885, 322143.864892112, 3089251.802767885),
    )
    acquisition = tmp_path / "acquisition.json"
    acquisition.write_text(json.dumps({
        "scenes": {"before": {"scene_id": SCENE}, "after": {"scene_id": "after-id"}}
    }))
    monkeypatch.setattr(module, "ACQUISITION_MANIFEST", acquisition)
    output_dir = tmp_path / "candidate"
    output_dir.mkdir()
    before_path = output_dir / "before_sigma0_lee_vv_vh_datamask.tif"
    before_path.write_bytes(_candidate_bytes(grid))
    manifest_path = tmp_path / "manifest.json"
    previous = module.build_manifest(
        Path("configs/case_studies/trishuli_2026_aoi.geojson"),
        output_dir, grid, {"before": SCENE, "after": "after-id"},
    )
    previous["attempt_history"] = [{"kind": "prior_failure"}]
    previous["local_recovery"] = {"performed": True, "network_request": False}
    manifest_path.write_text(json.dumps(previous))
    stac_roles = []
    request_roles = []

    def fake_stac(aoi, scene_id, start, end):
        stac_roles.append(scene_id)
        return {"matched_scene_id": scene_id}

    class FakeClient:
        last_response_content_type = "image/tiff"

        def __init__(self, authenticator):
            pass

        def request_raster(self, scene_id, payload):
            request_roles.append(scene_id)
            return _candidate_bytes(grid)

    monkeypatch.setattr(module, "verify_stac_candidate", fake_stac)
    monkeypatch.setattr(module, "ProcessAPIClient", FakeClient)
    monkeypatch.setattr(module.CopernicusAuthenticator, "from_env", classmethod(lambda cls: object()))
    monkeypatch.setenv("RESCUEX_CDSE_CLIENT_ID", "test-client")
    monkeypatch.setenv("RESCUEX_CDSE_CLIENT_SECRET", "test-secret")

    result = module.run(
        Path("configs/case_studies/trishuli_2026_aoi.geojson"),
        output_dir, execute=True, manifest_path=manifest_path,
    )

    assert stac_roles == ["after-id"]
    assert request_roles == ["after-id"]
    assert result["scenes"]["before"]["network_request"] is False
    assert result["scenes"]["before"]["local_reuse"] is True
    assert result["scenes"]["after"]["network_request"] is True
    assert result["network_request_performed"] is True
    assert result["attempt_history"] == [{"kind": "prior_failure"}]
    assert result["local_recovery"] == {"performed": True, "network_request": False}


def test_candidate_http400_diagnostics_are_persisted_without_credentials(tmp_path: Path):
    script_path = Path(__file__).parents[1] / "scripts" / "phase11d_candidate_acquire.py"
    spec = importlib.util.spec_from_file_location("phase11d_failure", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest_path = tmp_path / "candidate.json"
    manifest_path.write_text(json.dumps({
        "phase": "11D",
        "status": "CANDIDATE_PROFILE_IMPLEMENTED",
        "attempt_history": [],
    }))
    error = ProcessAPIRequestError(
        "candidate request failed",
        {
            "stage": "http_submission_or_response",
            "http_status": 400,
            "response_body_received": True,
            "error_fields": {"error": "COMMON_BAD_PAYLOAD", "message": "invalid filter"},
        },
    )
    result = module._record_failure(manifest_path, Path("aoi.geojson"), tmp_path / "candidate", error)
    assert result["status"] == "CANDIDATE_ACQUISITION_FAILED"
    attempt = result["attempt_history"][0]
    assert attempt["diagnostics"]["http_status"] == 400
    assert attempt["diagnostics"]["error_fields"]["message"] == "invalid filter"
    assert "authorization" not in json.dumps(result).lower()


def test_candidate_validation_quarantines_rejected_raster(tmp_path: Path, monkeypatch):
    script_path = Path(__file__).parents[1] / "scripts" / "phase11d_candidate_acquire.py"
    spec = importlib.util.spec_from_file_location("phase11d_quarantine", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    quarantine = tmp_path / "diagnostics"
    monkeypatch.setattr(module, "CANDIDATE_DIAGNOSTICS", quarantine)
    grid = AcquisitionGrid(
        "EPSG:32645", 10.0, 830, 496,
        (313843.864892112, 3084291.802767885, 322143.864892112, 3089251.802767885),
    )
    rejected = _candidate_bytes(grid)
    with MemoryFile(rejected) as memory:
        with memory.open() as dataset:
            values = dataset.read()[:2]
            profile = dataset.profile.copy()
            profile["count"] = 2
        with MemoryFile() as output_memory:
            with output_memory.open(**profile) as output:
                output.write(values)
                output.set_band_description(1, "VV")
                output.set_band_description(2, "VH")
            rejected = output_memory.read()

    class FakeClient:
        last_response_content_type = "image/tiff"

        def request_raster(self, scene_id, payload):
            return rejected

    destination = tmp_path / "candidate.tif"
    try:
        module._acquire_one(FakeClient(), "before", SCENE, AOI, grid, destination, 0)
    except RuntimeError as exc:
        assert "expected VV, VH, dataMask bands in that order" in str(exc)
    else:
        raise AssertionError("expected strict validation failure")
    assert not destination.exists()
    assert (quarantine / "before_rejected.tif").exists()
    report = json.loads((quarantine / "before_rejected.json").read_text())
    assert report["production_output"] is False
    assert report["validation"]["band_descriptions"] == ["VV", "VH"]
    assert report["validation"]["bands"] == 2
    assert report["credentials_saved"] is False


def test_recover_before_candidate_sets_metadata_and_status(tmp_path: Path, monkeypatch):
    script_path = Path(__file__).parents[1] / "scripts" / "phase11d_candidate_acquire.py"
    spec = importlib.util.spec_from_file_location("phase11d_recovery", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    grid = AcquisitionGrid(
        "EPSG:32645", 10.0, 830, 496,
        (313843.864892112, 3084291.802767885, 322143.864892112, 3089251.802767885),
    )
    content = _candidate_bytes_without_descriptions(grid)
    aoi_path, acquisition_path, quarantine = _write_recovery_inputs(
        module, tmp_path, grid, content, [None, None, None]
    )
    manifest_path = tmp_path / "candidate.json"
    manifest_path.write_text(json.dumps(module.build_manifest(
        aoi_path, tmp_path / "outputs", grid, {"before": SCENE, "after": "after-id"}
    )))
    destination = tmp_path / "outputs" / "before_sigma0_lee_vv_vh_datamask.tif"
    original_hash = hashlib.sha256(content).hexdigest()
    result = module.recover_before_candidate(
        aoi_path, manifest_path, quarantine, destination
    )
    assert result["status"] == "BEFORE_LOCALLY_RECOVERED_VALIDATED"
    assert result["network_request_performed"] is True
    assert result["validation"]["status"] == "BEFORE_ONLY_PASS"
    assert result["validation"]["after_status"] == "NOT_ACQUIRED"
    assert result["scenes"]["before"]["original_response_sha256"] == original_hash
    assert result["scenes"]["before"]["sha256"] == hashlib.sha256(destination.read_bytes()).hexdigest()
    assert destination.exists()
    assert hashlib.sha256(quarantine.read_bytes()).hexdigest() == original_hash


def test_recover_before_refuses_unproven_band_order(tmp_path: Path):
    script_path = Path(__file__).parents[1] / "scripts" / "phase11d_candidate_acquire.py"
    spec = importlib.util.spec_from_file_location("phase11d_recovery_order", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    grid = AcquisitionGrid(
        "EPSG:32645", 10.0, 830, 496,
        (313843.864892112, 3084291.802767885, 322143.864892112, 3089251.802767885),
    )
    content = _candidate_bytes_without_descriptions(grid)
    aoi_path, _, quarantine = _write_recovery_inputs(
        module, tmp_path, grid, content, ["VV", "VH", "dataMask"]
    )
    manifest_path = tmp_path / "candidate.json"
    manifest_path.write_text(json.dumps(module.build_manifest(
        aoi_path, tmp_path / "outputs", grid, {"before": SCENE, "after": "after-id"}
    )))
    try:
        module.recover_before_candidate(
            aoi_path, manifest_path, quarantine,
            tmp_path / "outputs" / "before.tif",
        )
    except RuntimeError as exc:
        assert "all original band descriptions" in str(exc)
    else:
        raise AssertionError("expected refusal when recovery evidence is not limited to missing descriptions")


def test_recover_before_rejects_invalid_grid_without_promotion(tmp_path: Path):
    script_path = Path(__file__).parents[1] / "scripts" / "phase11d_candidate_acquire.py"
    spec = importlib.util.spec_from_file_location("phase11d_recovery_invalid", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    grid = AcquisitionGrid(
        "EPSG:32645", 10.0, 830, 496,
        (313843.864892112, 3084291.802767885, 322143.864892112, 3089251.802767885),
    )
    content = _candidate_bytes_without_descriptions(
        grid, transform=(10, 0, grid.bounds[0] + 1, 0, -10, grid.bounds[3], 0, 0, 1)
    )
    aoi_path, _, quarantine = _write_recovery_inputs(
        module, tmp_path, grid, content, [None, None, None]
    )
    manifest_path = tmp_path / "candidate.json"
    manifest_path.write_text(json.dumps(module.build_manifest(
        aoi_path, tmp_path / "outputs", grid, {"before": SCENE, "after": "after-id"}
    )))
    try:
        module.recover_before_candidate(
            aoi_path, manifest_path, quarantine,
            tmp_path / "outputs" / "before.tif",
        )
    except RuntimeError as exc:
        assert "recovered candidate failed strict validation" in str(exc)
    else:
        raise AssertionError("expected invalid recovery evidence failure")


def test_recover_after_completes_pair_from_matching_quarantine(tmp_path: Path):
    script_path = Path(__file__).parents[1] / "scripts" / "phase11d_candidate_acquire.py"
    spec = importlib.util.spec_from_file_location("phase11d_recovery_after", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    grid = AcquisitionGrid(
        "EPSG:32645", 10.0, 830, 496,
        (313843.864892112, 3084291.802767885, 322143.864892112, 3089251.802767885),
    )
    after_scene = "after-id"
    content = _candidate_bytes_without_descriptions(grid)
    aoi_path = tmp_path / "aoi.json"
    aoi_path.write_text(json.dumps(AOI))
    acquisition_path = tmp_path / "acquisition.json"
    acquisition_path.write_text(json.dumps({
        "scenes": {"before": {"scene_id": SCENE}, "after": {"scene_id": after_scene}}
    }))
    module.ACQUISITION_MANIFEST = acquisition_path
    quarantine = tmp_path / "after_rejected.tif"
    quarantine.write_bytes(content)
    quarantine.with_suffix(".json").write_text(json.dumps({
        "sha256": hashlib.sha256(content).hexdigest(),
        "role": "after",
        "validation": {"band_descriptions": [None, None, None], "scene_id": after_scene},
    }))
    manifest_path = tmp_path / "candidate.json"
    manifest_path.write_text(json.dumps(module.build_manifest(
        aoi_path, tmp_path / "outputs", grid,
        {"before": SCENE, "after": after_scene},
    )))
    before = manifest_path.read_text()
    result = module.recover_candidate(
        aoi_path, manifest_path, quarantine,
        tmp_path / "outputs" / "after_sigma0_lee_vv_vh_datamask.tif", "after",
    )
    assert result["status"] == "AFTER_LOCALLY_RECOVERED_VALIDATED"
    assert result["validation"]["pair_complete"] is False
    assert result["validation"]["after_status"] == "PASS"
    assert result["scenes"]["after"]["local_recovery"] is True
    assert manifest_path.read_text() != before
