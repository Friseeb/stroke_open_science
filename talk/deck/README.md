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
