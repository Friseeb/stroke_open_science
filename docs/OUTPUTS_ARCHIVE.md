# Outputs Archive Handoff

This repository is code-first. Large benchmark outputs are published separately.

## Target external archive

- GitHub outputs repository or archival destination URL:
  - `https://github.com/Friseeb/stroke_open_science_outputs`
- Optional DOI archive (Zenodo/OSF/institutional):
  - `https://doi.org/TO_BE_ASSIGNED`

Replace placeholders before public release.

## What to publish externally

Recommended outputs to publish from local `data/` runs:

- `fully_enriched.csv`
- `high_impact_subset.csv`
- `enriched_preview.csv`
- `raw_openalex_articles.csv` (optional, if policy allows)
- `run_manifest.json` for scheduled runs
- Dashboard artifacts:
  - `discipline_year_summary.csv`
  - `discipline_overall_summary.csv`
  - `discipline_dashboard.html`

Generate a transfer manifest from local data:

```bash
./.venv/bin/python scripts/prepare_outputs_archive.py
```

This writes `outputs_archive/manifest.csv`.

## What to exclude from public output archives

- `enrich_cache.json`
- `llm_cache.json`
- local snapshot mirrors (Unpaywall/Crossref parquet)
- secret-bearing metadata or environment files

## GitHub linking requirement

In the source repository README, keep a visible link to the external outputs archive.
Set `outputs_archive/metadata.json` with the final archive URL so downstream tooling can discover it.
