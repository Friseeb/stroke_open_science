const puppeteer = require("puppeteer-core");
const SHOTS = [
  { name: "matrix", hash: "view=s1", sel: ["#report-card"], pad: 2 },
  { name: "trend_oa", hash: "metric=oa&trendLayout=overlay&markers=true", sel: ["#trend-key", "#trend-chart"] },
  { name: "trend_oa_panels", hash: "metric=oa&trendLayout=panels", sel: ["#trend-key", "#trend-chart"] },
  { name: "trend_data", hash: "metric=data&markers=false", sel: ["#trend-key", "#trend-chart"] },
  { name: "trend_code", hash: "metric=code&markers=false", sel: ["#trend-key", "#trend-chart"] },
  { name: "trend_preprint", hash: "metric=preprint&markers=false", sel: ["#trend-key", "#trend-chart"] },
  { name: "trend_reg", hash: "metric=reg&markers=false", sel: ["#trend-key", "#trend-chart"] },
  { name: "oa_status", hash: "oaGrouping=status&oaMode=bars", sel: ["#oa-key", "#oa-chart"] },
  { name: "oa_rain", hash: "oaMode=rain", sel: ["#oa-key", "#oa-chart"] },
  { name: "hi_gap", hash: "hiMode=gap", sel: ["#hi-key", "#hi-chart"] },
  { name: "das_year", hash: "dasGrouping=five&dasMode=bars", sel: ["#das-key", "#das-chart"] },
  { name: "das_disc", hash: "ftdMode=dots", sel: ["#das-disc-key", "#das-disc-chart"] },
  { name: "eq_route", hash: "eqSignal=route&eqMode=bars", sel: ["#eq-key", "#eq-chart"] },
  { name: "eq_ft", hash: "ftdMode=dots", sel: ["#eq-ft-key", "#eq-ft-chart"] },
  { name: "cm_inst", hash: "cmEntity=institutions&cmMin=50&cmTop=15&cmMode=dots", sel: ["#cm-chart"] },
  { name: "cm_journals", hash: "cmEntity=journals&cmMin=50&cmTop=12&cmMode=dots", sel: ["#cm-chart"] },
  { name: "bubbles_2025", hash: "bbEntity=countries&bbYear=2025&bbTrails=on", sel: ["#bb-key", "#bb-chart"] },
  { name: "hero", hash: "", viewport: true },
];
(async () => {
  const [url, out] = [process.argv[2], process.argv[3]];
  const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true, args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "light" }, { name: "prefers-reduced-motion", value: "reduce" }]);
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 2 });
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  for (const s of SHOTS) {
    await page.goto("about:blank"); await page.goto(url + "#" + s.hash, { waitUntil: "networkidle0", timeout: 60000 });
    await page.addStyleTag({ content: ".export{visibility:hidden} .fig-opts{visibility:hidden}" });
    await wait(1800);
    if (s.viewport) { await page.evaluate(() => window.scrollTo(0, 0)); await wait(800); await page.screenshot({ path: `${out}/${s.name}.png` }); console.log(s.name, "viewport"); continue; }
    await page.evaluate((sel) => { document.documentElement.style.scrollBehavior = "auto"; const n = document.querySelector(sel); window.scrollTo({ top: n.getBoundingClientRect().top + window.scrollY - 140, behavior: "instant" }); }, s.sel[0]);
    await wait(1600);
    const box = await page.evaluate((sels) => { let x0 = 1e9, y0 = 1e9, x1 = 0, y1 = 0; for (const sel of sels) { const n = document.querySelector(sel); if (!n || n.hidden) continue; const r = n.getBoundingClientRect(); if (r.width === 0) continue; x0 = Math.min(x0, r.left); y0 = Math.min(y0, r.top); x1 = Math.max(x1, r.right); y1 = Math.max(y1, r.bottom); } return { x: x0 + window.scrollX, y: y0 + window.scrollY, w: x1 - x0, h: y1 - y0 }; }, s.sel);
    const pad = s.pad === undefined ? 8 : s.pad;
    await page.screenshot({ path: `${out}/${s.name}.png`, clip: { x: box.x - pad, y: box.y - pad, width: box.w + 2 * pad, height: box.h + 2 * pad } });
    console.log(s.name, Math.round(box.w), "x", Math.round(box.h));
  }
  await browser.close();
})();
