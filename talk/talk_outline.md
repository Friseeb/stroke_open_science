# Open science in stroke research: measuring reproducibility and transparency

World Stroke Congress 2026, Seoul. Thu 22 Oct 2026, 15:45-16:00 (15 min), session
"The latest in stroke implementation science" (ID 340), Conference Room 202-203.
Speaker: Sebastian Fridman (Western University, London, Canada).

Goal set by the speaker: leave the room with an agenda of incentives for open science
in stroke, grounded in the first stroke-specific measurement of these practices.

Numbers below come from `talk/outputs/numbers.json` and `talk/outputs/tables/`
(stroke corpus: OpenAlex journal articles and reviews with a DOI, 2015-2025, n = 126,267; open access = any OpenAlex status other than closed) and from
`talk/evidence_brief.md`. Items marked TODO wait on the comparator enrichment or the
Europe PMC data-availability audit. Re-run `scripts/wsc2026_talk_analysis.py` and
`scripts/audit_data_availability_europepmc.py classify` before finalising.

Timing plan: 13 slides, roughly 1 minute each, 2 minutes spare for the agenda slide.

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
- Lower bounds: abstracts and metadata only, not full text. We fix that for data
  sharing with a full-text audit (slide 8).

Notes: Keep to 60 seconds. The method is the credibility; the audience does not need
details.

## 4. Finding 1: stroke went open access (2:45)

Figure: `fig01_oa_trend` (stroke 53% in 2015 to 75% in 2024; neurology 61% overall,
  a few points behind stroke throughout).

- Open access in stroke articles rose from 53% to 75% in ten years.
- Comparators: neurology runs a few points behind; neuroscience and cardiology TODO.

Notes: This is the good news slide. Let it land, then turn it.

## 5. Finding 2: but it is mostly paid (3:45)

Figure: `fig02_stroke_oa_status`.

- Of all stroke articles 2015-2025: gold 25%, diamond 15%, hybrid 9%, bronze 10%,
  green 7%, closed 34%. The journal Stroke itself is 69% free to read, mostly bronze
  after the 12-month embargo (43%) plus green (17%).
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
  2015, 0.2% in 2024. Never above 0.5% in any year.
- Code or repository link: under 0.1% every year.
- Preprint version: 0.1%. Stroke did not adopt preprints even during COVID.
- Registration identifier in the abstract: 2.9% in 2015, 6.0% in 2024. Rising, but
  that is trials and systematic reviews catching up with mandates from 2005 and 2011.

Notes: Say the caveat out loud: these are lower bounds from abstracts. Then: "so we
read the full text."

## 7. High impact is not better (5:45)

Figure: `fig07_high_impact_vs_rest`.

- Top 10% cited or impact factor 10+ (n = 21,816): open access 69% vs 65%, registration
  8.9% vs 4.0%, data in a repository 0.5% vs 0.3%, code 0.06% vs 0.07%.
- The papers we cite most are not the ones we can check most.

## 8. What data-availability statements actually say (6:45)

Figure: `fig11_das_audit` (TODO: numbers from the Europe PMC audit, ~20,000 open-access
stroke articles 2016-2025, sampled 2,000 per year).

- Share with any statement: TODO.
- "Available on request": TODO. Public repository: TODO. Restricted or controlled: TODO.
- The literature on "on request": 6.8% of authors who promised data delivered
  (Gabelica 2022); 0.5% of top-journal RCTs declaring sharing had downloadable data
  (Danchev 2021); surgical journals 3.1% before and 3.1% after the ICMJE statement
  rule (Bergeat 2022). Stroke trials: 20% of 391 vascular and cognitive trials yielded
  data, median 241 days (Scutt 2020).

Notes: Caveat: open-access full text only, so optimistic for stroke overall. This is the
slide the audience will photograph; make the three numbers huge.

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

- Comparator OA, data, code, preprint rates (neurology, neuroscience, cardiology).
- Europe PMC audit categories, overall and 2024.
- Diamond 15%: check which journals drive it (expect Frontiers, MDPI, Korean and Chinese
  society journals). If it is mostly Frontiers and MDPI, say "APC-free in DOAJ" rather
  than "diamond" to avoid a debate.
- AHA Stroke data-sharing policy wording and start date (page blocked automated fetch).
- Nature Registered Reports expansion date (June 2026) from the Nature page.
