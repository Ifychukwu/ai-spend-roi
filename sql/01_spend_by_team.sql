-- Where does the money go? Token spend by team and model, with each team's share of the total.
SELECT team,
       model_tier,
       ROUND(SUM(cost_gbp), 2)                                              AS cost_gbp,
       ROUND(100.0 * SUM(cost_gbp) / SUM(SUM(cost_gbp)) OVER (), 1)          AS share_of_total_pct,
       SUM(requests)                                                        AS requests,
       ROUND(1000.0 * SUM(cost_gbp) / SUM(requests), 3)                      AS cost_per_1k_requests_gbp
FROM v_usage
GROUP BY team, model_tier
ORDER BY cost_gbp DESC;
