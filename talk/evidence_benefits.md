# Evidence: what openness buys beyond verification

Readers, reuse and access. Three research agents checked every number on 15 Oct 2026 against PubMed, DOI pages,
full texts, openFDA, the Federal Register, NICE and HIRA. Status: VERIFIED unless marked PARTLY (secondary source or
part of the claim) or NOT VERIFIED. Verification itself is in `evidence_reanalysis.md`.

## Readers and citations

### Literature
- Systematic review of 134 studies: 64 (47.8%) found an open-access citation advantage, 37 (27.6%) none, 32 (23.9%)
  only in subsets; about 98% at high risk of bias; no meta-analysis possible. Medicine and health: 19 of 36.
  Langham-Putrow A et al. PLoS One 2021;16:e0253129. PMID 34161369.
- Randomised trial (11 physiology journals, 1,619 articles): open access gave +89% full-text downloads (95% CI 76-103%)
  and no citation advantage at 1 year (59% vs 63% cited). Davis PM et al. BMJ 2008;337:a568. PMID 18669565. 3 years:
  10.6 vs 10.7 mean citations (PARTLY, author's mailing-list post of BMJ 2010;341:c6854). Second trial, 36 journals:
  cited "no more frequently, nor earlier" (Davis, FASEB J 2011, PMID 21450907).
- Piwowar 2018 (PeerJ, PMID 29456894): open access 1.18 vs world average for field and year, closed 0.90, gold 0.83.
  Do not quote "+18% vs closed".
- Data: +9% (95% CI 5-13%) after many controls (Piwowar & Vision, PeerJ 2013, PMID 24109559); +4.3% (Colavizza,
  PLoS One 2024, PMID 39475849); "up to 25.36%" (Colavizza 2020, PMID 32320428).
- Code: no significant advantage in about 122,000 papers (Colavizza 2024).
- Preprints: 1.36x (1.30-1.42) in biology (Fu & Hughey, eLife 2019, PMID 31808742); in 25 high-impact clinical
  journals, no difference outside COVID (Zissette, JAMA Netw Open 2024, PMID 39058492).
- No stroke- or neurology-specific citation study found. Among the 50 most-cited neurology RCTs of 2018-2022, 25 were
  stroke trials and only 8 of 50 made analytic code available (Benkendorff, BMJ Open 2026, PMID 42855245).

### Stroke benchmark (exploratory, 15 Oct 2026)
Published run 2026-10-13T111229Z, stroke `fully_enriched.csv`, in-corpus articles 2015-2023, OpenAlex
`cited_by_count`, open = known `oa_status` other than closed, funded = non-blank OpenAlex `funders`. Strata = journal x
year (x funded). Estimators: Mantel-Haenszel rate ratio on citations capped at each year's 99th percentile, geometric-
mean ratio of (1 + citations), and P(an open article is cited more than a closed one in the same stratum). Script in the
session scratchpad only (temporary); port it into `scripts/wsc2026_talk_analysis.py` before any number goes on a slide.

| Comparison | Capped MH ratio | Geo-mean ratio | P(cited more) |
|---|---|---|---|
| Open vs closed, same journal and year | 1.57 | 1.74 | 0.60 |
| Open vs closed, same journal, year and funding | 1.28 | 1.30 | 0.56 |
| Hybrid vs closed, same journal, year and funding | 1.40 | 1.54 | 0.60 |
| Preprint version vs none, same journal, year and funding | 1.09 | 1.11 | 0.54 |
| Audited: deposit or public dataset vs other, same journal and year | 0.96 | 1.03 | 0.51 |
| Audited: "on request" vs other, same journal and year | 0.83 | 0.87 | 0.45 |

Crude medians 7 vs 4 citations (open vs closed). Funded share: 41% of open vs 20% of closed articles. Uncapped
ratio-of-sums estimates are unstable (one fell to 1.11 with funding strata) because citations are heavy-tailed; use the
robust estimators. Observational: authors may open their stronger work.

## Reuse and speed

- DeepISLES: the top three ISLES'22 entries (one nnU-Net, one MONAI SegResNet, one Factorizer) fused into one free tool
  (Apache-2.0; web service, GUI, Docker); validated on 1,685 Johns Hopkins scans (11 scanners, 4 vendors, 10 years),
  median Dice 0.82; beat a model trained on that same data (Dice +7.4%); neuroradiologists preferred its masks to
  manual ones. MRI only, research use, no regulatory clearance. de la Rosa E et al. Nat Commun 2025;16:7357.
  PMID 40783484. ISLES'22 data CC BY 4.0, 10,419 Zenodo downloads.
- nnU-Net (Apache-2.0): 9,782 citations (OpenAlex); underlies the ISLES'22 winner (peer-reviewed) and the ATLAS 2022
  and ISLES'24 winners (preprints). Isensee F et al. Nat Methods 2021;18:203-11. PMID 33288961.
- ATLAS v1.2: of 17 published segmentation methods, 12 released no code (Liew 2022, PMID 35710678).
- ISLES'24 (CT/CTP to final infarct): best Dice 0.285 (preprint, arXiv 2408.10966). The CT task is not solved.
- No open-source CT-perfusion or LVO-detection software with peer-reviewed validation found; PyPeT is a preprint
  (arXiv 2511.13310).
- INDI shared neuroimaging data: 913 publications by March 2017, authors in 50 countries; cost to regenerate the data
  $893 million to $1.71 billion. Milham MP et al. Nat Commun 2018;9:2818. PMID 30026557.
- SARS-CoV-2: genome posted on virological.org 10/11 Jan 2020 ("Please feel free to download, share, use, and analyze
  this data"); mRNA-1273 sequence finalised 13 Jan; first participant vaccinated 16 Mar 2020, "just 66 days after the
  genomic sequence of the virus was posted" (Jackson LA, NEJM 2020;383:1920-31, PMID 32663912; Corbett KS, Nature
  2020, PMID 32756549). Built on prior MERS and mRNA work.
- Genes held under Celera's IP for up to 2 years had 20-30% less follow-on research and product development than
  public-domain genes. Williams H. J Polit Econ 2013;121:1-27. doi:10.1086/669706.
- AlphaFold: open code and weights (2021); ColabFold built on it within a month (Mirdita, Nat Methods 2022, PMID
  35637307; corresponding author Steinegger, Seoul National University). AFDB > 214 million structures.
- Third-party reuse of shared gene-expression data kept growing for at least 6 years (Piwowar & Vision 2013).
- YODA: 79% of 336 J&J trials with shared IPD generated secondary publications (1,167; 209 by external teams).
  Taherifard, BMJ 2026, PMID 42686366.

## Value for public money

- Avoidable research waste estimated at 85% of investment (losses of about 50% at each of the last three stages:
  design, publication, reporting). Chalmers I, Glasziou P. Lancet 2009;374:86-9. PMID 19525005. PARTLY: no abstract;
  the figure and its derivation are confirmed by the authors' own BMJ blog (14 Jan 2016, "Is 85% of health research
  really 'wasted'?"), which gives $200 billion a year as the spending base.
- The Lancet 2014 series "Research: increasing value, reducing waste" opened with Macleod MR, Michie S, Roberts I,
  Dirnagl U, Chalmers I, Ioannidis JP, Al-Shahi Salman R, Chan AW, Glasziou P. Lancet 2014;383:101-4. PMID 24411643.
  Three authors are stroke researchers (Macleod and Al-Shahi Salman, Edinburgh; Dirnagl, Center for Stroke Research
  Berlin): VERIFIED from the PubMed affiliations.
- "On request" in vascular and cognitive trials: IPD obtained for 78 of 391 trials (20%), median 241 days (Scutt 2020,
  BMJ Open; see evidence_brief.md).
- Reuse figures above (INDI $0.9-1.7 billion to regenerate; Celera 20-30% less follow-on research; YODA 79% of trials
  with secondary publications) belong here too.

## Access: imaging AI and the business model

### Benefit of commercial tools (for balance)
- Viz.ai stepped-wedge cluster RCT (Houston): door-to-groin -11.2 min (95% CI -18.2 to -4.2), no mRS difference.
  Martinez-Gutierrez JC, JAMA Neurol 2023;80:1182-90. PMID 37721738 (PI received Viz grants).
- Brainomix at 26 English hospitals: thrombectomy rate 2.3% to 4.6% vs 1.6% to 2.6% elsewhere (interaction OR 1.24,
  1.08-1.43); observational, company co-authors. Nagaratnam K, Lancet Digit Health 2025. PMID 41339157.

### Cost and dependence
- NICE HTG708 (2024; manufacturers' estimates): e-Stroke about GBP 30,000/yr (comprehensive centre) or 15,000 (acute);
  RapidAI about 20,000/yr per centre; Viz about 30,000 / 15,000.
- US CMS NTAP for Viz.ai ContaCT, FY2021-22: up to $1,040 per case (65% of an applicant-estimated $1,600; 85 FR 58636).
- Korea: MOHW capped non-covered NCCT LVO screening AI at KRW 18,100 per exam from 1 Nov 2024 (PARTLY, Hitnews); no
  stroke AI covered by National Health Insurance as of Sep 2025 (PARTLY, press). JLK JBS-01K was the first AI
  "innovative medical technology" (MOHW Notice 2023-26, HIRA guideline, VERIFIED).
- DEFUSE 3: core and penumbra "calculated with the use of RAPID software"; DAWN "used the same automated perfusion
  software" (Albers, NEJM 2018, PMID 29364767). FDA K182130 (27 Dec 2018) added "aid in the selection of acute stroke
  patients ... for endovascular thrombectomy" to RAPID, "based on retrospective clinical data evaluation".

### Same scan, different software
- Brainomix vs RapidAI in 54 patients: thrombectomy eligibility discordant in 15% (46/54 agreed); core r 0.86, mismatch
  ratio r 0.48. Mallon DH, J Stroke Cerebrovasc Dis 2022. PMID 35994882.
- MR CLEAN CTP scans (n = 35): median core 50 mL (Philips), 41 mL (Siemens default), 11 mL (RAPID). Koopman MS, JNIS
  2019. PMID 31203208 (some authors Nico.lab shareholders).
- Newer packages mostly agree: RAPID vs Viz core rho 0.77 (Pisani, Ann Neurol 2023, PMID 37584452); DEFUSE 3
  eligibility equivalent overall (Alwood 2024, PMID 38703875).
- Real-world LVO triage: manufacturer sensitivity 97% fell to 85% (ICA/M1) and 69% with M2 (Kunst, JACR 2024,
  PMID 37196818).
- Academic detector on the open nnDetection framework beat two CE/FDA-cleared LVO products by 25-45% in sensitivity
  (Brugnara, Nat Commun 2023, PMID 37582829; partly open).
- Simpler imaging works in the late window: MR CLEAN-LATE (CTA collaterals, aOR 1.67, Lancet 2023, PMID 37003289);
  CLEAR (NCCT vs CTP selection, no difference in 90-day mRS, aOR 0.95, JAMA Neurol 2022, PMID 34747975).

### Access gap
- MT-GLASS: median thrombectomy access 2.79% of LVO patients (IQR 0.70-11.74); under 1% in 18 countries; none in 7;
  low-income countries 88% lower than high-income. Asif KS, Circulation 2023;147:1208-20. PMID 36883458.
- People per CT scanner: 25,000 (high income), 1,694,000 (low income). Hricak H, Lancet Oncol 2021. PMID 33676609.
- CT perfusion or MRI available to 70.5% (high income) vs 44.5% (low-middle income) of 1,506 respondents; 70.1% would
  treat on CT alone. Nguyen TN, SVIN 2023. PMID 41585765.
- Korea: 22.5% of 29,755 ischaemic stroke patients (2021) lived in districts with no thrombectomy centre (Lee J, BMC
  Health Serv Res 2026, PMID 41787379).

### Limits of open tools
- None of the open stroke-imaging tools found has regulatory clearance or LMIC validation; no cost-effectiveness study
  of an open tool exists.
- EU MDR Article 5(5): an in-house device may "not [be] transferred to another legal entity", so a hospital cannot hand
  its validated open tool to another hospital as a clinical device without a manufacturer.
- STIR Roadmap II (Wintermark, Stroke 2013, PMID 23860298): perfusion post-processing "should be standardized"; funders
  should help distribute "proprietary techniques and software across multiple platforms".
