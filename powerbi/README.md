# Power BI dashboard: AI Spend & ROI

A three-page report for a CFO and team leads: what we spend, what we get back, and where to save. Everything it needs is in [`data/`](data), so Power BI Desktop (free) is the only tool required. Allow about 90 minutes.

Rebuild the extract at any time with `python -m tokenroi.warehouse && python -m tokenroi.roi`, then copy `reports/roi_q3_2026.csv` into `powerbi/data/`.

## 1. Load the data

**Home → Get data → Text/CSV**, and load every file in `powerbi/data/`. In Power Query, check these types:

| Table | Column | Type |
|---|---|---|
| `dim_date` | `date` | Date |
| `fact_usage_daily` | `date` | Date |
| `fact_usage_daily` | `cost_gbp` | Fixed decimal |
| `fact_outcomes_weekly` | `week_start` | Date |
| all tables | `*_id` | Whole number |

Mark `dim_date` as the date table: **Table tools → Mark as date table → date**.

## 2. Relationships (Model view)

All are many-to-one, with a single filter direction from the dimension to the fact.

| From (many) | To (one) |
|---|---|
| `fact_usage_daily[date]` | `dim_date[date]` |
| `fact_usage_daily[team_id]` | `dim_team[team_id]` |
| `fact_usage_daily[feature_id]` | `dim_feature[feature_id]` |
| `fact_usage_daily[model_tier]` | `dim_model[model_tier]` |
| `fact_outcomes_weekly[team_id]` | `dim_team[team_id]` |
| `fact_outcomes_weekly[week_start]` | `dim_date[date]` |
| `survey_time_saved[team_id]` | `dim_team[team_id]` |
| `roi_q3_2026[team]` | `dim_team[team]` |

## 3. Measures

Create a `_Measures` table (**Enter data**, one dummy column), then add these measures:

```DAX
Token Cost = SUM ( fact_usage_daily[cost_gbp] )

Requests = SUM ( fact_usage_daily[requests] )

Billed Retries = SUM ( fact_usage_daily[attempts] ) - [Requests]

Retries per 100 Requests = DIVIDE ( [Billed Retries], [Requests] ) * 100

Cost per 1k Requests = DIVIDE ( [Token Cost], [Requests] ) * 1000

AI-assisted Outcomes = SUM ( fact_outcomes_weekly[ai_assisted_outcomes] )

Token Cost per Outcome = DIVIDE ( [Token Cost], [AI-assisted Outcomes] )

Cached Input Share =
DIVIDE ( SUM ( fact_usage_daily[cached_input_tokens] ), SUM ( fact_usage_daily[input_tokens] ) )

Monthly Budget = SUM ( dim_team[monthly_budget_gbp] )

Budget Variance % =
VAR months = DISTINCTCOUNT ( dim_date[month] )
RETURN DIVIDE ( [Token Cost], [Monthly Budget] * months ) - 1

Large Model Share = DIVIDE ( CALCULATE ( [Token Cost], dim_model[model_tier] = "large" ), [Token Cost] )

-- From the Python ROI model (Q3 2026), so the method stays in one tested place
Total Cost Q3 = SUM ( roi_q3_2026[total_cost_gbp] )
Value Q3 = SUM ( roi_q3_2026[value_gbp] )
ROI Q3 = DIVIDE ( [Value Q3] - [Total Cost Q3], [Total Cost Q3] )
Hours Saved Q3 = SUM ( roi_q3_2026[hours_saved] )
```

Format the cost measures as currency (£, 0 or 2 decimals), the shares as percentages, and ROI as a decimal number with 1 decimal place ("3.8").

**Why the ROI comes from Python and not DAX.** ROI depends on the pilot estimate, the survey correction and the platform-cost allocation. Re-implementing that logic in DAX would create a second version of it to keep in sync. Power BI shows the tested result, and slices it.

## 4. Pages

Use one colour per team throughout. Add a theme in **View → Themes → Customize** with these colours in this order: `#4C78A8 #F58518 #54A24B #E45756 #B279A2 #9D755D`.

### Page 1: Executive summary ("Is AI paying off?")

| Visual | Fields | Notes |
|---|---|---|
| 4 cards | `Token Cost` (Q3), `Total Cost Q3`, `Value Q3`, `ROI Q3` | Title the ROI card "£ back per £1, net" |
| Clustered bar | Axis `roi_q3_2026[team]`, values `roi`, `roi_if_survey_believed` | Sort by `roi`. This shows the survey overstatement at a glance |
| Card + text box | `Hours Saved Q3` | "≈ X working weeks saved this quarter" (divide by 37.5) |
| Slicer | `dim_date[quarter]` | Defaults to 2026-Q3 for the cost cards |

### Page 2: Unit economics ("What does one outcome cost?")

| Visual | Fields | Notes |
|---|---|---|
| Table | `dim_team[team]`, `dim_team[outcome_unit]`, `Token Cost per Outcome`, `roi_q3_2026[total_cost_per_outcome_gbp]`, `roi_q3_2026[value_per_outcome_gbp]` | Conditional formatting: data bars on value per outcome |
| Scatter | X `Token Cost per Outcome`, Y `roi_q3_2026[value_per_outcome_gbp]`, legend `team`, size `AI-assisted Outcomes` | Log scale on both axes; the diagonal is break-even |
| Line | Axis `dim_date[month]`, values `Token Cost per Outcome`, legend `team` | Shows efficiency over time |

### Page 3: Waste and savings ("Where can we save?")

| Visual | Fields | Notes |
|---|---|---|
| Line (daily) | Axis `dim_date[date]`, values `Retries per 100 Requests`, filter team = Engineering | Add a constant line at 5 labelled "alert threshold"; the May spike stands out |
| Clustered column | Axis `dim_date[month]`, values `Cost per 1k Requests`, filter team = Customer Support | Before and after caching on 1 July |
| Stacked bar | Axis `dim_feature[feature]`, values `Token Cost`, legend `dim_model[model_tier]` | Highlights large-model use on simple tasks |
| Matrix | Rows `model_quality[feature]`, columns `model_quality[model_tier]`, values `acceptance_rate` | Colour scale; supports the routing recommendation |
| Table | `dim_date[month]`, `dim_team[team]`, `Token Cost`, `Monthly Budget`, `Budget Variance %` | Filter `Budget Variance %` > 0 |

## 5. Publish

Power BI Desktop is free on Windows. Publishing online ("Publish to web") needs a work or school Microsoft account, so for a portfolio:

1. Save the report as `powerbi/ai_spend_roi.pbix` and commit it.
2. Export each page (**File → Export → Export to PDF**) to `powerbi/ai_spend_roi.pdf`.
3. Take a screenshot of each page into `powerbi/screenshots/` and add them to the main README.
