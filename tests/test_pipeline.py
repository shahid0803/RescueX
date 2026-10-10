from datetime import date

from floodlens.pipeline import PipelineRequest, ProcessingStatus, RescueXPipeline, result_classification


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
    assert result_classification(run) == "REAL EXECUTION INCOMPLETE — NO VERIFIED RESULT"


def test_fixture_result_is_not_real():
    run = RescueXPipeline().execute(fixture_request())
    assert result_classification(run) == "DEVELOPMENT FIXTURE — NOT REAL SATELLITE RESULT"


def test_real_result_requires_verified_outputs():
    request = fixture_request("REAL")
    run = RescueXPipeline().execute(request)
    run.status = ProcessingStatus.COMPLETED
    run.provenance["real_outputs_verified"] = False
    assert result_classification(run) == "REAL EXECUTION INCOMPLETE — NO VERIFIED RESULT"
