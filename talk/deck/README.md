# Deck files

`make_slides.py` generates the talk deck. `project/deck.json` is its index and
`project/slides/<id>.html` its slides. Speaker notes live in `speaker_notes.json` and references
in `references.json`. Run `.venv/bin/python talk/deck/make_slides.py` after source edits.

The current revision is `congress/Fridman_WSC2026_open_science_v6.pptx`. It preserves the
20-slide order, including disclosure and reference appendices. `preview.html` is a portable
browser preview with all illustrations embedded. The previous PowerPoint remains available.

The opening distinguishes computational reproducibility, replication with new data, and
transparency. Statistical power, surveys, animal-to-human translation and differences between
trials are not pooled into one crisis statistic. Benchmark figures show defined stroke
comparisons and retain denominator and interpretation limits in the notes.

Project illustrations and the official WSC cover banner are in `assets/`. The exact prompts,
generation mode and banner source are recorded in `assets/provenance.json`. Conceptual artwork
is separate from empirical plots. Main slides use titles of at most seven words and no more
than twenty body words; disclosure and reference appendices retain their required content.

To re-export the figures after a data refresh (needs the preview served on port 8766 and
puppeteer-core with the installed Chrome, as in the scratchpad `pup/` folder):

```bash
node talk/deck/export_dashboard_figures.js http://localhost:8766/ talk/outputs/figures/dashboard
```

Dashboard exports remain available for detailed comparisons. The current main deck draws
focused evidence graphics from benchmark values, rather than embedding full dashboards.
The QR codes on the close slide were generated with the `qrcode` Python package
(`qrcode.image.svg.SvgPathImage`) for the dashboard and repository URLs.

## Congress PowerPoint (`congress/`)

The World Stroke Congress wants a .pptx whose first slide carries the speaker's name and title and whose
second slide is its conflict-of-interest form; it allows common fonts only (Arial, Times New Roman), JPG
pictures. The opening carries the official WSC banner at the speaker's request.
`congress/Fridman_WSC2026_open_science.pptx` is built in two steps, with the HTML deck
as the single source, and every slide keeps the deck's look (the speaker's choice, 2026-10-14): the cover is
slide 1 and the `disclosure` slide reproduces the congress form (its two boxes and nine categories).

```bash
# 1. render every slide in Chrome with the congress fonts and record the layout (needs puppeteer-core)
NODE_PATH=<dir>/node_modules node talk/deck/congress/extract_slides.js \
    talk/deck/project talk/outputs/figures/dashboard /tmp/wsc_extract
# 2. build every slide as native, editable shapes
python talk/deck/congress/build_wsc_pptx.py --extract /tmp/wsc_extract \
    --out talk/deck/congress/Fridman_WSC2026_open_science.pptx --preview-dir /tmp/wsc_preview
```

`--template WSC-2026-PPT_w_disclosure_16_9.pptx` (from worldstrokecongress.org, promotional toolkit; not
committed) opens with the official title and disclosure slides instead. The builder prints `FIT` lines when a
text box would need more lines in PowerPoint than Chrome laid out, or when anything runs past the footer band;
fix those in the HTML slide. Figures are converted to JPG under `congress/media/`.
