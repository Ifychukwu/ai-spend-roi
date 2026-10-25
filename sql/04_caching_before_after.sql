-- Did prompt caching (live 1 July 2026) cut Customer Support's cost per request?
WITH s AS (
    SELECT CASE WHEN date < '2026-07-01' THEN 'before caching' ELSE 'after caching' END AS period,
           SUM(cost_gbp) AS cost_gbp, SUM(requests) AS requests,
           SUM(cached_input_tokens) * 1.0 / SUM(input_tokens) AS cached_share
    FROM v_usage
    WHERE team = 'Customer Support'
    GROUP BY period
)
SELECT period,
       ROUND(1000 * cost_gbp / requests, 3)  AS cost_per_1k_requests_gbp,
       ROUND(100 * cached_share, 1)          AS input_tokens_cached_pct
FROM s
ORDER BY period DESC;
