"""End-to-end RescueX run orchestration.

The fixture path intentionally reuses the existing geometry analysis modules.
Real satellite/model execution is refused until verified artifacts are
available; a run is never labelled REAL by default.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .analysis import run_analysis
from .models import RunRequest
from .phase4 import DEVELOPMENT_FIXTURE_LABEL, classify_phase3_artifacts
from .report import ATTRIBUTIONS, situation_report


class ProcessingStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATING_INPUT = "VALIDATING_INPUT"
    DISCOVERING_SATELLITES = "DISCOVERING_SATELLITES"
    SELECTING_SCENES = "SELECTING_SCENES"
    DOWNLOADING = "DOWNLOADING"
    PREPROCESSING = "PREPROCESSING"
    AI_INFERENCE = "AI_INFERENCE"
    FLOOD_ANALYSIS = "FLOOD_ANALYSIS"
    INFRASTRUCTURE_ANALYSIS = "INFRASTRUCTURE_ANALYSIS"
    CONNECTIVITY_ANALYSIS = "CONNECTIVITY_ANALYSIS"
    GENERATING_REPORT = "GENERATING_REPORT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    DEMO_FIXTURE = "DEMO_FIXTURE"


class PipelineRequest(RunRequest):
    execution_mode: Literal["FIXTURE", "REAL"] = "FIXTURE"
    source_manifest: dict[str, Any] = Field(default_factory=dict)


class ProcessingRun(BaseModel):
    run_id: str
    aoi: dict[str, Any]
    event_date: date
    created_at: datetime
    updated_at: datetime
    status: ProcessingStatus
    current_step: str
    progress: float = Field(ge=0, le=1)
    input_sources: dict[str, Any] = Field(default_factory=dict)
    selected_scenes: dict[str, Any] = Field(default_factory=dict)
    preprocessing_outputs: dict[str, Any] = Field(default_factory=dict)
    model_output: dict[str, Any] = Field(default_factory=dict)
    impact_outputs: dict[str, Any] = Field(default_factory=dict)
    connectivity_outputs: dict[str, Any] = Field(default_factory=dict)
    map_layers: dict[str, Any] = Field(default_factory=dict)
    report_output: str | None = None
    results: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    execution_mode: str
    history: list[dict[str, Any]] = Field(default_factory=list)


class RescueXPipeline:
    def __init__(self, artifact_root=None):
        from pathlib import Path
        self.artifact_root = Path(artifact_root or ".")

    def _transition(self, run: ProcessingRun, status: ProcessingStatus, step: str, progress: float) -> None:
        now = datetime.now(timezone.utc)
        run.status = status
        run.current_step = step
        run.progress = progress
        run.updated_at = now
        run.history.append({"status": status.value, "step": step, "progress": progress, "at": now.isoformat()})

    def execute(self, request: PipelineRequest) -> ProcessingRun:
        now = datetime.now(timezone.utc)
        run = ProcessingRun(
            run_id=str(uuid4()), aoi=request.aoi, event_date=request.event_date,
            created_at=now, updated_at=now, status=ProcessingStatus.CREATED,
            current_step="created", progress=0, execution_mode=request.execution_mode,
            input_sources=request.source_manifest,
            provenance={"attributions": ATTRIBUTIONS, "pipeline_version": "phase6-v1"},
        )
        try:
            self._transition(run, ProcessingStatus.VALIDATING_INPUT, "validate_inputs", .05)
            if request.execution_mode == "REAL":
                artifacts = classify_phase3_artifacts(self.artifact_root)
                if not artifacts["real_checkpoint_exists"] or not artifacts["real_georeferenced_mask_exists"]:
                    raise RuntimeError(
                        "REAL execution unavailable: no verified Phase 3 checkpoint and georeferenced flood mask exist"
                    )
            self._transition(run, ProcessingStatus.DEMO_FIXTURE if request.execution_mode == "FIXTURE" else ProcessingStatus.DISCOVERING_SATELLITES, "discover_data", .15)
            if request.execution_mode == "FIXTURE":
                for status, step, progress in (
                    (ProcessingStatus.SELECTING_SCENES, "select_scenes", .22),
                    (ProcessingStatus.DOWNLOADING, "fixture_inputs_no_download", .28),
                    (ProcessingStatus.PREPROCESSING, "fixture_inputs_already_prepared", .34),
                    (ProcessingStatus.AI_INFERENCE, "real_model_inference_not_available", .4),
                ):
                    self._transition(run, status, step, progress)
                run.warnings.extend([
                    DEVELOPMENT_FIXTURE_LABEL,
                    "Satellite discovery/download was not executed in fixture mode",
                    "AI inference was not executed; flood zones are controlled fixture inputs",
                ])
                self._transition(run, ProcessingStatus.FLOOD_ANALYSIS, "use_explicit_fixture_inputs", .45)
                results = run_analysis(request)
                run.results = results
                run.impact_outputs = results.get("infrastructure", {})
                run.connectivity_outputs = results.get("network", {})
                run.map_layers = {
                    "flood_zones": {
                        "type": "FeatureCollection",
                        "features": [
                            {"type": "Feature", "geometry": geometry, "properties": {"classification": "fixture"}}
                            for geometry in request.flood_zones
                        ],
                    }
                }
                run.model_output = {"status": "NOT_YET_AVAILABLE", "classification": "synthetic fixture input"}
                self._transition(run, ProcessingStatus.GENERATING_REPORT, "generate_report", .9)
                run.report_output = situation_report(request.event_date, results)
                self._transition(run, ProcessingStatus.COMPLETED, "completed_fixture_run", 1)
                return run
            self._transition(run, ProcessingStatus.FAILED, "real_execution_unavailable", 1)
            return run
        except Exception as exc:
            run.errors.append(str(exc))
            self._transition(run, ProcessingStatus.FAILED, "failed", 1)
            return run
