from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .analysis import run_analysis
from .models import RunRequest, RunResponse
from .report import ATTRIBUTIONS, situation_report
from .satellite.auth import CopernicusAuthenticator
from .satellite.download import DownloadService
from .satellite.models import SatelliteSearchRequest, SatelliteSearchResult
from .satellite.service import SatelliteService
from .satellite.stac import CDSEStacProvider
from .raster import inspect_raster, qc_report
from .ml.inference import infer_geotiff
from .connectivity import BlockedRoadSet, ConnectivityConfig, ConnectivityAnalysisResult, analyze_connectivity
from .models import Point, Road
from .pipeline import PipelineRequest, ProcessingRun, RescueXPipeline
from .report import processing_report

app = FastAPI(title="RescueX API", version="0.1.0")
_runs: dict[str, dict] = {}
_frontend = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
_satellite_searches: dict[str, SatelliteSearchResult] = {}
_satellite_downloads: dict[str, dict] = {}
_preprocessing_runs: dict[str, dict] = {}
_connectivity_runs: dict[str, ConnectivityAnalysisResult] = {}
_pipeline_runs: dict[str, ProcessingRun] = {}


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(_frontend)


@app.post("/api/pipeline/runs", response_model=ProcessingRun)
def create_pipeline_run(request: PipelineRequest) -> ProcessingRun:
    run = RescueXPipeline().execute(request)
    _pipeline_runs[run.run_id] = run
    return run


@app.get("/api/pipeline/runs/{run_id}", response_model=ProcessingRun)
def get_pipeline_run(run_id: str) -> ProcessingRun:
    from fastapi import HTTPException
    if run_id not in _pipeline_runs:
        raise HTTPException(status_code=404, detail="pipeline run not found")
    return _pipeline_runs[run_id]


@app.get("/api/pipeline/runs/{run_id}/report")
def get_pipeline_report(run_id: str) -> dict[str, str]:
    from fastapi import HTTPException
    if run_id not in _pipeline_runs:
        raise HTTPException(status_code=404, detail="pipeline run not found")
    return {"run_id": run_id, "report": processing_report(_pipeline_runs[run_id].model_dump(mode="json"))}


@app.get("/api/pipeline/runs/{run_id}/layers")
def get_pipeline_layers(run_id: str) -> dict:
    from fastapi import HTTPException
    if run_id not in _pipeline_runs:
        raise HTTPException(status_code=404, detail="pipeline run not found")
    run = _pipeline_runs[run_id]
    return {
        "run_id": run_id,
        "classification": "DEVELOPMENT FIXTURE — NOT REAL SATELLITE RESULT"
        if run.execution_mode == "FIXTURE" else "REAL DATA RESULT",
        "layers": {
            **run.map_layers,
            "flood": run.model_output,
            "infrastructure": run.impact_outputs,
            "connectivity": run.connectivity_outputs,
        },
    }


@app.post("/api/v1/runs", response_model=RunResponse)
def create_run(request: RunRequest) -> RunResponse:
    run_id = str(uuid4())
    created_at = datetime.now(timezone.utc)
    results = run_analysis(request)
    provenance = {
        "aoi": request.aoi,
        "event_date": request.event_date.isoformat(),
        "source_manifest": request.source_manifest,
        "production_boundary": "pre-event OSM and caller-supplied satellite-derived mask only",
        "attributions": ATTRIBUTIONS,
    }
    payload = {
        "run_id": run_id,
        "created_at": created_at,
        "event_date": request.event_date,
        "results": results,
        "provenance": provenance,
        "report": situation_report(request.event_date, results),
    }
    _runs[run_id] = payload
    return RunResponse(**payload)


@app.get("/api/v1/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: str) -> RunResponse:
    from fastapi import HTTPException

    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="run not found")
    return RunResponse(**_runs[run_id])


@app.post("/api/satellite/search", response_model=SatelliteSearchResult)
def satellite_search(request: SatelliteSearchRequest) -> SatelliteSearchResult:
    result = SatelliteService(CDSEStacProvider()).search(request)
    search_id = result.provenance.get("query_timestamp", str(len(_satellite_searches)))
    _satellite_searches[str(search_id)] = result
    return result


@app.post("/api/satellite/select", response_model=SatelliteSearchResult)
def satellite_select(request: SatelliteSearchRequest) -> SatelliteSearchResult:
    return satellite_search(request)


@app.get("/api/satellite/scenes/{scene_id}")
def satellite_scene(scene_id: str) -> dict:
    for result in _satellite_searches.values():
        for scene in result.candidates_before + result.candidates_after:
            if scene.scene_id == scene_id:
                return scene.model_dump(mode="json")
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="scene not found")


class SatelliteDownloadRequest(BaseModel):
    scene_id: str


@app.post("/api/satellite/download")
def satellite_download(request: SatelliteDownloadRequest) -> dict:
    from fastapi import HTTPException

    scene = next(
        (
            scene
            for result in _satellite_searches.values()
            for scene in result.candidates_before + result.candidates_after
            if scene.scene_id == request.scene_id
        ),
        None,
    )
    if scene is None:
        raise HTTPException(status_code=404, detail="scene not found; search before downloading")
    try:
        downloaded = DownloadService(
            Path(".rescuex-data"), CopernicusAuthenticator.from_env()
        ).download(scene)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _satellite_downloads[scene.scene_id] = downloaded.model_dump(mode="json")
    return _satellite_downloads[scene.scene_id]


@app.get("/api/satellite/status/{scene_id}")
def satellite_status(scene_id: str) -> dict:
    if scene_id in _satellite_downloads:
        return _satellite_downloads[scene_id]
    return {"scene_id": scene_id, "download_status": "not_downloaded"}


class RasterInspectRequest(BaseModel):
    input_path: str


class RasterQCResponse(BaseModel):
    input_path: str
    report: dict


@app.post("/api/preprocessing/inspect")
def preprocessing_inspect(request: RasterInspectRequest) -> dict:
    return inspect_raster(Path(request.input_path)).__dict__


@app.post("/api/preprocessing/process")
def preprocessing_process(request: RasterInspectRequest) -> dict:
    from fastapi import HTTPException

    try:
        report = qc_report(Path(request.input_path))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    run_id = str(uuid4())
    _preprocessing_runs[run_id] = {"run_id": run_id, "status": "completed", "qc": report.__dict__}
    return _preprocessing_runs[run_id]


@app.get("/api/preprocessing/runs/{run_id}")
def preprocessing_run(run_id: str) -> dict:
    from fastapi import HTTPException

    if run_id not in _preprocessing_runs:
        raise HTTPException(status_code=404, detail="preprocessing run not found")
    return _preprocessing_runs[run_id]


@app.get("/api/preprocessing/products/{product_id}")
def preprocessing_product(product_id: str) -> dict:
    for run in _preprocessing_runs.values():
        if run.get("run_id") == product_id:
            return run
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="processed product not found")


class FloodSegmentationRequest(BaseModel):
    input_path: str
    checkpoint_path: str
    probability_output: str
    mask_output: str
    threshold: float = 0.5


@app.post("/api/ai/flood-segmentation")
def flood_segmentation(request: FloodSegmentationRequest) -> dict:
    from fastapi import HTTPException

    try:
        return infer_geotiff(
            Path(request.input_path),
            Path(request.checkpoint_path),
            Path(request.probability_output),
            Path(request.mask_output),
            request.threshold,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ConnectivityRequest(BaseModel):
    roads: list[Road]
    settlements: list[Point] = []
    towns: list[Point] = []
    hospitals: list[Point] = []
    blocked: BlockedRoadSet = BlockedRoadSet()
    config: ConnectivityConfig
    phase4_source: str = "fixture"


@app.post("/api/connectivity/analyze")
def connectivity_analyze(request: ConnectivityRequest) -> dict:
    from fastapi import HTTPException

    try:
        result = analyze_connectivity(
            request.roads, request.settlements, request.towns, request.hospitals,
            request.blocked, request.config, phase4_source=request.phase4_source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _connectivity_runs[result.run_id] = result
    return result.model_dump(mode="json")


@app.get("/api/connectivity/runs/{run_id}")
def connectivity_run(run_id: str) -> dict:
    from fastapi import HTTPException

    if run_id not in _connectivity_runs:
        raise HTTPException(status_code=404, detail="connectivity run not found")
    return _connectivity_runs[run_id].model_dump(mode="json")


@app.get("/api/connectivity/summary/{run_id}")
def connectivity_summary(run_id: str) -> dict:
    from fastapi import HTTPException

    if run_id not in _connectivity_runs:
        raise HTTPException(status_code=404, detail="connectivity run not found")
    return _connectivity_runs[run_id].summary


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("floodlens.api:app", host="127.0.0.1", port=8000, reload=False)
