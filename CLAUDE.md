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
| `OPENALEX_API_KEY` | recommended | Free key = $1/day (10,000 list requests, resets 00:00 UTC); keyless gets 10x less |
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
python scripts/build_discipline_dashboard.py --inputs stroke=data/benchmarks/stroke/fully_enriched.csv ... \
  --out-dir data/benchmarks/dashboard            # add --enrichment-dir data/enrichment for legacy CSVs
python -m http.server 8000 --directory data/benchmarks/dashboard/site   # preview the interactive site
```

## Dashboards
- `build_discipline_dashboard.py` writes the static single-file report (`discipline_dashboard.html`) and,
  unless `--skip-site`, calls `build_dashboard_data.py` on each loaded frame to write `dashboard_data.json`
  and copy `dashboard/` (index.html, app.js, styles.css) + the JSON + `legacy.html` into `<out-dir>/site/`.
- `dashboard_data.json` stores **counts only** (`COUNT_KEYS`: n, oa, oa_<status>×6, code, data, material,
  preprint, reg, n_abs, das_audited, das_stmt, das_<category>×8) at the grain year × high_impact × journal
  (top 40 + Other) × first-author country (top 25 + Other) per discipline, plus year × high_impact × funder
  (top 25 + Other + no-funder; multi-valued, so funder n's exceed paper totals). Rows are flat int lists; the
  browser sums and divides. Legacy CSVs without the new columns get `available.*=false` and the page hides
  those charts. `--enrichment-dir` left-joins `<discipline>_work_metadata.csv` by `doi_norm` (fills blank /
  missing fields only, then derives `in_article_corpus` via `apply_corpus_flag`; registration flags are
  derived from title+abstract via `apply_registration_flags` when missing). Because the join is by DOI,
  release rows without a DOI (e.g. the DOI-less ISC conference abstracts in *Stroke*) get no metadata and
  are out of corpus (`corpus_rule` = `openalex_type_doi_only`); they are never counted as closed articles.
- **One OA definition** (`build_discipline_dashboard.derive_open_access`, text in `OA_DEFINITION`): open =
  OpenAlex `oa_status` known and not `closed`; the legacy `infer_oa_series` inference (`is_oa` / OA journal /
  OA URL / licence) applies only where `oa_status` is unknown. Both the site `oa` count and the legacy report's
  `oa_rate` use it, so OA rate = 1 − closed wherever `oa_status` is complete.
- **Years**: `assemble_payload` marks `partial_years` (≥ run year − 1, shaded on the site) and
  `default_year_range` = first year … last complete year (< run year). The site's year slider starts at that
  default (2015–2025 for a 2026 run) and the partial years remain selectable.
- GitHub Pages (outputs repo `docs/`): workflows copy `site/*` to `docs/` and the old report to `docs/legacy.html`.

## Pipeline stages (search_stroke_dois.py)
1. **OpenAlex retrieval** — parallel term×year cursor pagination → `data/{discipline}/raw_openalex_articles.csv`.
   The `select` list includes `type, open_access, locations, authorships, is_retracted, has_fulltext, funders`
   (`funders` is a valid select field; `grants` is not), flattened by `flatten_openalex_work_metadata` into
   `work_type`, `oa_status`, `primary_source_type`, `primary_source_is_in_doaj`, `has_preprint_version`,
   `is_preprint_record`, `preprint_servers`, `first_author_country`, `countries`, `funders`, `is_retracted`, `has_fulltext`.
2. **OpenAlex metadata backfill** (`--backfill-openalex-metadata`) — for retrieval datasets that predate those
   columns: batched `filter=doi:a|b|...` lookups (50 DOIs/request) for rows with a blank `work_type`, cached per
   batch in `openalex_metadata_cache.jsonl` (resumable; unknown DOIs recorded as `_missing`). Uses the budget
   helpers: waits for the daily reset on a keyed 429, never drops the key, pauses at
   `--openalex-metadata-min-budget-remaining`. A complete backfill rewrites `raw_openalex_articles.csv`.
   Not needed for new runs.
3. **PubMed retrieval** (optional `--include-pubmed`) — adds PMC OA links
4. **Unpaywall snapshot join** — DuckDB left-join on DOI, fills `is_oa`, `license_unpaywall`, `best_oa_location_url`
5. **Crossref relations join** — DuckDB, fills `repo_links` from supplement/data relations
6. **Regex extraction** — GitHub/Zenodo/OSF/dataset-repo patterns from title+abstract+url fields; registration
   flags (`reg_trial_registry`, `reg_prospero`, `reg_preregistration_wording`, `registered_any`,
   `registration_signal`) from `REGISTRY_PATTERNS`; `in_article_corpus` / `corpus_rule` from
   `apply_corpus_flag`: when the frame has any OpenAlex metadata, in corpus = `work_type` article/review AND
   `primary_source_type` journal AND non-blank DOI AND the row has metadata (`openalex_type_doi_only`; no
   name-based fallback for unenriched rows). `NON_JOURNAL_SOURCE_PATTERN` on the journal name is used only
   for legacy frames with no metadata at all (`source_name_fallback`). Rows are never dropped; the dashboard
   filters on the flag.
7. **API enrichment** — async Unpaywall/Zenodo/OSF/GitHub lookups with resumable JSON cache
8. **Dataset repo search** — DataCite → Dryad → Figshare API chain, async with rate limiting
9. **Embedding ranking** (optional) — SentenceTransformer cosine similarity to an open-science concept vector
10. **LLM extraction** (optional) — OpenAI or Ollama JSON extraction of `code_link`, `data_link`, `preregistered`, `preprint`.
    Afterwards `apply_metadata_preprint_flag` fills a blank `preprint` from `has_preprint_version`.
11. **DAS audit** (`--das-audit-sample-per-year N`, default 0 = off; or `--das-audit-all` for a census of every
    in-corpus article with open-access full text) — for in-corpus rows with a DOI: Europe PMC
    search resolves DOI → PMCID (`DOI:"..." OR ...`, ≤25 per query, `resultType=lite`, `OPEN_ACCESS:y AND HAS_FT:y AND SRC:MED`),
    a deterministic per-year sample of N full-text articles is fetched (`fullTextXML`, 5 workers, 0.1 s delay),
    data-availability statements are extracted (`extract_das_statements`) and classified (`classify_das_text`).
    `--das-audit-refetch-empty` drops cached full texts that yielded no statement so an improved extractor fetches
    them again (the newer record wins in `das_cache.jsonl`).
    Writes `das_pmcid`, `das_available`, `das_has_statement`, `das_primary`, `das_text`. Open-access full text only,
    so rates are optimistic relative to the whole corpus.
    - Extraction: `<sec sec-type="data-availability">`-style sections or DAS-like titles; `notes`/`fn`/`custom-meta`
      (`<meta-name>`)/`supplementary-material`/`ack`/`statement` elements flagged by attribute/title; short (<1500 chars)
      `fn`/`notes`/`ack` whose text matches `DAS_SENTENCE_PATTERN` (unmarked publisher boilerplate: AHA, Wolters Kluwer,
      PeerJ, Frontiers); last resort any `<p>` starting like a DAS or containing a DAS sentence (sliced to it, 20-700 chars).
      A statement that is only its heading (<15 chars of body) counts as no statement.
    - Categories (`DAS_PRIMARY_PRIORITY`, first match wins): `repository` (authors' own deposit: Zenodo, Dryad, OSF,
      GitHub, dbGaP, DOI 10.5281/10.6084/10.5061, "available at http..."), `public_source` (secondary analysis of a
      public/third-party dataset: UK Biobank, NHANES, NHIRD, CHARLS, MIMIC, GBD, HCUP/NIS, SEER, Medicare, CPRD, GWTG,
      "publicly available from the official ... website"), `controlled_or_restricted`, `on_request`, `in_article`,
      `not_available_or_na`, else `other_or_unclear`; `no_statement` when nothing was found. `DAS_REFUSAL_PATTERN`
      ("will not be made available", "no datasets were generated", "data sharing not applicable", "no additional data")
      forces `not_available_or_na` unless a repository or public source is named. `code_shared` is an extra
      multi-label flag only.
    - Validation: this extractor and classifier were validated as a standalone script on 19,637 open-access stroke
      articles (blind re-check rounds in `talk/outputs/das_audit/validation.md` on the `talk/wsc2026` branch); the
      residual miss rate is about 1% of articles. The standalone script was retired on 2026-10-11; the pipeline holds
      the only copy, and `tests/test_metadata_flags_das.py` carries the validated cases.
12. **High-impact subgroup** — filters by journal IF threshold + citation percentile (pooled across years within
    the discipline) → `high_impact_subset.csv`
13. **Preview export** — first N rows → `enriched_preview.csv`

Caches:
- `data/{discipline}/enrich_cache.json` — API enrichment results (resumable)
- `data/{discipline}/llm_cache.json` — LLM extraction results (resumable)
- `data/{discipline}/openalex_metadata_cache.jsonl` — batched OpenAlex work metadata by DOI (resumable). The JSONL
  written by the retired standalone `enrich_openalex_work_metadata.py` (list-valued fields, extra columns) loads
  as-is: copy or symlink `data/enrichment/<discipline>_work_metadata.jsonl` to this path and the backfill is free.
- `data/{discipline}/das_cache.jsonl` — Europe PMC DOI→PMCID resolutions and full-text DAS extractions (resumable).
  Lines from the retired standalone audit's `statements.jsonl` (no `kind` key) load as full-text records, so
  appending that file here avoids re-fetching those articles.
- `data/{discipline}/retrieval_slices/` — per-term per-window raw API results

Backfill an existing discipline and run the DAS audit on it. `--force` is needed because `fully_enriched.csv`
exists; retrieval is reused from the cached `raw_openalex_articles.csv` (so `--terms` does not matter), and the
enrichment / LLM caches make the re-run cheap:
```bash
python scripts/search_stroke_dois.py --discipline stroke --output-dir data/benchmarks/stroke \
  --start-year 2015 --force --disable-dataset-search \
  --backfill-openalex-metadata --das-audit-sample-per-year 1500
# or via the runner (presets resolved for you):
python scripts/run_discipline_benchmark.py --disciplines stroke --force --skip-dashboard \
  --disable-dataset-search --backfill-openalex-metadata --das-audit-sample-per-year 1500
```

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
| `preregistered` | boolean | Pre-registration found (LLM, candidate subset only) |
| `preprint` | str | Preprint URL/identifier (LLM), else preprint server names from OpenAlex, else `openalex:preprint_version` |
| `work_type` | str | OpenAlex work type (`article`, `review`, `preprint`, `dataset`, `erratum`, ...) |
| `oa_status` | str | OpenAlex OA status: `diamond`, `gold`, `hybrid`, `green`, `bronze`, `closed` |
| `primary_source_type` | str | OpenAlex primary source type (`journal`, `repository`, ...) |
| `primary_source_is_in_doaj` | boolean | Primary source listed in DOAJ |
| `has_preprint_version` | boolean | A location on a preprint server exists (and the record itself is not a preprint) |
| `is_preprint_record` | boolean | The work is a preprint record |
| `preprint_servers` | str | Pipe-joined preprint server names |
| `first_author_country` | str | ISO country of the first author |
| `countries` | str | Pipe-joined distinct author countries |
| `funders` | str | Pipe-joined funder names |
| `is_retracted` / `has_fulltext` | boolean | OpenAlex flags |
| `reg_trial_registry` / `reg_prospero` / `reg_preregistration_wording` | boolean | Regex registration signals over title+abstract |
| `registered_any` / `registration_signal` | boolean | Any regex registration signal (identical) |
| `in_article_corpus` | boolean | Journal article/review with a DOI and OpenAlex metadata (type article/review + journal source); rows without metadata/DOI are out. Journal-name fallback only for frames with no metadata at all |
| `corpus_rule` | str | `openalex_type_doi_only` or `source_name_fallback` (one value per frame) |
| `das_pmcid` | str | Europe PMC PMCID used for the DAS audit |
| `das_available` | boolean | Full text fetched and parsed (article was audited) |
| `das_has_statement` | boolean | A data-availability statement was found (audited rows only) |
| `das_primary` | str | `repository` (authors' deposit), `public_source` (public/third-party dataset), `controlled_or_restricted`, `on_request`, `in_article`, `not_available_or_na`, `other_or_unclear`, `no_statement` |
| `das_text` | str | Extracted statement(s), truncated to 1000 chars |
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

Tests live in `tests/` (`test_pipeline_deterministic.py`, `test_openalex_budget.py`, `test_metadata_flags_das.py`,
`test_dashboard_metrics.py`, `test_dashboard_data.py`). They load the scripts directly and test pure-logic
functions (DOI normalization, date windows, LLM payload parsing, regex extraction, deduplication, dashboard
count aggregation). No API calls, no fixtures on disk — safe to run in CI.

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

## OpenAlex budget constraint (metered pricing since mid-2026)
- One key, $1/day budget. Full 4-discipline run needs ~2 daily budgets: expect ~2 days on the
  free tier, or prepay ~$2 to finish in one day.
- On 429/budget exhaustion with a key, `search_stroke_dois.py` never falls back to keyless mode.
  It reads `x-ratelimit-reset` (fallback: next 00:00 UTC), sleeps until reset + 60 s, and resumes
  the same cursor. Cap: `--openalex-budget-wait-max-hours` (default 30; CI passes 5 because
  hosted runners cap jobs at 6 h). Header/endpoint names are unified in
  `openalex_requests_remaining()` / `openalex_reset_seconds()`.
- A slice that stops early is saved as `*.partial.csv` and is re-run next invocation; the raw
  dataset is not written and the run exits non-zero. Completed slices stay cached as before.
- Scheduled workflow: `max-parallel: 1`, `retrieval_slices/` cached via actions/cache, and a
  publish gate (all four `fully_enriched.csv` with >50,000 rows unless `allow_partial=true`).

## Architecture notes
- `search_stroke_dois.py` is intentionally monolithic for portability — all stages callable from
  one import. The `REPOSITORY_AND_GITHUB_PLAN.md` doc tracks a planned modularization.
- `extract_open_science_fireduck.py` is an empty placeholder for a planned FireDucks-based rewrite.
- Deduplication prefers OpenAlex rows over PubMed when both have the same DOI (OpenAlex has richer
  metadata), but prefers PubMed when a PubMed ID is present on only one side.
- The `.gitignore` excludes `data/`, `.venv/`, `.env`, caches, and large outputs. The
  `outputs_archive/` directory in this repo holds only `metadata.json` and `manifest.csv` as
  pointers to the separate outputs repo.
