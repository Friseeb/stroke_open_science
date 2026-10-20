# WSC presentation

The working deck is Claude's benchmark design from `0761838`, 18 slides since
15 October 2026: the opening now runs Purpose (reproducibility, access, value),
then one slide per purpose with the NINDS rt-PA data story, and the proposals
are a task force, open toolkits and a prize. `project/slides/*.html` and
`project/deck.json` are the authoritative editable sources. Evidence for the
opening: `../evidence_reanalysis.md`, `../evidence_benefits.md`.

- PowerPoint: `congress/Fridman_WSC2026_open_science_v8.pptx` (18 slides, static) and
  `congress/Fridman_WSC2026_open_science_v8_animated.pptx` (same slides with Morph between
  slides, titles that settle, numbers that fade in, charts that wipe in; all automatic, one
  click per slide). The 17-slide `Fridman_WSC2026_open_science.pptx` is the previous version.
- PDF with embedded fonts: `congress/Fridman_WSC2026_open_science_v8.pdf`
- Presentation in the browser: `preview.html` (offline; fonts, figures, D3 and the
  dashboard's `charts.js` are embedded). Keys: → / PageDown / Space next, ← / PageUp back,
  S speaker notes with timers in a second window (allow pop-ups), O overview, F full
  screen, B blank screen. Titles settle, numbers count up and blocks cascade (off under
  reduced motion); five charts are the dashboard's live D3 charts (hover for values);
  source lines link to their DOIs and findings to the same view of the public dashboard.
  The presentation layer lives in `present/deck.js` and `present/deck.css`; the chart data
  in `assets/live_charts.json` (refresh with `--dashboard-data`, below).
- Notes: `speaker_notes.json`, generated from each slide's `<aside>`

Instrument Sans and Instrument Serif are supplied in `assets/fonts/` with their
SIL Open Font License files. Static PowerPoint faces are also installed in the
local user Fonts folder. The browser preview embeds the fonts and figures.

Build the preview without changing slide layouts (add `--dashboard-data <dashboard_data.json>`
to refresh the live-chart data from a dashboard build, e.g. the published run's):

```bash
python talk/deck/make_slides.py
```

The PDF is Chrome's print of `preview.html` with reduced motion emulated, so every page is the
finished slide; the live charts print as their pictures.

```bash
NODE_PATH=<puppeteer-core node_modules> node talk/deck/print_pdf.js talk/deck/preview.html \
  talk/deck/congress/Fridman_WSC2026_open_science_v8.pdf
```

Export using the source typefaces and an existing 17-slide package. The builder
edits native text and rules and preserves the original dashboard figure images.

```bash
NODE_PATH=<puppeteer-core node_modules> node talk/deck/congress/extract_slides.js \
  talk/deck/project talk/outputs/figures/dashboard build/wsc_extract
python talk/deck/congress/build_wsc_pptx.py \
  --package-source talk/deck/congress/Fridman_WSC2026_open_science.pptx \
  --extract build/wsc_extract \
  --out talk/deck/congress/Fridman_WSC2026_open_science.pptx
```

`extract_slides.js` preserves source fonts and weights by default. The optional
fourth argument `--congress-fonts` produces a separately measured common-font
layout when a venue requires one.

The source dashboard exports live under `talk/outputs/figures/dashboard/`.
`render_institution_figure.js` refreshes the existing dashboard dot plot using
`dashboard/charts.js` and `talk/outputs/tables/stroke_commitment_institutions.csv`.
`render_slide_figures.js` draws the open-access trend (published open: gold, diamond
or hybrid), open-access route and data-statement pictures from `assets/live_charts.json`
with the same code as the live charts, so the .pptx and PDF match the presentation.
Run it after `make_slides.py --dashboard-data <dashboard_data.json>`, then run
`make_slides.py` once more.

When the slide count changes, `--package-source` needs a package with the new
count. Build one fresh first, then rebuild it in the source fonts:

```bash
python talk/deck/congress/build_wsc_pptx.py --extract build/wsc_extract --out build/package.pptx
python talk/deck/congress/build_wsc_pptx.py --package-source build/package.pptx \
  --extract build/wsc_extract --out talk/deck/congress/Fridman_WSC2026_open_science_v8.pptx
# the same with motion: add --animate (and a different --out)
```

The animated file has not been checked in PowerPoint by the builder; click through it once.
Morph needs PowerPoint 2019 or Microsoft 365 and falls back to a fade elsewhere.

The .pptx does not embed fonts. On a computer without Instrument Sans and
Instrument Serif, PowerPoint substitutes fonts and line breaks move; install
the fonts from `assets/fonts/` there, or present the PDF.
