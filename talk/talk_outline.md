# Open science in stroke research: measuring reproducibility and transparency

World Stroke Congress 2026, Seoul. Thu 22 Oct 2026, 15:45-16:00 (15 min), session
"The latest in stroke implementation science" (ID 340), Conference Room 202-203.
Speaker: Sebastian Fridman (Western University, London, Canada).

Version 4 (2026-10-13, evening): the introduction now shows the open-source lesion-analysis pipelines of
neuroscience, a new slide says where psychology and neuroscience stand today (consensus documents, the
newest replication results, neuropsychology), a disclosure slide is slide 2 (no disclosures), and the congress
.pptx is the same deck in the same look, converted to editable PowerPoint (talk/deck/congress/). Sources for the new
slides, each re-checked against its source: talk/evidence_intro.md.

Version 3 (2026-10-13). The arc the speaker asked for: the moment that started the project,
why open science matters (the reproducibility crisis in psychology and neuroscience), the same
problem in stroke, what open science is made of, what we measured, and what to do next (a task
force, a prize, awareness). The deck (17 slides) is the Slides artifact "Open Science in Stroke
Research"; it reuses the dashboard's figures and visual system.

Numbers come from the published run of 2026-10-13 (`data/runs/2026-10-13T111229Z`):
`talk/outputs/numbers.json` and `talk/outputs/tables/`, regenerated from it by
`scripts/wsc2026_talk_analysis.py`, and the run's dashboard payload. Stroke corpus: OpenAlex
journal articles and reviews with a DOI from the six title terms, 2015-2025, n = 140,281; open
access = any OpenAlex status other than closed; full-text audit = up to 1,500 open-access articles
per year with full text in Europe PMC (seed 2026), 16,362 for stroke; neurology, neuroscience and
cardiology audited the same way. A pooled audit rate averages equal yearly samples, not the corpus,
so the outline leads with single years and with 2022-2025. The June talk frames are retired because
the June retrieval was truncated. Literature numbers come from `talk/evidence_brief.md`. The figures
on the slides are exports of the public dashboard
(https://friseeb.github.io/stroke_open_science_outputs/; default view 2015-2025, all papers), so
slide and dashboard agree.

Timing: 17 slides in 14:45, leaving 15 s (version 4 trimmed several slides by 5-15 s to make room). Minutes in brackets are cumulative at the start of the slide.

---

## 1. Title (0:00, 20 s)

**Open science in stroke research: measuring reproducibility and transparency**

Notes: One sentence, no agenda slide. "I want to tell you how this project started, what it
found, and what I think we should do with it."

## 2. Disclosure (0:20, 5 s) — required by the congress

The congress requires its conflict-of-interest slide as slide 2. Both decks show the congress form in the deck's
own look (the speaker's choice, 2026-10-14): "No, nothing to disclose" ticked, and the nine categories with "None". The speaker confirmed no disclosures on
2026-10-13; if the congress's published faculty list still shows otherwise, ask the congress office to correct it.

## 3. Where I come from: in lesion neuroscience, the whole pipeline is open (0:25, 50 s) — NEW in version 4

Replaces "The moment this started". The speaker asked for the introduction to show the open-source lesion-analysis
pipelines of neuroscience. One line in the speaker's voice, five stages with named open tools, four open datasets.

> I came to stroke from imaging and neuroscience. There, every step of a lesion study has open-source tools and
> shared data.

- **1 Segment**: MRIcron 2007, ITK-SNAP 2006, LINDA 2016, nnU-Net 2021, DeepISLES 2025 (an ensemble of the ISLES
  2022 winners, validated on 1,685 external scans; neuroradiologists preferred its masks to manual ones).
- **2 Normalise**: cost-function masking 2001, enantiomorphic normalisation 2008, SPM Clinical Toolbox 2012, ANTs 2008.
- **3 Map the symptom**: VLSM 2003, NiiStat, SVR-LSM 2014, LESYMAP 2018.
- **4 Map disconnection**: lesion network mapping 2015, BCBtoolkit 2018, Lesion Quantification Toolkit 2021.
- **5 Share**: BIDS 2016, NeuroVault 2015, OpenNeuro (1,913 public datasets on 13 Oct 2026).
- **Open stroke data**: ATLAS v2.0, 1,271 MRIs with traced lesions, 955 public (Liew 2022); ISLES 2022, 250 of 400
  cases public under CC BY; Aphasia Recovery Cohort, 230 people and 902 sessions, CC0 (Gibson 2024); SOOP, 1,715
  admissions, CC0 (Absher 2024).
- Footer: open data has not guaranteed open code: of 17 segmentation methods published on ATLAS v1.2, 12 reported no
  public code (Liew 2022).

Notes: Fifty seconds, first person. Most tools are BSD, GPL or Apache licensed; a few need MATLAB, and some data sit
behind data use agreements (say so if asked). The turn: when I moved to clinical stroke, the trial data and code were
not there. The earlier anecdote draft ("the data were available on request ...") is retired unless it is a real episode.

## 4. Why open science: the fields next door had their crisis first (1:15, 45 s)

Four numbers, then why it happened. What those fields did about it is the next slide.

- **36%**: of 100 psychology findings replicated with a significant result; effect sizes about
  half the originals (Open Science Collaboration, Science 2015).
- **21%**: median statistical power of neuroscience studies (Button 2013, Nat Rev Neurosci).
- **6 of 53**: landmark preclinical cancer findings that Amgen could reproduce (Begley & Ellis,
  Nature 2012).
- **70%**: of 1,576 researchers had failed to reproduce another group's experiment; 52% called
  it a significant crisis (Baker, Nature 2016).
- Why it happened: small samples, flexible analyses, selective reporting. Four routine analysis
  choices raise a 5% false-positive rate to 61% (Simmons 2011); 63% of 2,155 psychologists
  admitted not reporting all their measures (John 2012).

Notes: Forty-five seconds. Psychology and neuroscience are the speaker's former fields; say so.
"They measured themselves, it hurt, and they changed how they publish."

## 5. Where the fields next door are now: the rules now exist, practice is catching up (2:00, 1 min) — NEW in version 4

Left, "What they agreed on":

- **2013** Registered Reports launch at *Cortex*, a neuroscience and neuropsychology journal; more than 300 journals
  offer them now (Chambers 2013; Center for Open Science).
- **2015** TOP guidelines for journals (Nosek 2015, Science), 5,000+ signatories; revised as TOP 2025, which
  certifies transparency, not just asks for it (Grant 2026).
- **2016** BIDS, one standard for organising and sharing neuroimaging data (Gorgolewski 2016).
- **2017** A manifesto for reproducible science (Munafò 2017); COBIDAS, OHBM's best-practice standard for MRI
  (Nichols 2017).
- **2024** *Psychological Science* makes open data and materials the default and checks that results reproduce
  (Hardwicke & Vazire 2024).
- **2025** PECANS, a Delphi consensus checklist for cognitive and neuropsychological studies, 206 experts in round 1
  (Costa 2025).

Right, "Where they are now":

- **55%** of 274 social and behavioural science claims replicated; effects fell from r = 0.25 to 0.10 (SCORE,
  Tyner 2026, Nature). Authors made data available for 24% of 600 papers (Miske 2026, Nature).
- **7% and 14%** of 2022 psychology articles were preregistered, or shared raw data; 3% and 2% in 2014-2017
  (Hardwicke 2024).
- **1 of 62** Registered Reports at *Cortex*, 2018-2022, studied patients; sensitive clinical data is the barrier
  neuropsychologists named most (Binney 2025, Brain Communications).
- Footer: Registered Reports, 44% positive results against 96% (Scheel 2021). The best-known evidence that rigour
  alone restores replication (Protzko 2023) was retracted in 2024.

Notes: Sixty seconds. Psychology did not fix itself: it measured itself, agreed on rules, and is still short of them.
Neuroimaging: 70 teams, one fMRI dataset, no two pipelines alike (NARPS 2020); cluster inference up to 70% false
positives (Eklund 2016). Closest to this room: lesion network mapping, used in more than 200 studies, was challenged
in Nature Neuroscience in January 2026 with public data only (van den Heuvel 2026), with replies in the same journal;
that debate exists because the data were open. Lesion mapping itself: maps shift by about 16 mm with vascular anatomy
(Mah 2014); fewer than 40% of N = 30 resamples reach significance (Lorca-Puls 2018).


## 6. Stroke is not immune (3:00, 50 s)

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

## 7. What open science is made of (3:50, 45 s)

Four questions a field should be able to answer about its own literature (existing slide):
can people read it (open access, by which route); can they check it (data and code); can they
reuse it (deposited, not promised on request); was it planned in advance (registration).
Footer: audits exist for neurology, cardiology and general medicine; none for stroke (Rauh 2020;
Heckerman 2025; Scutt 2020).

## 8. How we measured (4:35, 45 s)

- Living pipeline: OpenAlex, 2015 onward, stroke plus neurology, neuroscience and cardiology;
  140,281 stroke journal articles and reviews with a DOI, 2015-2025, from 231,580 records
  retrieved for six title terms (2015-2026).
- Signals from metadata and abstracts (open-access status, repository links, preprint versions,
  registration identifiers), plus a full-text audit of data-availability statements in up to 1,500
  open-access articles per year via Europe PMC (16,362 for stroke), for all four fields.
- Automated, re-runs every six months, code and data public, dashboard public.
- Figure: the dashboard's report card (indicator by discipline) as the overview.

Notes: Forty-five seconds. "Everything I show next is on the dashboard, and you can change
the selection yourself." Open-access full text only, so audit rates run high, and a pooled rate
gives every year the same weight: lead with single years. If asked: neurology 129,644,
neuroscience 509,973, cardiology 312,703 articles. On the report card neuroscience leads on code,
GitHub, deposit and preprints, partly because its title term "neural" also catches
machine-learning papers (about 45% of that corpus matches only "neural").

## 9. Finding 1: stroke went open access (5:20, 40 s)

Figure: dashboard trend, open access by year and discipline.

- 53% in 2015 to 75% in 2024 (66% over 2015-2025). Cardiology 70%, neurology 62%,
  neuroscience 65% over the same years; stroke sits between cardiology and neurology every year
  through 2024 (in the incomplete 2025 it is just above cardiology, 75% vs 74%).

Notes: The good-news slide. Let it land, then turn it. The peak so far is 77% in 2023. Do not
rank neuroscience: about 45% of it comes only from the title term "neural", much of it machine
learning; without those papers it is 67% open access. It is above stroke until 2019 and below
neurology in 2024 and 2025.

## 10. Finding 2: the growth in open access was paid for (6:00, 40 s)

Figure: dashboard open-access status by year, six statuses in their own colours.

- Of all stroke articles 2015-2025: gold 25%, diamond 16%, hybrid 10%, bronze 10%, green 6%,
  closed 34%. From 2015 to 2024 gold, a paid route, grew the most (+18 points); diamond (+9)
  outgrew hybrid (+7). Green fell from 9% in 2015 to 3% in 2025. Bronze can be withdrawn at any
  time.
- Open access became a transaction between funders and publishers. It did not come with
  openness of anything else.

Notes: Gold plus hybrid is about half of the open articles over the decade (52% with 2025, 49%
through 2024) and the majority every year since 2021: 35% in 2015, 53% in 2021, 59% in 2024. Diamond is a long tail of about 4,800 free journals: Cureus is the largest
(1,187 articles), then Journal of Physical Therapy Science (487) and Journal of Stroke (334).
About a quarter of Korean (27%) and Japanese (25%) first-author articles are diamond, Chinese 5%.
The growth figures stop at 2024 because 2025 is still filling in; green was already down to 4% in
2024, so its fall does not rest on the partial year.

## 11. Finding 3: in abstracts, data and code did not move (6:40, 1 min)

Figures: dashboard trends for data in a repository, GitHub or code links and preprints (three
small charts); registration as a number tile.

- Data in a public repository: 0.2% of stroke articles in 2015, 0.2% in 2024, never above 0.6%.
  Code link: under 0.1% every year 2015-2024. Preprint version: 2.7% in 2024, 1.5% over
  2015-2025, up from under 0.2% before 2019; a lower bound, and partly publisher-driven.
  Registration identifier in the abstract: 2.8% in 2015, 5.3% in 2024; stroke (4.6%) ahead of
  cardiology (4.1%), neurology (2.4%) and neuroscience (1.0%).
- High impact is barely better at sharing: top-cited or IF 10+ (16% of the corpus): open access
  74% vs 65%, registration 10.0% vs 3.5%, but data 0.45% vs 0.34%, code 0.08% vs 0.06%.
- These are lower bounds from abstracts and metadata. "So we read the full text."

Notes: Say the caveat before anyone says it for you: lower bounds from abstracts. Preprints did
move, but only as far as OpenAlex links them: it merged many preprint records into their published
articles between 6 and 12 October 2026, and much of what it links is Research Square ("In Review",
an opt-in at submission) and SSRN (Lancet and Elsevier), so the rise is partly publisher-driven.
GitHub appears in 2.5% of the 1,500 audited 2024 full texts (1.3% pooled over the decade), against
code links in under 0.1% of abstracts. Two code definitions are in use: the high-impact line here
(0.08% vs 0.06%) and the 0.07% of abstracts on slide 12 also count Zenodo and OSF links; the
dashboard's code chart counts GitHub and code-repository links only, so a viewer who selects high
impact there sees 0.026% vs 0.015%. Registration nearly doubled, from a low base. Neuroscience
caveat: its title term "neural" pulls in machine-learning papers; without them its registration
rate is still only about 1.5%.

## 12. What data-availability statements actually say (7:40, 1 min 15 s)

Figure: dashboard statements by year (five classes).

- Share with any statement: 74% in 2025, from 14% in 2015 (47% pooled over 2015-2025).
  Statements arrived with the journal mandates, so the trend is policy, not culture.
- "Available on request": 29% in 2025, from 0.6% in 2015 (19% pooled), now the single largest
  answer. Deposit or a named public dataset: 9.8% in 2025, from 0.7% in 2015; authors' own
  repository deposit 5.9% in 2025 (2.8% pooled). Pooled shares of the rest: public dataset 1.4%;
  restricted or controlled 6%; in the article or supplement 10%; "not available" 4%.
- 2022-2025 against the others: stroke says "on request" more than any other field (30%;
  neurology 27%, neuroscience 26%, cardiology 24%), writes statements more often than the other
  clinical fields (69%; neurology 64%, cardiology 61%) and as often as neuroscience once its
  machine-learning papers are set aside (68%; 72% as defined), and deposits or names a public
  dataset at the level of the other clinical fields (6.9%; cardiology 7.3%, neurology 5.6%), well
  under neuroscience (17.5%).
- Full text versus abstract, same audited articles: GitHub in 1.3% of full texts vs code, OSF
  or Zenodo links in 0.07% of abstracts; trial registration 14.1% of full texts vs 7.5% of abstracts.
- What "on request" delivers elsewhere: 6.8% of authors who promised data delivered (Gabelica
  2022); 0.6% (2 of 334) of top-journal RCTs declaring sharing had downloadable data (Danchev
  2021); 20% of 391 vascular and cognitive trials yielded data, median 241 days (Scutt 2020).

Notes: The slide people photograph. Three numbers huge, all for 2025: 74% write a statement, 29%
say "on request", 9.8% deposit or name a public dataset. Caveat out loud: open-access full text
only, so optimistic. Pooled shares weigh every year the same (up to 1,500 audited a year), so they
are not corpus rates. Neuroscience caveat: its title term "neural" also catches machine-learning
papers; without them neuroscience writes statements in 68% (stroke 69%) and deposits 13.6%.

## 13. Who pays to be read, and who shares (8:55, 55 s)

Figures: dashboard open-access route by income group and full-text indicators by income group.
World Bank income group of the first author's country (known for 85% of the corpus): high 62%,
upper-middle 32% (mostly China), lower-middle 6%, low 0.3% (400 articles; do not lean on it).

- Open access is highest where income is lowest: 67% (high), 70% (upper-middle), 75%
  (lower-middle), 88% (low). Lower-middle-income authors publish 42% through routes that cost
  the author nothing (diamond, green); high-income authors 19%; upper-middle-income authors pay
  an APC for 43%.
- Sharing does not follow: lower-middle-income authors share least. Deposit or public source:
  4.0% (high), 5.2% (upper-middle), 1.8% (lower-middle). GitHub: 1.6%, 0.8%, 0.3%. Registration
  in the full text: 15.0%, 14.2%, 5.7%. Statements at all: 43%, 57%, 23%.
- Reading access has been solved for the global South by free routes. Reuse has not. That is the
  inequality open science can close, and the word "stroke" in the room makes it concrete.

Notes: The full-text rates pool 2015-2025 over equal yearly samples, and lower-middle rests on
only 609 audited articles. The gap holds in 2022-2025 alone: a statement in 37% of lower-middle
full texts vs 65% high and 78% upper-middle; deposit or public source 3.0% vs 6.2% and 8.7%.
Korea: 5,490 first-author articles, 75% open access, 0% detectable data sharing in abstracts and
metadata; 1.3% of 1,293 audited full texts deposit or name a public source.

## 14. Who is already doing it (9:50, 55 s)

Figure: dashboard commitment index, institutions (minimum 50 audited articles; the dashboard
keeps the 60 institutions with the most audited articles, all 82 or more). Commitment index
= mean over three verified full-text signals (data deposit or public source in the statement,
GitHub in the full text, trial registration in the full text) of the entity's rate divided by the
stroke-wide rate (4.2%, 1.3%, 14.1%). 1.0 = stroke average.

- Institutions: Center for Stroke Research Berlin 5.2x (part of Charité), Charité 4.4x, Oxford
  2.9x, Hamburg-Eppendorf 2.6x, Edinburgh 2.5x, Stanford 2.3x, Nottingham 2.2x, Massachusetts
  General 2.2x, Glasgow 2.1x, King's College London 2.0x, Johns Hopkins 1.9x. Say the n: Charité
  129 audited articles, Oxford 177, Hamburg-Eppendorf 109.
- Journals (30 or more audited): Nature Communications, Brain Communications, PeerJ (81%
  deposit), NeuroImage Clinical lead; the journal Stroke is about 15th of 99 at 1.5x, above the
  average but not among the leaders. Funders (30 or more audited): US federal (NIDCD, NIBIB,
  HHS), ANR, Swiss Heart Foundation, Leducq, DFG, Horizon 2020, BMBF. Countries (50 or more
  audited): Belgium 2.4x, Germany 2.2x, Switzerland 2.0x, France 1.8x, Ireland 1.7x, UK 1.5x.
- This is what a prize would recognise: measurable, verified in full text, repeatable every six
  months.

Notes: Small counts are a hint, not a ranking: GitHub is rare (1.3%), so one more GitHub mention
in 100 audited articles adds about 0.26, and the order shifts between runs. With every institution
at 50 or more audited, the German Center for Neurodegenerative Diseases (5.6x, 61 audited), the
Berlin Institute of Health at Charité (5.2x, 64) and Zurich (4.7x, 64) also lead. The baselines
pool 2015-2025 with every year weighted the same, and the signals rose over the decade, so an
index also reflects which years an entity published in. Oxford is also listed as a funder in
OpenAlex (4.9x, 33 audited, second among funders); it is an institution, so it is left out of
the funders. The point is not the names: the measurement exists and is cheap.

## 15. Why mandates alone did not work (10:45, 1 min)

Existing slide: 3.1% to 3.1% (Bergeat 2022); OR 0.9 for badges at BMJ Open vs under 3% to 39% at
Psychological Science (Rowhani-Farid 2020; Kidwell 2016); 0 of 92 promotion guidelines (Rice
2020); 44% vs 96% positive results in Registered Reports (Scheel 2021). Footnote: cardiology
survey, n = 198, funding named the most essential incentive (Cobey 2024, Open Heart). The pivot sentence:
"Stroke researchers are not less honest than psychologists. They respond to the same incentives,
and ours point the other way."

## 16. What to do next: a task force, a prize, awareness (11:45, 2 min 15 s)

Three columns, each with an owner and the items from the incentives agenda folded in.

1. **A WSO task force on open science** (costs nothing to start): a position statement (no
   stroke society has one); retire "available on request" in Stroke, IJS, ESJ and JSCVD in
   favour of a repository, a controlled-access platform (VISTA, Vivli) or a stated reason;
   Registered Reports for stroke trials and cohort analyses, with in-principle acceptance tied
   to WSO and ESO grants (the Children's Tumor Foundation and PLOS ONE model; Nature opened the
   format to clinical science in June 2026); embargoed sharing as the trial default (12 months,
   as in COMPASS and ACT-GLOBAL).
2. **A prize** for the teams, institutions and journals that share: the commitment index of
   slide 14, verified in full text and recomputed every six months; on the Einstein
   Foundation model; presented at this congress.
3. **Awareness**: the public dashboard and its six-monthly benchmark; open-science items in
   promotion criteria (0 of 92 today; CIHR's narrative CV and UKRI's R4RI already allow datasets
   and code as outputs); targets to discuss: data in a repository or controlled-access platform
   for 25% of stroke articles by 2030, "on request" under 10%, one Registered Report track in a
   stroke journal by 2028.

Notes: Two minutes fifteen. Invite the WSO leadership in the room to take the task force home.
Say which items cost nothing (statement, retiring "on request", promotion criteria) and which need
money (Registered Reports, the prize, infrastructure that mostly exists: VISTA, ATLAS, ENIGMA).

## 17. Close: collaborate (14:00, 45 s)

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

## Corpus sensitivity (2026-10-13)

The benchmark corpus is an OpenAlex **title** search for the six stroke terms. A title-and-abstract search for
stroke 2024 (`--openalex-search-field title_and_abstract`, `scripts/compare_corpus_definitions.py`, table
`talk/outputs/tables/corpus_sensitivity_2024.csv`) returns 2.4 times as many in-corpus articles (37,878 vs 15,602;
99% of the title corpus is inside it) with the same open-access share (75.5% vs 75.2%; every status within 1.4
points), the same data, code and preprint rates, and a slightly lower registration signal (3.7% vs 4.3%, and
3.3% among the extra articles). The comparison script reads no abstracts, so these registration shares are of all
articles, not of those with an abstract: the title corpus's 4.3% is slide 11's 5.3%. The corpus definition does not
move the headline numbers; say so if asked.

Should we also search outside OpenAlex? We checked stroke 2024 against PubMed with the same six title terms (live
query, 13 October 2026). PubMed returns 11,816 records, and 94% of them are already in our corpus: 79% in 2024 and
most of the rest in 2023, because PubMed's 2024 search also catches articles that went online in 2023 and were
printed in 2024, while OpenAlex dates them by the online date. OpenAlex types most of what remains as letters,
errata, editorials, preprints, conference papers or book chapters, and it lacks only 7 PubMed records, all NCBI
Bookshelf entries. PubMed calls 384 of the records we do not count in any year research articles, reviews or case
reports; OpenAlex holds almost all of them, but our corpus rule or our title search leaves them out. Adding them
would move 2024 open access from 75.2% to 74.4%, the data, code, preprint and registration rates by about 0.1 point,
and the open-access status shares by under 1 point. The gap runs the other way: 37% of our 2024 corpus is not in
PubMed at all. That part is mostly regional journals outside MEDLINE and conference abstracts in journal
supplements, and it holds most of the diamond open access (2,259 of 3,051 diamond articles). So OpenAlex stays the
source, and PubMed serves as a check, not a second search.

If asked about PubMed-based audits: limited to the articles PubMed holds, our 2024 corpus would have the same open
access (75%) but a different mix: diamond 8% instead of 20%, gold over 40% instead of 30%, and a registration
identifier in 8% of abstracts instead of 5%. Open-access comparisons with PubMed-based studies are fair; status-mix
and registration comparisons depend on the source. The pipeline's own `--include-pubmed` option stays off (no
workflow passes it): as built it cannot add to the corpus, because PubMed rows carry no OpenAlex metadata, and it
can remove articles, because deduplication prefers the row with a PMID (3 corpus articles lost in the 2024 test).
Its date split also dropped 515 PMIDs (`return merged[:target_count]`, `scripts/search_stroke_dois.py:1682`).

## Numbers to re-verify before the slides are final

- RESCUE BT2 primary outcome figures if quoted (mRS 0-1 at 90 days, tirofiban vs aspirin).
- STEM primary outcome figures if quoted.
- Diamond 16%: Cureus is its largest journal (1,187 articles), then Journal of Physical Therapy
  Science (487) and Journal of Stroke (334), in a long tail of about 4,800 journals; it is not
  driven by Frontiers or MDPI. "Diamond" is OpenAlex's classification, which the dashboard counts
  as free to the author; if Cureus is questioned, say that it is OpenAlex's label, not ours.
- Danchev 2021: the evidence brief gives 0.5%, but 2 of 334 is 0.6%, which the das slide notes now
  uses; check against the paper.
