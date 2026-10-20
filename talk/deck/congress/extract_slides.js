// Extract the Slides deck (talk/deck/project) into a layout JSON that build_wsc_pptx.py turns into native
// PowerPoint shapes. Each slide is rendered in Chrome at 1920 x 1080 preserving the source fonts.
// The optional --congress-fonts argument substitutes common congress fonts
// (Instrument Sans -> Arial, Instrument Serif -> Times New Roman, weight 600+ -> bold), so every line break
// and position is measured with the fonts PowerPoint will use. Also writes one PNG per slide (what the .pptx
// should look like) and a PNG of every inline <svg> (the QR codes), which the builder converts to JPG.
//
// Usage (puppeteer-core must be resolvable, e.g. NODE_PATH=<dir>/node_modules):
//   node talk/deck/congress/extract_slides.js talk/deck/project talk/outputs/figures/dashboard <out dir>
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const path = require("path");

const [deckDir, figDir, outDir, fontMode] = process.argv.slice(2);
const congressFonts = fontMode === "--congress-fonts";
if (!deckDir || !figDir || !outDir) {
  console.error("usage: node extract_slides.js <deck project dir> <figure dir> <out dir>");
  process.exit(2);
}
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

// uploaded asset id -> dashboard export name (talk/outputs/figures/dashboard/<name>.png)
const BLOBS = {  // version 5: white, large-label exports (talk/outputs/figures/dashboard_white_large)
  "0589d919d1dbced9c40bd9fd6ee5aa98": "trend_oa",
  "fe5c40d680a79965d24e69517fae6799": "oa_status",
  "9cdee74e6826e99260e7beac7d81b768": "das_year",
  "5ed4f9d16988b6807df9a74278a7df20": "cm_inst",
  "1fb20c959926284dd1854d9c6102e55e": "matrix", "132f503925f35b32dc8876a44ed61ac2": "trend_oa",
  "96fde507943b392dd08bf6db6c11315d": "trend_data", "9f18b9e4a7d4ea6ca13fc229c654623f": "trend_code",
  "67939026af6f2060dc9d39d3844cc83b": "trend_preprint", "837a5f4520811da05dfc2266dcdc66ae": "trend_reg",
  "902bac47b083c3a58b90bccb23a37e71": "oa_status", "7283090421ebd52d983830d9f2327368": "das_year",
  "3cbd9b26c3fb379a188b53906e212ea5": "das_disc", "82578c9fd21556d92fd12ae68fbf6f25": "eq_route",
  "c2d75a6018dc709db7762c9a8bacf42f": "eq_ft", "4af052f78d2110e6a65d8d016cdbe00e": "cm_inst",
};

function pageHtml(section) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>
*{margin:0;box-sizing:border-box} html,body{width:1920px;height:1080px;overflow:hidden}
section{position:relative;width:1920px;height:1080px;overflow:hidden} aside{display:none}
table{border-collapse:collapse}
@font-face{font-family:'Instrument Sans';src:url('file://${path.resolve(deckDir,"../assets/fonts/InstrumentSans-variable.ttf")}');font-weight:400 700}
@font-face{font-family:'Instrument Serif';src:url('file://${path.resolve(deckDir,"../assets/fonts/InstrumentSerif-Regular.ttf")}');font-weight:400}
</style></head><body>${section}</body></html>`;
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  const deck = JSON.parse(fs.readFileSync(path.join(deckDir, "deck.json"), "utf8"));
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox", "--allow-file-access-from-files"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });
  const slides = [];
  for (const id of deck.order) {
    let html = fs.readFileSync(path.join(deckDir, "slides", `${id}.html`), "utf8");
    const missing = [];
    html = html.replace(/\/_blob\/([0-9a-f]{32})/g, (m, k) => {
      if (!BLOBS[k]) { missing.push(k); return "missing.png"; }
      return "file://" + path.resolve(figDir, BLOBS[k] + ".png");
    });
    if (missing.length) throw new Error(`${id}: unknown asset ids ${missing.join(", ")}`);
    html = html.replace(/src="((?:\.\.\/)+[^\"]+)"/g,
      (_, src) => 'src="file://' + path.resolve(deckDir, "slides", src) + '"');
    const file = path.resolve(outDir, `${id}.page.html`);
    fs.writeFileSync(file, pageHtml(html));
    await page.goto("file://" + file, { waitUntil: "load" });
    await page.evaluate(() => document.fonts.ready);
    const data = await page.evaluate((congressFonts) => {
      const S = document.querySelector("section");
      // congress fonts, measured as PowerPoint will draw them
      if (congressFonts) for (const el of [S, ...S.querySelectorAll("*")]) {
        const cs = getComputedStyle(el);
        const serif = /Instrument Serif|Times|serif$/i.test(cs.fontFamily) && !/sans-serif/i.test(cs.fontFamily);
        el.style.fontFamily = serif ? '"Times New Roman"' : "Arial";
        el.style.fontWeight = parseInt(cs.fontWeight, 10) >= 600 ? "700" : "400";
      }
      void S.offsetHeight;
      const sr = S.getBoundingClientRect();
      const px = (v) => parseFloat(v) || 0;
      const rel = (r) => ({ x: r.left - sr.left, y: r.top - sr.top, w: r.width, h: r.height });
      const visibleColor = (c) => c && c !== "transparent" && !/rgba\(\d+, \d+, \d+, 0\)/.test(c);
      const inAside = (el) => !!el.closest("aside");
      const out = { id: S.id, bg: getComputedStyle(S).backgroundColor, boxes: [], images: [], texts: [], svgs: [], notes: "" };
      const aside = S.querySelector("aside");
      if (aside) out.notes = aside.textContent.trim();
      const TEXT = new Set(["P", "H1", "H2", "H3", "LI", "TD", "TH"]);
      let svgIndex = 0;
      for (const el of S.querySelectorAll("*")) {
        if (inAside(el) || el.tagName === "ASIDE") continue;
        if (el.closest("svg") && el.tagName.toLowerCase() !== "svg") continue;
        const cs = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        if (r.width < 0.5 || r.height < 0.5) continue;
        // filled or bordered boxes
        const borders = {};
        for (const side of ["top", "right", "bottom", "left"]) {
          const w = px(cs[`border-${side}-width`] ?? cs.getPropertyValue(`border-${side}-width`));
          const st = cs.getPropertyValue(`border-${side}-style`);
          if (w > 0 && st !== "none") borders[side] = { w, color: cs.getPropertyValue(`border-${side}-color`) };
        }
        const fill = visibleColor(cs.backgroundColor) ? cs.backgroundColor : null;
        if ((fill || Object.keys(borders).length) && el.tagName !== "svg") out.boxes.push({ ...rel(r), fill, borders, tag: el.tagName, round: cs.borderRadius === "50%" });
        if (el.tagName === "IMG") {
          const pl = px(cs.paddingLeft), pt = px(cs.paddingTop);
          const cw = r.width - pl - px(cs.paddingRight), ch = r.height - pt - px(cs.paddingBottom);
          const nw = el.naturalWidth, nh = el.naturalHeight;
          let w = cw, h = ch;
          if (cs.objectFit === "contain" && nw && nh) { const s = Math.min(cw / nw, ch / nh); w = nw * s; h = nh * s; }
          const box = rel(r);
          out.images.push({ src: decodeURIComponent(el.src.replace("file://", "")), x: box.x + pl + (cw - w) / 2, y: box.y + pt + (ch - h) / 2, w, h, alt: el.alt || "" });
          continue;
        }
        if (el.tagName.toLowerCase() === "svg") {
          el.setAttribute("data-svg-index", String(svgIndex));
          out.svgs.push({ index: svgIndex++, ...rel(r), label: el.getAttribute("aria-label") || "", markup: el.outerHTML });
          continue;
        }
        if (!TEXT.has(el.tagName)) continue;
        const bl = px(cs.borderLeftWidth), bt = px(cs.borderTopWidth);
        const pl = px(cs.paddingLeft), pr = px(cs.paddingRight), ptop = px(cs.paddingTop), pb = px(cs.paddingBottom);
        const box = rel(r);
        const content = { x: box.x + bl + pl, y: box.y + bt + ptop, w: r.width - bl - pl - pr - px(cs.borderRightWidth), h: r.height - bt - ptop - pb - px(cs.borderBottomWidth) };
        // runs: text nodes with their own computed style; <br> = line break
        const runs = [];
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
        let n = walker.nextNode();
        while (n) {
          if (n.nodeType === 1 && n.tagName === "BR") runs.push({ br: true });
          if (n.nodeType === 3 && n.textContent) {
            const pcs = getComputedStyle(n.parentElement);
            let t = n.textContent.replace(/[ \t\r\n]+/g, " ");
            if (pcs.textTransform === "uppercase") t = t.toUpperCase();
            runs.push({
              text: t, color: pcs.color, size: px(pcs.fontSize), bold: parseInt(pcs.fontWeight, 10) >= 600,
              italic: pcs.fontStyle === "italic", underline: /underline/.test(pcs.textDecorationLine),
              serif: /Instrument Serif|Times/.test(pcs.fontFamily),
              family: pcs.fontFamily.split(",")[0].replace(/[\"']/g, "").trim(), weight: parseInt(pcs.fontWeight,10), spacing: pcs.letterSpacing === "normal" ? 0 : px(pcs.letterSpacing),
            });
          }
          n = walker.nextNode();
        }
        if (!runs.length) continue;
        // trim the paragraph's outer whitespace
        const first = runs.find((q) => !q.br), last = [...runs].reverse().find((q) => !q.br);
        if (first) first.text = first.text.replace(/^ +/, "");
        if (last) last.text = last.text.replace(/ +$/, "");
        // line boxes as Chrome laid them out
        const range = document.createRange();
        range.selectNodeContents(el);
        // a rect starts a new line only when its middle is below the current line (a smaller inline span, such as the
        // sans arrow inside a serif number, has its own top but sits on the same line)
        const rects = [...range.getClientRects()].filter((cr) => cr.width > 0.5).sort((a, b) => a.top - b.top);
        let lines = 0, lineBottom = -Infinity;
        for (const cr of rects) {
          if ((cr.top + cr.bottom) / 2 > lineBottom) { lines++; lineBottom = cr.bottom; } else lineBottom = Math.max(lineBottom, cr.bottom);
        }
        const lh = cs.lineHeight === "normal" ? px(cs.fontSize) * 1.15 : px(cs.lineHeight);
        const valign = (el.tagName === "TD" || el.tagName === "TH") ? cs.verticalAlign : "top";  // cells stretch to the row
        const item = { tag: el.tagName, ...content, align: cs.textAlign, valign, lineHeight: lh, lines, runs };
        if (el.tagName === "LI") {
          const ul = el.parentElement;
          item.bullet = cs.listStyleType !== "none";
          item.indent = Math.max(18, el.getBoundingClientRect().left - ul.getBoundingClientRect().left);
        }
        out.texts.push(item);
      }
      return out;
    }, congressFonts);
    await page.screenshot({ path: path.join(outDir, `${id}.png`) });
    for (const s of data.svgs) {
      const handle = await page.$(`svg[data-svg-index="${s.index}"]`);
      const shot = path.join(outDir, `${id}_svg${s.index}.png`);
      await handle.screenshot({ path: shot, omitBackground: false });
      s.file = shot;
    }
    slides.push(data);
    console.log(`${id}: ${data.texts.length} texts, ${data.boxes.length} boxes, ${data.images.length} images, ${data.svgs.length} svgs`);
  }
  fs.writeFileSync(path.join(outDir, "slides.json"), JSON.stringify({ order: deck.order, slides }, null, 1));
  await browser.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
