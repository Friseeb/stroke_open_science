# Open science in stroke research: measuring reproducibility and transparency

World Stroke Congress 2026, Seoul. Thu 22 Oct 2026, 15:45-16:00 (15 min), session
"The latest in stroke implementation science" (ID 340), Conference Room 202-203.
Speaker: Sebastian Fridman (Western University, London, Canada).

Version 3 (2026-10-13). The arc the speaker asked for: the moment that started the project,
why open science matters (the reproducibility crisis in psychology and neuroscience), the same
problem in stroke, what open science is made of, what we measured, and what to do next (a task
force, a prize, awareness). The deck (14 slides) is the Slides artifact "Open Science in Stroke
Research"; it reuses the dashboard's figures and visual system.

Numbers come from `talk/outputs/numbers.json` and `talk/outputs/tables/` (stroke corpus:
OpenAlex journal articles and reviews with a DOI, 2015-2025, n = 126,207; open access = any
OpenAlex status other than closed; full-text audit = 20,515 open-access stroke articles with full
text in Europe PMC, 2,000 sampled per year, seed 2026; comparators audited the same way) and from
`talk/evidence_brief.md`. The figures on the slides are exports of the public dashboard
(https://friseeb.github.io/stroke_open_science_outputs/), so slide and dashboard agree.

Timing: 14 slides in 14:30, leaving 30 s. Minutes in brackets are cumulative at the start of the slide.

---

## 1. Title (0:00)

**Open science in stroke research: measuring reproducibility and transparency**

Notes: One sentence, no agenda slide. "I want to tell you how this project started, what it
found, and what I think we should do with it."

## 2. The moment this started (0:20, 40 s) — NEW, personal

One large sentence on an otherwise empty slide, in the speaker's words. Draft to personalise:

> I came to stroke from imaging and neuroscience. [In 20__ I tried to build on a published
> result: the data were "available on request", the code was not there, and the request went
> unanswered. I could not tell whether the finding was wrong or I was.]

Three small lines underneath: imaging · neuroscience · neurology.

Notes: Thirty to forty seconds, first person, no slide reading. The point is not the anecdote;
it is that the speaker has been on the receiving end of a closed literature. Alternative openings
if the story above is not right: a model from a paper that could not be retrained because the
training set was never released; a perfusion-threshold result that two groups reproduced with
opposite signs because the processing code differed.

## 3. Why open science: the fields next door had their crisis first (1:00, 60 s) — NEW

Four numbers, then one line on what those fields did about it.

- **36%**: of 100 psychology findings replicated with a significant result; effect sizes about
  half the originals (Open Science Collaboration, Science 2015).
- **21%**: median statistical power of neuroscience studies (Button 2013, Nat Rev Neurosci).
- **6 of 53**: landmark preclinical cancer findings that Amgen could reproduce (Begley & Ellis,
  Nature 2012).
- **70%**: of 1,576 researchers had failed to reproduce another group's experiment; 52% called
  it a significant crisis (Baker, Nature 2016).
- What changed: preregistration and Registered Reports (300+ journals), open-data badges, the
  Open Science Framework, data and code as a condition of publication. Registered Reports:
  44% positive results against 96% in the standard literature (Scheel 2021).

Notes: Psychology and neuroscience are the speaker's former fields; say so. "They measured
themselves, it hurt, and they changed how they publish."

## 4. Stroke is not immune (2:00, 60 s) — NEW

Preclinical, then clinical.

- **1,026** candidate neuroprotectants in animal stroke; none translated (O'Collins 2006, Ann
  Neurol). Publication bias alone overstated efficacy by about a third: one in seven animal
  experiments never published (Sena 2010, PLoS Biol). NXY-059: SAINT I positive (NEJM 2006),
  SAINT II negative (NEJM 2007).
- **Tirofiban**: no benefit before thrombectomy in RESCUE BT (JAMA 2022), benefit without a
  large-vessel occlusion in RESCUE BT2 (NEJM 2023). Different question, different answer; only
  protocols, data and code tell us which.
- **Middle meningeal artery embolisation**: three trials in one issue of the NEJM (20 Nov 2024).
  EMBOLISE positive (recurrence 4% vs 11%), STEM positive, MAGIC-MT neutral (6.7% vs 9.9%).
  [Confirm with the speaker that "MMA embo trials" is the example meant; the pooled analysis
  found benefit only without surgery.]
- Line: "Replication is how a field finds out which result to trust. Without the data and the
  code, we are left arguing about it."

Notes: Keep to three examples; the audience knows these trials. Do not editorialise on any
single trial; the point is heterogeneity that cannot be resolved from the papers alone.

## 5. What open science is made of (3:00, 45 s)

Four questions a field should be able to answer about its own literature (existing slide):
can people read it (open access, by which route); can they check it (data and code); can they
reuse it (deposited, not promised on request); was it planned in advance (registration).
Footer: audits exist for neurology, cardiology and general medicine; none for stroke (Rauh 2020;
Heckerman 2025; Scutt 2020).

## 6. How we measured (3:45, 45 s)

- Living pipeline: OpenAlex, 2015 onward, stroke plus neurology, neuroscience and cardiology;
  126,207 stroke journal articles and reviews with a DOI (199,000 records retrieved).
- Signals from metadata and abstracts (open-access status, repository links, preprint versions,
  registration identifiers), plus a full-text audit of data-availability statements for 2,000
  open-access articles per year via Europe PMC, for all four fields.
- Automated, re-runs every six months, code and data public, dashboard public.
- Figure: the dashboard's report card (indicator by discipline) as the overview.

Notes: Sixty seconds at most. "Everything I show next is on the dashboard, and you can change
the selection yourself."

## 7. Finding 1: stroke went open access (4:30, 45 s)

Figure: dashboard trend, open access by year and discipline.

- 53% in 2015 to 75% in 2024 (66% over the decade). Cardiology 70%, neurology 61%,
  neuroscience 60% over the decade; stroke sits between cardiology and neurology throughout.

Notes: The good-news slide. Let it land, then turn it.

## 8. Finding 2: mostly paid (5:15, 45 s)

Figure: dashboard open-access status by year, six statuses in their own colours.

- Of all stroke articles 2015-2025: gold 25%, diamond 15%, hybrid 9%, bronze 10%, green 7%,
  closed 34%. Gold and hybrid, the paid routes, grew the most; green stayed flat near 7%;
  bronze can disappear.
- Open access became a transaction between funders and publishers. It did not come with
  openness of anything else.

## 9. Finding 3: nothing else moved (6:00, 60 s)

Figures: dashboard trends for data in a repository, code links and preprints (three small
charts) and the registration trend.

- Data in a public repository: 0.2% of stroke articles in 2015, 0.2% in 2024, never above 0.6%.
  Code or repository link: under 0.1% every year. Preprint version: 0.1%, even during COVID.
  Registration identifier in the abstract: 2.9% in 2015, 6.0% in 2024; stroke (4.8%) ahead of
  cardiology (3.6%), neurology (2.3%) and neuroscience (1.1%).
- High impact is not better: top-cited or IF 10+ (16% of the corpus): open access 73% vs 64%,
  registration 10.1% vs 3.8%, data 0.4% vs 0.4%, code 0.07% vs 0.07%.
- These are lower bounds from abstracts and metadata. "So we read the full text."

## 10. What data-availability statements actually say (7:00, 75 s)

Figures: dashboard statements by year (five classes) and full-text indicators by discipline.

- Share with any statement: 49% over the decade, 14% in 2015, 78% in 2025. Statements arrived
  with the journal mandates, so the trend is policy, not culture.
- Of all audited articles: "available on request" 21% (32% in 2025); authors' own repository
  deposit 2.8% (5.0% in 2025); public dataset 1.5%; restricted or controlled 6%; in the article
  or supplement 10%; "not available" 4%.
- 2022-2025 against the others: a statement in 70% (cardiology 61%, neurology 63%); "on
  request" 31% (cardiology 21%, neurology 26%, neuroscience 10%); deposit or public source 6.5%
  (cardiology 10.1%, neuroscience 8.9%, neurology 5.9%). Stroke writes the most statements and
  deposits the least.
- Full text versus abstract: GitHub in 1.4% of full texts vs code links in 0.04% of abstracts;
  trial registration 14.9% vs 7.9%.
- What "on request" delivers elsewhere: 6.8% of authors who promised data delivered (Gabelica
  2022); 0.5% of top-journal RCTs declaring sharing had downloadable data (Danchev 2021); 20% of
  391 vascular and cognitive trials yielded data, median 241 days (Scutt 2020).

Notes: The slide people photograph. Three numbers huge: 78% write a statement, 32% say "on
request", 5% deposit. Caveat out loud: open-access full text only, so optimistic.

## 11. Who pays to be read, and who shares (8:15, 60 s)

Figures: dashboard open-access route by income group and full-text indicators by income group.
World Bank income group of the first author's country (known for 86% of the corpus): high 63%,
upper-middle 30% (mostly China), lower-middle 6%, low 0.3% (355 articles; do not lean on it).

- Open access is highest where income is lowest: 66% (high), 69% (upper-middle), 74%
  (lower-middle), 86% (low). Lower-middle-income authors publish 42% through routes that cost
  the author nothing (diamond, green); high-income authors 19%; upper-middle-income authors pay
  an APC for 43%.
- Sharing runs the other way. Deposit or public source: 4.2% (high), 5.0% (upper-middle), 2.6%
  (lower-middle). GitHub: 1.9%, 0.8%, 0.1%. Registration in the full text: 15.5%, 15.3%, 6.8%.
  Statements at all: 45%, 60%, 27%.
- Reading access has been solved for the global South by free routes. Reuse has not. That is the
  inequality open science can close, and the word "stroke" in the room makes it concrete.

Notes: Korea: 4,950 first-author articles, 75% open access, 0% detectable data sharing.

## 12. Who is already doing it (9:15, 60 s)

Figure: dashboard commitment index, institutions (minimum 50 audited articles). Commitment index
= mean over three verified full-text signals (data deposit or public source in the statement,
GitHub in the full text, trial registration in the full text) of the entity's rate divided by the
stroke-wide rate (4.3%, 1.4%, 14.9%). 1.0 = stroke average.

- Institutions (≥ 50 audited): Charité 3.7x, Edinburgh 3.0x, Hamburg-Eppendorf 3.0x, Johns
  Hopkins 2.6x, Oxford 2.4x, Massachusetts General 2.3x, Nottingham 2.2x, UCL 2.1x. Say the n.
- Journals: Brain Communications, PeerJ (84% deposit), Nature Communications, NeuroImage
  Clinical lead; the big stroke journals are not on the list. Funders: NIH institutes, the ERC,
  the Center for Stroke Research Berlin. Countries: Belgium 2.7x, Ireland 2.1x, Germany 2.0x,
  UK 1.7x.
- This is what a prize would recognise: measurable, verified in full text, repeatable every six
  months.

## 13. Why mandates alone did not work (10:15, 60 s)

Existing slide: 3.1% to 3.1% (Bergeat 2022); OR 0.9 for badges at BMJ Open vs under 3% to 39% at
Psychological Science (Rowhani-Farid 2020; Kidwell 2016); 0 of 92 promotion guidelines (Rice
2020); 44% vs 96% positive results in Registered Reports (Scheel 2021). The pivot sentence:
"Stroke researchers are not less honest than psychologists. They respond to the same incentives,
and ours point the other way."

## 14. What to do next: a task force, a prize, awareness (11:15, 2 min 15 s)

Three columns, each with an owner and the items from the incentives agenda folded in.

1. **A WSO task force on open science** (costs nothing to start): a position statement (no
   stroke society has one); retire "available on request" in Stroke, IJS, ESJ and JSCVD in
   favour of a repository, a controlled-access platform (VISTA, Vivli) or a stated reason;
   Registered Reports for stroke trials and cohort analyses, with in-principle acceptance tied
   to WSO and ESO grants (the Children's Tumor Foundation and PLOS ONE model; Nature opened the
   format to clinical science in June 2026); embargoed sharing as the trial default (12 months,
   as in COMPASS and ACT-GLOBAL).
2. **A prize** for the teams, institutions and journals that share: the commitment index on the
   previous slide, verified in full text and recomputed every six months; on the Einstein
   Foundation model; presented at this congress.
3. **Awareness**: the public dashboard and its six-monthly benchmark; open-science items in
   promotion criteria (0 of 92 today; CIHR's narrative CV and UKRI's R4RI already allow datasets
   and code as outputs); targets to discuss: data in a repository or controlled-access platform
   for 25% of stroke articles by 2030, "on request" under 10%, one Registered Report track in a
   stroke journal by 2028.

Notes: Two minutes. Invite the WSO leadership in the room to take the task force home. Say which
items cost nothing (statement, retiring "on request", promotion criteria) and which need money
(Registered Reports, the prize, infrastructure that mostly exists: VISTA, ATLAS, ENIGMA).

## 15. Close: collaborate (13:30, 60 s)

One line: "We measured ourselves. The numbers are not flattering, but they are measurable, which
means they are improvable."

Then the invitation, with links and QR codes: the Stroke Open-Science Benchmark
(https://friseeb.github.io/stroke_open_science_outputs/), the code
(https://github.com/Friseeb/stroke_open_science), and the speaker's contact (sfridma@uwo.ca).
"Fork it, challenge it, run it on your field, or join the task force."

Companion project if asked: the Author Context Explorer (provenance-first author context, human
review before anything attaches to a person); the same restraint applies to any prize that names
people.

---

## Sources added in version 3

- Open Science Collaboration. Estimating the reproducibility of psychological science. Science
  2015;349:aac4716.
- Button KS et al. Power failure. Nat Rev Neurosci 2013;14:365-376.
- Begley CG, Ellis LM. Raise standards for preclinical cancer research. Nature 2012;483:531-533.
- Baker M. 1,500 scientists lift the lid on reproducibility. Nature 2016;533:452-454.
- O'Collins VE et al. 1,026 experimental treatments in acute stroke. Ann Neurol 2006;59:467-477.
- Sena ES et al. Publication bias in reports of animal stroke studies. PLoS Biol 2010;8:e1000344.
- Lees KR et al. NXY-059 for acute ischemic stroke (SAINT I). NEJM 2006;354:588-600. Shuaib A
  et al. SAINT II. NEJM 2007;357:562-571.
- Qiu Z et al. RESCUE BT. JAMA 2022;328:543-553. Zi W et al. RESCUE BT2. NEJM 2023;388:2025-2036.
- Davies JM et al. EMBOLISE; Fiorella D et al. STEM; Liu J et al. MAGIC-MT. NEJM 2024;391
  (20 Nov 2024).

## Numbers to re-verify before the slides are final

- RESCUE BT2 primary outcome figures if quoted (mRS 0-1 at 90 days, tirofiban vs aspirin).
- STEM primary outcome figures if quoted.
- Diamond 15%: which journals drive it (expect Frontiers, MDPI, Korean and Chinese society
  journals); if mostly Frontiers and MDPI, say "APC-free in DOAJ" rather than "diamond".
