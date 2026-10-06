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
| `OPENALEX_API_KEY` | recommended | Free OpenAlex key: $1/day budget (10,000 list requests); keyless mode gets 10x less |
| `UNPAYWALL_EMAIL` | no | Email for Unpaywall API |
| `UNPAYWALL_SNAPSHOT` | no | Path/glob to local Unpaywall parquet snapshot |
| `CROSSREF_RELATIONS` | no | Path/glob to local Crossref relations parquet |
| `GITHUB_TOKEN` | CI only | PAT for outputs repo push (set in GitHub Secrets) |
| `LLM_PROVIDER` | no | `openai` or `ollama` (default: `openai`) |
| `OPENAI_API_KEY` | no | Required if `LLM_PROVIDER=openai` |
| `OPENAI_LLM_MODEL` | no | Default: `gpt-4o-mini` |
| `OLLAMA_BASE_URL` | no | Default: `http://localhost:11434` |
| `EMBEDDING_DEVICE` | no | `auto` / `cpu` / `cuda` / `mps` |

## OpenAlex budget (metered pricing)

Since mid-2026 OpenAlex meters API usage. A free API key gets **$1/day = 10,000 list
requests** ($0.0001 each), resetting at **00:00 UTC**; without a key the budget is 10x
smaller. The full four-discipline benchmark needs roughly two daily budgets, so on the
free tier expect it to span **~2 days**; prepaying ~$2 of credit finishes in one day.

When the key's budget runs out mid-run the pipeline does **not** drop the key or fall
back to keyless mode. It reads `x-ratelimit-reset` (or computes the time to the next
00:00 UTC), logs the wait, sleeps until the reset plus a 60 s margin, and resumes the
same cursor. The wait is capped by `--openalex-budget-wait-max-hours` (default 30);
beyond the cap the slice stops early, is saved as `retrieval_slices/.../*.partial.csv`
(never treated as complete), the run exits non-zero, and re-running the same command
resumes only the unfinished slices. Keyless fallback is used only when no key is set.

## Pipeline stages

```text
OpenAlex retrieval (incl. work type, OA status, preprint locations, countries, funders)
→  OpenAlex metadata backfill (--backfill-openalex-metadata, legacy datasets only)
→  PubMed (optional)  →  Unpaywall/Crossref snapshot joins
→  Regex extraction (GitHub/Zenodo/OSF/dataset repos · registration signals · in_article_corpus flag)
→  API enrichment (Unpaywall · Zenodo · OSF · GitHub · DataCite · Dryad · Figshare)
→  Embedding ranking (optional)  →  LLM extraction (optional; preprint filled from metadata otherwise)
→  Data-availability-statement audit via Europe PMC (--das-audit-sample-per-year N)
→  Journal metrics  →  High-impact subgroup  →  CSV export
```

The DAS audit resolves DOIs to PMCIDs with batched Europe PMC searches, samples N open-access
full texts per year, and classifies the data-availability statement (repository, controlled /
restricted, on request, in article, not available, other, no statement). Only the open-access
subset has full text, so those rates are optimistic relative to the whole corpus.

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
| `openalex_metadata_cache.jsonl` | Resumable batched OpenAlex work-metadata lookups (backfill only) |
| `das_cache.jsonl` | Resumable Europe PMC DOI→PMCID resolutions and DAS extractions |

Key output columns: `doi`, `title`, `year`, `discipline`, `is_oa`, `oa_status`, `license`,
`journal`, `journal_impact_factor`, `cited_by_count`, `work_type`, `primary_source_type`,
`in_article_corpus`, `github`, `zenodo`, `osf`, `dataset_urls`, `dataset_repos`,
`has_public_dataset`, `preregistered`, `registration_signal`, `preprint`, `has_preprint_version`,
`first_author_country`, `countries`, `funders`, `code_link`, `data_link`, `das_available`,
`das_primary`, `das_text`, `open_science_score`, `high_impact_flag`. See `CLAUDE.md` for the full
schema.

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
deduplication, OA inference, high-impact subgroup logic, dataset repo detection,
keyword signal scoring, OpenAlex budget-reset waiting, and partial-slice resume.
No API calls, no on-disk fixtures.

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
  test_openalex_budget.py        # Budget-wait and partial-slice resume tests (mocked HTTP)
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

The scheduled workflow runs the four disciplines one at a time (they share one OpenAlex
key), caches `retrieval_slices/` between runs so an interrupted job resumes, and refuses
to publish unless every discipline's `fully_enriched.csv` exists with >50,000 rows
(override with the `allow_partial` input). On the free tier the first run typically
exhausts the daily budget; re-dispatch the workflow the next day to finish from cache.

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
