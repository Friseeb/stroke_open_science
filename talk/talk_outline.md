# Open science in stroke research: measuring reproducibility and transparency

World Stroke Congress 2026, Seoul. Thu 22 Oct 2026, 15:45-16:00 (15 min), session
"The latest in stroke implementation science" (ID 340), Conference Room 202-203.
Speaker: Sebastian Fridman (Western University, London, Canada).

Goal set by the speaker: leave the room with an agenda of incentives for open science
in stroke, grounded in the first stroke-specific measurement of these practices.

Numbers below come from `talk/outputs/numbers.json` and `talk/outputs/tables/`
(stroke corpus: OpenAlex journal articles and reviews with a DOI, 2015-2025, n = 126,207; open access = any OpenAlex status other than closed; full-text audit = 20,515 open-access stroke articles with full text in Europe PMC, 2,000 sampled per year, seed 2026; comparators audited the same way) and from
`talk/evidence_brief.md`. All numbers come from pipeline output: run
`scripts/search_stroke_dois.py` per discipline (with `--das-audit-all` or
`--das-audit-sample-per-year N` for stroke), then `scripts/wsc2026_talk_analysis.py`
before finalising. The two standalone scripts were retired on 2026-10-11.

Timing plan: 13 slides, roughly 1 minute each, 2 minutes spare for the agenda slide.
Regenerated 2026-10-11 from pipeline output (all four disciplines audited). Slides 8b and 8c
are the two new slides for the equity and prize arguments; to stay at 13, fold slide 6 into
slide 7 and slide 8c into slide 11.

---

## 1. Title (0:00)

**Open science in stroke research: measuring reproducibility and transparency**

Notes: One sentence. "I am going to show you ten years of stroke publishing measured
automatically, and then argue that what we measured is a design problem, not a
motivation problem."

## 2. Why measure (0:45)

- Open science has four practical parts for a clinical field: can people read it, can
  they check it, can they reuse it, was it planned in advance.
- Reproducibility audits exist for neurology, cardiology and general medicine. None
  exist for stroke. (Rauh 2020; Heckerman 2025; Scutt 2020)
- Implementation science applies to our own practices too: you cannot improve what you
  do not measure.

Notes: Position the talk inside the session theme. Implementation science for research
practice itself.

## 3. How we measured (1:45)

- Living pipeline: OpenAlex title search, 2015 onward, stroke plus three comparator
  fields (neurology, neuroscience, cardiology). About 200,000 stroke records, 126,000
  journal articles and reviews with a DOI after cleaning (no-DOI records are mostly
  conference abstracts and are dropped).
- Signals: open-access status (six OpenAlex categories), repository links for data and
  code, preprint versions, registration identifiers in abstracts.
- Automated, re-runs every six months, code on GitHub, dashboard public. Figure: pipeline
  schematic (one line of boxes). Show the dashboard URL.
- Lower bounds: abstracts and metadata only, not full text. We fix that with a full-text
  audit of 20,515 open-access stroke articles (and the three comparators) on slide 8:
  abstracts find code in 0.04% of articles, the full text in 1.4%; registration 7.9% vs 14.9%.

Notes: Keep to 60 seconds. The method is the credibility; the audience does not need
details.

## 4. Finding 1: stroke went open access (2:45)

Figure: `fig01_oa_trend` (stroke 53% in 2015 to 75% in 2024).

- Open access in stroke articles rose from 53% to 75% in ten years (66% over the decade).
- Comparators over the decade: cardiology 70%, neurology 61%, neuroscience 60%. Stroke sits
  between cardiology and neurology throughout.

Notes: This is the good news slide. Let it land, then turn it.

## 5. Finding 2: but it is mostly paid (3:45)

Figure: `fig02_stroke_oa_status`.

- Of all stroke articles 2015-2025: gold 25%, diamond 15%, hybrid 9%, bronze 10%,
  green 7%, closed 34%. Cardiology: gold 25%, diamond 15%, hybrid 10%, bronze 13%, green 7%,
  closed 30%. Neuroscience is the only field where green (12%) beats diamond (9%).
  The journal Stroke itself is 69% free to read, mostly bronze after the 12-month embargo
  (43%) plus green (17%).
- Gold and hybrid, the paid routes, grew the most. Green (repository) stayed flat near
  7%. Bronze (free to read, no licence) is 10% and can disappear.
- Open access became a transaction between funders and publishers. It did not come with
  openness of anything else.

Notes: Mention APCs and the LMIC angle briefly: a 15-minute talk cannot do the equity
argument justice, but the audience in Seoul includes many LMIC trialists.

## 6. Finding 3: nothing else moved (4:45)

Figure: `fig03_data_sharing_trend` and `fig04_code_sharing_trend` side by side, or the
high-impact chart `fig07`.

- Data in a public repository, detectable from metadata: 0.2% of stroke articles in
  2015, 0.2% in 2024. Never above 0.6% in any year. Comparators 0.2-0.3%.
- Code or repository link: under 0.1% every year (0.2% in 2025).
- Preprint version: 0.1%. Stroke did not adopt preprints even during COVID (neuroscience 0.5%).
- Registration identifier in the abstract: 2.9% in 2015, 6.0% in 2024, 6.9% in 2025. Rising,
  but that is trials and systematic reviews catching up with mandates from 2005 and 2011.
  Stroke (4.8%) is ahead of cardiology (3.6%), neurology (2.3%) and neuroscience (1.1%).

Notes: Say the caveat out loud: these are lower bounds from abstracts. Then: "so we
read the full text."

## 7. High impact is not better (5:45)

Figure: `fig07_high_impact_vs_rest`.

- Top 10% cited within their publication year, or impact factor 10+ (n = 20,568, 16% of
  the corpus): open access 73% vs 64%, registration 10.1% vs 3.8%, data in a repository
  0.4% vs 0.4%, code 0.07% vs 0.07%.
- The papers we cite most are not the ones we can check most.

## 8. What data-availability statements actually say (6:45)

Figure: `fig11_das_audit` (Europe PMC audit, 20,515 open-access stroke articles 2015-2025,
2,000 sampled per year).

- Share with any statement: 49% over the decade, 14% in 2015, 78% in 2025. Statements
  arrived with the journal mandates, so the trend is policy, not culture.
- Of all audited articles: "available on request" 21% (32% in 2025); authors' own
  repository deposit 2.8% (5.0% in 2025); secondary analysis of a public dataset 1.5%;
  restricted or controlled 6%; in the article or supplement 10%; "not available" 4%.
- 2022-2025, stroke vs the others: a statement in 70% (cardiology 61%, neurology 63%);
  "on request" 31% (cardiology 21%, neurology 26%, neuroscience 10%); deposit or public
  source 6.5% (cardiology 10.1%, neuroscience 8.9%, neurology 5.9%). Stroke writes the
  most statements and deposits the least.
- Full text vs abstract (same articles): GitHub in 1.4% of full texts vs code links in
  0.04% of abstracts; trial registration 14.9% vs 7.9%.
- The literature on "on request": 6.8% of authors who promised data delivered
  (Gabelica 2022); 0.5% of top-journal RCTs declaring sharing had downloadable data
  (Danchev 2021); surgical journals 3.1% before and 3.1% after the ICMJE statement
  rule (Bergeat 2022). Stroke trials: 20% of 391 vascular and cognitive trials yielded
  data, median 241 days (Scutt 2020).

Notes: Caveat: open-access full text only, so optimistic for stroke overall. This is the
slide the audience will photograph; make the three numbers huge: 78% write a statement,
32% say "on request", 5% deposit.

## 8b. Who pays to be read, and who shares (NEW, equity)

Figures: `fig12_oa_route_by_income` and `fig13_fulltext_sharing_by_income`. Tables:
`stroke_equity_by_income_group.csv`. World Bank income group of the first author's country
(known for 86% of the corpus): high 63%, upper-middle 30% (mostly China), lower-middle 6%,
low 0.3% (355 articles; do not lean on it).

- Open access is highest where income is lowest: 66% (high), 69% (upper-middle), 74%
  (lower-middle), 86% (low). But the route differs. Lower-middle-income authors publish
  42% of their articles through routes that cost the author nothing (diamond, green);
  high-income authors 19%. Upper-middle-income authors pay an APC for 43%.
- Sharing in the full text runs the other way. Data deposited or a public source: 4.2%
  (high), 5.0% (upper-middle), 2.6% (lower-middle). GitHub: 1.9%, 0.8%, 0.1%. Trial
  registration mentioned: 15.5%, 15.3%, 6.8%. Statements at all: 45%, 60%, 27%.
- Reading access has been solved for the global South by free routes. Reuse has not:
  the data and code that lower-income teams could build on are not there, and their own
  work is the least likely to be shared. That is the inequality open science can close.

Notes: Seoul is a high-income audience with LMIC trialists in the room. Korea: 4,950
first-author articles, 75% open access, 0% detectable data sharing.

## 8c. Who is already doing it (NEW, the prize shortlist)

Figure: `fig14_commitment_institutions`. Tables: `stroke_commitment_{institutions,journals,
funders,countries}.csv`. Commitment index = mean over three verified full-text signals
(data deposit or public source in the statement, GitHub in the full text, trial
registration in the full text) of the entity's rate divided by the stroke-wide rate
(4.3%, 1.4%, 14.9%). 1.0 = stroke average. Minimum 30 audited articles; an institution
gets credit for any author.

- Institutions: MIT 10x (n=33), Pompeu Fabra 8x (36), Institut für Schlaganfall- und
  Demenzforschung Munich 8x (69), Padua 7x (98), USC 7x (226), Rochester 6x, Exeter 6x,
  Yale 6x (188), Guangdong Medical College 6x. Say the n out loud; under 50 is a hint,
  not a ranking.
- Journals: Brain Communications 8x, PeerJ 8x (84% deposit), Nature Communications 7x,
  NeuroImage Clinical 4x. The big stroke journals are not on the list.
- Funders: NIH institutes (NIDCD 8x, NIBIB 6x, NIMH 6x), the ERC 6x, Center for Stroke
  Research Berlin 6x, ANR 5x, Horizon 2020 4x.
- Countries (first author): Belgium 2.7x, Ireland 2.1x, Germany 2.0x, UK 1.7x.
- This is what a WSO prize would recognise: measurable, verified in full text, repeatable
  every six months by the pipeline.

Notes: Hand this slide to agenda item 3. The point is not the names; it is that the
measurement exists and is cheap.

## 9. Why mandates alone did not work (7:45)

- Statements without verification produce statements, not data (Bergeat; Danchev).
- Badges: worked at Psychological Science (under 3% to 39%), failed in the one medical
  trial at BMJ Open (OR 0.9) (Kidwell 2016; Rowhani-Farid 2020).
- Careers: of 92 biomedical promotion guidelines worldwide, zero mention data sharing,
  registration or open access (Rice 2020).
- Cardiology survey: researchers name funding the most essential incentive and say
  "policy alone will not lead to implementation" (Cobey 2024).

Notes: The pivot sentence: "Stroke researchers are not less honest than psychologists.
They respond to the same incentives, and ours point the other way."

## 10. Where stroke already has the pieces (8:45)

- VISTA holds more than 82,000 patients from 38 acute trials. HERMES pooled 1,287
  patients from 5 thrombectomy trials in a year because trialists wanted to.
- ATLAS v2.0: 1,271 open lesion-segmented MRIs. ENIGMA Stroke Recovery: 2,100 patients
  across 39 cohorts by federated analysis.
- Stroke, IJS and ESJ all require a data-availability statement. None offers
  Registered Reports. No WSO or ESO position statement on open science exists.

Notes: The point is that infrastructure is not the bottleneck. Recognition is.

## 11. An incentives agenda for stroke (9:45, 2.5 min)

Six items, each with an owner.

1. **Journals: retire "available on request".** Stroke, IJS, ESJ and JSCVD accept
   either a repository or a controlled-access platform (VISTA, Vivli) or a stated
   reason. Verified, not self-declared.
2. **Journals and WSO: Registered Reports for stroke trials and cohort analyses**, with
   in-principle acceptance tied to WSO and ESO grant awards, as the Children's Tumor
   Foundation did with PLOS ONE. Nature opened Registered Reports to clinical science
   in June 2026.
3. **WSO: a position statement and a reproducibility prize.** The Einstein Foundation
   award model; a WSO award for reuse of stroke data, presented at this congress.
4. **Funders: count datasets and code as outputs.** CIHR's narrative CV and UKRI's R4RI
   already allow it; stroke funders can require it.
5. **Institutions: put open-science items in promotion criteria.** Zero of 92 do today.
   Utrecht dropped the impact factor in 2022; Columbia and Calgary count datasets.
6. **Embargoed sharing as the default for trials**, 12 months after the primary
   publication, already written into COMPASS and ACT-GLOBAL. VISTA as the trusted
   archive; federated or synthetic access where consent or GDPR blocks sharing.

Notes: Say which items cost nothing (1, 3, 5) and which need money (2, 4, 6).

## 12. How we will know it worked (12:15)

- The pipeline re-runs every six months; the dashboard is public. Code and data are
  open. The audit on slide 8 can be repeated by anyone with the script.
- Targets to propose: repository or controlled-access data for 25% of stroke articles
  by 2030; "on request" below 10%; one Registered Report track in a stroke journal by
  2028.

Notes: Implementation science closes the loop with measurement. Put the dashboard URL
and the GitHub repository on the slide.

## 13. Close (13:15)

One line. "We measured ourselves. The numbers are not flattering, but they are
measurable, which means they are improvable."

Acknowledgements, funding, conflicts, contact.

---

## Numbers to re-verify before the slides are final

- Diamond 15%: check which journals drive it (expect Frontiers, MDPI, Korean and Chinese
  society journals). If it is mostly Frontiers and MDPI, say "APC-free in DOAJ" rather
  than "diamond" to avoid a debate.
- AHA Stroke data-sharing policy wording and start date (page blocked automated fetch).
- Nature Registered Reports expansion date (June 2026) from the Nature page.
