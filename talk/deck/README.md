# Deck files

The talk deck is the Slides artifact "Open Science in Stroke Research". `project/deck.json` is its
index and `project/slides/<id>.html` its slides (one `<section>` each, inline styles only); the
figures on the slides are exports of the dashboard preview, stored under
`talk/outputs/figures/dashboard/` and uploaded to the artifact as assets (`/_blob/<id>` in `<img src>`).

To re-export the figures after a data refresh (needs the preview served on port 8766 and
puppeteer-core with the installed Chrome, as in the scratchpad `pup/` folder):

```bash
node talk/deck/export_dashboard_figures.js http://localhost:8766/ talk/outputs/figures/dashboard
```

Then upload the changed PNGs to the artifact as assets and point the slides at the new ids.
The QR codes on the close slide were generated with the `qrcode` Python package
(`qrcode.image.svg.SvgPathImage`) for the dashboard and repository URLs.

## Congress PowerPoint (`congress/`)

The World Stroke Congress wants a .pptx whose first slide carries the speaker's name and title and whose
second slide is its conflict-of-interest form; it allows common fonts only (Arial, Times New Roman), JPG
pictures and no logos. `congress/Fridman_WSC2026_open_science.pptx` is built in two steps, with the HTML deck
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
