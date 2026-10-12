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
- `dashboard_data.json` (schema v2) stores **counts only** (`COUNT_KEYS`: n, oa, oa_<status>×6, code, data, material,
  preprint, reg, n_abs, das_audited, das_stmt, das_<category>×8, ft_github, ft_reg, ft_supp) at the grain year × high_impact × journal
  (top 40 + Other) × first-author country (top 25 + Other) per discipline, plus year × high_impact × funder
  (top 25 + Other + no-funder; multi-valued, so funder n's exceed paper totals). Rows are flat int lists; the
  browser sums and divides. Legacy CSVs without the new columns get `available.*=false` and the page hides
  those charts. `--enrichment-dir` left-joins `<discipline>_work_metadata.csv` by `doi_norm` (fills blank /
  missing fields only, then derives `in_article_corpus` via `apply_corpus_flag`; registration flags are
  derived from title+abstract via `apply_registration_flags` when missing). Because the join is by DOI,
  release rows without a DOI (e.g. the DOI-less ISC conference abstracts in *Stroke*) get no metadata and
  are out of corpus (`corpus_rule` = `openalex_type_doi_only`); they are never counted as closed articles.
- Besides the journal × country cells, v2 ships three more count tables per discipline: `funder_cells`
  (year × hi × funder, multi-valued), `income_cells` (year × hi × first-author World Bank income group) and
  `institution_cells` (year × hi × institution, multi-valued, top 60 by audited papers). The full-text flags
  (`ft_*`) and the DAS categories use `das_audited` as denominator; `METRICS[*].denominator` says which.
- The site (`dashboard/index.html`, `app.js`, `styles.css`, no build step) is a tabbed explorer: one sticky
  selection bar (year presets + custom range, disciplines, focus, a single *slice* control for income group /
  journal / country / funder, all vs high-impact, reset, copy link, CSV) scoping nine views: Overview (hero,
  tiles, emphasis OA trend, DAS five classes, full text vs abstract table), Trends (metric × compare
  disciplines / income groups / subset × rate or count), Open access (routes free-to-author / APC / bronze /
  closed or six statuses; by year and by discipline), Data statements (five ordered classes or eight categories as
  small multiples; denominator audited or with-statement; signals by discipline), Equity (income-group tiles,
  OA route or any metric by income group, full-text signals by income group), Commitment (index = mean over the
  chosen verified full-text signals of entity rate ÷ discipline rate, 1 = average; entity, min audited, top N),
  Journals (metric, min papers, top N), Countries & funders (sortable tables with full-text columns), Methods.
  The selection lives in the URL hash, so a link reproduces a view. A *Quick views* row applies named
  selections (Stroke in Korea, statements 2022–2025, who pays to be read, prize shortlist, full text vs abstract).
  Policy milestones from `configs/policy_events.json` (ICMJE statements 2018, Plan S 2021, OSTP memo 2022, NIH DMS
  2023; shipped as `policy_events`) draw as hairlines with hover detail on the trend and by-year charts (toggle in
  Trends; labels hidden on half-width charts). Every chart has PNG / SVG download buttons (client-side Plotly).
- Visual system (2026-10-12 pass): editorial, not boxed. IBM Plex Sans for UI and columns, Source Serif 4 for the
  masthead, the deck ("bajada"), the hero sentence and section titles; a 12px modular scale (`--m`, `--fs-*`: 12 /
  15 / 18 / 24 / 36 / 72 / 96) with line-heights on a 12px baseline grid; sections are a 2px ink rule plus a title
  on the page, tiles sit on rules, only the selection band is a filled object; cool-biased neutrals; the selection
  band is two explicit rows (years presets + custom row on demand, disciplines, papers / focus, slice, quick-view
  menu, actions). Tufte-style data density: inline SVG sparklines in the overview tiles (replacing meter bars) and a
  by-year trend column in the journal, country and funder tables; Trends offers a small-multiples layout; the
  overview's emphasis chart drops the legend (grey series are named in the subtitle). Screenshots for review are
  taken with puppeteer-core driving the installed Chrome (Chrome's own --screenshot flag misreports phone widths). Colours: one validated blue ordinal ramp
  (darkest = most open) plus a neutral grey for closed / no statement; one fixed colour per discipline;
  dark-mode steps are selected, not flipped. Every chart has a table twin.
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
   `is_preprint_record`, `preprint_servers`, `first_author_country`, `countries`, `funders`, `institutions` (first 10
   distinct author institutions, order kept), `first_author_institution`, `is_retracted`, `has_fulltext`.
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
   filters on the flag. `first_author_income_group` (`high` / `upper_middle` / `lower_middle` / `low`, blank if
   unknown) comes from `first_author_country` via `configs/country_income_groups.csv` (World Bank API
   classification fetched 2026-10-11, plus Taiwan, Jersey and the French overseas departments GF/GP/MQ/RE added by hand as `high`; override with `--country-income-csv`).
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
    Writes `das_pmcid`, `das_available`, `das_has_statement`, `das_primary`, `das_text`, and the whole-full-text
    flags `das_mentions_github`, `das_mentions_supplement`, `das_mentions_trial_registration` (full-text code-sharing
    and registration signals for the audited sample; abstract-based `github` / `registration_signal` undercount).
    Open-access full text only, so rates are optimistic relative to the whole corpus.
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
12. **High-impact subgroup** — journal IF ≥ threshold OR citations ≥ the percentile **within the paper's publication
    year** (citations accrue with age; pooled percentile only for rows without a year). `high_impact_reason` records
    the per-year threshold, e.g. `cited_by_count>=41 (top 10.0% of 2019)` → `high_impact_subset.csv`
13. **Preview export** — first N rows → `enriched_preview.csv`

Caches:
- `data/{discipline}/enrich_cache.json` — API enrichment results (resumable)
- `data/{discipline}/llm_cache.json` — LLM extraction results (resumable)
- `data/{discipline}/openalex_metadata_cache.jsonl` — batched OpenAlex work metadata by DOI (resumable). The JSONL
  written by the retired standalone `enrich_openalex_work_metadata.py` (list-valued fields, extra columns) loads
  as-is: copy or symlink `data/enrichment/<discipline>_work_metadata.jsonl` to this path and the backfill is free.
- `data/{discipline}/das_cache.jsonl` — Europe PMC DOI→PMCID resolutions and full-text DAS extractions (resumable).
  In CI, `enrich_cache.json`, `openalex_metadata_cache.jsonl` and `das_cache.jsonl` are kept in the Actions cache across
  runs (like `retrieval_slices/`), so a job that hits the 6 h runner cap resumes its lookups on the next dispatch.
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

## Refresh model: refresh what changes, accumulate what does not

A benchmark run is **not** a rebuild from scratch, and should never be treated as one. The stages differ in
how they age and in what they cost, and the workflow is organised around that:

| Stage | Ages? | Cost per discipline | Treatment |
|---|---|---|---|
| OpenAlex retrieval (records, OA status, citations, metadata) | Yes: OA status flips when embargoes end, citations accrue, indexing lags | ~30 min, ~$0.50 of OpenAlex credit (daily $1 free allowance first, then prepaid credit) | **Re-pulled fully every run.** A current snapshot is the point of the benchmark, and a full pull is cheaper and simpler than an incremental merge. Completed slices are cached in the Actions cache so an interrupted job resumes. |
| Europe PMC data-availability audit (full-text fetch + classification) | No: a published article's statement does not change | ~1.5 h cold, minutes warm | **Accumulated forever** in `das_cache.jsonl`. Only articles not yet fetched are fetched; the per-year sample is deterministic (seed + corpus), so new runs mostly hit the cache and only audit the newest year's articles. |
| API enrichment (Unpaywall, Zenodo, OSF, GitHub, dataset repos) | Rarely | up to ~1 h cold | **Accumulated** in `enrich_cache.json`. |
| OpenAlex metadata backfill | n/a for new retrievals (captured at retrieval) | free when cached | `openalex_metadata_cache.jsonl`, only for legacy frames. |
| Dashboard, high-impact subset, exports | derived | minutes | Recomputed from the frames every run. |

Where the accumulated caches live, in order of preference:
1. **Actions cache** (`stage-caches-v1-<discipline>-...`, restored by prefix): fast path between consecutive runs.
2. **Outputs repo release `caches`** (`<discipline>-caches.tar.gz`, one rolling release, replaced after every real run,
   skipped for smoke tests and dry runs): survives Actions-cache expiry and lets a local run seed CI. The first seed
   (2026-10-12) came from the local talk run: 2,000 audited articles per year per discipline.
3. **Local `data/<discipline>/`**: the same files; copy or symlink them to seed a local run.

Consequences: a six-monthly run costs about $2 and two to three hours of runner time in total; a re-dispatch after a
timeout resumes rather than repeats; and the full-text audit grows monotonically into a census over time. The one
thing that is deliberately redone is retrieval, because that is where the data actually changes. Nothing in the
pipeline needs the previous run's frames; it needs the caches.

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
| `das_mentions_github` / `das_mentions_supplement` / `das_mentions_trial_registration` | boolean | Whole-full-text flags for audited rows (NA otherwise) |
| `institutions` / `first_author_institution` | str | OpenAlex author institutions (first 10 distinct, `\|`-joined) / first author's first institution |
| `first_author_income_group` | str | World Bank income group of `first_author_country` (`high`, `upper_middle`, `lower_middle`, `low`; blank if unknown) |
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
