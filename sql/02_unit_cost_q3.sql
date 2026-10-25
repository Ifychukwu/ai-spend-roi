-- The headline for each team: token cost per business outcome, Q3 2026 (July to September).
SELECT team,
       ROUND(SUM(token_cost_gbp), 2)                                         AS token_cost_gbp,
       SUM(ai_assisted_outcomes)                                             AS ai_assisted_outcomes,
       ROUND(SUM(token_cost_gbp) / SUM(ai_assisted_outcomes), 4)             AS token_cost_per_outcome_gbp
FROM v_team_month
WHERE month BETWEEN '2026-07' AND '2026-09'
GROUP BY team
ORDER BY token_cost_per_outcome_gbp DESC;
