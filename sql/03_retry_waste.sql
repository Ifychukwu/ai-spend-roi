-- Waste from failed attempts: every failure is billed, and a buggy client can multiply them.
SELECT team,
       month,
       SUM(requests)                                                         AS requests,
       SUM(failed_requests)                                                  AS failed_requests,
       SUM(attempts) - SUM(requests)                                         AS billed_retries,
       ROUND(100.0 * SUM(failed_requests) / SUM(requests), 2)                AS failure_rate_pct,
       ROUND(SUM(failed_attempt_cost_gbp), 2)                                AS failed_attempt_cost_gbp
FROM v_usage
GROUP BY team, month
HAVING failure_rate_pct > 3
ORDER BY failed_attempt_cost_gbp DESC;
