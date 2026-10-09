from floodlens.models import Point, Road
from floodlens.network import connectivity_analysis


def road(id, start, end):
    return Road(id=id, start=start, end=end, length_m=1, geometry=[Point(id=id+"a",x=0,y=0), Point(id=id+"b",x=1,y=1)])


def test_alternate_route_prevents_false_cutoff():
    result = connectivity_analysis(
        [road("blocked", "village", "town"), road("alternate", "village", "town")],
        [Point(id="village",x=0,y=0)],
        [Point(id="town",x=1,y=1)],
        {"blocked"},
    )
    assert result["cut_off_count"] == 0
    assert result["settlements"][0]["post_event_connected"] is True


def test_cutoff_requires_baseline_connection():
    result = connectivity_analysis(
        [road("blocked", "village", "town")],
        [Point(id="village",x=0,y=0), Point(id="isolated",x=4,y=4)],
        [Point(id="town",x=1,y=1)],
        {"blocked"},
    )
    assert result["cut_off_count"] == 1
    assert result["settlements"][1]["cut_off"] is False
