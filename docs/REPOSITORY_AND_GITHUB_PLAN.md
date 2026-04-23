# Repository Improvement And GitHub Release Plan

## Current State

Observed from the current workspace:

- the folder is not yet initialized as a Git repository
- a local `.env` file exists, so secret handling matters immediately
- the workspace is about 11 GB
- the `data/` directory alone is about 9.5 GB
- the codebase is script-oriented, with one very large main pipeline script
- repository documentation is currently light
- there is no visible automated test suite
- there is no visible CI configuration
- there is no license file yet

This means the repository is already useful for local work, but it is not yet in ideal condition
for public release or outside collaboration.

## Recommended Publication Boundary

Recommended default for a public GitHub repository:

- include:
  - source code in `scripts/`
  - configuration templates in `configs/`
  - method notes in `docs/`
  - lightweight example fixtures only if they are small and sanitized
- exclude:
  - the full `data/` working tree
  - caches such as `enrich_cache.json` and `llm_cache.json`
  - local snapshots such as Unpaywall and Crossref parquet mirrors
  - `.env`
  - `.venv`
  - dated scheduled runs

Rationale:

- the current data tree is too large for a normal source repository
- benchmark outputs are generated artifacts, not source
- local snapshots may have redistribution or operational restrictions
- secrets and local tokens must never be published

## Recommended External Sharing Strategy

Option A: code-first GitHub repository

- publish code, docs, configs, and small example fixtures only
- keep large benchmark outputs outside GitHub
- release frozen benchmark outputs through Zenodo, OSF, institutional storage, or GitHub Releases if
  the files are modest

Option B: code repository plus separate data repository

- keep code and tests in the main repository
- publish benchmark outputs in a separate data-focused repository or archival service

Option C: private GitHub first, public later

- use a private GitHub repository to harden structure, tests, and documentation
- move public only after method and licensing decisions are stable

Recommended choice:

- Option C first, then Option A once the project boundary is clean

## Priority Improvements

### 1. Protect The Publication Boundary

Actions:

- keep `data/` excluded by default
- keep `.env` excluded
- add a short data policy document
- define whether any sample fixtures should live under `data/examples/`

Why this matters:

- this is the single highest-risk area for accidental GitHub publication mistakes

### 2. Add Method Documentation

Actions:

- keep the collaborator brief in `docs/`
- add a paper-level schema note for the main outputs
- document which stages are deterministic, heuristic, or LLM-assisted

Why this matters:

- outside collaborators need to know which results are firm and which are approximate

### 3. Add Minimal Test Coverage

Recommended first tests:

- DOI normalization
- journal normalization
- deduplication behavior
- OA inference behavior
- regex extraction behavior for GitHub, Zenodo, OSF, and dataset repositories
- high-impact subgroup logic

Why this matters:

- these are the highest-value deterministic rules in the repository
- they can be tested without expensive API calls

### 4. Refactor The Main Pipeline Script

Current issue:

- `scripts/search_stroke_dois.py` currently concentrates retrieval, normalization, enrichment,
  scoring, and export logic in one large file

Recommended direction:

- split into modules such as:
  - `retrieval.py`
  - `normalization.py`
  - `enrichment.py`
  - `dataset_repos.py`
  - `llm_extract.py`
  - `benchmark.py`
  - `io_utils.py`

Why this matters:

- smaller modules are easier to test, review, and extend
- public repositories benefit from navigable code organization

### 5. Make Reproducibility Explicit

Actions:

- document exact expected environment variables
- decide whether `requirements.txt` is enough or whether a locked environment file is needed
- add a formal run-manifest schema
- consider a fixed smoke-test command that always produces a small reproducible artifact

Why this matters:

- collaborators need to rerun the benchmark without reverse-engineering the repository

### 6. Add CI Before Public Release

Recommended GitHub Actions checks:

- install dependencies
- run deterministic unit tests
- run a lightweight smoke test with `--max-per-query`
- optionally run linting or formatting checks

Why this matters:

- it makes the repository credible to external collaborators immediately

### 7. Decide On License And Citation Policy

Actions:

- choose an explicit software license
- add a `CITATION.cff`
- decide how to cite datasets and benchmark releases separately from code

Why this matters:

- public repositories should state reuse permissions clearly

## Methodological Improvement Opportunities

These are the most useful scientific improvements, not just repository cleanup:

1. Build a validation set with expert-reviewed positives and negatives.
2. Compare OpenAlex-only versus OpenAlex-plus-PubMed cohorts directly.
3. Quantify performance of regex-only, API-only, and LLM-assisted signal recovery.
4. Separate core benchmark metrics from exploratory metrics.
5. Reassess the high-impact definition for cross-discipline comparability.

## Questions To Resolve Before Public GitHub Release

1. Is the public repository intended to share code only, or code plus benchmark outputs?
2. Are LLM-assisted fields part of the official method or an optional augmentation layer?
3. What is the acceptable reproducibility standard for this project: script-level, release-level, or
   publication-level?
4. Which license is appropriate for the intended reuse model?
5. Should the first public release be stroke-only, or already positioned as a cross-discipline
   benchmarking framework?

## Suggested Release Sequence

Recommended order:

1. Finalize docs and publication boundary.
2. Initialize Git locally and make the first clean commit.
3. Add tests for deterministic logic.
4. Add CI.
5. Choose license and citation metadata.
6. Create a private GitHub repository first.
7. Invite the expert collaborator for review.
8. Publish publicly only after method and scope are stable.

## Bottom-Line Recommendation

The repository is already good enough to support serious local work. To make it collaboration-ready
and GitHub-ready, the biggest wins are not algorithmic. They are scope control, documentation,
testing, and a clean separation between source code and generated data.
