// Print preview.html to a PDF, one 1920 x 1080 page per slide. Reduced motion is emulated, so every page is the
// finished slide (no entrance animation caught half way) and the live charts print as their pictures.
// Usage, from the repository root with puppeteer-core on NODE_PATH:
//   node talk/deck/print_pdf.js talk/deck/preview.html talk/deck/congress/Fridman_WSC2026_open_science_v8.pdf
const path = require("path");
const puppeteer = require("puppeteer-core");
(async () => {
  const [src, out] = process.argv.slice(2);
  if (!src || !out) throw new Error("usage: node print_pdf.js <preview.html> <out.pdf>");
  const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true, args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });
  await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }, { name: "prefers-color-scheme", value: "light" }]);
  await page.goto("file://" + path.resolve(src), { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await new Promise((r) => setTimeout(r, 800));
  await page.pdf({ path: out, width: "1920px", height: "1080px", printBackground: true, preferCSSPageSize: true });
  const n = await page.evaluate(() => document.querySelectorAll("section").length);
  console.log("wrote", out, "(" + n + " slides)");
  await browser.close();
})();
