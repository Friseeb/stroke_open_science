# Expert Collaborator Brief

## Purpose

This note is intended for expert review of the current `stroke_open_science` repository before
further methodological expansion and possible public release on GitHub.

The project currently functions as a scalable literature-mining pipeline that:

- retrieves publications by discipline, term, and year
- enriches records with open-science indicators
- creates paper-level benchmark tables
- produces cross-discipline summary dashboards

This document separates:

- the current implementation decision
- the rationale for that decision
- viable alternatives
- questions where expert input would materially improve the study design

## Current Pipeline In Plain Terms

At a high level, the repository does the following:

1. Retrieve papers from OpenAlex, with optional PubMed augmentation.
2. Standardize and deduplicate records.
3. Add open-access and repository signals from snapshots, regex extraction, and APIs.
4. Optionally rank papers by embedding similarity to an "open science" concept.
5. Optionally use an LLM on a targeted subset to extract harder signals.
6. Label a high-impact subset.
7. Aggregate paper-level results into discipline-year and discipline-level summaries.

## Decision Register

### 1. Retrieval Source Strategy

Current decision:

- Use OpenAlex as the primary retrieval source.
- Optionally merge PubMed records for better biomedical recall.

Justification:

- OpenAlex provides broad scholarly coverage plus citation and OA metadata in a form that is easy
  to query programmatically.
- PubMed adds domain relevance for biomedicine and helps recover papers that may be underrepresented
  or differently indexed in OpenAlex.
- Keeping PubMed optional allows the same codebase to support non-biomedical comparisons.

Options:

- OpenAlex only.
  Pros: simpler pipeline, one retrieval source, easier reproducibility.
  Cons: weaker biomedical recall and less alignment with domain-specific indexing.
- PubMed first, then map into OpenAlex.
  Pros: stronger biomedical specificity, possible use of MeSH terms.
  Cons: harder cross-discipline comparability and weaker non-biomedical portability.
- Dual-source mandatory retrieval.
  Pros: higher recall.
  Cons: more complexity, more deduplication burden, slower runs.

Questions for expert review:

- Should biomedical benchmarking be defined by OpenAlex coverage, PubMed coverage, or their union?
- Is stroke best treated as a biomedical corpus only, or should adjacent rehabilitation,
  engineering, and health-services literatures remain in scope?

### 2. Query Definition And Discipline Presets

Current decision:

- Use manually curated discipline presets from `configs/discipline_presets.json`.
- Search multiple related terms per discipline.

Justification:

- The presets are transparent and easy to review.
- The same structure supports cross-discipline comparisons with parallel logic.
- It avoids premature dependence on opaque topic classifiers.

Options:

- Keep curated term lists and revise them manually with expert input.
- Replace or supplement terms with controlled vocabularies such as MeSH.
- Use OpenAlex concepts or topic filters instead of plain text title search.

Questions for expert review:

- Are the current stroke terms too broad, too narrow, or missing key subdomains?
- Should transient ischemic attack remain in the stroke cohort or be treated separately?
- Is title search sufficient, or should abstract-based retrieval be introduced despite the expected
  increase in noise?

### 3. Retrieval Windowing And Resume Strategy

Current decision:

- Support date-windowed retrieval by year or smaller windows such as 6-month slices.
- Save retrieval slices under `retrieval_slices/` so interrupted runs can resume.

Justification:

- Large OpenAlex and PubMed queries are operationally fragile.
- Smaller slices reduce the cost of timeouts and rate limiting.
- Slice-level caching improves reproducibility of dated reruns.

Options:

- Annual windows only.
  Pros: simpler mental model.
  Cons: more expensive reruns after failure.
- Shorter windows such as quarterly.
  Pros: better resume behavior.
  Cons: more files and more orchestration overhead.

Questions for expert review:

- Should the benchmark prefer operational simplicity or exact rerun reproducibility?
- Is a dated-snapshot strategy sufficient for publication, or is formal release versioning needed?

### 4. Deduplication Logic

Current decision:

- Standardize DOI values.
- Prefer records with DOI, PMID, abstract availability, and stronger metadata.
- Deduplicate first by OpenAlex `id`, then DOI, then PMID.

Justification:

- DOI is the most stable cross-source identifier for publication-level merging.
- PMID is a strong fallback for biomedical records.
- Ranking retained records by metadata completeness preserves the most informative version.

Options:

- DOI-only deduplication.
  Pros: simple and precise where DOI exists.
  Cons: loses PMID-only records and incomplete matches.
- Fuzzy title-based deduplication.
  Pros: may recover records without DOI or PMID.
  Cons: higher false-match risk and harder auditability.

Questions for expert review:

- Is it acceptable to keep DOI/PMID-negative records, or should the benchmark require persistent
  identifiers?
- Should duplicate resolution explicitly prefer one source over another for biomedical records?

### 5. Open Access Inference

Current decision:

- Treat OA as present when any of the following are available: explicit OA flag, OA journal flag,
  OA landing URL, or Unpaywall license.

Justification:

- OA metadata fields are incomplete and inconsistently populated across sources.
- Combining several weak signals improves recall of true OA items.

Options:

- Strict OA definition using only source-reported boolean fields.
  Pros: higher specificity.
  Cons: more false negatives.
- Tiered OA definition that distinguishes gold/hybrid/green/best-evidence.
  Pros: richer analysis.
  Cons: more complexity and more edge cases.

Questions for expert review:

- Is the benchmark meant to measure any public access, or specific forms of open access?
- Should OA type be preserved as a separate analytic variable instead of a single inferred flag?

### 6. Snapshot-First Enrichment

Current decision:

- Use local parquet snapshots for Unpaywall and Crossref relations when available.
- Fall back to live APIs for missing fields.

Justification:

- Snapshot joins are much cheaper and more scalable than API-only enrichment.
- Local snapshots reduce dependence on rate limits during serious runs.
- API fallback still allows smaller-scale runs without local mirrors.

Options:

- API-only enrichment.
  Pros: simpler setup.
  Cons: slower, less reproducible, more vulnerable to rate limits.
- Snapshot-only enrichment.
  Pros: maximum reproducibility.
  Cons: excludes users without local mirrors and may lag behind live metadata.

Questions for expert review:

- For public release, should the reference workflow assume snapshot availability or remain API-first?
- Are there additional local resources that would materially improve benchmark quality?

### 7. Regex Extraction For Code, Data, And Repository Signals

Current decision:

- Run deterministic regex extraction over titles, abstracts, OA URLs, and repository link fields.
- Detect direct links to GitHub, Zenodo, OSF, and multiple dataset repositories.

Justification:

- Regex extraction is cheap, transparent, auditable, and reproducible.
- It captures the highest-confidence explicit signals before heavier enrichment stages.

Options:

- Keep deterministic regex as the first-pass signal layer.
- Expand repository coverage further.
- Replace some regex logic with URL canonicalization or learned classifiers.

Questions for expert review:

- Which repository signals should count as "open materials" in the primary benchmark?
- Should supplementary material URLs count equally with dedicated repository links?

### 8. Dataset Repository Detection

Current decision:

- Use a two-stage dataset strategy:
  1. regex detection for known repositories or accession patterns
  2. targeted API search through DataCite, Dryad, and Figshare for missing rows

Justification:

- Dataset sharing is expressed inconsistently across papers.
- Explicit regex detection is precise, while DataCite-style lookup can recover linked datasets not
  named directly in the paper metadata.

Options:

- Keep current strategy.
- Restrict the benchmark to direct dataset links only.
- Add domain repositories specific to stroke imaging, neurophysiology, or clinical data.

Questions for expert review:

- Which dataset repositories are methodologically important enough to add now?
- Should accession-only evidence count as public data sharing if public accessibility is uncertain?

### 9. API Enrichment Prioritization

Current decision:

- Rank pending API enrichments using citation count and missingness, then cap total API lookups.

Justification:

- The repository is designed for scale.
- Prioritizing highly cited or information-poor records improves value per API call.
- Explicit caps make large runs operationally predictable.

Options:

- Uniform API enrichment for all rows.
  Pros: more complete.
  Cons: slower and harder to scale.
- Strict prioritization to only the top-cited rows.
  Pros: efficient.
  Cons: may bias signal recovery toward influential papers.

Questions for expert review:

- Is selective enrichment acceptable for the intended scientific use, or should completeness outrank
  efficiency?
- If selective enrichment remains, should the benchmark label which rows received full enrichment?

### 10. Embedding-Based Open Science Score

Current decision:

- Compute an optional embedding similarity score between each paper and a fixed "open science"
  concept string.

Justification:

- The score is a soft prioritization tool, not a hard label.
- It helps target the LLM stage toward papers more likely to contain relevant signals.

Options:

- Keep the score as an internal ranking feature only.
- Promote it to an analytic variable in downstream summaries.
- Replace it with supervised classification once labeled data exist.

Questions for expert review:

- Is a concept-similarity score useful for this benchmark, or too heuristic for serious analysis?
- Would a small expert-labeled training set be a better next step than continued prompt-based
  targeting?

### 11. Targeted LLM Extraction

Current decision:

- Use OpenAI or Ollama on a targeted subset of likely positive papers.
- Restrict LLM outputs to `code_link`, `data_link`, `preregistered`, and `preprint`.
- Cache outputs so reruns are stable and inexpensive.

Justification:

- These signals are often present in prose rather than structured metadata.
- A targeted LLM stage increases recall without paying the cost of model calls on every row.
- Restricting the schema reduces prompt drift and simplifies audit.

Options:

- Disable LLM entirely and rely on deterministic methods only.
  Pros: maximum reproducibility and lower cost.
  Cons: weaker recall for subtle or prose-only signals.
- Run the LLM on all rows.
  Pros: maximal coverage.
  Cons: expensive, slower, less operationally stable.
- Use LLM output only as a candidate generator for human review.
  Pros: stronger methodological conservatism.
  Cons: slower manual workflow.

Questions for expert review:

- Is LLM-assisted extraction acceptable in the benchmark core, or should it be reported as an
  exploratory layer?
- What validation threshold would make LLM-derived fields credible for publication?

### 12. High-Impact Subgroup Definition

Current decision:

- Label a paper as high-impact if either:
  - journal impact factor is at least the configured threshold
  - citation count is at or above the configured percentile of the retrieved cohort

Justification:

- Venue prestige and article influence capture different notions of impact.
- The hybrid rule is easy to explain and produces a traceable reason field.

Options:

- Journal metric only.
  Pros: stable and simple.
  Cons: misses influential papers in lower-impact venues.
- Citation percentile only.
  Pros: article-level.
  Cons: time-sensitive and field-dependent.
- More sophisticated field-normalized citation measures.
  Pros: methodologically stronger.
  Cons: more data requirements and more complexity.

Questions for expert review:

- Is this subgroup intended as a pragmatic benchmark or a publication-quality impact construct?
- Should the impact definition be field-normalized across disciplines?

### 13. Benchmark Summary Metrics

Current decision:

- Aggregate paper-level outputs into discipline-year and discipline-level summary tables.
- Report OA rate, open-material rate, repository-specific rates, preregistration/preprint rates,
  high-impact rate, any-open-science rate, and citation averages.

Justification:

- These summaries are useful for comparison across disciplines and over time.
- They are straightforward to recompute from the paper-level table.

Options:

- Keep simple descriptive summaries.
- Add uncertainty intervals or bootstrap estimates.
- Add stratification by article type, venue, study design, or region if metadata become available.

Questions for expert review:

- Which summary metrics are essential for the primary dashboard?
- Should repository-specific rates remain separate, or collapse into broader "materials/data/code"
  categories?

### 14. Caching, Outputs, And Reproducibility

Current decision:

- Write intermediate CSV outputs, JSON caches, retrieval slices, and scheduled manifests.

Justification:

- Long-running API workflows need recoverability.
- Explicit intermediate outputs make debugging easier.
- Dated manifests support schedule-based benchmarking.

Options:

- Continue current file-based workflow.
- Move to a more formal pipeline framework with typed artifacts and task metadata.
- Keep current scripts but add schema validation and release manifests.

Questions for expert review:

- Is the current script-driven workflow sufficient, or should the project move toward a more formal
  workflow engine?
- Which artifacts must be retained for audit and publication reproducibility?

## Recommended Topics For Expert Input

The most important expert choices are:

1. Corpus definition: what should count as the stroke literature?
2. Retrieval logic: title-only search versus broader topic or abstract-based retrieval.
3. Evidence policy: which signals are acceptable as primary benchmark evidence?
4. LLM policy: core method, optional augmentation, or validation-only layer.
5. Impact policy: pragmatic subgroup versus more formal field-normalized benchmark.

## Proposed Immediate Validation Work

Before treating the benchmark as publication-ready, the repository would benefit from:

- a manually reviewed gold-standard sample across positive and negative cases
- precision and recall checks for repository-link extraction
- explicit comparison of OpenAlex-only versus OpenAlex-plus-PubMed retrieval
- audit of LLM-derived fields against expert judgement
- sensitivity analysis for the high-impact definition

## Bottom-Line Recommendation

The repository already has a reasonable architecture for a scalable benchmark prototype. The most
important next step is not adding more sources or more model complexity. It is deciding, with domain
expert input, which parts of the current pipeline are acceptable as primary study methods and which
should remain exploratory or supplementary.
