"""Cost arithmetic, SQL definitions and the ROI method."""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tokenroi import data, roi, warehouse

SQL = Path(__file__).resolve().parents[1] / "sql"


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    path = warehouse.build(tmp_path_factory.mktemp("wh") / "test.db", export=False)
    return sqlite3.connect(path)


def test_price_matches_hand_calculation():
    # 1M input (half cached) + 0.5M output on the large model: 0.5*4 + 0.5*4*0.1 + 0.5*20
    assert data.price(["large"], [1_000_000], [500_000], [500_000])[0] == pytest.approx(2.0 + 0.2 + 10.0)
    assert data.price(["small"], [0], [0], [0])[0] == 0


def test_generator_is_reproducible_and_internally_consistent():
    a, b = data.generate(5), data.generate(5)
    pd.testing.assert_frame_equal(a["fact_usage_daily"], b["fact_usage_daily"])
    u = a["fact_usage_daily"]
    assert (u["cached_input_tokens"] <= u["input_tokens"]).all() and (u["attempts"] >= u["requests"]).all()
    assert np.allclose(u["cost_gbp"], data.price(u["model_tier"], u["input_tokens"], u["cached_input_tokens"],
                                                 u["output_tokens"]), atol=1e-3)
    sup = u[u.team_id == 1]
    assert sup.loc[sup.date < data.CACHING_LIVE, "cached_input_tokens"].sum() == 0
    assert sup.loc[sup.date >= data.CACHING_LIVE, "cached_input_tokens"].sum() > 0


def test_sql_views_agree_with_pandas(con):
    sql = pd.read_sql(open(SQL / "02_unit_cost_q3.sql").read(), con).set_index("team")
    u = pd.read_sql("SELECT * FROM fact_usage_daily WHERE date >= '2026-07-01'", con)
    o = pd.read_sql("SELECT * FROM fact_outcomes_weekly WHERE week_start >= '2026-07-01'", con)
    t = pd.read_sql("SELECT team_id, team FROM dim_team", con).set_index("team_id")["team"]
    expected = (u.groupby("team_id")["cost_gbp"].sum() / o.groupby("team_id")["ai_assisted_outcomes"].sum()).rename(t)
    for team, v in expected.items():
        assert sql.loc[team, "token_cost_per_outcome_gbp"] == pytest.approx(v, abs=6e-5)  # SQL rounds to 4 dp


def test_every_sql_file_runs(con):
    for f in sorted(SQL.glob("0[1-9]*.sql")):
        assert len(pd.read_sql(f.read_text(), con)) > 0, f.name


def test_caching_halves_support_cost_per_request(con):
    r = pd.read_sql(open(SQL / "04_caching_before_after.sql").read(), con).set_index("period")
    assert r.loc["after caching", "cost_per_1k_requests_gbp"] < 0.6 * r.loc["before caching", "cost_per_1k_requests_gbp"]


def test_retry_storm_is_the_largest_waste(con):
    r = pd.read_sql(open(SQL / "03_retry_waste.sql").read(), con)
    assert r.iloc[0]["team"] == "Engineering" and r.iloc[0]["month"] == "2026-05"


def test_pilot_effect_recovers_a_known_difference():
    rng = np.random.default_rng(0)
    p = pd.DataFrame({"team_id": 1, "arm": np.repeat(["control", "ai_assisted"], 2000),
                      "handle_minutes": np.r_[rng.normal(20, 4, 2000), rng.normal(15, 4, 2000)]})
    fx = roi.pilot_effect(p, n_boot=500).iloc[0]
    assert fx.ci_low < 5 < fx.ci_high and abs(fx.minutes_saved - 5) < 0.5


def test_survey_haircut_is_learnt_from_pilot_teams_only():
    fx = pd.DataFrame({"team_id": [1], "minutes_saved": [3.0], "ci_low": [2.5], "ci_high": [3.5]})
    survey = pd.DataFrame({"team_id": [1, 2], "self_reported_minutes_saved": [6.0, 10.0]})
    ts, haircut = roi.time_saved(fx, survey)
    assert haircut == pytest.approx(0.5)
    ts = ts.set_index("team_id")
    assert ts.loc[1, "minutes_saved"] == 3.0 and ts.loc[2, "minutes_saved"] == pytest.approx(5.0)
    assert ts.loc[2, "minutes_low"] < 5.0 < ts.loc[2, "minutes_high"]


def test_platform_cost_is_fully_allocated_and_roi_is_consistent(con):
    t, _ = roi.roi_table(con)
    assert t["platform_cost_gbp"].sum() == pytest.approx(3 * data.PLATFORM_COST_GBP_PER_MONTH)
    assert (t["roi_low"] <= t["roi"]).all() and (t["roi"] <= t["roi_high"]).all()
    assert (t["roi_if_survey_believed"] > t["roi"]).all()


def test_routing_never_trades_away_more_than_the_tolerance(con):
    s = roi.savings(con)
    for d in s["routing_decisions"]:
        assert d["quality_to"] >= d["quality_from"] - roi.QUALITY_TOLERANCE - 1e-9
    assert 0 < s["q3_cost_after_both_gbp"] < s["q3_token_cost_gbp"]
