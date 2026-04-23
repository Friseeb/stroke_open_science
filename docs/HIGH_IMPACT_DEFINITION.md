# High-impact subgroup definition

Current rule in `search_stroke_dois.py` marks a paper as high-impact when **either** condition is true:

1. `journal_impact_factor >= impact_factor_threshold` (default `10.0`), OR
2. `cited_by_count` is above the `citation_percentile_threshold` (default `90th percentile`) among retrieved papers.

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
