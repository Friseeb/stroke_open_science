# CLAUDE.md — Stroke Open Science Pipeline

## Project purpose
Living meta-research pipeline that tracks open-science practices (open access, preregistration,
data/code sharing, preprints) across stroke neurology and comparator disciplines. Source data comes
from OpenAlex and PubMed; outputs are versioned CSVs and an HTML dashboard. The intent is a
periodic benchmark (every 6 months via GitHub Actions) publishable as a methods/meta-science paper.

## Two-repo layout
| Repo | Purpose |
|------|---------|
| `Friseeb/stroke_open_science` (this repo) | Source code, configs, tests, CI |
| `Friseeb/stroke_open_science_outputs` | Generated benchmark outputs (large CSVs, dashboards) |

The outputs repo is pushed automatically by the scheduled GitHub Action after each extraction run.
Local outputs land in `data/` which is excluded from this repo.

## Key environment variables (copy `configs/.env.example` → `.env`)
| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENALEX_MAILTO` | yes | Polite-pool access for OpenAlex API |
| `OPENALEX_API_KEY` | optional | Higher rate limits (premium) |
| `UNPAYWALL_EMAIL` | optional | Unpaywall API calls |
| `UNPAYWALL_SNAPSHOT` | optional | Path/glob to local Unpaywall parquet snapshot |
| `CROSSREF_RELATIONS` | optional | Path/glob to local Crossref relations snapshot |
| `GITHUB_TOKEN` | CI only | Push to outputs repo (use GitHub Actions Secret, not `.env`) |
| `LLM_PROVIDER` | optional | `openai` or `ollama` |
| `OPENAI_API_KEY` | optional | If using OpenAI LLM extraction |
| `OPENAI_LLM_MODEL` | optional | Defaults to `gpt-4o-mini` |
| `OLLAMA_BASE_URL` | optional | Defaults to `http://localhost:11434` |
| `OLLAMA_MODEL` | optional | Defaults to `llama3.1:8b` |
| `EMBEDDING_DEVICE` | optional | `auto` / `cpu` / `cuda` / `mps` |

**Never commit `.env` to git.** Store `GITHUB_TOKEN` only in GitHub Actions Secrets
(`Settings → Secrets and variables → Actions`).

## Quick start
```bash
conda env create -f environment.yml
conda activate stroke_open_science
cp configs/.env.example .env   # fill in your values
python scripts/search_stroke_dois.py --discipline stroke --start-year 2018 --end-year 2024
```

Smoke test (no API calls, fast):
```bash
python scripts/search_stroke_dois.py --discipline stroke --start-year 2024 --end-year 2024 \
  --max-per-query 50 --disable-api-enrich --openalex-mailto your@email.com
```

Run all disciplines:
```bash
python scripts/run_discipline_benchmark.py
```

Build dashboard only (from existing data):
```bash
python scripts/build_discipline_dashboard.py
```

## Pipeline stages (search_stroke_dois.py)
1. **OpenAlex retrieval** — parallel term×year cursor pagination → `data/{discipline}/raw_openalex_articles.csv`
2. **PubMed retrieval** (optional `--include-pubmed`) — adds PMC OA links
3. **Unpaywall snapshot join** — DuckDB left-join on DOI, fills `is_oa`, `license_unpaywall`, `best_oa_location_url`
4. **Crossref relations join** — DuckDB, fills `repo_links` from supplement/data relations
5. **Regex extraction** — GitHub/Zenodo/OSF/dataset-repo patterns from title+abstract+url fields
6. **API enrichment** — async Unpaywall/Zenodo/OSF/GitHub lookups with resumable JSON cache
7. **Dataset repo search** — DataCite → Dryad → Figshare API chain, async with rate limiting
8. **Embedding ranking** (optional) — SentenceTransformer cosine similarity to an open-science concept vector
9. **LLM extraction** (optional) — OpenAI or Ollama JSON extraction of `code_link`, `data_link`, `preregistered`, `preprint`
10. **High-impact subgroup** — filters by journal IF threshold + citation percentile → `high_impact_subset.csv`
11. **Preview export** — first N rows → `enriched_preview.csv`

Caches:
- `data/{discipline}/enrich_cache.json` — API enrichment results (resumable)
- `data/{discipline}/llm_cache.json` — LLM extraction results (resumable)
- `data/{discipline}/retrieval_slices/` — per-term per-window raw API results

## Output schema (key columns)
| Column | Type | Description |
|--------|------|-------------|
| `doi` | str | Normalized lowercase DOI |
| `title` | str | Article title |
| `abstract` | str | Full abstract |
| `year` | Int64 | Publication year |
| `discipline` | str | Pipeline label (e.g., `stroke`) |
| `is_oa` | boolean | Open access flag |
| `license` / `license_unpaywall` | str | License string |
| `journal` | str | Journal name |
| `journal_impact_factor` | float | From `configs/journal_metrics.csv` |
| `cited_by_count` | float | From OpenAlex |
| `github` | str | First GitHub URL found |
| `zenodo` | str | First Zenodo URL/DOI found |
| `osf` | str | First OSF URL found |
| `dataset_urls` | str | Semicolon-joined dataset repo URLs |
| `dataset_repos` | str | Semicolon-joined repo type names |
| `has_public_dataset` | boolean | Any dataset URL found |
| `preregistered` | boolean | Pre-registration found |
| `preprint` | str | Preprint URL/identifier |
| `code_link` | str | Code repository URL |
| `data_link` | str | Data repository URL |
| `open_science_score` | float | Embedding cosine similarity (optional) |
| `high_impact_flag` | boolean | Meets IF/citation thresholds |
| `high_impact_reason` | str | Why flagged (e.g., `if≥10;pct≥90`) |
| `source_db` | str | `openalex` or `pubmed` |

## Running tests
```bash
pip install pytest
python -m pytest -q
```

Tests live in `tests/test_pipeline_deterministic.py`. They load the pipeline module directly and
test pure-logic functions (DOI normalization, date windows, LLM payload parsing, regex extraction,
deduplication). No API calls, no fixtures on disk — safe to run in CI.

## Adding a new discipline
1. Add terms to `configs/discipline_presets.json`.
2. Run: `python scripts/run_discipline_benchmark.py --disciplines <name>`.
3. Dashboard rebuilds automatically at the end.

## Credential rotation
If the GitHub PAT in `.env` is ever exposed (e.g., appears in logs), immediately:
1. Go to GitHub → Settings → Developer settings → Personal access tokens → revoke the token.
2. Create a new token with `repo` and `workflow` scopes.
3. Add it as a GitHub Actions Secret named `OUTPUTS_REPO_PAT`.
4. Update `.env` locally (never commit).

## Architecture notes
- `search_stroke_dois.py` is intentionally monolithic for portability — all stages callable from
  one import. The `REPOSITORY_AND_GITHUB_PLAN.md` doc tracks a planned modularization.
- `extract_open_science_fireduck.py` is an empty placeholder for a planned FireDucks-based rewrite.
- Deduplication prefers OpenAlex rows over PubMed when both have the same DOI (OpenAlex has richer
  metadata), but prefers PubMed when a PubMed ID is present on only one side.
- The `.gitignore` excludes `data/`, `.venv/`, `.env`, caches, and large outputs. The
  `outputs_archive/` directory in this repo holds only `metadata.json` and `manifest.csv` as
  pointers to the separate outputs repo.
