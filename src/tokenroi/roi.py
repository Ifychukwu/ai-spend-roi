"""Return on AI spend per team, and where the money could be saved.

Usage:   python -m tokenroi.roi
Outputs: reports/metrics.json, reports/roi_q3_2026.csv, reports/figures/*.png

Method, in the order a finance partner would ask:
1. **Cost.** Token cost from metered usage, plus the platform team's cost allocated
   by request share (total cost of ownership, not just the API bill).
2. **Time saved per outcome.** Measured by a randomised pilot where one exists
   (Customer Support, Claims). Elsewhere, the team's self-reported figure is
   scaled down by how much pilot teams over-reported (the survey-to-pilot ratio).
3. **Value.** Minutes saved × loaded hourly cost × AI-assisted outcomes.
4. **ROI** = (value − total cost) / total cost, with a 95% interval carried from
   the pilot estimate (and widened for teams that rely on the survey adjustment).
5. **Savings.** Prompt caching where a large fixed prompt is resent, routing to a
   cheaper model where offline quality drops by no more than 2 points, and the
   one-off cost of the May retry storm.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from tokenroi.data import CACHED_INPUT_DISCOUNT, FEATURES, MODELS, PLATFORM_COST_GBP_PER_MONTH, RETRY_STORM, price  # noqa: E402
from tokenroi.warehouse import connect  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FIG = ROOT / "reports" / "figures"
Q3 = ("2026-07-01", "2026-09-30")
QUALITY_TOLERANCE = 0.02


def pilot_effect(pilot: pd.DataFrame, n_boot: int = 4000, seed: int = 0) -> pd.DataFrame:
    """Minutes saved per item = mean(control) − mean(AI-assisted), with a bootstrap 95% interval."""
    rng = np.random.default_rng(seed)
    rows = []
    for team_id, g in pilot.groupby("team_id"):
        c = g.loc[g.arm == "control", "handle_minutes"].to_numpy()
        t = g.loc[g.arm == "ai_assisted", "handle_minutes"].to_numpy()
        boots = [rng.choice(c, len(c)).mean() - rng.choice(t, len(t)).mean() for _ in range(n_boot)]
        rows.append({"team_id": team_id, "minutes_saved": c.mean() - t.mean(),
                     "ci_low": np.percentile(boots, 2.5), "ci_high": np.percentile(boots, 97.5),
                     "n_control": len(c), "n_ai": len(t)})
    return pd.DataFrame(rows)


def time_saved(pilot_fx: pd.DataFrame, survey: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Best estimate of minutes saved per outcome for every team, and the survey haircut used."""
    s = survey.merge(pilot_fx, on="team_id", how="left")
    ratio = (s["minutes_saved"] / s["self_reported_minutes_saved"]).dropna()
    haircut = float(ratio.mean())
    spread = float(ratio.max() - ratio.min()) / 2 + 0.10      # extra uncertainty when relying on the haircut
    s["method"] = np.where(s["minutes_saved"].notna(), "randomised pilot", "survey x pilot haircut")
    est = np.where(s["minutes_saved"].notna(), s["minutes_saved"], s["self_reported_minutes_saved"] * haircut)
    lo = np.where(s["minutes_saved"].notna(), s["ci_low"], s["self_reported_minutes_saved"] * max(haircut - spread, 0))
    hi = np.where(s["minutes_saved"].notna(), s["ci_high"], s["self_reported_minutes_saved"] * (haircut + spread))
    out = s[["team_id", "self_reported_minutes_saved"]].assign(minutes_saved=est, minutes_low=lo, minutes_high=hi,
                                                               method=s["method"])
    return out, haircut


def roi_table(con, start=Q3[0], end=Q3[1]) -> tuple[pd.DataFrame, dict]:
    teams = pd.read_sql("SELECT * FROM dim_team", con)
    usage = pd.read_sql("SELECT * FROM fact_usage_daily WHERE date BETWEEN ? AND ?", con, params=(start, end))
    outc = pd.read_sql("SELECT * FROM fact_outcomes_weekly WHERE week_start BETWEEN ? AND ?", con, params=(start, end))
    pilot = pd.read_sql("SELECT * FROM pilot_items", con)
    survey = pd.read_sql("SELECT * FROM survey_time_saved", con)
    months = pd.date_range(start, end, freq="MS").size

    fx = pilot_effect(pilot)
    ts, haircut = time_saved(fx, survey)
    cost = usage.groupby("team_id").agg(token_cost_gbp=("cost_gbp", "sum"), requests=("requests", "sum"))
    cost["platform_cost_gbp"] = PLATFORM_COST_GBP_PER_MONTH * months * cost["requests"] / cost["requests"].sum()
    cost["total_cost_gbp"] = cost["token_cost_gbp"] + cost["platform_cost_gbp"]
    o = outc.groupby("team_id")[["outcomes", "ai_assisted_outcomes"]].sum()
    t = teams.set_index("team_id").join(cost).join(o).join(ts.set_index("team_id"))
    hours = t["ai_assisted_outcomes"] / 60
    t["value_gbp"] = hours * t["minutes_saved"] * t["loaded_hourly_cost_gbp"]
    t["value_low_gbp"] = hours * t["minutes_low"] * t["loaded_hourly_cost_gbp"]
    t["value_high_gbp"] = hours * t["minutes_high"] * t["loaded_hourly_cost_gbp"]
    t["value_if_survey_believed_gbp"] = hours * t["self_reported_minutes_saved"] * t["loaded_hourly_cost_gbp"]
    t["token_cost_per_outcome_gbp"] = t["token_cost_gbp"] / t["ai_assisted_outcomes"]
    t["total_cost_per_outcome_gbp"] = t["total_cost_gbp"] / t["ai_assisted_outcomes"]
    t["value_per_outcome_gbp"] = t["value_gbp"] / t["ai_assisted_outcomes"]
    for k in ("", "_low", "_high"):
        t[f"roi{k}"] = (t[f"value{k}_gbp"] - t["total_cost_gbp"]) / t["total_cost_gbp"]
    t["roi_if_survey_believed"] = (t["value_if_survey_believed_gbp"] - t["total_cost_gbp"]) / t["total_cost_gbp"]
    t["hours_saved"] = hours * t["minutes_saved"]
    pilot_rows = fx.merge(teams[["team_id", "team"]]).round(2).to_dict(orient="records")
    return t.reset_index(), {"pilot": pilot_rows, "survey_haircut": round(haircut, 3)}


def savings(con, start=Q3[0], end=Q3[1]) -> dict:
    """What Q3 would have cost with caching everywhere it applies and quality-safe model routing."""
    u = pd.read_sql("""SELECT u.*, f.feature, f.system_prompt_tokens FROM fact_usage_daily u
                       JOIN dim_feature f USING (feature_id) WHERE date BETWEEN ? AND ?""", con, params=(start, end))
    q = pd.read_sql("SELECT * FROM model_quality", con).set_index(["feature", "model_tier"])["acceptance_rate"]
    base = u["cost_gbp"].sum()

    # Caching: cache the fixed prompt (93% hit rate, as observed in Support) where it is not cached yet.
    cached = u.copy()
    sys_tok = cached["attempts"] * cached["system_prompt_tokens"]
    todo = cached["cached_input_tokens"] == 0
    cached.loc[todo, "cached_input_tokens"] = (sys_tok[todo] * 0.93).round()
    cached["cost_gbp"] = price(cached["model_tier"], cached["input_tokens"], cached["cached_input_tokens"], cached["output_tokens"])
    by_feature_cache = (u.groupby("feature")["cost_gbp"].sum() - cached.groupby("feature")["cost_gbp"].sum())

    # Routing: cheapest tier within the quality tolerance of the tier in use (no re-routing to better models).
    order = list(MODELS.sort_values("input_gbp_per_mtok")["model_tier"])   # cheapest first
    decisions, routed = [], cached.copy()
    for (feat, tier), g in cached.groupby(["feature", "model_tier"]):
        cur = q[(feat, tier)]
        choice = next(m for m in order if q[(feat, m)] >= cur - QUALITY_TOLERANCE)
        if order.index(choice) > order.index(tier):
            choice = tier
        routed.loc[g.index, "model_tier"] = choice
        decisions.append({"feature": feat, "from": tier, "to": choice, "quality_from": cur, "quality_to": q[(feat, choice)]})
    routed["cost_gbp"] = price(routed["model_tier"], routed["input_tokens"], routed["cached_input_tokens"], routed["output_tokens"])
    by_feature_route = cached.groupby("feature")["cost_gbp"].sum() - routed.groupby("feature")["cost_gbp"].sum()

    storm = pd.read_sql("""SELECT * FROM fact_usage_daily WHERE team_id = 3 AND date BETWEEN ? AND ?""", con,
                        params=(RETRY_STORM[0].strftime("%Y-%m-%d"), RETRY_STORM[1].strftime("%Y-%m-%d")))
    normal_attempts = storm["requests"] * (1 + 0.015)
    storm_waste = float((storm["cost_gbp"] * (storm["attempts"] - normal_attempts) / storm["attempts"]).sum())
    return {
        "q3_token_cost_gbp": round(base, 2),
        "caching_saving_gbp": round(float(by_feature_cache.sum()), 2),
        "caching_saving_by_feature_gbp": by_feature_cache[by_feature_cache > 1].round(2).sort_values(ascending=False).to_dict(),
        "routing_saving_gbp": round(float(by_feature_route.sum()), 2),
        "routing_saving_by_feature_gbp": by_feature_route[by_feature_route > 1].round(2).sort_values(ascending=False).to_dict(),
        "routing_decisions": [d for d in decisions if d["from"] != d["to"]],
        "q3_cost_after_both_gbp": round(float(routed["cost_gbp"].sum()), 2),
        "saving_pct": round(100 * (1 - routed["cost_gbp"].sum() / base), 1),
        "retry_storm_excess_cost_gbp": round(storm_waste, 2),
    }


def main() -> dict:
    con = connect()
    t, extra = roi_table(con)
    sv = savings(con)
    monthly = pd.read_sql("SELECT team, month, token_cost_gbp, monthly_budget_gbp FROM v_team_month", con)
    cols = ["team", "outcome_unit", "ai_assisted_outcomes", "token_cost_gbp", "platform_cost_gbp", "total_cost_gbp",
            "token_cost_per_outcome_gbp", "total_cost_per_outcome_gbp", "method", "self_reported_minutes_saved",
            "minutes_saved", "minutes_low", "minutes_high", "hours_saved", "value_gbp", "value_per_outcome_gbp",
            "roi", "roi_low", "roi_high", "roi_if_survey_believed"]
    table = t[cols].sort_values("roi", ascending=False)
    totals = {"token_cost_gbp": round(float(t["token_cost_gbp"].sum()), 2),
              "platform_cost_gbp": round(float(t["platform_cost_gbp"].sum()), 2),
              "total_cost_gbp": round(float(t["total_cost_gbp"].sum()), 2),
              "value_gbp": round(float(t["value_gbp"].sum()), 2),
              "value_if_survey_believed_gbp": round(float(t["value_if_survey_believed_gbp"].sum()), 2),
              "hours_saved": round(float(t["hours_saved"].sum()), 0)}
    totals["roi"] = round((totals["value_gbp"] - totals["total_cost_gbp"]) / totals["total_cost_gbp"], 3)
    totals["token_share_of_total_cost_pct"] = round(100 * totals["token_cost_gbp"] / totals["total_cost_gbp"], 1)
    results = {"period": "2026-Q3", "totals": totals, **extra, "teams": table.round(4).to_dict(orient="records"),
               "savings": sv,
               "over_budget_months": monthly[monthly.token_cost_gbp > monthly.monthly_budget_gbp]
               .round(2).to_dict(orient="records")}
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "metrics.json").write_text(json.dumps(results, indent=2, default=float))
    table.round(4).to_csv(ROOT / "reports" / "roi_q3_2026.csv", index=False)
    _plots(con, table, sv, extra)
    return results


def _plots(con, table, sv, extra):
    FIG.mkdir(parents=True, exist_ok=True)
    m = pd.read_sql("SELECT team, month, token_cost_gbp FROM v_team_month", con).pivot(index="month", columns="team",
                                                                                           values="token_cost_gbp")
    ax = m[m.sum().sort_values(ascending=False).index].plot.area(figsize=(9, 4), alpha=0.85)
    ax.set_ylabel("Token cost (£)"); ax.set_xlabel(""); ax.set_title("Monthly token spend by team, 2026")
    ax.legend(title="", frameon=False, bbox_to_anchor=(1.01, 1), loc="upper left")
    ax.annotate("retry storm", xy=(4, m.sum(axis=1).iloc[4]), xytext=(2.2, m.sum(axis=1).max() * 1.02),
                arrowprops={"arrowstyle": "->"})
    ax.annotate("Support caching live", xy=(6, m.sum(axis=1).iloc[6]), xytext=(5.6, m.sum(axis=1).max() * 0.55),
                arrowprops={"arrowstyle": "->"})
    plt.tight_layout(); plt.savefig(FIG / "spend_by_team.png", dpi=140); plt.close()

    t = table.set_index("team").sort_values("roi")
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.barh(t.index, t["roi"], xerr=[t["roi"] - t["roi_low"], t["roi_high"] - t["roi"]], color="#4C78A8", capsize=3,
            label="Measured / adjusted")
    ax.scatter(t["roi_if_survey_believed"], t.index, color="#E45756", zorder=3, label="If the survey were believed")
    ax.axvline(0, color="grey", lw=0.8)
    ax.set_xlim(min(-0.5, t["roi_low"].min() - 0.3), t["roi_if_survey_believed"].max() * 1.08)
    ax.set_xlabel("ROI = (value − total cost) / total cost   (3 = £3 back for every £1 spent, net)")
    ax.set_title("Q3 2026 return on AI spend by team (95% intervals)")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    for y, (v, lo) in enumerate(zip(t["roi"], t["roi_low"])):
        ax.text(max(v, 0) + 0.15, y + 0.28, f"{v:.1f}", fontsize=8)
    plt.tight_layout(); plt.savefig(FIG / "roi_by_team.png", dpi=140); plt.close()

    fig, ax = plt.subplots(figsize=(7, 3.2))
    parts = {"Q3 token cost": sv["q3_token_cost_gbp"], "Prompt caching": -sv["caching_saving_gbp"],
             "Model routing": -sv["routing_saving_gbp"], "After both": sv["q3_cost_after_both_gbp"]}
    ax.bar(list(parts), [abs(v) for v in parts.values()], color=["#4C78A8", "#54A24B", "#54A24B", "#4C78A8"])
    for i, v in enumerate(parts.values()):
        ax.text(i, abs(v), f"£{abs(v):,.0f}", ha="center", va="bottom")
    ax.set_ylabel("£"); ax.set_title(f"Q3 token cost could fall {sv['saving_pct']}% with no quality loss")
    plt.tight_layout(); plt.savefig(FIG / "savings.png", dpi=140); plt.close()


if __name__ == "__main__":
    r = main()
    print(json.dumps({k: r[k] for k in ("totals", "pilot", "survey_haircut", "savings")}, indent=2, default=float))
    print(pd.DataFrame(r["teams"])[["team", "ai_assisted_outcomes", "token_cost_per_outcome_gbp", "total_cost_per_outcome_gbp",
                                     "minutes_saved", "value_per_outcome_gbp", "roi", "roi_low", "roi_high",
                                     "roi_if_survey_believed"]].round(3).to_string())
