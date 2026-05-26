# Stroke Open Science

A living meta-research pipeline that automatically tracks and analyzes open-science practices
(open access, preregistration, data/code sharing, preprints) in stroke neurology publications
and across comparator disciplines using OpenAlex, Unpaywall, and DuckDB.

## Repository layout

| Repo | Contents |
|------|----------|
| [Friseeb/stroke_open_science](https://github.com/Friseeb/stroke_open_science) | Source code, configs, tests, CI **(this repo)** |
| [Friseeb/stroke_open_science_outputs](https://github.com/Friseeb/stroke_open_science_outputs) | Generated benchmark CSVs and dashboards |

Large benchmark outputs are published to the outputs repo automatically by the
[scheduled GitHub Action](.github/workflows/scheduled_extraction.yml) (runs every 6 months).

## Quick start

```bash
# 1. Create environment
conda env create -f environment.yml
conda activate stroke_open_science

# 2. Configure credentials
cp configs/.env.example .env
# Edit .env with your OPENALEX_MAILTO (required) and optional API keys

# 3. Smoke test (50 records, no API enrichment, ~1 min)
python scripts/search_stroke_dois.py \
  --discipline stroke \
  --start-year 2024 --end-year 2024 \
  --max-per-query 50 \
  --disable-api-enrich \
  --openalex-mailto your@email.com

# 4. Full stroke benchmark
python scripts/search_stroke_dois.py --discipline stroke --start-year 2018 --end-year 2024

# 5. All disciplines + dashboard
python scripts/run_discipline_benchmark.py
python scripts/build_discipline_dashboard.py
```

## Environment variables

Copy `configs/.env.example` to `.env` (never commit `.env`):

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENALEX_MAILTO` | **yes** | Email for OpenAlex polite-pool access |
| `OPENALEX_API_KEY` | no | Premium OpenAlex key (higher rate limits) |
| `UNPAYWALL_EMAIL` | no | Email for Unpaywall API |
| `UNPAYWALL_SNAPSHOT` | no | Path/glob to local Unpaywall parquet snapshot |
| `CROSSREF_RELATIONS` | no | Path/glob to local Crossref relations parquet |
| `GITHUB_TOKEN` | CI only | PAT for outputs repo push (set in GitHub Secrets) |
| `LLM_PROVIDER` | no | `openai` or `ollama` (default: `openai`) |
| `OPENAI_API_KEY` | no | Required if `LLM_PROVIDER=openai` |
| `OPENAI_LLM_MODEL` | no | Default: `gpt-4o-mini` |
| `OLLAMA_BASE_URL` | no | Default: `http://localhost:11434` |
| `EMBEDDING_DEVICE` | no | `auto` / `cpu` / `cuda` / `mps` |

## Pipeline stages

```text
OpenAlex retrieval  →  PubMed (optional)  →  Unpaywall/Crossref snapshot joins
→  Regex extraction (GitHub/Zenodo/OSF/dataset repos)
→  API enrichment (Unpaywall · Zenodo · OSF · GitHub · DataCite · Dryad · Figshare)
→  Embedding ranking (optional)  →  LLM extraction (optional)
→  Journal metrics  →  High-impact subgroup  →  CSV export
```

## Output files

Each discipline run produces these files under `data/{discipline}/`:

| File | Description |
|------|-------------|
| `raw_openalex_articles.csv` | Raw retrieval output (deduplicated) |
| `enriched_preview.csv` | First 50 000 enriched rows |
| `fully_enriched.csv` | Complete enriched dataset |
| `high_impact_subset.csv` | Papers meeting IF ≥ 10 or citation ≥ 90th percentile |
| `enrich_cache.json` | Resumable API enrichment cache |
| `llm_cache.json` | Resumable LLM extraction cache |

Key output columns: `doi`, `title`, `year`, `discipline`, `is_oa`, `license`,
`journal`, `journal_impact_factor`, `cited_by_count`, `github`, `zenodo`, `osf`,
`dataset_urls`, `dataset_repos`, `has_public_dataset`, `preregistered`, `preprint`,
`code_link`, `data_link`, `open_science_score`, `high_impact_flag`.

## Disciplines

Comparator disciplines are defined in `configs/discipline_presets.json`.
Default disciplines: `stroke`, `neuroscience`, `neurology`, `cardiology`.

To add a discipline, add its search terms to `discipline_presets.json` and re-run
`run_discipline_benchmark.py`.

## Testing

```bash
pip install pytest
python -m pytest -q
```

Tests cover DOI normalization, date windows, LLM payload parsing, regex extraction,
deduplication, OA inference, high-impact subgroup logic, dataset repo detection, and
keyword signal scoring. No API calls, no on-disk fixtures.

## Structure

```text
scripts/
  search_stroke_dois.py          # Main pipeline (3 500+ lines, all stages)
  run_discipline_benchmark.py    # Multi-discipline orchestrator
  build_discipline_dashboard.py  # HTML dashboard generator
  run_scheduled_benchmark.py     # Scheduled-run wrapper
  prepare_outputs_archive.py     # Manifest/metadata for outputs repo
configs/
  discipline_presets.json        # Search terms per discipline
  journal_metrics.csv            # Journal impact factors
  .env.example                   # Credential template
tests/
  test_pipeline_deterministic.py # Pure-logic unit tests
docs/
  REPOSITORY_AND_GITHUB_PLAN.md  # Architecture and roadmap
  EXPERT_COLLABORATOR_BRIEF.md   # Context for collaborators
  HIGH_IMPACT_DEFINITION.md      # Definition of the high-impact subgroup
outputs_archive/
  metadata.json                  # Pointer to stroke_open_science_outputs
  manifest.csv                   # File inventory
.github/workflows/
  ci.yml                         # Run tests on push/PR
  scheduled_extraction.yml       # 6-month automated extraction + outputs push
```

## GitHub Actions setup

Before the scheduled workflow can push to the outputs repo, add these secrets at
`Settings → Secrets and variables → Actions` in **this** repo:

| Secret name | Value |
|-------------|-------|
| `OPENALEX_MAILTO` | Your email |
| `OUTPUTS_REPO_PAT` | A GitHub PAT with `repo` + `workflow` scopes |

Optional secrets: `OPENALEX_API_KEY`, `UNPAYWALL_EMAIL`, `OPENAI_API_KEY`.

## Citation

If you use this pipeline, please cite:

```bibtex
@software{stroke_open_science,
  author    = {Fridman, Sebastian},
  title     = {Stroke Open Science Pipeline},
  url       = {https://github.com/Friseeb/stroke_open_science},
  year      = {2026}
}
```

See `CITATION.cff` for full citation metadata.

## License

See `LICENSE`.
