// Draw the slide pictures of the live charts with the dashboard's own charts.js, at slide scale: each chart is laid
// out at its narrow live-chart width (vw) with the dashboard's type sizes and rendered ~2x, so labels and lines read
// from the back of a room. Data: talk/deck/assets/live_charts.json, the same as the live HTML charts, so the picture
// in the .pptx and PDF matches the chart the presentation draws.
// Run from the repository root with puppeteer-core on NODE_PATH; writes talk/outputs/figures/dashboard/<name>.{png,svg}.
const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer-core");
// chart key in live_charts.json -> the picture's box on its slide and the output name
const FIGURES = [
  { chart: "oa_trend", box: { w: 1664, h: 580 }, out: "trend_oa_slide" },   // oa-trend.html
  { chart: "oa_status", box: { w: 960, h: 616 }, out: "oa_status_slide" },  // oa-type.html
  { chart: "das_year", box: { w: 1664, h: 400 }, out: "das_year_slide" },   // das.html
];
(async () => {
  const root = process.cwd();
  const live = JSON.parse(fs.readFileSync(path.join(root, "talk/deck/assets/live_charts.json"), "utf8"));
  const font = fs.readFileSync(path.join(root, "talk/deck/assets/fonts/InstrumentSans-variable.ttf")).toString("base64");
  const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true, args: ["--no-sandbox"] });
  for (const f of FIGURES) {
    const cfg = live.charts[f.chart];
    const scale = f.box.w / cfg.vw;                   // same scale as the live chart in preview.html
    const h = f.box.h / scale;
    const page = await browser.newPage();
    await page.setViewport({ width: Math.ceil(cfg.vw) + 20, height: Math.ceil(h) + 20, deviceScaleFactor: scale * 1.25 });
    await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }, { name: "prefers-color-scheme", value: "light" }]);
    await page.setContent(`<html><head><style>
      @font-face{font-family:'Instrument Sans';src:url(data:font/ttf;base64,${font});font-weight:400 700}
      :root{--bg:#f1f1ef;--surface-2:#e9e9e6;--hair:#c6c6c1;--grid:#dcdcd8;--ink:#141414;--ink-2:#4a4a47;--ink-3:#85857f;--accent:#d7263d;--neutral-mark:#b4b4ae}
      body{margin:0;background:#f1f1ef;font-family:'Instrument Sans',Helvetica,Arial,sans-serif}
      #fig{width:${cfg.vw}px;height:${h.toFixed(2)}px;background:#f1f1ef}
      .live-key{display:flex;gap:6px 18px;flex-wrap:wrap;font-size:12px;line-height:16px;color:#4a4a47;padding:0 0 8px}
      .key-item{display:inline-flex;align-items:center;gap:7px}.key-swatch{width:14px;height:2px;display:inline-block}.key-swatch.is-rect{height:10px}
      #fig.big-text svg text{font-size:var(--live-text,18px)}
      svg.ch{overflow:visible}
    </style></head><body><div id="fig"><div class="live-key" id="key"></div><div id="plot"></div></div></body></html>`);
    await page.addScriptTag({ path: path.join(root, "talk/deck/assets/vendor/d3-7.9.0.min.js") });
    await page.addScriptTag({ path: path.join(root, "dashboard/charts.js") });
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate((cfg, h) => {
      const fig = document.getElementById("fig");
      if (cfg.textSize) { fig.classList.add("big-text"); fig.style.setProperty("--live-text", cfg.textSize + "px"); }
      const key = document.getElementById("key");
      Charts.key(key, cfg.key || []);
      const keyH = key.hidden ? 0 : key.offsetHeight;
      Charts[cfg.kind](document.getElementById("plot"), Object.assign({}, cfg.opts, { height: Math.max(160, Math.round(h - keyH)) }));
    }, cfg, h);
    await new Promise((r) => setTimeout(r, 300));
    const out = path.join(root, "talk/outputs/figures/dashboard", f.out);
    await (await page.$("#fig")).screenshot({ path: out + ".png" });
    fs.writeFileSync(out + ".svg", await page.$eval("#plot svg", (n) => n.outerHTML));
    console.log("wrote", path.relative(root, out) + ".png", "at scale", scale.toFixed(2));
    await page.close();
  }
  await browser.close();
})();
