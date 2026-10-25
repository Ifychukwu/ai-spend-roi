# Data

Everything is **synthetic** and regenerated from a seed by `tokenroi.data.generate(seed=26)`; `python -m tokenroi.warehouse` writes it to `data/northwind_ai.db` (SQLite, git-ignored) and to `powerbi/data/*.csv` (committed, about 160 KB). Northwind Insurance is fictional and contains no personal data.

The structure mirrors what a real model gateway or provider billing export gives you, joined to operational data a business already has.

| Table | Grain | Key columns |
|---|---|---|
| `fact_usage_daily` | team × feature × model × day | `requests`, `failed_requests`, `attempts` (every billed call, including retries), `input_tokens`, `cached_input_tokens`, `output_tokens`, `cost_gbp` |
| `fact_outcomes_weekly` | team × week | `outcomes`, `ai_assisted_outcomes` (outcomes produced with the AI feature in the loop) |
| `pilot_items` | one handled item | randomised `arm` (`control` / `ai_assisted`) and `handle_minutes`, Customer Support and Claims, Feb–Mar 2026 |
| `survey_time_saved` | team | `self_reported_minutes_saved` per outcome, `respondents` |
| `model_quality` | feature × model | reviewer `acceptance_rate` from an offline evaluation |
| `dim_team` | team | `headcount`, `loaded_hourly_cost_gbp`, `outcome_unit`, `monthly_budget_gbp` |
| `dim_feature`, `dim_model`, `dim_date` | | system prompt length; illustrative £ per million input/output tokens; calendar with UK bank holidays |

**Pricing** is illustrative (large £4 / £20, medium £1.20 / £6, small £0.25 / £1.25 per million input / output tokens; cached input billed at 10%). Change `MODELS` in `src/tokenroi/data.py` to your provider's price list.

**Planted for the analysis to find:** prompt caching switched on for Customer Support on 1 July 2026; a client retry bug in Engineering on 11–24 May 2026; large-model use for simple tasks in Marketing and HR; self-reported time savings 1.7–2.6× the true effect.
