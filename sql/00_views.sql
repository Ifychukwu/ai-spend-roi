-- Shared definitions. Every report and dashboard reads these views, so "cost" means the same thing everywhere.

-- One row per team, feature, model and day, with the cost split into what was useful and what was wasted.
CREATE VIEW v_usage AS
SELECT u.date,
       substr(u.date, 1, 7)                                   AS month,
       t.team, f.feature, u.model_tier,
       u.requests, u.failed_requests, u.attempts,
       u.input_tokens, u.cached_input_tokens, u.output_tokens,
       u.cost_gbp,
       -- cost of attempts that failed and had to be retried (input is resent in full on every attempt)
       u.cost_gbp * (u.attempts - u.requests) / NULLIF(u.attempts, 0) AS failed_attempt_cost_gbp
FROM fact_usage_daily u
JOIN dim_team t    USING (team_id)
JOIN dim_feature f USING (feature_id);

-- Monthly cost and outcomes per team: the grain of the ROI review.
CREATE VIEW v_team_month AS
WITH cost AS (
    SELECT team, month, SUM(cost_gbp) AS token_cost_gbp, SUM(requests) AS requests
    FROM v_usage GROUP BY team, month
), outc AS (
    SELECT t.team, substr(o.week_start, 1, 7) AS month,
           SUM(o.outcomes) AS outcomes, SUM(o.ai_assisted_outcomes) AS ai_assisted_outcomes
    FROM fact_outcomes_weekly o JOIN dim_team t USING (team_id)
    GROUP BY t.team, month
)
SELECT c.team, c.month, c.token_cost_gbp, c.requests, o.outcomes, o.ai_assisted_outcomes,
       c.token_cost_gbp / NULLIF(o.ai_assisted_outcomes, 0) AS token_cost_per_outcome_gbp,
       d.monthly_budget_gbp,
       c.token_cost_gbp - d.monthly_budget_gbp            AS over_budget_gbp
FROM cost c
LEFT JOIN outc o USING (team, month)
JOIN dim_team d ON d.team = c.team;
