/* deck.js — presentation layer for preview.html: navigation, motion, live charts and presenter tools.
 * It works on the slides as written (their inline styles) and never changes the slide sources or the .pptx.
 * Keys: → / PageDown / Space next · ← / PageUp previous · Home / End · S notes · R read · O overview · F full screen · B blank.
 * Touch: swipe or tap the right or left of the slide. A phone or tablet held upright gets the reading view instead: the
 * slides as a scrolling list with the speaker notes under each (R toggles it anywhere; rotating returns to automatic).
 * Motion is off under prefers-reduced-motion (and in print). */
(function () {
  "use strict";
  const slides = [...document.querySelectorAll("section")];
  const META = JSON.parse(document.getElementById("deck-meta").textContent);
  const LIVE = JSON.parse(document.getElementById("deck-live").textContent || "null");
  const reduced = () => !!(window.matchMedia && (window.matchMedia("(prefers-reduced-motion: reduce)").matches || window.matchMedia("print").matches));
  const EASE = "cubic-bezier(.2,.7,.2,1)";
  let cur = 0, overview = false, notesWin = null, started = null, slideStart = Date.now();
  let reading = false, readPref = null, readEl = null;
  const upright = window.matchMedia("(orientation: portrait) and (max-width: 900px)");

  // ------------------------------------------------------------------ canvas
  function resize() {
    document.documentElement.style.setProperty("--scale", Math.min(innerWidth / 1920, innerHeight / 1080) * 0.985);
    setReading(readPref === null ? upright.matches : readPref);
    if (reading) layoutRead();
    if (overview) layoutOverview();
  }

  // ------------------------------------------------------------------ navigation
  function show(n, animate = true) {
    cur = Math.max(0, Math.min(slides.length - 1, n));
    if (reading) { document.getElementById("read-" + slides[cur].id).scrollIntoView({ behavior: reduced() ? "auto" : "smooth" }); return; }
    slides.forEach((s, k) => s.classList.toggle("active", k === cur));
    const s = slides[cur];
    document.getElementById("count").textContent = `${cur + 1} / ${slides.length}`;
    document.getElementById("progress").style.width = ((cur + 1) / slides.length) * 100 + "%";
    history.replaceState(null, "", "#" + s.id);
    slideStart = Date.now();
    if (window.Charts) Charts.hideTip();
    if (!overview) {
      renderLive(s);
      if (animate) animateIn(s);
    }
    updateNotes();
  }
  const next = () => show(cur + 1);
  const prev = () => show(cur - 1);

  // ------------------------------------------------------------------ motion
  const isSpacer = (el) => !el.textContent.trim() && !el.querySelector("img,svg,.live-chart") && el.tagName !== "IMG";
  const isHeader = (el) => el.matches('p[style*="top:56px"]');
  const isFooter = (el) => el.matches('p[style*="bottom:64px"]');

  /** Blocks that enter one after another: the children of the outermost flex rows, plus loose elements. */
  function blocksOf(s, skip) {
    const rows = [...s.querySelectorAll("div")].filter((d) => {
      const cs = getComputedStyle(d);
      return cs.display === "flex" && cs.flexDirection === "row" && [...d.children].filter((c) => !isSpacer(c)).length >= 2;
    });
    const chosen = [];
    for (const r of rows) {
      if (chosen.some((b) => b.contains(r))) continue;
      for (const c of r.children) if (!isSpacer(c) && !skip.includes(c)) chosen.push(c);
    }
    const loose = [...s.children].filter((c) => !isSpacer(c) && !skip.includes(c) && !c.matches("aside,a.explore") && !isHeader(c) && !isFooter(c)
      && !chosen.some((b) => b.contains(c) || c.contains(b)));
    return chosen.concat(loose).sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
  }

  /** "36%", "+89%", "1.6×", "140,281", "+18 points": counted up from zero; years and ranges are left alone. */
  const NUM = /^([+£$]?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(\s?[%×x]?(?:\s[a-z]+)?)$/i;
  function countUp(el, delay) {
    if (el.children.length) return;
    const text = el.textContent.trim(), m = text.match(NUM);
    if (!m) return;
    const value = parseFloat((m[2] + (m[3] || "")).replace(/,/g, ""));
    if (!m[1] && !m[4] && !m[3] && value >= 1900 && value <= 2100) return;   // a year
    const dec = m[3] ? m[3].length - 1 : 0, commas = m[2].includes(",");
    const fmt = (v) => m[1] + (commas ? v.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) : v.toFixed(dec)) + m[4];
    const t0 = performance.now() + delay, dur = 1100;
    el.textContent = fmt(0);
    const step = (now) => {
      const p = Math.min(1, Math.max(0, (now - t0) / dur));
      el.textContent = p >= 1 ? text : fmt(value * (1 - Math.pow(1 - p, 3)));
      if (p < 1 && el.isConnected) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function animateIn(s) {
    if (reduced()) return;
    s.getAnimations({ subtree: true }).forEach((a) => a.cancel());
    s.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 260, easing: "ease-out" });
    const title = s.querySelector("h1, h2");
    const eyebrow = (s.querySelector(':scope > p > span[style*="font-weight:500"]') || {}).parentElement || null;
    const footer = s.querySelector('p[style*="bottom:64px"]');
    const explore = s.querySelector("a.explore");
    const purposeMorph = s.id === "crisis" && slides[cur - 1] && slides[cur - 1].id === "purpose";
    if (title) {
      const big = title.tagName === "H1" ? 1.18 : purposeMorph ? 2.1 : 1.45;
      title.animate([
        { transform: `scale(${big})`, opacity: 0, clipPath: "inset(100% 0 0 0)" },
        { transform: `scale(${big})`, opacity: 1, clipPath: "inset(0 0 0 0)", offset: 0.3 },
        { transform: "scale(1)", opacity: 1, clipPath: "inset(0 0 0 0)" },
      ], { duration: purposeMorph ? 1300 : 1100, easing: EASE, fill: "backwards" });
    }
    if (eyebrow) eyebrow.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 500, delay: 150, easing: "ease-out", fill: "backwards" });
    const blocks = blocksOf(s, [title, eyebrow, footer].filter(Boolean));
    let last = 250;
    blocks.forEach((b, k) => {
      const delay = 300 + k * 85;
      last = delay;
      const pic = b.matches("img") ? b : null;
      if (pic && s.id !== "cover") {
        pic.animate([{ clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0 0 0)" }], { duration: 1000, delay, easing: EASE, fill: "backwards" });
      } else if (!b.matches(".live-chart")) {
        b.animate([{ opacity: 0, transform: "translateY(26px)" }, { opacity: 1, transform: "none" }], { duration: 650, delay, easing: EASE, fill: "backwards" });
      }
      b.querySelectorAll("img").forEach((im) => { if (!im.closest(".live-chart")) im.animate([{ clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0 0 0)" }], { duration: 1000, delay: delay + 100, easing: EASE, fill: "backwards" }); });
      const serif = [b, ...b.querySelectorAll("p")].filter((p) => p.tagName === "P" && /Instrument Serif/.test(getComputedStyle(p).fontFamily) && parseFloat(getComputedStyle(p).fontSize) >= 56);
      serif.forEach((p) => countUp(p, delay + 80));
    });
    for (const el of [footer, explore]) if (el) el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 600, delay: last + 350, easing: "ease-out", fill: "backwards" });
  }

  // ------------------------------------------------------------------ live charts (the dashboard's charts.js)
  function renderLive(s) {
    if (!LIVE || !window.Charts) return;
    s.querySelectorAll(".live-chart").forEach((el) => {
      const cfg = LIVE.charts[el.dataset.chart];
      if (!cfg) return;
      if (el.dataset.ready) { if (!reduced()) requestAnimationFrame(() => Charts.replay(el.querySelector(".live-plot"))); return; }
      requestAnimationFrame(() => requestAnimationFrame(() => {
        const W = el.offsetWidth, H = el.offsetHeight;
        if (!W || !H) return;
        const scale = W / cfg.vw;
        const inner = document.createElement("div");
        inner.className = "live-inner" + (cfg.textSize ? " big-text" : "");
        inner.style.width = cfg.vw + "px";
        if (cfg.textSize) inner.style.setProperty("--live-text", cfg.textSize + "px");
        inner.style.transform = `scale(${scale})`;
        const key = document.createElement("div"); key.className = "live-key";
        const plot = document.createElement("div"); plot.className = "live-plot";
        inner.append(key, plot);
        el.replaceChildren(inner);
        Charts.key(key, cfg.key || []);
        const keyH = key.hidden ? 0 : key.offsetHeight;
        const opts = Object.assign({}, cfg.opts, { height: Math.max(160, Math.round(H / scale - keyH)) });
        try {
          Charts[cfg.kind](plot, opts);
          el.dataset.ready = "1";
          if (!reduced()) Charts.replay(plot);
        } catch (err) { console.error("live chart", el.dataset.chart, err); }
      }));
    });
  }

  // ------------------------------------------------------------------ presenter: speaker notes window with timers
  const fmtClock = (ms) => { const t = Math.max(0, Math.floor(ms / 1000)); return Math.floor(t / 60) + ":" + String(t % 60).padStart(2, "0"); };
  const NOTES_HTML = `<!doctype html><html><head><meta charset="utf-8"><title>Speaker notes · Open science in stroke research</title><style>
body{margin:0;font-family:"Instrument Sans",Helvetica,Arial,sans-serif;background:#f1f1ef;color:#141414;display:grid;grid-template-rows:auto 1fr auto;height:100vh}
header{display:flex;gap:20px;align-items:baseline;padding:16px 24px;border-bottom:1px solid #c6c6c1}
#n{color:#d7263d;font-weight:600;font-size:22px}#title{font-size:30px;font-weight:500}
#clocks{margin-left:auto;font-variant-numeric:tabular-nums;color:#4a4a47;font-size:20px;white-space:nowrap}#clocks b{color:#141414}
#notes{padding:22px 26px;font-size:25px;line-height:1.45;overflow:auto;max-width:72ch}
footer{display:flex;gap:14px;align-items:center;padding:12px 24px;border-top:1px solid #c6c6c1;color:#4a4a47;font-size:18px}
button{font:inherit;padding:6px 16px;border:1px solid #141414;background:none;border-radius:999px;cursor:pointer}#nextwrap{margin-left:auto}
</style></head><body><header><span id="n"></span><span id="title"></span><span id="clocks">total <b id="total">0:00</b> · this slide <b id="slide">0:00</b> · <span id="clock"></span></span></header>
<div id="notes"></div><footer><button id="p">Previous</button><button id="x">Next</button><button id="r">Restart timer</button><span id="nextwrap">Next: <b id="next"></b></span></footer></body></html>`;

  function openNotes() {
    if (notesWin && !notesWin.closed) { notesWin.focus(); return; }
    notesWin = window.open("", "deck-notes", "width=1000,height=760");
    if (!notesWin) { readPref = true; setReading(true); return; }  // pop-ups blocked: the reading view shows the notes
    notesWin.document.open(); notesWin.document.write(NOTES_HTML); notesWin.document.close();
    notesWin.document.getElementById("p").onclick = prev;
    notesWin.document.getElementById("x").onclick = next;
    notesWin.document.getElementById("r").onclick = () => { started = Date.now(); slideStart = Date.now(); tick(); };
    notesWin.addEventListener("keydown", onKey);
    if (!started) started = Date.now();
    updateNotes();
  }
  function updateNotes() {
    if (!notesWin || notesWin.closed) return;
    const d = notesWin.document, id = slides[cur].id, nid = slides[cur + 1] ? slides[cur + 1].id : null;
    d.getElementById("n").textContent = `${cur + 1} / ${slides.length}`;
    d.getElementById("title").textContent = META.titles[id] || id;
    d.getElementById("notes").textContent = META.notes[id] || "";
    d.getElementById("next").textContent = nid ? META.titles[nid] || nid : "end";
    tick();
  }
  function tick() {
    if (!notesWin || notesWin.closed) return;
    const d = notesWin.document;
    d.getElementById("total").textContent = fmtClock(Date.now() - (started || Date.now()));
    d.getElementById("slide").textContent = fmtClock(Date.now() - slideStart);
    d.getElementById("clock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  setInterval(tick, 500);

  // ------------------------------------------------------------------ presenter: overview, full screen, blank
  function layoutOverview() {
    const cols = 6, pad = 32, gap = 18;
    const k = (innerWidth - 2 * pad - (cols - 1) * gap) / cols / 1920;
    slides.forEach((s, n) => {
      const c = n % cols, r = Math.floor(n / cols);
      s.style.transform = `translate(${pad + c * (1920 * k + gap)}px, ${pad + r * (1080 * k + gap)}px) scale(${k})`;
    });
    document.body.style.minHeight = 2 * pad + Math.ceil(slides.length / cols) * (1080 * k + gap) + "px";
  }
  function toggleOverview(on) {
    overview = on === undefined ? !overview : on;
    document.body.classList.toggle("overview", overview);
    if (overview) { if (window.Charts) Charts.hideTip(); layoutOverview(); }
    else { slides.forEach((s) => s.style.removeProperty("transform")); document.body.style.removeProperty("min-height"); show(cur); }
  }
  slides.forEach((s, n) => s.addEventListener("click", (e) => { if (overview) { e.preventDefault(); cur = n; toggleOverview(false); } }, true));
  const fullscreen = () => (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen()).catch(() => {});
  const blank = () => { const b = document.getElementById("blank"); b.hidden = !b.hidden; };

  // ------------------------------------------------------------------ keys, pointer
  function onKey(e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key;
    if (overview && (k === "Escape" || k === "o" || k === "O" || k === "Enter")) { e.preventDefault(); toggleOverview(false); return; }
    if (["ArrowRight", "PageDown", " ", "ArrowDown"].includes(k)) { e.preventDefault(); next(); }
    else if (["ArrowLeft", "PageUp", "ArrowUp", "Backspace"].includes(k)) { e.preventDefault(); prev(); }
    else if (k === "Home") show(0);
    else if (k === "End") show(slides.length - 1);
    else if (k === "s" || k === "S") openNotes();
    else if (k === "o" || k === "O") { if (!reading) toggleOverview(); }
    else if (k === "r" || k === "R") { readPref = !reading; setReading(readPref); }
    else if (k === "f" || k === "F") fullscreen();
    else if (k === "b" || k === "B" || k === ".") blank();
  }
  document.addEventListener("keydown", onKey);
  document.getElementById("prev").onclick = prev;
  document.getElementById("next").onclick = next;
  let idle;
  const wake = () => { document.body.classList.remove("idle"); clearTimeout(idle); idle = setTimeout(() => document.body.classList.add("idle"), 2200); };
  document.addEventListener("mousemove", wake);
  window.addEventListener("resize", resize);
  upright.addEventListener("change", () => { readPref = null; resize(); });

  // ------------------------------------------------------------------ touch: swipe, or tap the right / left third
  let touch = null;
  document.addEventListener("touchstart", (e) => {
    wake();
    const t = e.touches[0];
    touch = reading || overview || e.touches.length !== 1 ? null : { x: t.clientX, y: t.clientY, at: Date.now() };
  }, { passive: true });
  document.addEventListener("touchend", (e) => {
    if (!touch) return;
    const t = e.changedTouches[0], dx = t.clientX - touch.x, dy = t.clientY - touch.y, quick = Date.now() - touch.at < 400;
    touch = null;
    if (Math.abs(dx) > 40 && Math.abs(dx) > 1.5 * Math.abs(dy)) { if (dx < 0) next(); else prev(); return; }
    if (quick && Math.abs(dx) < 10 && Math.abs(dy) < 10 && !e.target.closest("a, button, .live-chart")) {
      e.preventDefault();
      if (t.clientX < innerWidth / 3) prev(); else next();
    }
  }, { passive: false });

  // ------------------------------------------------------------------ reading view: every slide at the screen's width, its notes below
  const marks = slides.map((s) => { const m = document.createComment(s.id); s.before(m); return m; });
  const readHidden = () => { try { return localStorage.getItem("deck-notes-hidden") === "1"; } catch (e) { return false; } };
  function buildRead() {
    readEl = document.createElement("main");
    readEl.id = "read";
    const bar = document.createElement("div");
    bar.className = "read-bar";
    const name = document.createElement("p");
    name.className = "read-name";
    name.textContent = META.title || document.title;
    const ctl = document.createElement("div");
    ctl.className = "read-controls";
    const tog = document.createElement("button");
    tog.type = "button"; tog.id = "read-notes"; tog.textContent = "Notes";
    tog.setAttribute("aria-pressed", String(!readHidden()));
    document.body.classList.toggle("no-notes", readHidden());
    tog.onclick = () => {
      const hide = !document.body.classList.contains("no-notes");
      document.body.classList.toggle("no-notes", hide);
      tog.setAttribute("aria-pressed", String(!hide));
      try { localStorage.setItem("deck-notes-hidden", hide ? "1" : "0"); } catch (e) { /* storage blocked: the choice lasts this visit */ }
    };
    ctl.append(tog);
    (META.links || []).forEach((l) => {
      const a = document.createElement("a");
      a.href = l.href; a.target = "_blank"; a.rel = "noopener"; a.textContent = l.label + " ↗";
      ctl.append(a);
    });
    bar.append(name, ctl);
    readEl.append(bar);
    slides.forEach((s, n) => {
      const item = document.createElement("article");
      item.className = "read-item"; item.id = "read-" + s.id;
      const label = document.createElement("p");
      label.className = "read-label";
      label.innerHTML = `<b>${String(n + 1).padStart(2, "0")}</b>&nbsp;&nbsp;`;
      label.append(META.titles[s.id] || s.id);
      const frame = document.createElement("div");
      frame.className = "read-frame";
      const notes = document.createElement("p");
      notes.className = "read-notes";
      notes.textContent = META.notes[s.id] || "";
      item.append(label, frame);
      if (notes.textContent) item.append(notes);
      readEl.append(item);
    });
    document.body.append(readEl);
  }
  function layoutRead() {
    const f = readEl && readEl.querySelector(".read-frame");
    if (f && f.clientWidth) readEl.style.setProperty("--rk", f.clientWidth / 1920);
  }
  function setReading(on) {
    if (on === reading) return;
    reading = on;
    if (on) {
      if (overview) toggleOverview(false);
      if (window.Charts) Charts.hideTip();
      if (!readEl) buildRead();
      const frames = readEl.querySelectorAll(".read-frame");
      slides.forEach((s, n) => { s.classList.remove("active"); frames[n].append(s); });
      document.body.classList.add("reading");
      layoutRead();
      if (cur > 0) document.getElementById("read-" + slides[cur].id).scrollIntoView();
    } else {
      document.body.classList.remove("reading");
      slides.forEach((s, n) => marks[n].after(s));
      show(cur, false);
    }
  }
  // the slide nearest the top of the screen is the current one, so turning the phone keeps the place
  let readTick = 0;
  window.addEventListener("scroll", () => {
    if (!reading || readTick) return;
    readTick = requestAnimationFrame(() => {
      readTick = 0;
      const k = slides.findIndex((s) => s.closest(".read-item").getBoundingClientRect().bottom > innerHeight * 0.35);
      if (k >= 0 && k !== cur) { cur = k; history.replaceState(null, "", "#" + slides[k].id); }
    });
  }, { passive: true });
  window.addEventListener("beforeunload", () => { if (notesWin && !notesWin.closed) notesWin.close(); });

  const start = slides.findIndex((s) => s.id === location.hash.slice(1));
  cur = Math.max(0, start);
  resize();
  wake();
  if (!reading) show(cur);
})();
