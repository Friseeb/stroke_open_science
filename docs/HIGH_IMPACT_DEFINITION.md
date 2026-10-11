# High-impact subgroup definition

Current rule in `search_stroke_dois.py` marks a paper as high-impact when **either** condition is true:

1. `journal_impact_factor >= impact_factor_threshold` (default `10.0`), OR
2. `cited_by_count` is at or above the `citation_percentile_threshold` (default `90th percentile`) **among retrieved
   papers of the same publication year**. Citations accrue with age, so a pooled percentile would favour older papers;
   the per-year threshold is written into `high_impact_reason` (e.g. `cited_by_count>=41 (top 10.0% of 2019)`).
   Rows without a usable year, or frames without a `year` column, use the pooled percentile (changed 2026-10-11).

CLI knobs:

- `--impact-factor-threshold`
- `--citation-percentile-threshold`
- `--journal-metrics-csv`
- `--high-impact-csv`

Output columns used for traceability:

- `high_impact_flag`
- `high_impact_reason`
- `journal_impact_factor`
- `cited_by_count`

This gives a practical hybrid of venue-level prestige and article-level influence.
