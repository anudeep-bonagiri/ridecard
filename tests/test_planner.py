import datetime as dt
from ridecard import planner


def test_resolve_day():
    tue = dt.date(2026, 10, 6)
    assert planner.resolve_day("saturday", tue) == "2026-10-10"
    assert planner.resolve_day("tomorrow", tue) == "2026-10-07"
    assert planner.resolve_day("tuesday", tue) == "2026-10-06"


def test_keyword_parse_and_rank_offline():
    req = planner.parse_request("3 hours from Boerne, bats and history", use_llm=False)
    assert req["start"] == "Boerne" and req["hours"] == 3
    best = planner.rank(req, offline=True)[0]
    assert best["ride"]["id"] == "old-tunnel-luckenbach"


def test_go_call():
    assert planner.go_call({"rain_pct": 70, "gust_mph": 10, "low_f": 60, "high_f": 80}).startswith("THINK TWICE")
    assert planner.go_call({"rain_pct": 0, "gust_mph": 10, "low_f": 60, "high_f": 80}).startswith("GO")
