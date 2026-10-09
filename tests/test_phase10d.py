from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import rasterio
from affine import Affine
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
import importlib.util
import subprocess
import sys

from floodlens.satellite.auth import CopernicusAuthenticator
from floodlens.satellite.process_api import (
    MAX_STORAGE_BYTES,
    ProcessAPIClient,
    acquire_scene,
    build_grid,
    build_process_payload,
    enrich_band_descriptions,
    verify_stac_candidate,
)


AOI = {
    "type": "Polygon",
    "coordinates": [[[85.11, 27.88], [85.19, 27.88], [85.19, 27.91], [85.11, 27.91], [85.11, 27.88]]],
}
SCENE = "S1D_IW_GRDH_1SDV_20260816T122141_20260816T122206_004151_007980_B091_COG"
START = datetime(2026, 8, 16, 12, 21, 41, tzinfo=timezone.utc)
END = datetime(2026, 8, 16, 12, 22, 6, tzinfo=timezone.utc)


def raster_bytes(width=4, height=3, transform=None):
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            width=width,
            height=height,
            count=2,
            dtype="float32",
            crs="EPSG:32645",
            transform=Affine(*transform) if transform else from_origin(320000, 3090000, 20, 20),
            nodata=-9999,
        ) as dataset:
            dataset.write(np.ones((2, height, width), dtype="float32"))
            dataset.set_band_description(1, "VV")
            dataset.set_band_description(2, "VH")
        return memory.read()


def test_payload_binds_exact_scene_and_processing_contract():
    grid = build_grid(AOI)
    payload = build_process_payload(SCENE, AOI, grid, START, END)
    data = payload["input"]["data"][0]
    assert data["type"] == "sentinel-1-grd"
    assert "ids" not in data["dataFilter"]
    assert data["dataFilter"]["timeRange"] == {
        "from": "2026-08-16T12:21:41Z",
        "to": "2026-08-16T12:22:06Z",
    }
    assert data["dataFilter"]["acquisitionMode"] == "IW"
    assert data["dataFilter"]["orbitDirection"] == "ASCENDING"
    assert data["dataFilter"]["polarization"] == "DV"
    assert data["processing"] == {"backCoeff": "GAMMA0_ELLIPSOID", "orthorectify": True}
    assert "speckleFilter" not in data["processing"]
    assert payload["output"]["width"] == grid.width
    assert payload["output"]["height"] == grid.height
    assert "resx" not in payload["output"]
    assert "resy" not in payload["output"]
    assert set(payload["output"]) >= {"width", "height"}
    assert "VV" in payload["evalscript"] and "VH" in payload["evalscript"]
    assert payload["input"]["bounds"]["bbox"] == list(grid.bounds)
    assert payload["input"]["bounds"]["bbox"][2] - payload["input"]["bounds"]["bbox"][0] == grid.width * 20.0
    assert payload["input"]["bounds"]["bbox"][3] - payload["input"]["bounds"]["bbox"][1] == grid.height * 20.0


def test_process_api_sends_cached_token_in_authorization_header():
    class Authenticator:
        def get_token(self):
            return "test-token"

    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"raster"

    def opener(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        return Response()

    ProcessAPIClient(Authenticator(), endpoint="https://example.test/process", opener=opener).request_raster(
        SCENE, {"input": {}, "output": {}}
    )
    assert captured["authorization"] == "Bearer test-token"


def test_bounded_acquisition_validates_two_band_float_raster(tmp_path: Path):
    grid = build_grid(AOI)
    output = tmp_path / "before_vv_vh.tif"
    class FakeClient:
        def request_raster(self, scene_id, payload):
            assert scene_id == SCENE
            return raster_bytes(width=grid.width, height=grid.height, transform=grid.transform)

    record = acquire_scene(FakeClient(), SCENE, AOI, grid, output, START, END)
    assert output.exists()
    assert record["validation"]["valid"] is True
    assert record["validation"]["bands"] == 2
    assert record["validation"]["dtype"] == ["float32", "float32"]


def test_band_description_enrichment_preserves_pixels(tmp_path: Path):
    path = tmp_path / "response.tif"
    original = raster_bytes(width=4, height=3)
    path.write_bytes(original)
    with rasterio.open(path) as dataset:
        before = dataset.read().copy()
    report = enrich_band_descriptions(path)
    with rasterio.open(path) as dataset:
        after = dataset.read().copy()
        assert dataset.descriptions == ("VV", "VH")
    assert report["applied"] is True
    np.testing.assert_array_equal(before, after)


def test_acquisition_creates_missing_output_directory_before_disk_check(tmp_path: Path):
    grid = build_grid(AOI)
    output = tmp_path / "missing" / "nested" / "before_vv_vh.tif"

    class FakeClient:
        def request_raster(self, scene_id, payload):
            return raster_bytes(width=grid.width, height=grid.height, transform=grid.transform)

    record = acquire_scene(FakeClient(), SCENE, AOI, grid, output, START, END)
    assert record["validation"]["valid"] is True
    assert output.exists()


def test_invalid_raster_diagnostic_is_preserved_separately(tmp_path: Path):
    grid = build_grid(AOI)
    output = tmp_path / "production" / "before_vv_vh.tif"
    diagnostic = tmp_path / "diagnostics" / "before_rejected.tif"

    class FakeClient:
        last_response_content_type = "image/tiff"

        def request_raster(self, scene_id, payload):
            return raster_bytes(width=4, height=3, transform=grid.transform)

    try:
        acquire_scene(
            FakeClient(), SCENE, AOI, grid, output, START, END,
            preserve_invalid_diagnostic=diagnostic,
        )
    except Exception as exc:
        assert getattr(exc, "diagnostics")["preserved"] is True
    else:
        raise AssertionError("expected strict validation failure")
    assert diagnostic.exists()
    assert not output.exists()
    assert not output.with_suffix(output.suffix + ".part").exists()
    report = __import__("json").loads(diagnostic.with_suffix(".json").read_text())
    assert report["production_output"] is False
    assert report["expected_grid"]["width"] == grid.width
    assert "secret" not in str(report).lower()


def test_json_error_is_not_preserved_as_tiff(tmp_path: Path):
    grid = build_grid(AOI)
    diagnostic = tmp_path / "diagnostics" / "before_rejected.tif"

    class FakeClient:
        last_response_content_type = "application/json"

        def request_raster(self, scene_id, payload):
            return b'{"error":"secret-token"}'

    try:
        acquire_scene(
            FakeClient(), SCENE, AOI, grid, tmp_path / "before.tif",
            START, END, preserve_invalid_diagnostic=diagnostic,
        )
    except Exception as exc:
        assert getattr(exc, "diagnostics")["preserved"] is False
        assert "secret-token" not in str(exc.diagnostics)
    else:
        raise AssertionError("expected JSON response failure")
    assert not diagnostic.exists()
    assert not diagnostic.with_suffix(".json").exists()


def test_existing_before_validation_requires_recorded_checksum(tmp_path: Path):
    script_path = Path(__file__).parents[1] / "scripts" / "phase10d_acquire.py"
    spec = importlib.util.spec_from_file_location("phase10d_acquire", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    grid = build_grid(AOI)
    path = tmp_path / "before.tif"
    path.write_bytes(raster_bytes(width=grid.width, height=grid.height, transform=grid.transform))
    manifest = {"scenes": {"before": {"scene_id": module.BEFORE_ID}}}
    try:
        module.validate_existing_before_artifact(path, manifest, AOI, grid)
    except Exception as exc:
        assert "MISSING_MANIFEST_EVIDENCE" in str(exc)
    else:
        raise AssertionError("expected recorded checksum mismatch")


def test_reconciliation_rejects_wrong_checksum_without_modifying_raster(tmp_path: Path):
    script_path = Path(__file__).parents[1] / "scripts" / "phase10d_acquire.py"
    spec = importlib.util.spec_from_file_location("phase10d_reconcile", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    aoi_path = tmp_path / "aoi.json"
    aoi_path.write_text(__import__("json").dumps(AOI))
    output = tmp_path / "before.tif"
    content = raster_bytes(width=4, height=3)
    output.write_bytes(content)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(__import__("json").dumps({"scenes": {"before": {}}}))
    try:
        module.reconcile_before_artifact(manifest_path, aoi_path, output, "wrong")
    except Exception as exc:
        assert "SHA-256" in str(exc)
    else:
        raise AssertionError("expected reconciliation checksum failure")
    assert output.read_bytes() == content


def test_reconciliation_preserves_prior_failure_history(tmp_path: Path):
    script_path = Path(__file__).parents[1] / "scripts" / "phase10d_acquire.py"
    spec = importlib.util.spec_from_file_location("phase10d_reconcile_history", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    grid = build_grid(AOI)
    aoi_path = tmp_path / "aoi.json"
    aoi_path.write_text(__import__("json").dumps(AOI))
    output = tmp_path / "before.tif"
    output.write_bytes(raster_bytes(width=grid.width, height=grid.height, transform=grid.transform))
    import hashlib
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(__import__("json").dumps({
        "scenes": {"before": {"scene_id": module.BEFORE_ID}},
        "status": "PARTIALLY_COMPLETED",
        "failures": ["old rejected attempt"],
    }))
    result = module.reconcile_before_artifact(manifest_path, aoi_path, output, checksum)
    assert result["scenes"]["before"]["status"] == "VALIDATED"
    assert result["attempt_history"][0]["failures"] == ["old rejected attempt"]
    assert result["scenes"]["before"]["network_request"] is False


def test_pair_reconciliation_validates_hashes_grids_and_preserves_failures(tmp_path: Path):
    script_path = Path(__file__).parents[1] / "scripts" / "phase10d_reconcile_pair.py"
    spec = importlib.util.spec_from_file_location("phase10d_pair", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    grid = build_grid(AOI)
    aoi_path = tmp_path / "aoi.json"
    aoi_path.write_text(__import__("json").dumps(AOI))
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    before_path = output_dir / "before_vv_vh.tif"
    after_path = output_dir / "after_vv_vh.tif"
    before_path.write_bytes(raster_bytes(width=grid.width, height=grid.height, transform=grid.transform))
    after_path.write_bytes(raster_bytes(width=grid.width, height=grid.height, transform=grid.transform))
    import hashlib
    before_hash = hashlib.sha256(before_path.read_bytes()).hexdigest()
    after_hash = hashlib.sha256(after_path.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(__import__("json").dumps({
        "scenes": {
            "before": {"scene_id": module.BEFORE_ID},
            "after": {"scene_id": module.AFTER_ID},
        },
        "status": "AFTER_ONLY_REAL_EXECUTED",
        "failures": ["stale rejected BEFORE"],
        "request_diagnostics": {"production_output": False},
    }))
    result = module.reconcile_pair(manifest_path, aoi_path, output_dir, before_hash, after_hash)
    assert result["status"] == "PAIR_ACQUIRED_AND_VALIDATED"
    assert result["failures"] == []
    assert result["scenes"]["before"]["status"] == "VALIDATED"
    assert result["scenes"]["after"]["status"] == "VALIDATED"
    assert result["attempt_history"][0]["failures"] == ["stale rejected BEFORE"]
    assert result["attempt_history"][0]["request_diagnostics"] == {"production_output": False}
    assert result["reconciliation"]["network_request"] is False
    assert before_path.exists() and after_path.exists()


def test_pair_reconciliation_rejects_wrong_provenance_and_checksum(tmp_path: Path):
    script_path = Path(__file__).parents[1] / "scripts" / "phase10d_reconcile_pair.py"
    spec = importlib.util.spec_from_file_location("phase10d_pair_failure", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(__import__("json").dumps({
        "scenes": {"before": {"scene_id": "wrong"}, "after": {"scene_id": module.AFTER_ID}}
    }))
    aoi_path = tmp_path / "aoi.json"
    aoi_path.write_text(__import__("json").dumps(AOI))
    try:
        module.reconcile_pair(manifest_path, aoi_path, tmp_path, "a", "b")
    except Exception as exc:
        assert "provenance" in str(exc)
    else:
        raise AssertionError("expected provenance failure")


def test_pair_reconciliation_rejects_missing_or_misaligned_artifacts(tmp_path: Path):
    script_path = Path(__file__).parents[1] / "scripts" / "phase10d_reconcile_pair.py"
    spec = importlib.util.spec_from_file_location("phase10d_pair_missing", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    grid = build_grid(AOI)
    aoi_path = tmp_path / "aoi.json"
    aoi_path.write_text(__import__("json").dumps(AOI))
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    before = output_dir / "before_vv_vh.tif"
    before.write_bytes(raster_bytes(width=grid.width, height=grid.height, transform=grid.transform))
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(__import__("json").dumps({
        "scenes": {
            "before": {"scene_id": module.BEFORE_ID},
            "after": {"scene_id": module.AFTER_ID},
        }
    }))
    try:
        import hashlib
        before_hash = hashlib.sha256(before.read_bytes()).hexdigest()
        module.reconcile_pair(manifest_path, aoi_path, output_dir, before_hash, "b")
    except Exception as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("expected missing AFTER failure")
    after = output_dir / "after_vv_vh.tif"
    after.write_bytes(raster_bytes(
        width=grid.width, height=grid.height,
        transform=(20, 0, grid.bounds[0] + 1, 0, -20, grid.bounds[3], 0, 0, 1),
    ))
    after_hash = hashlib.sha256(after.read_bytes()).hexdigest()
    try:
        module.reconcile_pair(manifest_path, aoi_path, output_dir, before_hash, after_hash)
    except Exception as exc:
        assert "failed strict validation" in str(exc)
    else:
        raise AssertionError("expected misaligned AFTER failure")


def test_conflicting_execution_modes_are_rejected_before_network():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/phase10d_acquire.py",
            "--before-only",
            "--after-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "not allowed with argument" in result.stderr


def test_budget_rejects_before_request(tmp_path: Path):
    class NeverCalled:
        def request_raster(self, scene_id, payload):
            raise AssertionError("request must not be made")

    grid = build_grid(AOI)
    output = tmp_path / "blocked.tif"
    try:
        acquire_scene(NeverCalled(), SCENE, AOI, grid, output, START, END, MAX_STORAGE_BYTES)
    except Exception as exc:
        assert "storage budget" in str(exc)
    else:
        raise AssertionError("expected storage budget failure")


def test_token_diagnostic_redacts_access_token():
    class Response:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"access_token":"secret","token_type":"Bearer","expires_in":1800}'

    import floodlens.satellite.auth as auth_module
    original = auth_module.urlopen
    auth_module.urlopen = lambda request, timeout: Response()
    try:
        report = CopernicusAuthenticator("id", "secret").diagnose_token_request()
    finally:
        auth_module.urlopen = original
    assert report["status"] == "TOKEN_RECEIVED"
    assert report["access_token_key_present"] is True
    assert report["expires_in"] == 1800
    assert "access_token" not in report


def test_process_api_unauthorized_is_classified_separately():
    from urllib.error import HTTPError
    from floodlens.satellite.errors import ProcessAPIAuthError

    class Authenticator:
        def get_token(self):
            return "test-token"

    def opener(request, timeout):
        raise HTTPError(request.full_url, 401, "unauthorized", {}, None)

    client = ProcessAPIClient(Authenticator(), opener=opener)
    try:
        client.request_raster(SCENE, {})
    except ProcessAPIAuthError as exc:
        assert "HTTP 401" in str(exc)
    else:
        raise AssertionError("expected ProcessAPIAuthError")


def test_process_api_failure_records_sanitized_http_diagnostics():
    from io import BytesIO
    from urllib.error import HTTPError
    from floodlens.satellite.errors import ProcessAPIRequestError

    class Authenticator:
        def get_token(self):
            return "test-token"

    def opener(request, timeout):
        raise HTTPError(
            request.full_url,
            400,
            "bad request",
            {"Content-Type": "application/json"},
            BytesIO(
                b'{"error":"InvalidDataFilter","message":"ids unsupported","access_token":"secret"}'
            ),
        )

    client = ProcessAPIClient(Authenticator(), opener=opener)
    try:
        client.request_raster(SCENE, {})
    except ProcessAPIRequestError as exc:
        assert exc.diagnostics["stage"] == "http_submission_or_response"
        assert exc.diagnostics["endpoint"] == "https://sh.dataspace.copernicus.eu/process/v1"
        assert exc.diagnostics["http_status"] == 400
        assert exc.diagnostics["content_type"] == "application/json"
        assert exc.diagnostics["response_body_received"] is True
        assert exc.diagnostics["error_fields"]["error"] == "InvalidDataFilter"
        assert "secret" not in str(exc.diagnostics)
    else:
        raise AssertionError("expected ProcessAPIRequestError")


def test_stac_uniqueness_check_requires_expected_scene_and_metadata():
    class Response:
        headers = {"Content-Type": "application/geo+json"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return __import__("json").dumps({
                "features": [{
                    "id": SCENE,
                    "geometry": AOI,
                    "assets": {"vv": {}, "vh": {}},
                    "properties": {
                        "datetime": "2026-08-16T12:21:41.058298Z",
                        "platform": "sentinel-1d",
                        "sar:instrument_mode": "IW",
                        "sat:orbit_state": "ascending",
                        "sat:relative_orbit": 85,
                        "sar:polarizations": ["VV", "VH"],
                    },
                }],
            }).encode()

    report = verify_stac_candidate(AOI, SCENE, START, END, opener=lambda request, timeout: Response())
    assert report["status"] == "VERIFIED_UNIQUE"
    assert report["distinct_acquisition_count"] == 1


def test_stac_uniqueness_check_rejects_ambiguous_window():
    from floodlens.satellite.errors import CatalogUnavailableError

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            features = []
            for index, scene_id in enumerate((SCENE, "other-scene")):
                features.append({
                    "id": scene_id,
                    "geometry": AOI,
                    "assets": {"vv": {}, "vh": {}},
                    "properties": {
                        "datetime": f"2026-08-16T12:21:{41 + index:02d}Z",
                        "platform": "sentinel-1d",
                        "sar:instrument_mode": "IW",
                        "sat:orbit_state": "ascending",
                        "sat:relative_orbit": 85,
                        "sar:polarizations": ["VV", "VH"],
                    },
                })
            return __import__("json").dumps({"features": features}).encode()

    try:
        verify_stac_candidate(AOI, SCENE, START, END, opener=lambda request, timeout: Response())
    except CatalogUnavailableError as exc:
        assert "items for the narrow window" in str(exc)
    else:
        raise AssertionError("expected ambiguous STAC window to be rejected")
