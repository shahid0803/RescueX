from datetime import date

from floodlens.pipeline import PipelineRequest, ProcessingStatus, RescueXPipeline


def fixture_request(mode="FIXTURE"):
    return PipelineRequest(
        aoi={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
        event_date=date(2026, 8, 15),
        flood_zones=[{"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}],
        execution_mode=mode,
    )


def test_fixture_pipeline_has_explicit_status_and_report():
    run = RescueXPipeline().execute(fixture_request())
    assert run.status == ProcessingStatus.COMPLETED
    assert run.execution_mode == "FIXTURE"
    assert "DEVELOPMENT FIXTURE" in run.warnings[0]
    assert run.report_output is not None
    assert [item["status"] for item in run.history][0] == "VALIDATING_INPUT"
    assert run.map_layers["flood_zones"]["features"]


def test_real_pipeline_refuses_without_verified_artifacts(tmp_path):
    run = RescueXPipeline(tmp_path).execute(fixture_request("REAL"))
    assert run.status == ProcessingStatus.FAILED
    assert "REAL execution unavailable" in run.errors[0]
