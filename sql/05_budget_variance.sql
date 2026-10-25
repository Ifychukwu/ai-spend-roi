-- Which teams went over their monthly AI budget, and by how much?
SELECT team, month,
       ROUND(token_cost_gbp, 2)       AS token_cost_gbp,
       monthly_budget_gbp,
       ROUND(over_budget_gbp, 2)      AS over_budget_gbp,
       ROUND(100.0 * token_cost_gbp / monthly_budget_gbp - 100, 1) AS variance_pct
FROM v_team_month
WHERE over_budget_gbp > 0
ORDER BY month, variance_pct DESC;
