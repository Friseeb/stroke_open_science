# Validation of the data-availability-statement parser

Audit scope: 19,637 open-access stroke articles with full text in Europe PMC, 2016 to 2025,
2,000 sampled per year (seed 2026), fetched 2026-10-06. Source: `scripts/audit_data_availability_europepmc.py`.

## Method

1. Statement extraction from JATS XML: sections typed or titled as data/code availability, notes,
   footnotes, custom metadata, acknowledgements; then a sentence-level fallback for unmarked
   statements using publisher templates (AHA, Wolters Kluwer, PeerJ, Frontiers, Springer).
2. Classification by regex into one primary category with priority
   repository > public_source > controlled_or_restricted > on_request > in_article >
   not_available_or_na > other_or_unclear. Explicit refusals win unless a repository or public
   source is named. Heading-only statements count as no statement.
3. Blind re-check: a random sample of 100 recent (2022-2025) articles classified as "no statement"
   is re-read in full text with a broad statement-phrase scanner; every hit is inspected by hand.

## Blind re-check results

| Round | Parser state | Flagged of 100 | Real misses | Narrative false alarms |
|---|---|---|---|---|
| 1 | Marked sections + basic sentence fallback | 30 | 6 | 24 |
| 2 | Publisher templates added, all no-statement articles re-fetched | 5 | 3 | 2 |
| 3 | "shared/provided on request", "data and materials publicly available" added, re-fetched | 5 | 1 | 4 |

Round 3 residual: about 1% of articles still marked "no statement" contain one, which is about
0.3% of all audited articles. The round 3 miss ("readers seeking access must complete a formal
data sharing agreement") was added to the detector afterwards without a further re-fetch.

## Classifier spot checks

21 real statement sentences with hand-assigned categories pass in both the standalone script and
the pipeline port (tests/test_metadata_flags_das.py in the main repository). Reclassification of
the full set with the final rules reduced "other or unclear" from 9.2% to 3.9% of articles,
mainly by recognising the Frontiers template "will be made available by the authors, without
undue reservation" as on-request, and by separating secondary analyses of public datasets
(UK Biobank, NHANES, CHARLS, GBD, NHIRD, ...) from authors' own repository deposits.

## Known limits

- Open-access full text only; closed articles are not audited, so the figures are optimistic for
  the stroke literature as a whole.
- Journals with no statement section and no template phrasing (Cureus, J Phys Ther Sci, J Stroke)
  show near-zero statement rates; three spot checks of each found no availability wording in the
  text, so these are genuine absences, not parser failures.
- "In article or supplement" and "on request" can co-occur; the priority order assigns one label.
