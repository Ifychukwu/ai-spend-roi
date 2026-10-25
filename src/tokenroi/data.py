"""Synthetic usage, outcome and pilot data for "Northwind Insurance", a fictional UK insurer.

Six teams use model-powered features. Every request is metered in tokens, and every
team has a business outcome it is paid to produce (tickets resolved, claims processed...).
The generator is seeded and plants the things a real cost review finds:

* a support system prompt of ~3,000 tokens resent on every request until prompt
  caching is switched on in July 2026;
* marketing and HR sending short, simple tasks to the large model;
* a retry storm in Engineering (a client bug, 11-24 May 2026): a quarter of
  requests fail and the client retries each failure three times, all billed;
* self-reported time savings that are about twice what a controlled pilot measures.

All prices are illustrative per-million-token list prices in GBP, set in ``MODELS``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

START, END = "2026-01-01", "2026-09-30"
CACHING_LIVE = pd.Timestamp("2026-07-01")
RETRY_STORM = (pd.Timestamp("2026-05-11"), pd.Timestamp("2026-05-24"))

# Illustrative list prices (GBP per million tokens). Cached input is billed at 10% of the input price.
MODELS = pd.DataFrame([
    ("large", 4.00, 20.00),
    ("medium", 1.20, 6.00),
    ("small", 0.25, 1.25),
], columns=["model_tier", "input_gbp_per_mtok", "output_gbp_per_mtok"])
CACHED_INPUT_DISCOUNT = 0.90

TEAMS = pd.DataFrame([
    # team_id, team, headcount, loaded £/hour, outcome unit, monthly budget £
    (1, "Customer Support", 60, 28.0, "ticket resolved", 450),
    (2, "Claims", 35, 34.0, "claim processed", 850),
    (3, "Engineering", 40, 62.0, "pull request merged", 3_200),
    (4, "Underwriting", 20, 48.0, "quote issued", 90),
    (5, "Marketing", 12, 40.0, "campaign asset approved", 75),
    (6, "HR", 6, 32.0, "employee query answered", 90),
], columns=["team_id", "team", "headcount", "loaded_hourly_cost_gbp", "outcome_unit", "monthly_budget_gbp"])


@dataclass(frozen=True)
class Feature:
    feature: str
    team_id: int
    model_mix: dict            # share of requests per model tier
    req_per_head_day: float    # requests per person per working day
    sys_tokens: int            # fixed system prompt / instructions resent each request
    in_tokens: int             # mean variable input (the user's content)
    out_tokens: int            # mean output
    growth: float              # monthly growth in usage


FEATURES = [
    Feature("Ticket reply drafting", 1, {"medium": 1.0}, 38, 3000, 900, 350, 0.03),
    Feature("Claim document summary", 2, {"large": 0.7, "medium": 0.3}, 14, 1200, 14000, 700, 0.02),
    Feature("Coding assistant", 3, {"large": 0.85, "medium": 0.15}, 55, 2500, 6000, 900, 0.06),
    Feature("Risk note extraction", 4, {"medium": 0.8, "small": 0.2}, 22, 800, 4000, 400, 0.01),
    Feature("Campaign copy", 5, {"large": 1.0}, 30, 600, 300, 250, 0.04),
    Feature("HR policy assistant", 6, {"large": 1.0}, 45, 1500, 120, 220, 0.02),
]

# Outcomes per working day per head, and the share produced with AI assistance.
OUTCOMES = {1: (9.0, 0.92), 2: (3.2, 0.85), 3: (0.55, 0.9), 4: (2.4, 0.7), 5: (0.35, 0.8), 6: (3.0, 1.0)}

# Minutes saved per outcome: what a controlled pilot would show, and what staff say in a survey.
TRUE_MINUTES_SAVED = {1: 3.1, 2: 11.0, 3: 38.0, 4: 6.0, 5: 9.0, 6: 4.0}
SURVEY_INFLATION = {1: 2.1, 2: 1.9, 3: 2.3, 4: 1.8, 5: 2.6, 6: 1.7}

# Offline quality evaluation (acceptance rate by reviewers) per feature and model tier.
QUALITY = pd.DataFrame([
    ("Ticket reply drafting", "large", 0.86), ("Ticket reply drafting", "medium", 0.85), ("Ticket reply drafting", "small", 0.74),
    ("Claim document summary", "large", 0.91), ("Claim document summary", "medium", 0.84), ("Claim document summary", "small", 0.66),
    ("Coding assistant", "large", 0.78), ("Coding assistant", "medium", 0.69), ("Coding assistant", "small", 0.48),
    ("Risk note extraction", "large", 0.93), ("Risk note extraction", "medium", 0.92), ("Risk note extraction", "small", 0.90),
    ("Campaign copy", "large", 0.82), ("Campaign copy", "medium", 0.81), ("Campaign copy", "small", 0.73),
    ("HR policy assistant", "large", 0.95), ("HR policy assistant", "medium", 0.95), ("HR policy assistant", "small", 0.94),
], columns=["feature", "model_tier", "acceptance_rate"])

PLATFORM_COST_GBP_PER_MONTH = 6_000    # share of the platform team, gateway and monitoring, allocated by requests


def price(model_tier, input_tokens, cached_input_tokens, output_tokens) -> np.ndarray:
    """Cost in GBP of a batch of requests."""
    m = MODELS.set_index("model_tier").loc[np.asarray(model_tier)]
    uncached = np.asarray(input_tokens) - np.asarray(cached_input_tokens)
    return (uncached * m["input_gbp_per_mtok"].to_numpy()
            + np.asarray(cached_input_tokens) * m["input_gbp_per_mtok"].to_numpy() * (1 - CACHED_INPUT_DISCOUNT)
            + np.asarray(output_tokens) * m["output_gbp_per_mtok"].to_numpy()) / 1e6


def generate(seed: int = 26) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    days = pd.date_range(START, END, freq="D")
    workday = days.dayofweek < 5
    # UK bank holidays in the period
    holidays = pd.to_datetime(["2026-01-01", "2026-04-03", "2026-04-06", "2026-05-04", "2026-05-25", "2026-08-31"])
    workday &= ~days.isin(holidays)
    month_idx = (days.year - 2026) * 12 + days.month - 1

    usage = []
    for fid, f in enumerate(FEATURES, start=1):
        head = int(TEAMS.loc[TEAMS.team_id == f.team_id, "headcount"].iloc[0])
        for tier, share in f.model_mix.items():
            base = f.req_per_head_day * head * share * (1 + f.growth) ** month_idx
            lam = np.where(workday, base, base * 0.04)
            requests = rng.poisson(lam * rng.lognormal(0, 0.08, len(days)))
            fail_rate = np.full(len(days), 0.015)
            retries = np.ones(len(days))                      # each failure is retried once; every attempt is billed
            if f.team_id == 3:
                storm = (days >= RETRY_STORM[0]) & (days <= RETRY_STORM[1])
                fail_rate[storm], retries[storm] = 0.25, 3.0
            failed = rng.binomial(requests, fail_rate)
            attempts = requests + failed * retries
            sys_tok = attempts * f.sys_tokens
            var_in = rng.gamma(4, f.in_tokens / 4, len(days)) * attempts
            out = rng.gamma(5, f.out_tokens / 5, len(days)) * requests + failed * retries * f.out_tokens * 0.3
            cached = np.zeros(len(days))
            if f.team_id == 1:
                cached = np.where(days >= CACHING_LIVE, sys_tok * 0.93, 0)
            usage.append(pd.DataFrame({
                "date": days, "feature_id": fid, "team_id": f.team_id, "model_tier": tier,
                "requests": requests, "failed_requests": failed, "attempts": np.round(attempts).astype(np.int64),
                "input_tokens": np.round(sys_tok + var_in).astype(np.int64),
                "cached_input_tokens": np.round(cached).astype(np.int64),
                "output_tokens": np.round(out).astype(np.int64)}))
    usage = pd.concat(usage, ignore_index=True)
    usage["cost_gbp"] = price(usage["model_tier"], usage["input_tokens"], usage["cached_input_tokens"],
                              usage["output_tokens"]).round(4)

    # Weekly outcomes per team.
    weeks = pd.date_range(START, END, freq="W-MON")
    out_rows = []
    for t in TEAMS.itertuples():
        per_day, ai_share = OUTCOMES[t.team_id]
        for w in weeks:
            wd = int(((pd.date_range(w, w + pd.Timedelta(days=6)) <= END)
                      & pd.date_range(w, w + pd.Timedelta(days=6)).isin(days[workday])).sum())
            n = rng.poisson(per_day * t.headcount * wd)
            out_rows.append((w, t.team_id, n, int(rng.binomial(n, ai_share))))
    outcomes = pd.DataFrame(out_rows, columns=["week_start", "team_id", "outcomes", "ai_assisted_outcomes"])

    # A randomised pilot in Customer Support and Claims (Feb-Mar 2026): handle time per item, with and without AI.
    pilot = []
    for team_id, base_min, sd, n in [(1, 14.0, 6.0, 1600), (2, 52.0, 18.0, 700)]:
        arm = rng.choice(["control", "ai_assisted"], n)
        mins = rng.gamma((base_min / sd) ** 2, sd ** 2 / base_min, n)
        mins = np.where(arm == "ai_assisted", mins - rng.normal(TRUE_MINUTES_SAVED[team_id], 2.0, n), mins)
        pilot.append(pd.DataFrame({"team_id": team_id, "arm": arm, "handle_minutes": np.clip(mins, 1, None).round(1),
                                   "pilot_date": pd.Timestamp("2026-02-02") + pd.to_timedelta(rng.integers(0, 56, n), "D")}))
    pilot = pd.concat(pilot, ignore_index=True)
    pilot.insert(0, "item_id", np.arange(1, len(pilot) + 1))

    survey = pd.DataFrame({"team_id": TEAMS.team_id,
                           "self_reported_minutes_saved": [round(TRUE_MINUTES_SAVED[t] * SURVEY_INFLATION[t], 1)
                                                           for t in TEAMS.team_id],
                           "respondents": [41, 22, 31, 14, 10, 5]})

    features = pd.DataFrame([{"feature_id": i, "feature": f.feature, "team_id": f.team_id,
                              "system_prompt_tokens": f.sys_tokens} for i, f in enumerate(FEATURES, start=1)])
    dates = pd.DataFrame({"date": days, "is_working_day": workday.astype(int), "month": days.strftime("%Y-%m"),
                          "quarter": "2026-Q" + days.quarter.astype(str), "weekday": days.day_name()})
    return {"dim_team": TEAMS.copy(), "dim_feature": features, "dim_model": MODELS.copy(), "dim_date": dates,
            "fact_usage_daily": usage, "fact_outcomes_weekly": outcomes, "pilot_items": pilot,
            "survey_time_saved": survey, "model_quality": QUALITY.copy()}
