/* Open-Science Benchmark — interactive static dashboard (schema v2).
 * Loads dashboard_data.json (pre-aggregated counts) and recomputes every rate client-side for
 * the current selection. Views: overview, trends, open access, data statements, equity,
 * commitment, journals, countries & funders, methods. No server, no build step. */
(function () {
  "use strict";

  const DATA_URL = "dashboard_data.json";
  const MIN_N_RATE = 10;          // below this many papers a rate is not drawn (tiles still show n)
  const CELL_OFFSET = 4;          // [year, hi, journal, country, ...counts]
  const DIM_OFFSET = 3;           // [year, hi, <dim>, ...counts] for funder / income / institution tables

  const VIEWS = [
    ["overview", "Overview"], ["trends", "Trends"], ["oa", "Open access"], ["das", "Data statements"],
    ["equity", "Equity"], ["commitment", "Commitment"], ["journals", "Journals"], ["geo", "Countries & funders"],
    ["methods", "Methods"],
  ];

  // Dark-mode steps of the same categorical hues (validated set; see docs).
  const DARK_SERIES = { "#2a78d6": "#3987e5", "#eb6834": "#d95926", "#1baf7a": "#199e70", "#eda100": "#c98500",
    "#7b61c9": "#9085e9", "#c04d8c": "#d55181", "#5c7f8f": "#7fa3b3", "#8a7a3a": "#b3a05a" };
  // Ordinal blue ramps (validated: light 700/550/450/350/250, dark 600/500/400/300/200), darkest = most open.
  const RAMP5 = { light: ["#0d366b", "#1c5cab", "#2a78d6", "#5598e7", "#86b6ef"], dark: ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4"] };
  const RAMP3 = { light: ["#0d366b", "#2a78d6", "#86b6ef"], dark: ["#184f95", "#3987e5", "#9ec5f4"] };
  const RAMP4 = { light: ["#0d366b", "#1c5cab", "#5598e7", "#86b6ef"], dark: ["#184f95", "#256abf", "#6da7ec", "#9ec5f4"] };

  const OA_ROUTES = [
    { key: "free", label: "Free to author (diamond, green)", statuses: ["diamond", "green"] },
    { key: "paid", label: "APC paid (gold, hybrid)", statuses: ["gold", "hybrid"] },
    { key: "bronze", label: "Bronze (free to read, no licence)", statuses: ["bronze"] },
    { key: "closed", label: "Closed", statuses: ["closed"], neutral: true },
  ];
  const DAS_FIVE = [
    { key: "deposit", label: "Deposited or public source", cats: ["repository", "public_source"] },
    { key: "controlled", label: "Controlled or restricted", cats: ["controlled_or_restricted"] },
    { key: "on_request", label: "On request", cats: ["on_request"] },
    { key: "in_article", label: "In article or supplement", cats: ["in_article"] },
    { key: "na", label: "Not available or unclear", cats: ["not_available_or_na", "other_or_unclear"] },
    { key: "none", label: "No statement", cats: ["no_statement"], neutral: true },
  ];

  let DATA = null;
  const K = {};                   // count key -> index within the counts part of a row
  let METRICS = [];               // client metric defs: {key, label, short, definition, numerators, denominator}
  const state = {
    view: "overview",
    disciplines: [], focus: null, yearMin: null, yearMax: null,
    slice: { kind: "", key: "" }, hi: false,
    metric: "oa", trendCompare: "disciplines", trendShow: "rate",
    oaGrouping: "route", dasGrouping: "five", dasDenominator: "audited",
    eqSignal: "route", cmEntity: "institutions", cmMin: 50, cmTop: 15, cmSignals: ["das_deposit", "ft_github", "ft_reg"],
    journalMetric: "oa", journalMin: 100, journalTop: 25,
    markers: true,
    sort: {},
  };
  const QUICK_VIEWS = [
    { label: "Stroke overview", hash: "view=overview&focus=stroke" },
    { label: "Stroke in Korea", hash: "view=overview&focus=stroke&slice=country:KR" },
    { label: "What statements say, 2022–2025", hash: "view=das&focus=stroke&years=2022-2025" },
    { label: "Who pays to be read", hash: "view=equity&focus=stroke&eqSignal=route" },
    { label: "Prize shortlist", hash: "view=commitment&focus=stroke&cmEntity=institutions&cmMin=100&cmTop=15" },
    { label: "Full text vs abstract", hash: "view=trends&metric=ft_github&trendCompare=disciplines" },
  ];

  // ------------------------------------------------------------------ utilities
  const $ = (id) => document.getElementById(id);
  const el = (tag, attrs, children) => {
    const node = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else if (v !== null && v !== undefined) node.setAttribute(k, v);
    }
    if (children) for (const c of [].concat(children)) if (c !== null && c !== undefined) node.append(c);
    return node;
  };
  const fmtInt = (v) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : Math.round(v).toLocaleString("en-US");
  const fmtPct = (v, digits) => {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const d = digits !== undefined ? digits : (v < 0.1 ? 1 : 0);
    return (v * 100).toFixed(d) + "%";
  };
  const fmtX = (v) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : v.toFixed(1) + "×";
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const isDark = () => getComputedStyle(document.documentElement).colorScheme.trim() === "dark";
  const ramp = (r) => (isDark() ? r.dark : r.light);
  const seriesColor = (hex) => (isDark() ? (DARK_SERIES[hex] || hex) : hex);

  function tokens() {
    const cs = getComputedStyle(document.documentElement);
    const get = (name) => cs.getPropertyValue(name).trim();
    return { ink: get("--ink"), ink2: get("--ink-2"), ink3: get("--ink-3"), grid: get("--grid"), border: get("--border"),
      surface: get("--surface"), surface2: get("--surface-2"), font: get("--font"), neutral: get("--neutral-mark"), accent: get("--accent") };
  }

  function discByKey(key) { return DATA.disciplines.find((d) => d.key === key); }
  function focusDisc() { return discByKey(state.focus); }
  function selectedDiscs() { return DATA.disciplines.filter((d) => state.disciplines.includes(d.key)); }
  function yearsInRange() { return DATA.years.filter((y) => y >= state.yearMin && y <= state.yearMax); }
  function discColor(d) { return seriesColor(d.color); }

  // ------------------------------------------------------------------ metrics
  function buildMetrics() {
    METRICS = DATA.metrics.map((m) => ({ key: m.key, label: m.label, short: m.short || m.label, definition: m.definition,
      numerators: [m.key], denominator: m.denominator || (m.key === "reg" ? "n_abs" : "n") }));
    if (K.das_repository !== undefined) {
      METRICS.splice(METRICS.findIndex((m) => m.key === "das_stmt") + 1, 0, {
        key: "das_deposit", label: "Data deposited or public source (full text)", short: "Deposit (full text)",
        definition: "Share of audited open-access full texts whose data-availability statement names the authors' own repository deposit or a public / third-party dataset. Denominator: audited papers.",
        numerators: ["das_repository", "das_public_source"], denominator: "das_audited" });
      METRICS.push({ key: "das_on_request", label: "Data 'on request' (full text)", short: "On request",
        definition: "Share of audited open-access full texts whose statement says the data are available on request. Denominator: audited papers.",
        numerators: ["das_on_request"], denominator: "das_audited" });
    }
  }
  const metric = (key) => METRICS.find((m) => m.key === key) || METRICS[0];
  function numer(counts, m) { return m.numerators.reduce((s, k) => s + (counts[K[k]] || 0), 0); }
  function denom(counts, m) { return counts[K[m.denominator]] || 0; }
  function rate(counts, key) {
    if (!counts) return null;
    const m = typeof key === "string" ? metric(key) : key;
    const d = denom(counts, m);
    if (!d || d < MIN_N_RATE) return null;
    return numer(counts, m) / d;
  }
  function metricAvailable(d, key) {
    const m = metric(key);
    if (m.denominator === "das_audited") return !!d.available.das;
    if (m.key === "reg") return !!d.available.registration;
    return true;
  }
  function oaKnown(counts) { return DATA.oa_status_order.reduce((s, st) => s + counts[K["oa_" + st]], 0); }

  // ------------------------------------------------------------------ aggregation
  function emptyCounts() { return new Array(DATA.count_keys.length).fill(0); }
  function addRow(acc, row, offset) { for (let i = 0; i < acc.length; i++) acc[i] += row[offset + i]; }
  function indexOf(list, key, prop) {
    if (!key) return null;
    const i = list.findIndex((item) => (prop ? item[prop] : item) === key);
    return i < 0 ? -1 : i;
  }
  /** The slice as an index into the discipline's own lists; -1 = requested value absent here. */
  function sliceIndex(disc) {
    const s = state.slice;
    if (!s.kind) return null;
    if (s.kind === "journal") return indexOf(disc.journals, s.key, "key");
    if (s.kind === "country") return indexOf(disc.countries, s.key, "key");
    if (s.kind === "funder") return indexOf(disc.funders, s.key);
    if (s.kind === "income") return indexOf(disc.income_groups || [], s.key);
    return null;
  }
  function tableFor(disc, kind) {
    if (kind === "funder") return { rows: disc.funder_cells, offset: DIM_OFFSET, pos: 2 };
    if (kind === "income") return { rows: disc.income_cells || [], offset: DIM_OFFSET, pos: 2 };
    if (kind === "institution") return { rows: disc.institution_cells || [], offset: DIM_OFFSET, pos: 2 };
    return { rows: disc.cells, offset: CELL_OFFSET, pos: kind === "country" ? 3 : 2 };
  }

  /** Aggregate counts by year for one discipline under the current selection. */
  function aggregateDiscipline(disc) {
    const byYear = new Map();
    const total = emptyCounts();
    const kind = state.slice.kind;
    const idx = sliceIndex(disc);
    if (idx === -1) return { byYear, total, applicable: false };
    const t = tableFor(disc, kind || "journal");
    for (const row of t.rows) {
      const year = row[0];
      if (year < state.yearMin || year > state.yearMax) continue;
      if (state.hi && row[1] !== 1) continue;
      if (idx !== null && row[t.pos] !== idx) continue;
      let acc = byYear.get(year);
      if (!acc) { acc = emptyCounts(); byYear.set(year, acc); }
      addRow(acc, row, t.offset);
      addRow(total, row, t.offset);
    }
    return { byYear, total, applicable: true };
  }

  /** Aggregate counts grouped by one dimension (journal, country, funder, income, institution). The slice
   *  applies only when it lives in the same table (journal <-> country); otherwise the group-by is discipline-wide. */
  function aggregateBy(disc, dim) {
    const groups = new Map();
    const t = tableFor(disc, dim);
    const sameTable = (dim === "journal" || dim === "country") && (state.slice.kind === "journal" || state.slice.kind === "country") && state.slice.kind !== dim;
    const idx = sameTable ? sliceIndex(disc) : null;
    const slicePos = state.slice.kind === "country" ? 3 : 2;
    if (idx === -1) return groups;
    for (const row of t.rows) {
      const year = row[0];
      if (year < state.yearMin || year > state.yearMax) continue;
      if (state.hi && row[1] !== 1) continue;
      if (idx !== null && row[slicePos] !== idx) continue;
      let acc = groups.get(row[t.pos]);
      if (!acc) { acc = emptyCounts(); groups.set(row[t.pos], acc); }
      addRow(acc, row, t.offset);
    }
    return groups;
  }
  /** Discipline-wide totals (year + subset only), the baseline for the commitment index. */
  function baselineCounts(disc) {
    const total = emptyCounts();
    for (const row of disc.cells) {
      if (row[0] < state.yearMin || row[0] > state.yearMax) continue;
      if (state.hi && row[1] !== 1) continue;
      addRow(total, row, CELL_OFFSET);
    }
    return total;
  }

  // ------------------------------------------------------------------ URL state
  const HASH_KEYS = ["view", "focus", "hi", "metric", "trendCompare", "trendShow", "oaGrouping", "dasGrouping", "dasDenominator",
    "eqSignal", "cmEntity", "cmMin", "cmTop", "journalMetric", "journalMin", "journalTop", "markers"];
  function writeHash() {
    const p = new URLSearchParams();
    for (const k of HASH_KEYS) p.set(k, String(state[k]));
    p.set("years", state.yearMin + "-" + state.yearMax);
    p.set("disc", state.disciplines.join(","));
    if (state.slice.kind) p.set("slice", state.slice.kind + ":" + state.slice.key);
    p.set("cmSignals", state.cmSignals.join(","));
    history.replaceState(null, "", "#" + p.toString());
  }
  function readHash() {
    const h = location.hash.replace(/^#/, "");
    if (!h) return;
    const p = new URLSearchParams(h);
    const allDisc = DATA.disciplines.map((d) => d.key);
    const disc = (p.get("disc") || "").split(",").filter((k) => allDisc.includes(k));
    if (disc.length) state.disciplines = allDisc.filter((k) => disc.includes(k));
    if (p.get("focus") && state.disciplines.includes(p.get("focus"))) state.focus = p.get("focus");
    const yrs = (p.get("years") || "").split("-").map(Number);
    if (yrs.length === 2 && yrs.every((y) => DATA.years.includes(y)) && yrs[0] <= yrs[1]) { state.yearMin = yrs[0]; state.yearMax = yrs[1]; }
    if (p.get("hi") === "true") state.hi = true;
    if (p.get("markers") === "false") state.markers = false;
    const slice = (p.get("slice") || "").split(":");
    if (slice.length >= 2 && ["journal", "country", "funder", "income"].includes(slice[0])) state.slice = { kind: slice[0], key: slice.slice(1).join(":") };
    for (const k of ["view", "metric", "trendCompare", "trendShow", "oaGrouping", "dasGrouping", "dasDenominator", "eqSignal", "cmEntity", "journalMetric"]) {
      if (p.get(k)) state[k] = p.get(k);
    }
    for (const k of ["cmMin", "cmTop", "journalMin", "journalTop"]) if (p.get(k) && !Number.isNaN(+p.get(k))) state[k] = +p.get(k);
    const sig = (p.get("cmSignals") || "").split(",").filter(Boolean);
    if (sig.length) state.cmSignals = sig;
    if (!VIEWS.some((v) => v[0] === state.view)) state.view = "overview";
    if (!METRICS.some((m) => m.key === state.metric)) state.metric = "oa";
    if (!METRICS.some((m) => m.key === state.journalMetric)) state.journalMetric = "oa";
  }

  // ------------------------------------------------------------------ selection UI
  function resetState() {
    state.disciplines = DATA.disciplines.map((d) => d.key);
    state.focus = state.disciplines.includes("stroke") ? "stroke" : state.disciplines[0];
    const dflt = Array.isArray(DATA.default_year_range) && DATA.default_year_range.length === 2 ? DATA.default_year_range : DATA.years;
    state.yearMin = dflt[0]; state.yearMax = dflt[dflt.length - 1];
    state.slice = { kind: "", key: "" }; state.hi = false;
    state.metric = "oa"; state.trendCompare = "disciplines"; state.trendShow = "rate";
    state.oaGrouping = "route"; state.dasGrouping = "five"; state.dasDenominator = "audited"; state.eqSignal = "route";
    state.cmEntity = "institutions"; state.cmMin = 50; state.cmTop = 15; state.cmSignals = ["das_deposit", "ft_github", "ft_reg"];
    state.journalMetric = "oa"; state.journalMin = 100; state.journalTop = 25;
    state.markers = true;
  }

  function yearPresets() {
    const all = DATA.years;
    const complete = DATA.default_year_range || [all[0], all[all.length - 1]];
    const presets = [
      { label: complete[0] + "–" + complete[1], min: complete[0], max: complete[1] },
      { label: "Since 2020", min: Math.max(all[0], 2020), max: complete[1] },
      { label: "Last 3 years", min: Math.max(all[0], complete[1] - 2), max: complete[1] },
      { label: "All years", min: all[0], max: all[all.length - 1] },
    ];
    const seen = new Set();
    return presets.filter((p) => p.min <= p.max && !seen.has(p.min + "-" + p.max) && seen.add(p.min + "-" + p.max));
  }

  function buildSelection() {
    // Disciplines
    const chips = $("discipline-chips");
    chips.replaceChildren();
    for (const d of DATA.disciplines) {
      const on = state.disciplines.includes(d.key);
      const input = el("input", { type: "checkbox", id: "chip-" + d.key, checked: on ? "" : null });
      const chip = el("label", { class: "chip" + (on ? " is-on" : ""), for: "chip-" + d.key },
        [input, el("span", { class: "swatch", "aria-hidden": "true" }), el("span", { text: d.label })]);
      chip.style.setProperty("--c", d.color);
      input.addEventListener("change", () => {
        const next = DATA.disciplines.map((x) => x.key).filter((k) => (k === d.key ? input.checked : state.disciplines.includes(k)));
        if (!next.length) { input.checked = true; return; }
        state.disciplines = next;
        chip.classList.toggle("is-on", input.checked);
        if (!state.disciplines.includes(state.focus)) state.focus = state.disciplines[0];
        buildFocusSelect(); buildSliceSelect(); renderAll();
      });
      chips.append(chip);
    }
    buildFocusSelect();
    $("focus-select").onchange = (e) => { state.focus = e.target.value; buildSliceSelect(); renderAll(); };

    // Years
    const presets = $("year-presets");
    presets.replaceChildren();
    for (const p of yearPresets()) {
      const b = el("button", { type: "button", class: "seg-btn", text: p.label, "aria-pressed": "false" });
      b.addEventListener("click", () => { state.yearMin = p.min; state.yearMax = p.max; syncYears(); renderAll(); });
      b.dataset.min = p.min; b.dataset.max = p.max;
      presets.append(b);
    }
    const yMin = $("year-min"), yMax = $("year-max");
    const lo = DATA.years[0], hi = DATA.years[DATA.years.length - 1];
    for (const inp of [yMin, yMax]) { inp.min = lo; inp.max = hi; }
    const onYear = () => {
      let a = +yMin.value, b = +yMax.value;
      if (a > b) { if (document.activeElement === yMin) b = a; else a = b; }
      state.yearMin = a; state.yearMax = b;
      syncYears(); renderAll();
    };
    yMin.oninput = onYear; yMax.oninput = onYear;
    if (!document.querySelector(".range-fill")) yMin.parentElement.append(el("span", { class: "range-fill", "aria-hidden": "true" }));
    syncYears();

    buildSliceSelect();
    $("slice-select").onchange = (e) => {
      const v = e.target.value;
      state.slice = v ? { kind: v.split(":")[0], key: v.slice(v.indexOf(":") + 1) } : { kind: "", key: "" };
      renderAll();
    };
    $("hi-all").onclick = () => setHi(false);
    $("hi-only").onclick = () => setHi(true);
    syncHi();
    $("reset-btn").onclick = () => { resetState(); buildSelection(); buildViewOptions(); showView(state.view); renderAll(); };
    const quick = $("quick-views");
    quick.replaceChildren();
    for (const q of QUICK_VIEWS) {
      quick.append(el("button", { type: "button", text: q.label, onclick: () => {
        resetState();
        const base = new URLSearchParams(); for (const k of HASH_KEYS) base.set(k, String(state[k]));
        base.set("years", state.yearMin + "-" + state.yearMax); base.set("disc", state.disciplines.join(","));
        for (const [k, v] of new URLSearchParams(q.hash)) base.set(k, v);
        location.hash = base.toString();
      } }));
    }
    $("download-btn").onclick = downloadCsv;
    $("share-btn").onclick = copyLink;
  }

  function syncYears() {
    $("year-readout").textContent = state.yearMin === state.yearMax ? String(state.yearMin) : state.yearMin + "–" + state.yearMax;
    const yMin = $("year-min"), yMax = $("year-max");
    yMin.value = state.yearMin; yMax.value = state.yearMax;
    const lo = DATA.years[0], hi = DATA.years[DATA.years.length - 1];
    const fill = document.querySelector(".range-fill");
    if (fill && hi > lo) {
      const a = (state.yearMin - lo) / (hi - lo) * 100, b = (state.yearMax - lo) / (hi - lo) * 100;
      fill.style.left = a + "%"; fill.style.width = (b - a) + "%";
    }
    for (const b of $("year-presets").children) {
      const active = +b.dataset.min === state.yearMin && +b.dataset.max === state.yearMax;
      b.classList.toggle("is-active", active); b.setAttribute("aria-pressed", String(active));
    }
  }
  function buildFocusSelect() {
    const sel = $("focus-select");
    sel.replaceChildren();
    for (const d of selectedDiscs()) sel.append(el("option", { value: d.key, text: d.label }));
    sel.value = state.focus;
  }
  function buildSliceSelect() {
    const d = focusDisc();
    const sel = $("slice-select");
    sel.replaceChildren(el("option", { value: "", text: "Everything in " + d.label }));
    const top = DATA.top_n || {};
    const group = (label, items) => {
      if (!items.length) return;
      const g = el("optgroup", { label });
      for (const it of items) g.append(el("option", { value: it.value, text: it.label }));
      sel.append(g);
    };
    if (d.available.income && (d.income_groups || []).length) {
      group("First-author income group", DATA.income_order.map((k) => ({ value: "income:" + k, label: (DATA.income_labels || {})[k] || k })));
    }
    group("Journal (top " + (top.journals || "") + ")", d.journals.filter((j) => j.key !== "Other").map((j) => ({ value: "journal:" + j.key, label: j.label })));
    if (d.available.country) group("First-author country (top " + (top.countries || "") + ")", d.countries.filter((c) => c.key !== "Other").map((c) => ({ value: "country:" + c.key, label: c.label + (c.label !== c.key ? " (" + c.key + ")" : "") })));
    if (d.available.funders) group("Funder (top " + (top.funders || "") + ")", d.funders.filter((f) => f !== "Other" && f !== "(no funder listed)").map((f) => ({ value: "funder:" + f, label: f })));
    const want = state.slice.kind ? state.slice.kind + ":" + state.slice.key : "";
    sel.value = [...sel.options].some((o) => o.value === want) ? want : "";
    if (sel.value !== want) state.slice = { kind: "", key: "" };
  }
  function setHi(on) { state.hi = on; syncHi(); renderAll(); }
  function syncHi() {
    $("hi-all").classList.toggle("is-active", !state.hi); $("hi-all").setAttribute("aria-pressed", String(!state.hi));
    $("hi-only").classList.toggle("is-active", state.hi); $("hi-only").setAttribute("aria-pressed", String(state.hi));
  }
  function sliceLabel() {
    const s = state.slice;
    if (!s.kind) return "";
    const d = focusDisc();
    if (s.kind === "journal") return labelFor(d.journals, s.key);
    if (s.kind === "country") return labelFor(d.countries, s.key);
    if (s.kind === "income") return ((DATA.income_labels || {})[s.key] || s.key) + " first authors";
    return s.key;
  }
  function selectionLabel() {
    const parts = [state.hi ? "high-impact papers" : "all papers"];
    if (state.slice.kind) parts.push(sliceLabel());
    parts.push(state.yearMin === state.yearMax ? String(state.yearMin) : state.yearMin + "–" + state.yearMax);
    return parts.join(" · ");
  }
  function labelFor(list, key) { const item = list.find((x) => x.key === key); return item ? item.label : key; }

  // ------------------------------------------------------------------ views + per-view options
  function buildTabs() {
    const tabs = $("view-tabs");
    tabs.replaceChildren();
    for (const [key, label] of VIEWS) {
      const b = el("button", { type: "button", class: "tab", id: "tab-" + key, role: "tab", text: label, "aria-selected": "false", "aria-controls": "view-" + key });
      b.addEventListener("click", () => { showView(key); renderAll(); });
      tabs.append(b);
    }
  }
  function showView(key) {
    state.view = key;
    for (const [k] of VIEWS) {
      $("view-" + k).hidden = k !== key;
      $("tab-" + k).setAttribute("aria-selected", String(k === key));
    }
  }
  function fillSelectOptions(sel, options, value) {
    sel.replaceChildren();
    for (const o of options) sel.append(el("option", { value: o.value, text: o.label }));
    sel.value = options.some((o) => o.value === value) ? value : (options[0] ? options[0].value : "");
    return sel.value;
  }
  function bind(id, key, parse) {
    const sel = $(id);
    sel.value = String(state[key]);
    sel.onchange = (e) => { state[key] = parse ? parse(e.target.value) : e.target.value; renderAll(); };
  }
  function buildViewOptions() {
    const metricOpts = METRICS.map((m) => ({ value: m.key, label: m.label }));
    state.metric = fillSelectOptions($("metric-select"), metricOpts, state.metric);
    bind("metric-select", "metric");
    bind("trend-compare", "trendCompare"); bind("trend-show", "trendShow");
    bind("oa-grouping", "oaGrouping");
    bind("das-grouping", "dasGrouping"); bind("das-denominator", "dasDenominator");
    const eqOpts = [{ value: "route", label: "open-access route" }].concat(METRICS.filter((m) => m.key !== "material").map((m) => ({ value: m.key, label: m.label })));
    state.eqSignal = fillSelectOptions($("eq-signal"), eqOpts, state.eqSignal);
    bind("eq-signal", "eqSignal");
    bind("cm-entity", "cmEntity"); bind("cm-min", "cmMin", Number); bind("cm-top", "cmTop", Number);
    const checks = $("cm-signals");
    checks.replaceChildren();
    for (const s of DATA.commitment_signals || []) {
      const input = el("input", { type: "checkbox", id: "cmsig-" + s.key, checked: state.cmSignals.includes(s.key) ? "" : null });
      input.addEventListener("change", () => {
        const next = (DATA.commitment_signals || []).map((x) => x.key).filter((k) => (k === s.key ? input.checked : state.cmSignals.includes(k)));
        if (!next.length) { input.checked = true; return; }
        state.cmSignals = next; renderAll();
      });
      checks.append(el("label", { for: "cmsig-" + s.key }, [input, el("span", { text: s.label })]));
    }
    state.journalMetric = fillSelectOptions($("journal-metric"), metricOpts.filter((o) => o.value !== "material"), state.journalMetric);
    bind("journal-metric", "journalMetric"); bind("journal-min", "journalMin", Number); bind("journal-top", "journalTop", Number);
    const mt = $("markers-toggle");
    mt.checked = state.markers;
    mt.onchange = (e) => { state.markers = e.target.checked; renderAll(); };
  }

  // ------------------------------------------------------------------ Plotly helpers
  function baseLayout(t) {
    return {
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: t.font, color: t.ink2, size: 12 },
      margin: { l: 52, r: 24, t: 12, b: 44 },
      xaxis: { gridcolor: "rgba(0,0,0,0)", linecolor: t.border, zeroline: false, tickfont: { color: t.ink3 }, fixedrange: true },
      yaxis: { gridcolor: t.grid, gridwidth: 1, zeroline: false, tickfont: { color: t.ink3 }, fixedrange: true },
      hoverlabel: { bgcolor: t.surface, bordercolor: t.border, font: { color: t.ink, family: t.font, size: 12 } },
      legend: { orientation: "h", y: -0.18, x: 0, font: { color: t.ink2 } },
      showlegend: true,
    };
  }
  const PLOT_CONFIG = { displayModeBar: false, responsive: true, displaylogo: false };
  const isNarrow = (id) => ($(id).clientWidth || 800) < 600;
  const tickStep = (id, nYears) => (isNarrow(id) && nYears > 7 ? 2 : 1);
  function plot(id, traces, layout) {
    const div = $(id);
    const bar = exportBar(div);
    if (!traces.length) {
      Plotly.purge(div);
      div.replaceChildren(el("div", { class: "chart-empty", text: "No data for this selection." }));
      bar.hidden = true;
      return;
    }
    if (div.querySelector(".chart-empty")) div.replaceChildren();
    Plotly.react(div, traces, layout, PLOT_CONFIG);
    bar.hidden = false;
  }
  /** PNG / SVG download buttons under a chart (Plotly renders them client-side). */
  function exportBar(div) {
    let bar = div.nextElementSibling;
    if (bar && bar.classList.contains("export")) return bar;
    bar = el("div", { class: "export" });
    for (const fmt of ["png", "svg"]) {
      bar.append(el("button", { type: "button", text: fmt.toUpperCase(), title: "Download this chart as " + fmt.toUpperCase(), onclick: () => {
        const w = div.clientWidth || 1000, h = div.clientHeight || 420;
        Plotly.downloadImage(div, { format: fmt, width: w, height: h, scale: fmt === "png" ? 2 : 1, filename: div.id + "_" + (DATA ? DATA.run_date : "") });
      } }));
    }
    div.insertAdjacentElement("afterend", bar);
    return bar;
  }
  /** Policy milestones as hairlines with a short label; the full detail is in the label's hover. */
  function policyMarkers(t, years, categorical, id) {
    if (!state.markers || !(DATA.policy_events || []).length) return { shapes: [], annotations: [] };
    const shapes = [], annotations = [];
    const labels = !(id && isNarrow(id));   // half-width charts keep the hairlines, drop the labels
    let i = 0;
    for (const e of DATA.policy_events) {
      if (!years.includes(e.year)) continue;
      const x = categorical ? years.indexOf(e.year) - 0.5 : e.year - 0.5;
      shapes.push({ type: "line", xref: "x", yref: "paper", x0: x, x1: x, y0: 0, y1: 1, line: { color: t.ink3, width: 1 }, layer: "below" });
      if (labels) annotations.push({ xref: "x", yref: "paper", x, y: 1 - 0.07 * (i % 2), xanchor: "left", yanchor: "top", xshift: 4, text: e.short, showarrow: false,
        font: { color: t.ink3, size: 10 }, bgcolor: t.surface, opacity: 0.95, hovertext: e.label + (e.detail ? " — " + e.detail : ""), captureevents: true });
      i++;
    }
    return { shapes, annotations };
  }
  function partialYearShapes(t, years, categorical) {
    const partial = (DATA.partial_years || []).filter((y) => years.includes(y));
    if (!partial.length) return { shapes: [], annotations: [] };
    let x0, x1;
    if (categorical) { const idx = partial.map((y) => years.indexOf(y)); x0 = Math.min(...idx) - 0.5; x1 = Math.max(...idx) + 0.5; }
    else { x0 = Math.min(...partial) - 0.5; x1 = Math.max(...partial) + 0.5; }
    return {
      shapes: [{ type: "rect", xref: "x", yref: "paper", x0, x1, y0: 0, y1: 1, fillcolor: t.surface2, opacity: 0.7, line: { width: 0 }, layer: "below" }],
      annotations: [{ xref: "x", yref: "paper", x: (x0 + x1) / 2, y: 1, yanchor: "bottom", text: "incomplete", showarrow: false, font: { color: t.ink3, size: 11 } }],
    };
  }
  /** Stacked-by-year bars for ordered classes; classes = [{key,label,sum(counts)->n,neutral}], denomFn(counts)->n. */
  function stackedByYear(opts) {
    const t = tokens();
    const years = yearsInRange();
    const agg = aggregateDiscipline(focusDisc());
    const denoms = years.map((y) => (agg.byYear.get(y) ? opts.denomFn(agg.byYear.get(y)) : 0));
    if (!agg.applicable || !denoms.some((v) => v > 0)) { plot(opts.id, [], {}); renderTable(opts.tableId, [], [], {}); return null; }
    const colors = ramp(opts.classes.length - (opts.classes.some((c) => c.neutral) ? 1 : 0) <= 3 ? RAMP3 : RAMP5);
    const traces = [], shares = {}, counts = {};
    let ci = 0;
    opts.classes.forEach((c) => {
      const color = c.neutral ? t.neutral : colors[Math.min(ci++, colors.length - 1)];
      counts[c.key] = years.map((y) => (agg.byYear.get(y) ? c.sum(agg.byYear.get(y)) : 0));
      shares[c.key] = years.map((y, i) => (denoms[i] >= MIN_N_RATE ? counts[c.key][i] / denoms[i] : null));
      const dark = !c.neutral && ci <= 3;
      traces.push({
        type: "bar", name: c.label, x: years.map(String), y: shares[c.key], customdata: counts[c.key],
        marker: { color, line: { color: t.surface, width: 2 } },
        text: shares[c.key].map((v) => (v !== null && v >= 0.08 ? fmtPct(v, 0) : "")),
        textposition: "inside", insidetextanchor: "middle", insidetextfont: { color: dark ? "#ffffff" : "#0b0b0b", size: 11 },
        hovertemplate: "<b>%{y:.1%}</b> · %{customdata:,} papers<extra>" + c.label + "</extra>",
      });
    });
    const layout = baseLayout(t);
    const partial = partialYearShapes(t, years, true);
    Object.assign(layout, {
      barmode: "stack", bargap: 0.34, margin: { l: 52, r: 16, t: 20, b: 86 },
      legend: Object.assign(layout.legend, { y: -0.2, traceorder: "normal" }),
      yaxis: Object.assign(layout.yaxis, { tickformat: ".0%", range: [0, 1.0001] }),
      xaxis: Object.assign(layout.xaxis, { type: "category", tickvals: years.filter((y, i) => i % tickStep(opts.id, years.length) === 0).map(String), tickangle: 0 }),
      shapes: partial.shapes.concat(policyMarkers(t, years, true, opts.id).shapes), annotations: partial.annotations.concat(policyMarkers(t, years, true, opts.id).annotations), uniformtext: { mode: "hide", minsize: 10 },
    });
    plot(opts.id, traces, layout);
    const cols = [{ key: "cat", label: "Class" }].concat(years.map((y) => ({ key: "y" + y, label: String(y), fmt: "pct" })));
    const rows = opts.classes.map((c) => { const o = { cat: c.label }; years.forEach((y, i) => { o["y" + y] = shares[c.key][i]; }); return o; });
    rows.push(Object.assign({ cat: "n (denominator)" }, Object.fromEntries(years.map((y, i) => ["y" + y, denoms[i]]))));
    renderTable(opts.tableId, cols, rows, { sortable: false, rowFmt: (row) => (row.cat === "n (denominator)" ? "int" : null) });
    return { denomTotal: denoms.reduce((a, b) => a + b, 0) };
  }

  // ------------------------------------------------------------------ render dispatch
  function renderAll() {
    writeHash();
    const d = focusDisc();
    const note = [];
    if (state.slice.kind && (state.slice.kind === "funder" || state.slice.kind === "income")) {
      note.push("Slicing by " + (state.slice.kind === "funder" ? "funder" : "income group") + ": journal and country breakdowns are discipline-wide for this slice.");
    }
    if (state.slice.kind === "funder") note.push("A paper counts once under each listed funder.");
    if (state.hi) note.push("High-impact: " + (DATA.high_impact && DATA.high_impact.description ? DATA.high_impact.description : "journal IF or top citation decile."));
    $("filter-note").textContent = note.join(" ");
    const r = { overview: renderOverview, trends: renderTrends, oa: renderOa, das: renderDas, equity: renderEquity,
      commitment: renderCommitment, journals: renderJournals, geo: renderGeo, methods: renderMethods }[state.view];
    if (r) r(d);
  }

  // ------------------------------------------------------------------ Overview
  function renderOverview(d) {
    const agg = aggregateDiscipline(d);
    const c = agg.total;
    const t = tokens();
    const hero = $("hero");
    hero.replaceChildren();
    const oa = rate(c, "oa"), onReq = rate(c, "das_on_request"), dep = rate(c, "das_deposit");
    hero.append(
      el("div", { class: "hero-left" }, [el("div", { class: "hero-label", text: "Open access · " + d.label }), el("div", { class: "hero-value", text: fmtPct(oa) })]),
      el("p", { class: "hero-text", text: agg.applicable
        ? fmtInt(c[K.n]) + " journal articles and reviews (" + selectionLabel() + "). " + (onReq !== null
          ? "Among " + fmtInt(c[K.das_audited]) + " audited open-access full texts, " + fmtPct(onReq) + " say the data are available on request and " + fmtPct(dep) + " point to a deposited or public dataset."
          : "Run the data-availability audit to see what full texts say.")
        : "This slice is not available for " + d.label + "." }));

    const tiles = $("tiles");
    tiles.replaceChildren();
    const mk = (label, value, sub, frac, na) => {
      const tile = el("div", { class: "tile" + (na ? " is-na" : "") }, [el("div", { class: "tile-label", text: label }), el("div", { class: "tile-value", text: value }), el("div", { class: "tile-sub", text: sub })]);
      if (frac !== null && frac !== undefined) {
        const bar = el("div", { class: "tile-bar" }, el("span"));
        bar.firstChild.style.width = clamp(frac * 100, 0, 100) + "%";
        bar.style.setProperty("--c", discColor(d));
        tile.append(bar);
      }
      return tile;
    };
    for (const key of ["data", "code", "preprint", "reg", "das_stmt", "das_deposit", "ft_github", "ft_reg"]) {
      const m = metric(key);
      const available = metricAvailable(d, key);
      const r = available ? rate(c, m) : null;
      const sub = !available ? "not in this dataset" : fmtInt(numer(c, m)) + " of " + fmtInt(denom(c, m)) + (m.denominator === "das_audited" ? " audited" : m.denominator === "n_abs" ? " with abstract" : "");
      tiles.append(mk(m.short, fmtPct(r), sub, r, r === null));
    }

    // OA trend: emphasis form (focus in colour, others in neutral)
    const years = yearsInRange();
    const traces = [], ann = [];
    for (const x of selectedDiscs()) {
      const a = aggregateDiscipline(x);
      if (!a.applicable) continue;
      const ys = years.map((y) => rate(a.byYear.get(y), "oa"));
      if (ys.every((v) => v === null)) continue;
      const focus = x.key === d.key;
      traces.push({ type: "scatter", mode: "lines+markers", name: x.label, x: years, y: ys, connectgaps: false,
        line: { color: focus ? discColor(x) : t.neutral, width: 2 }, marker: { size: 8, color: focus ? discColor(x) : t.neutral, line: { color: t.surface, width: 2 } },
        opacity: focus ? 1 : 0.8, hovertemplate: "<b>%{y:.1%}</b><extra>" + x.label + "</extra>" });
      let last = ys.length - 1; while (last >= 0 && ys[last] === null) last--;
      if (last >= 0 && focus) ann.push({ x: years[last], y: ys[last], xanchor: "left", xshift: 8, text: x.label, showarrow: false, font: { color: t.ink, size: 12 } });
    }
    const layout = baseLayout(t);
    const partial = partialYearShapes(t, years, false);
    Object.assign(layout, { showlegend: traces.length >= 2, hovermode: "x unified", margin: { l: 48, r: 96, t: 20, b: 60 },
      yaxis: Object.assign(layout.yaxis, { tickformat: ".0%", rangemode: "tozero" }),
      xaxis: Object.assign(layout.xaxis, { dtick: tickStep("ov-trend-chart", years.length), range: [years[0] - 0.6, years[years.length - 1] + 0.4] }),
      annotations: ann.concat(partial.annotations, policyMarkers(t, years, false, "ov-trend-chart").annotations), shapes: partial.shapes.concat(policyMarkers(t, years, false, "ov-trend-chart").shapes) });
    plot("ov-trend-chart", traces, layout);
    $("ov-trend-sub").textContent = d.label + " highlighted; other selected disciplines in grey. " + selectionLabel() + ".";

    // DAS five classes by year (focus)
    const res = stackedByYear({ id: "ov-das-chart", tableId: "ov-das-table-none", classes: dasClasses("five", "audited"), denomFn: (x) => x[K.das_audited] });
    $("ov-das-sub").textContent = res ? "Primary class of the data-availability statement in " + fmtInt(res.denomTotal) + " audited open-access full texts · " + d.label + "." : "No audited full texts in this selection.";

    // Full text vs abstract table
    const rows = [];
    for (const x of selectedDiscs()) {
      const a = aggregateDiscipline(x);
      if (!a.applicable) continue;
      rows.push({ label: x.label, n: a.total[K.das_audited], code_abs: rate(a.total, "code"), code_ft: rate(a.total, "ft_github"), reg_abs: rate(a.total, "reg"), reg_ft: rate(a.total, "ft_reg"), stmt: rate(a.total, "das_stmt") });
    }
    renderTable("ov-ft-table", [
      { key: "label", label: "Discipline" }, { key: "n", label: "Audited full texts", fmt: "int" },
      { key: "code_abs", label: "Code link in abstract/metadata", fmt: "pct" }, { key: "code_ft", label: "GitHub in full text", fmt: "pct" },
      { key: "reg_abs", label: "Registration in abstract", fmt: "pct" }, { key: "reg_ft", label: "Registration in full text", fmt: "pct" },
      { key: "stmt", label: "Has data statement", fmt: "pct" },
    ], rows, { sortable: false });
  }

  // ------------------------------------------------------------------ Trends
  function renderTrends(d) {
    const t = tokens();
    const years = yearsInRange();
    const m = metric(state.metric);
    const asCount = state.trendShow === "count";
    const series = [];   // {label, color, byYear}
    if (state.trendCompare === "disciplines") {
      for (const x of selectedDiscs()) {
        if (!metricAvailable(x, m.key)) continue;
        const a = aggregateDiscipline(x);
        if (a.applicable) series.push({ label: x.label, color: discColor(x), byYear: a.byYear, focus: x.key === d.key });
      }
    } else if (state.trendCompare === "income") {
      const colors = ramp(RAMP4);
      (DATA.income_order || []).forEach((g, i) => {
        const idx = (d.income_groups || []).indexOf(g);
        if (idx < 0) return;
        const byYear = new Map();
        for (const row of d.income_cells || []) {
          if (row[0] < state.yearMin || row[0] > state.yearMax || (state.hi && row[1] !== 1) || row[2] !== idx) continue;
          let acc = byYear.get(row[0]); if (!acc) { acc = emptyCounts(); byYear.set(row[0], acc); }
          addRow(acc, row, DIM_OFFSET);
        }
        series.push({ label: (DATA.income_labels || {})[g] || g, color: colors[i], byYear, focus: false });
      });
    } else {
      const saved = state.hi;
      for (const [hi, label, color] of [[false, "All papers", t.neutral], [true, "High-impact", discColor(d)]]) {
        state.hi = hi;
        const a = aggregateDiscipline(d);
        if (a.applicable) series.push({ label, color, byYear: a.byYear, focus: hi });
      }
      state.hi = saved;
    }
    const traces = [], ann = [], tableRows = [];
    for (const s of series) {
      const ys = years.map((y) => (asCount ? (s.byYear.get(y) ? numer(s.byYear.get(y), m) : null) : rate(s.byYear.get(y), m)));
      const ns = years.map((y) => (s.byYear.get(y) ? denom(s.byYear.get(y), m) : 0));
      if (ys.every((v) => v === null)) continue;
      traces.push({ type: "scatter", mode: "lines+markers", name: s.label, x: years, y: ys, customdata: ns, connectgaps: false,
        line: { color: s.color, width: s.focus ? 3 : 2 }, marker: { size: s.focus ? 9 : 8, color: s.color, line: { color: t.surface, width: 2 } },
        hovertemplate: (asCount ? "<b>%{y:,}</b>" : "<b>%{y:.1%}</b>") + " · n = %{customdata:,}<extra>" + s.label + "</extra>" });
      let last = ys.length - 1; while (last >= 0 && ys[last] === null) last--;
      if (last >= 0 && series.length <= 2) ann.push({ x: years[last], y: ys[last], xanchor: "left", xshift: 8, text: s.label, showarrow: false, font: { color: t.ink2, size: 12 } });
      tableRows.push({ label: s.label, ys });
    }
    const layout = baseLayout(t);
    const partial = partialYearShapes(t, years, false);
    const ymax = Math.max(0, ...traces.flatMap((tr) => tr.y.filter((v) => v !== null)));
    const pctFmt = ymax < 0.02 ? ".2%" : ymax < 0.1 ? ".1%" : ".0%";
    Object.assign(layout, { showlegend: traces.length >= 2, hovermode: "x unified", margin: { l: 60, r: series.length <= 2 ? 120 : 24, t: 20, b: 60 },
      yaxis: Object.assign(layout.yaxis, { tickformat: asCount ? ",.0f" : pctFmt, rangemode: "tozero", title: { text: asCount ? m.label + " (papers)" : m.label, font: { color: t.ink3, size: 12 } } }),
      xaxis: Object.assign(layout.xaxis, { dtick: tickStep("trend-chart", years.length), range: [years[0] - 0.6, years[years.length - 1] + 0.4] }),
      annotations: ann.concat(partial.annotations, policyMarkers(t, years, false).annotations), shapes: partial.shapes.concat(policyMarkers(t, years, false).shapes) });
    plot("trend-chart", traces, layout);
    $("trend-title").textContent = m.label + " by year";
    $("trend-sub").textContent = m.definition + " Selection: " + selectionLabel() + ". Points with fewer than " + MIN_N_RATE + " papers are omitted." + (state.trendCompare !== "disciplines" ? " Focus discipline: " + d.label + "." : "");
    const cols = [{ key: "label", label: "Series" }].concat(years.map((y) => ({ key: "y" + y, label: String(y), fmt: asCount ? "int" : "pct" })));
    renderTable("trend-table", cols, tableRows.map((r) => { const o = { label: r.label }; years.forEach((y, i) => { o["y" + y] = r.ys[i]; }); return o; }), { sortable: false });
  }

  // ------------------------------------------------------------------ Open access
  function oaClasses(grouping) {
    if (grouping === "status") return DATA.oa_status_order.map((s) => ({ key: s, label: s[0].toUpperCase() + s.slice(1), sum: (c) => c[K["oa_" + s]], neutral: s === "closed" }));
    return OA_ROUTES.map((r) => ({ key: r.key, label: r.label, sum: (c) => r.statuses.reduce((s, st) => s + c[K["oa_" + st]], 0), neutral: !!r.neutral }));
  }
  function renderOa(d) {
    const classes = oaClasses(state.oaGrouping);
    const res = stackedByYear({ id: "oa-chart", tableId: "oa-table", classes, denomFn: oaKnown });
    $("oa-title").textContent = (state.oaGrouping === "status" ? "Open-access status by year · " : "Open-access route by year · ") + d.label;
    $("oa-sub").textContent = res ? "Share of papers with a known OpenAlex status (" + fmtInt(res.denomTotal) + "). " + selectionLabel() + ". Free to author = diamond or green; APC = gold or hybrid." : "No OA-status data for this selection.";
    // Routes by discipline: horizontal stacked bars
    const t = tokens();
    const discs = selectedDiscs().map((x) => ({ x, a: aggregateDiscipline(x) })).filter((o) => o.a.applicable && oaKnown(o.a.total) >= MIN_N_RATE);
    const colors = ramp(RAMP3);
    const traces = [];
    let ci = 0;
    for (const c of classes) {
      const color = c.neutral ? t.neutral : (state.oaGrouping === "status" ? ramp(RAMP5)[Math.min(ci, 4)] : colors[Math.min(ci, 2)]);
      if (!c.neutral) ci++;
      const vals = discs.map((o) => c.sum(o.a.total) / oaKnown(o.a.total));
      traces.push({ type: "bar", orientation: "h", name: c.label, y: discs.map((o) => o.x.label), x: vals, customdata: discs.map((o) => c.sum(o.a.total)),
        marker: { color, line: { color: t.surface, width: 2 } }, width: 0.5,
        text: vals.map((v) => (v >= 0.08 ? fmtPct(v, 0) : "")), textposition: "inside", insidetextanchor: "middle", insidetextfont: { color: c.neutral || ci > 3 ? "#0b0b0b" : "#ffffff", size: 11 },
        hovertemplate: "<b>%{x:.1%}</b> · %{customdata:,} papers<extra>" + c.label + " · %{y}</extra>" });
    }
    const layout = baseLayout(t);
    Object.assign(layout, { barmode: "stack", height: Math.max(220, 56 * discs.length + 110), margin: { l: 10, r: 16, t: 12, b: 70 },
      yaxis: { automargin: true, tickfont: { color: t.ink2, size: 12 }, fixedrange: true, gridcolor: "rgba(0,0,0,0)", autorange: "reversed" },
      xaxis: Object.assign(layout.xaxis, { tickformat: ".0%", range: [0, 1.0001], gridcolor: t.grid }), legend: Object.assign(layout.legend, { y: -0.3, traceorder: "normal" }), uniformtext: { mode: "hide", minsize: 10 } });
    plot("oa-disc-chart", discs.length ? traces : [], layout);
    $("oa-disc-sub").textContent = "Pooled over the selection (" + selectionLabel() + "); papers with a known status only.";
    renderTable("oa-disc-table", [{ key: "label", label: "Discipline" }, { key: "n", label: "Known status", fmt: "int" }].concat(classes.map((c) => ({ key: c.key, label: c.label, fmt: "pct" }))),
      discs.map((o) => Object.assign({ label: o.x.label, n: oaKnown(o.a.total) }, Object.fromEntries(classes.map((c) => [c.key, c.sum(o.a.total) / oaKnown(o.a.total)])))), { sortable: false });
  }

  // ------------------------------------------------------------------ Data statements
  function dasClasses(grouping, denominator) {
    const neutralOut = denominator === "stmt";
    if (grouping === "eight") return DATA.das_order.filter((c) => !(neutralOut && c === "no_statement")).map((c) => ({ key: c, label: (DATA.das_labels || {})[c] || c, sum: (x) => x[K["das_" + c]], neutral: c === "no_statement" }));
    return DAS_FIVE.filter((c) => !(neutralOut && c.neutral)).map((c) => ({ key: c.key, label: c.label, sum: (x) => c.cats.reduce((s, k) => s + x[K["das_" + k]], 0), neutral: !!c.neutral }));
  }
  function renderDas(d) {
    const denomFn = state.dasDenominator === "stmt" ? ((x) => x[K.das_stmt]) : ((x) => x[K.das_audited]);
    const classes = dasClasses(state.dasGrouping, state.dasDenominator);
    let res = null;
    if (state.dasGrouping === "eight") res = smallMultiplesByYear({ id: "das-chart", tableId: "das-table", classes, denomFn });
    else res = stackedByYear({ id: "das-chart", tableId: "das-table", classes, denomFn });
    $("das-title").textContent = "Data-availability statements by year · " + d.label;
    $("das-sub").textContent = res
      ? "Primary class of the statement in " + fmtInt(res.denomTotal) + (state.dasDenominator === "stmt" ? " audited articles that have a statement" : " audited open-access full texts") + " (Europe PMC sample). " + selectionLabel() + "." + (state.dasGrouping === "eight" ? " One panel per category, same scale." : "")
      : "No audited papers in this selection.";
    // By discipline: grouped bars of signals
    const t = tokens();
    const sig = [["das_stmt", "Has statement"], ["das_deposit", "Deposited / public source"], ["das_on_request", "On request"], ["ft_github", "GitHub in full text"], ["ft_reg", "Registration in full text"]];
    const discs = selectedDiscs().map((x) => ({ x, a: aggregateDiscipline(x) })).filter((o) => o.a.applicable && o.a.total[K.das_audited] >= MIN_N_RATE);
    const traces = discs.map((o) => ({ type: "bar", name: o.x.label, x: sig.map((s) => s[1]), y: sig.map((s) => rate(o.a.total, s[0])), customdata: sig.map(() => o.a.total[K.das_audited]),
      marker: { color: discColor(o.x), line: { color: t.surface, width: 2 } }, hovertemplate: "<b>%{y:.1%}</b> · n audited = %{customdata:,}<extra>" + o.x.label + "</extra>" }));
    const layout = baseLayout(t);
    Object.assign(layout, { barmode: "group", bargap: 0.3, bargroupgap: 0.08, margin: { l: 52, r: 16, t: 12, b: 70 }, yaxis: Object.assign(layout.yaxis, { tickformat: ".0%", rangemode: "tozero" }), legend: Object.assign(layout.legend, { y: -0.22 }) });
    plot("das-disc-chart", discs.length ? traces : [], layout);
    $("das-disc-sub").textContent = "Audited open-access full texts, pooled over the selection (" + selectionLabel() + "). Optimistic relative to each whole corpus.";
    renderTable("das-disc-table", [{ key: "label", label: "Discipline" }, { key: "n", label: "Audited", fmt: "int" }].concat(sig.map((s) => ({ key: s[0], label: s[1], fmt: "pct" }))),
      discs.map((o) => Object.assign({ label: o.x.label, n: o.a.total[K.das_audited] }, Object.fromEntries(sig.map((s) => [s[0], rate(o.a.total, s[0])])))), { sortable: false });
  }
  /** One small panel per class (single hue), shared y scale: the honest form for > 7 classes. */
  function smallMultiplesByYear(opts) {
    const t = tokens();
    const years = yearsInRange();
    const agg = aggregateDiscipline(focusDisc());
    const denoms = years.map((y) => (agg.byYear.get(y) ? opts.denomFn(agg.byYear.get(y)) : 0));
    if (!agg.applicable || !denoms.some((v) => v > 0)) { plot(opts.id, [], {}); renderTable(opts.tableId, [], [], {}); return null; }
    const n = opts.classes.length, cols = isNarrow(opts.id) ? 2 : 4, rowsN = Math.ceil(n / cols);
    const traces = [], annotations = [], layout = baseLayout(t);
    let ymax = 0;
    const shares = {};
    opts.classes.forEach((c, i) => {
      shares[c.key] = years.map((y, k) => (denoms[k] >= MIN_N_RATE ? c.sum(agg.byYear.get(y)) / denoms[k] : null));
      ymax = Math.max(ymax, ...shares[c.key].filter((v) => v !== null));
    });
    opts.classes.forEach((c, i) => {
      const ax = i === 0 ? "" : String(i + 1);
      const r = Math.floor(i / cols), col = i % cols;
      const xd = [col / cols + 0.02, (col + 1) / cols - 0.02], yd = [1 - (r + 1) / rowsN + 0.06, 1 - r / rowsN - 0.08];
      traces.push({ type: "scatter", mode: "lines+markers", x: years, y: shares[c.key], xaxis: "x" + ax, yaxis: "y" + ax, name: c.label, showlegend: false, connectgaps: false,
        line: { color: c.neutral ? t.neutral : t.accent, width: 2 }, marker: { size: 6, color: c.neutral ? t.neutral : t.accent, line: { color: t.surface, width: 2 } },
        hovertemplate: "<b>%{y:.1%}</b> · %{x}<extra>" + c.label + "</extra>" });
      layout["xaxis" + ax] = { domain: xd, anchor: "y" + ax, gridcolor: "rgba(0,0,0,0)", linecolor: t.border, tickfont: { color: t.ink3, size: 10 }, fixedrange: true, dtick: Math.max(1, Math.round(years.length / 3)), zeroline: false };
      layout["yaxis" + ax] = { domain: yd, anchor: "x" + ax, gridcolor: t.grid, tickfont: { color: t.ink3, size: 10 }, fixedrange: true, tickformat: ".0%", range: [0, ymax * 1.15 || 1], zeroline: false, showticklabels: col === 0 };
      annotations.push({ xref: "paper", yref: "paper", x: (xd[0] + xd[1]) / 2, y: yd[1] + 0.015, xanchor: "center", yanchor: "bottom", text: c.label, showarrow: false, font: { color: t.ink2, size: 11 } });
    });
    Object.assign(layout, { showlegend: false, height: Math.max(320, 170 * rowsN), margin: { l: 44, r: 10, t: 10, b: 30 }, annotations, hovermode: "closest" });
    plot(opts.id, traces, layout);
    const colsT = [{ key: "cat", label: "Category" }].concat(years.map((y) => ({ key: "y" + y, label: String(y), fmt: "pct" })));
    const rows = opts.classes.map((c) => { const o = { cat: c.label }; years.forEach((y, i) => { o["y" + y] = shares[c.key][i]; }); return o; });
    rows.push(Object.assign({ cat: "n (denominator)" }, Object.fromEntries(years.map((y, i) => ["y" + y, denoms[i]]))));
    renderTable(opts.tableId, colsT, rows, { sortable: false, rowFmt: (row) => (row.cat === "n (denominator)" ? "int" : null) });
    return { denomTotal: denoms.reduce((a, b) => a + b, 0) };
  }

  // ------------------------------------------------------------------ Equity
  function incomeAggregates(d) {
    const out = [];
    const groups = aggregateBy(d, "income");
    (DATA.income_order || []).forEach((g, i) => {
      const idx = (d.income_groups || []).indexOf(g);
      const c = idx >= 0 ? groups.get(idx) : null;
      if (c) out.push({ key: g, label: (DATA.income_labels || {})[g] || g, counts: c, color: ramp(RAMP4)[i] });
    });
    return out;
  }
  function renderEquity(d) {
    const t = tokens();
    const tiles = $("equity-tiles");
    tiles.replaceChildren();
    const groups = d.available.income ? incomeAggregates(d) : [];
    if (!groups.length) {
      tiles.append(el("div", { class: "tile is-na" }, [el("div", { class: "tile-label", text: "Income group" }), el("div", { class: "tile-value", text: "—" }), el("div", { class: "tile-sub", text: "first_author_income_group is not in this dataset" })]));
      plot("eq-route-chart", [], {}); plot("eq-ft-chart", [], {}); renderTable("eq-route-table", [], [], {}); renderTable("eq-ft-table", [], [], {});
      $("eq-route-sub").textContent = ""; $("eq-ft-sub").textContent = "";
      return;
    }
    const totalN = groups.reduce((s, g) => s + g.counts[K.n], 0);
    for (const g of groups) {
      const share = g.counts[K.n] / totalN;
      const tile = el("div", { class: "tile" }, [el("div", { class: "tile-label", text: g.label }), el("div", { class: "tile-value", text: fmtPct(share) }), el("div", { class: "tile-sub", text: fmtInt(g.counts[K.n]) + " papers · OA " + fmtPct(rate(g.counts, "oa")) })]);
      const bar = el("div", { class: "tile-bar" }, el("span")); bar.firstChild.style.width = clamp(share * 100, 0, 100) + "%"; bar.style.setProperty("--c", g.color); tile.append(bar);
      tiles.append(tile);
    }
    const labels = groups.map((g) => g.label + "\n(n=" + fmtInt(g.counts[K.n]) + ")");
    if (state.eqSignal === "route") {
      const classes = oaClasses("route");
      const traces = [];
      const colors = ramp(RAMP3);
      let ci = 0;
      for (const c of classes) {
        const color = c.neutral ? t.neutral : colors[ci++];
        const vals = groups.map((g) => (oaKnown(g.counts) >= MIN_N_RATE ? c.sum(g.counts) / oaKnown(g.counts) : null));
        traces.push({ type: "bar", name: c.label, x: labels, y: vals, customdata: groups.map((g) => c.sum(g.counts)), marker: { color, line: { color: t.surface, width: 2 } }, width: 0.6,
          text: vals.map((v) => (v !== null && v >= 0.08 ? fmtPct(v, 0) : "")), textposition: "inside", insidetextanchor: "middle", insidetextfont: { color: c.neutral || ci > 2 ? "#0b0b0b" : "#ffffff", size: 11 },
          hovertemplate: "<b>%{y:.1%}</b> · %{customdata:,} papers<extra>" + c.label + "</extra>" });
      }
      const layout = baseLayout(t);
      Object.assign(layout, { barmode: "stack", margin: { l: 52, r: 16, t: 12, b: 100 }, yaxis: Object.assign(layout.yaxis, { tickformat: ".0%", range: [0, 1.0001] }), xaxis: Object.assign(layout.xaxis, { type: "category" }), legend: Object.assign(layout.legend, { y: -0.3, traceorder: "normal" }), uniformtext: { mode: "hide", minsize: 10 } });
      plot("eq-route-chart", traces, layout);
      $("eq-route-title").textContent = "Who pays to be read · open-access route by first-author income group · " + d.label;
      $("eq-route-sub").textContent = "Share of papers with a known OpenAlex status. Free to author = diamond or green; APC = gold or hybrid. " + selectionLabel() + ".";
      renderTable("eq-route-table", [{ key: "label", label: "Income group" }, { key: "n", label: "Papers", fmt: "int" }].concat(classes.map((c) => ({ key: c.key, label: c.label, fmt: "pct" }))),
        groups.map((g) => Object.assign({ label: g.label, n: g.counts[K.n] }, Object.fromEntries(classes.map((c) => [c.key, oaKnown(g.counts) ? c.sum(g.counts) / oaKnown(g.counts) : null])))), { sortable: false });
    } else {
      const m = metric(state.eqSignal);
      const vals = groups.map((g) => rate(g.counts, m));
      const traces = [{ type: "bar", name: m.label, x: labels, y: vals, customdata: groups.map((g) => denom(g.counts, m)), marker: { color: groups.map((g) => g.color), line: { color: t.surface, width: 2 } }, width: 0.5,
        text: vals.map((v) => fmtPct(v, 1)), textposition: "outside", textfont: { color: t.ink2, size: 12 }, hovertemplate: "<b>%{y:.1%}</b> · n = %{customdata:,}<extra>" + m.label + "</extra>" }];
      const layout = baseLayout(t);
      Object.assign(layout, { showlegend: false, margin: { l: 52, r: 16, t: 24, b: 70 }, yaxis: Object.assign(layout.yaxis, { tickformat: ".0%", rangemode: "tozero" }), xaxis: Object.assign(layout.xaxis, { type: "category" }) });
      plot("eq-route-chart", vals.some((v) => v !== null) ? traces : [], layout);
      $("eq-route-title").textContent = m.label + " by first-author income group · " + d.label;
      $("eq-route-sub").textContent = m.definition + " " + selectionLabel() + ".";
      renderTable("eq-route-table", [{ key: "label", label: "Income group" }, { key: "n", label: "Denominator", fmt: "int" }, { key: "v", label: m.label, fmt: "pct" }],
        groups.map((g, i) => ({ label: g.label, n: denom(g.counts, m), v: vals[i] })), { sortable: false });
    }
    // Full-text signals grouped by income group
    const sig = [["das_stmt", "Has statement"], ["das_deposit", "Deposited / public source"], ["das_on_request", "On request"], ["ft_github", "GitHub in full text"], ["ft_reg", "Registration in full text"]];
    const audited = groups.filter((g) => g.counts[K.das_audited] >= MIN_N_RATE);
    const traces = audited.map((g) => ({ type: "bar", name: g.label, x: sig.map((s) => s[1]), y: sig.map((s) => rate(g.counts, s[0])), customdata: sig.map(() => g.counts[K.das_audited]),
      marker: { color: g.color, line: { color: t.surface, width: 2 } }, hovertemplate: "<b>%{y:.1%}</b> · n audited = %{customdata:,}<extra>" + g.label + "</extra>" }));
    const layout2 = baseLayout(t);
    Object.assign(layout2, { barmode: "group", bargap: 0.3, bargroupgap: 0.08, margin: { l: 52, r: 16, t: 12, b: 70 }, yaxis: Object.assign(layout2.yaxis, { tickformat: ".0%", rangemode: "tozero" }), legend: Object.assign(layout2.legend, { y: -0.22 }) });
    plot("eq-ft-chart", audited.length && d.available.das ? traces : [], layout2);
    $("eq-ft-title").textContent = "Sharing in the full text, by first-author income group · " + d.label;
    $("eq-ft-sub").textContent = d.available.das ? "Audited open-access full texts only (Europe PMC sample); groups with fewer than " + MIN_N_RATE + " audited papers are omitted. " + selectionLabel() + "." : "No data-availability audit in this dataset.";
    renderTable("eq-ft-table", [{ key: "label", label: "Income group" }, { key: "n", label: "Audited", fmt: "int" }].concat(sig.map((s) => ({ key: s[0], label: s[1], fmt: "pct" }))),
      groups.map((g) => Object.assign({ label: g.label, n: g.counts[K.das_audited] }, Object.fromEntries(sig.map((s) => [s[0], rate(g.counts, s[0])])))), { sortable: false });
  }

  // ------------------------------------------------------------------ Commitment
  function signalRate(counts, s) {
    const d = counts[K[s.denominator]] || 0;
    if (!d) return null;
    return s.numerators.reduce((a, k) => a + (counts[K[k]] || 0), 0) / d;
  }
  function renderCommitment(d) {
    const t = tokens();
    const entity = state.cmEntity;
    const signals = (DATA.commitment_signals || []).filter((s) => state.cmSignals.includes(s.key));
    const base = baselineCounts(d);
    const baseRates = signals.map((s) => signalRate(base, s) || 0);
    const dimOf = { institutions: "institution", journals: "journal", funders: "funder", countries: "country" }[entity];
    const list = { institutions: d.institutions || [], journals: d.journals, funders: d.funders, countries: d.countries }[entity];
    const available = { institutions: d.available.institutions, journals: true, funders: d.available.funders, countries: d.available.country }[entity] && d.available.das;
    const items = [];
    if (available) {
      const groups = aggregateBy(d, dimOf);
      for (const [idx, c] of groups.entries()) {
        const item = list[idx];
        if (!item) continue;
        const key = item.key || item;
        if (key === "Other" || key === "(no institution listed)" || key === "(no funder listed)") continue;
        const nAud = c[K.das_audited];
        if (nAud < state.cmMin) continue;
        const rates = signals.map((s) => signalRate(c, s));
        const ratios = rates.map((r, i) => (baseRates[i] > 0 ? (r || 0) / baseRates[i] : 0));
        const label = entity === "countries" ? (item.label || key) : (item.label || key);
        items.push({ label, n: c[K.n], n_audited: nAud, index: ratios.reduce((a, b) => a + b, 0) / Math.max(1, ratios.length),
          das_deposit: signalRate(c, (DATA.commitment_signals || [])[0]), ft_github: rate(c, "ft_github"), ft_reg: rate(c, "ft_reg"), on_request: rate(c, "das_on_request"), stmt: rate(c, "das_stmt") });
      }
    }
    items.sort((a, b) => b.index - a.index || b.n_audited - a.n_audited);
    const top = items.slice(0, state.cmTop);
    const labels = top.map((i) => i.label.length > 44 ? i.label.slice(0, 42) + "…" : i.label).reverse();
    const traces = top.length ? [
      { type: "bar", orientation: "h", x: top.map((i) => i.index).reverse(), y: labels, customdata: top.map((i) => [i.n_audited, i.das_deposit, i.ft_github, i.ft_reg]).reverse(),
        marker: { color: discColor(d), line: { color: t.surface, width: 2 } }, width: 0.55, name: "commitment index",
        text: top.map((i) => fmtX(i.index)).reverse(), textposition: "outside", textfont: { color: t.ink2, size: 11 }, cliponaxis: false,
        hovertemplate: "<b>%{x:.1f}×</b> the " + d.label + " average · %{customdata[0]:,} audited<br>deposit %{customdata[1]:.1%} · GitHub %{customdata[2]:.1%} · registration %{customdata[3]:.1%}<extra>%{y}</extra>" },
    ] : [];
    const layout = baseLayout(t);
    const xmax = Math.max(3, ...top.map((i) => i.index)) * 1.18;
    Object.assign(layout, { showlegend: false, height: Math.max(240, 26 * top.length + 90), margin: { l: 10, r: 40, t: 24, b: 44 },
      yaxis: { automargin: true, tickfont: { color: t.ink2, size: 12 }, fixedrange: true, gridcolor: "rgba(0,0,0,0)" },
      xaxis: Object.assign(layout.xaxis, { gridcolor: t.grid, range: [0, xmax], title: { text: "commitment index (1 = " + d.label + " average)", font: { color: t.ink3, size: 12 } } }),
      shapes: [{ type: "line", xref: "x", yref: "paper", x0: 1, x1: 1, y0: 0, y1: 1, line: { color: t.ink3, width: 1 } }],
      annotations: [{ xref: "x", yref: "paper", x: 1, y: 1.02, yanchor: "bottom", text: "average", showarrow: false, font: { color: t.ink3, size: 11 } }] });
    plot("cm-chart", traces, layout);
    const entityLabel = { institutions: "institutions (credit to any author)", journals: "journals", funders: "funders", countries: "first-author countries" }[entity];
    $("cm-title").textContent = "Most committed " + entityLabel + " · " + d.label;
    $("cm-sub").textContent = available
      ? "Index = mean over the selected verified full-text signals of (entity rate ÷ " + d.label + " rate); " + signals.map((s, i) => s.label + " " + fmtPct(baseRates[i], 1)).join(", ") + " discipline-wide. At least " + state.cmMin + " audited articles; " + items.length + " qualify. " + selectionLabel() + "."
      : "This view needs the data-availability audit" + (entity === "institutions" ? " and the institutions column" : "") + " in the dataset.";
    renderTable("cm-table", [
      { key: "label", label: entity === "countries" ? "Country" : entity === "funders" ? "Funder" : entity === "journals" ? "Journal" : "Institution" },
      { key: "n_audited", label: "Audited", fmt: "int" }, { key: "n", label: "Papers", fmt: "int" },
      { key: "index", label: "Index", fmt: "x", bar: true }, { key: "das_deposit", label: "Deposit / public source", fmt: "pct" },
      { key: "ft_github", label: "GitHub (full text)", fmt: "pct" }, { key: "ft_reg", label: "Registration (full text)", fmt: "pct" },
      { key: "on_request", label: "On request", fmt: "pct" }, { key: "stmt", label: "Has statement", fmt: "pct" },
    ], items, { sortable: true, color: discColor(d), name: "commitment", defaultSort: { key: "index", dir: "desc" }, barKey: "index" });
  }

  // ------------------------------------------------------------------ Journals
  function renderJournals(d) {
    const t = tokens();
    const m = metric(state.journalMetric);
    const groups = aggregateBy(d, "journal");
    const items = [];
    for (const [idx, c] of groups.entries()) {
      const j = d.journals[idx];
      if (!j || j.key === "Other" || c[K.n] < state.journalMin) continue;
      const row = { label: j.label, n: c[K.n], v: rate(c, m) };
      for (const x of METRICS) row[x.key] = metricAvailable(d, x.key) ? rate(c, x) : null;
      items.push(row);
    }
    const plotted = items.filter((i) => i.v !== null).sort((a, b) => b.v - a.v).slice(0, state.journalTop);
    const labels = plotted.map((i) => i.label.length > 44 ? i.label.slice(0, 42) + "…" : i.label).reverse();
    const traces = plotted.length ? [{ type: "bar", orientation: "h", x: plotted.map((i) => i.v).reverse(), y: labels, customdata: plotted.map((i) => denom(groups.get(d.journals.findIndex((j) => j.label === i.label)) || emptyCounts(), m)).reverse(),
      marker: { color: discColor(d), line: { color: t.surface, width: 2 } }, width: 0.55, name: m.label,
      text: plotted.map((i) => fmtPct(i.v, m.key === "oa" ? 0 : 1)).reverse(), textposition: "outside", textfont: { color: t.ink2, size: 11 }, cliponaxis: false,
      hovertemplate: "<b>%{x:.1%}</b> · n = %{customdata:,}<extra>%{y}</extra>" }] : [];
    const layout = baseLayout(t);
    const xmax = Math.max(0.0001, ...plotted.map((i) => i.v)) * 1.2;
    Object.assign(layout, { showlegend: false, height: Math.max(240, 26 * plotted.length + 90), margin: { l: 10, r: 48, t: 12, b: 44 },
      yaxis: { automargin: true, tickfont: { color: t.ink2, size: 12 }, fixedrange: true, gridcolor: "rgba(0,0,0,0)" },
      xaxis: Object.assign(layout.xaxis, { gridcolor: t.grid, tickformat: ".0%", range: [0, Math.min(1.05, xmax)], title: { text: m.label, font: { color: t.ink3, size: 12 } } }) });
    plot("journal-chart", traces, layout);
    $("journal-title").textContent = "Journals by " + m.label.toLowerCase() + " · " + d.label;
    $("journal-sub").textContent = items.length ? plotted.length + " of " + items.length + " journals with at least " + state.journalMin + " papers (" + selectionLabel() + "). Top-" + (DATA.top_n.journals || "") + " journals by volume only; the table carries every metric." : "No journal reaches " + state.journalMin + " papers under this selection.";
    const cols = [{ key: "label", label: "Journal" }, { key: "n", label: "Papers", fmt: "int" }].concat(METRICS.filter((x) => x.key !== "material" && metricAvailable(d, x.key)).map((x) => ({ key: x.key, label: x.short, fmt: "pct", bar: x.key === m.key })));
    renderTable("journal-table", cols, items, { sortable: true, color: discColor(d), name: "journals", defaultSort: { key: m.key, dir: "desc" }, barKey: m.key });
  }

  // ------------------------------------------------------------------ Countries & funders
  function dimRows(d, groups, list, labelOf) {
    const rows = [];
    for (const [idx, c] of groups.entries()) {
      const item = list[idx];
      if (!item) continue;
      const row = { label: labelOf(item), other: (item.key || item) === "Other" || item === "(no funder listed)", n: c[K.n] };
      for (const m of METRICS) row[m.key] = metricAvailable(d, m.key) ? rate(c, m) : null;
      rows.push(row);
    }
    return rows;
  }
  function dimCols(d, first) {
    return [{ key: "label", label: first }, { key: "n", label: "Papers", fmt: "int" }]
      .concat(METRICS.filter((m) => m.key !== "material" && metricAvailable(d, m.key)).map((m) => ({ key: m.key, label: m.short, fmt: "pct", bar: m.key === "oa" })));
  }
  function renderGeo(d) {
    $("country-card").hidden = !d.available.country;
    $("funder-card").hidden = !d.available.funders;
    if (d.available.country) {
      const rows = dimRows(d, aggregateBy(d, "country"), d.countries, (c) => (c.key === "Other" ? "Other countries" : c.label));
      $("country-title").textContent = "First-author countries · " + d.label;
      $("country-sub").textContent = "Top-" + (DATA.top_n.countries || "") + " first-author countries by volume; " + selectionLabel() + (state.slice.kind === "country" ? " (country slice ignored here)" : "") + ". Click a column to sort; full-text columns use audited papers as denominator.";
      renderTable("country-table", dimCols(d, "Country"), rows, { sortable: true, color: discColor(d), name: "countries", barKey: "oa" });
    }
    if (d.available.funders) {
      const rows = dimRows(d, aggregateBy(d, "funder"), d.funders, (f) => (f === "Other" ? "Other funders" : f));
      $("funder-title").textContent = "Funders · " + d.label;
      $("funder-sub").textContent = "Top-" + (DATA.top_n.funders || "") + " funders by volume (a paper counts once under each listed funder); " + (state.hi ? "high-impact papers" : "all papers") + ", " + state.yearMin + "–" + state.yearMax + ". Journal, country and income slices do not apply here.";
      renderTable("funder-table", dimCols(d, "Funder"), rows, { sortable: true, color: discColor(d), name: "funders", barKey: "oa" });
    }
  }

  // ------------------------------------------------------------------ tables
  function renderTable(containerId, cols, rows, opts) {
    const container = $(containerId);
    if (!container) return;
    container.replaceChildren();
    if (!cols.length || !rows.length) return;
    const o = Object.assign({ sortable: false, color: null, name: containerId, rowFmt: null, defaultSort: { key: "n", dir: "desc" }, barKey: "oa" }, opts);
    let sortKey = null, sortDir = "desc";
    if (o.sortable) {
      const saved = state.sort[o.name] || o.defaultSort;
      sortKey = saved.key; sortDir = saved.dir;
      rows = rows.slice().sort((a, b) => {
        const va = a[sortKey], vb = b[sortKey];
        if (va === null || va === undefined) return 1;
        if (vb === null || vb === undefined) return -1;
        if (typeof va === "string") return sortDir === "asc" ? va.localeCompare(vb) : vb.localeCompare(va);
        return sortDir === "asc" ? va - vb : vb - va;
      });
    }
    const table = el("table", { class: "data" });
    const thead = el("thead"), tr = el("tr");
    for (const c of cols) {
      const th = el("th", { scope: "col" });
      if (o.sortable) {
        th.setAttribute("aria-sort", c.key === sortKey ? (sortDir === "asc" ? "ascending" : "descending") : "none");
        const btn = el("button", { type: "button" }, [el("span", { text: c.label }), el("span", { class: "sort-ind", "aria-hidden": "true" })]);
        btn.addEventListener("click", () => {
          const dir = c.key === sortKey ? (sortDir === "asc" ? "desc" : "asc") : (c.key === "label" ? "asc" : "desc");
          state.sort[o.name] = { key: c.key, dir };
          renderAll();
        });
        th.append(btn);
      } else th.textContent = c.label;
      tr.append(th);
    }
    thead.append(tr); table.append(thead);
    const tbody = el("tbody");
    const maxBar = Math.max(0.0001, ...rows.map((r) => (typeof r[o.barKey] === "number" ? r[o.barKey] : 0)));
    for (const r of rows) {
      const row = el("tr", { class: r.other ? "is-other" : null });
      const forced = o.rowFmt ? o.rowFmt(r) : null;
      for (const c of cols) {
        const v = r[c.key];
        const fmt = forced || c.fmt;
        const text = fmt === "pct" ? fmtPct(v) : fmt === "int" ? fmtInt(v) : fmt === "x" ? fmtX(v) : (v === null || v === undefined ? "—" : String(v));
        const td = el("td", { text });
        if (c.bar && typeof v === "number" && o.color) {
          td.classList.add("bar-cell");
          const bar = el("span", { class: "bar", "aria-hidden": "true" });
          bar.style.width = clamp(v / maxBar * 100, 0, 100) + "%";
          bar.style.setProperty("--c", o.color);
          td.prepend(bar);
        }
        row.append(td);
      }
      tbody.append(row);
    }
    table.append(tbody);
    container.append(table);
  }

  // ------------------------------------------------------------------ CSV + link
  function downloadCsv() {
    const years = yearsInRange();
    const header = ["discipline", "year", "subset", "slice"].concat(DATA.count_keys).concat(METRICS.map((m) => m.key + "_rate"));
    const lines = [header.join(",")];
    const q = (s) => '"' + String(s).replace(/"/g, '""') + '"';
    for (const d of selectedDiscs()) {
      const agg = aggregateDiscipline(d);
      if (!agg.applicable) continue;
      for (const y of years) {
        const c = agg.byYear.get(y);
        if (!c) continue;
        const rates = METRICS.map((m) => { const dn = denom(c, m); return dn ? (numer(c, m) / dn).toFixed(4) : ""; });
        lines.push([d.key, y, state.hi ? "high_impact" : "all", q(state.slice.kind ? state.slice.kind + ":" + state.slice.key : "all")].concat(c).concat(rates).join(","));
      }
    }
    const blob = new Blob([lines.join("\n") + "\n"], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: "open_science_selection_" + DATA.run_date + ".csv" });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function copyLink() {
    writeHash();
    const btn = $("share-btn");
    const done = () => { btn.textContent = "Link copied"; setTimeout(() => { btn.textContent = "Copy link"; }, 1600); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(location.href).then(done, () => window.prompt("Copy this link", location.href));
    else window.prompt("Copy this link", location.href);
  }

  // ------------------------------------------------------------------ Methods + footer
  function renderMethods() {
    const body = $("methods-body");
    body.replaceChildren();
    body.append(el("h3", { text: "Metric definitions" }));
    const dl = el("dl");
    for (const m of METRICS) dl.append(el("dt", { text: m.label }), el("dd", { text: m.definition }));
    dl.append(el("dt", { text: "OA route" }), el("dd", { text: "Free to author = OpenAlex diamond or green; APC paid = gold or hybrid; bronze = free to read without a licence; closed. Shares use papers with a known status as the denominator." }));
    dl.append(el("dt", { text: "Data-availability statement classes" }), el("dd", { text: "Five ordered classes for the chart: deposited or public source (repository, public_source); controlled or restricted; on request; in article or supplement; not available or unclear (not_available_or_na, other_or_unclear); plus no statement. The eight underlying categories are available as small multiples and in every table." }));
    dl.append(el("dt", { text: "Commitment index" }), el("dd", { text: "For an institution, journal, funder or first-author country: the mean over the selected verified full-text signals (data deposited or public source in the statement; GitHub mentioned in the full text; trial registration mentioned in the full text) of the entity's rate divided by the discipline-wide rate under the same selection. 1.0 is the discipline average. Only entities with at least the chosen number of audited articles are ranked; small counts are noisy." }));
    dl.append(el("dt", { text: "Income group" }), el("dd", { text: "World Bank classification of the first author's country (high, upper-middle, lower-middle, low), from the pipeline's country-income configuration; unknown when the country is missing or unclassified." }));
    dl.append(el("dt", { text: "High-impact subset" }), el("dd", { text: (DATA.high_impact && DATA.high_impact.description) || "" }));
    if ((DATA.policy_events || []).length) dl.append(el("dt", { text: "Policy markers" }), el("dd", { text: DATA.policy_events.map((e) => e.year + ": " + e.label).join(". ") + ". Drawn at the start of the year on the trend and by-year charts; hover a label for the detail." }));
    body.append(dl);
    body.append(el("h3", { text: "Corpus" }));
    const ul1 = el("ul");
    for (const d of DATA.disciplines) ul1.append(el("li", { text: d.label + ": " + fmtInt(d.totals.in_corpus) + " articles/reviews kept of " + fmtInt(d.totals.rows_in_file) + " retrieved records (" + fmtInt(d.totals.dropped) + " excluded; rule: " + (DATA.corpus_rule[d.key] || "n/a") + "). Years " + d.years[0] + "–" + d.years[d.years.length - 1] + "." }));
    body.append(ul1);
    body.append(el("h3", { text: "Reading notes" }));
    const ul2 = el("ul");
    for (const n of DATA.methods_notes) ul2.append(el("li", { text: n }));
    ul2.append(el("li", { text: "Rates are not drawn for cells with fewer than " + MIN_N_RATE + " papers. Colours: one blue ramp for ordered classes (darkest = most open), a neutral grey for closed / no statement, and one fixed colour per discipline; every chart has a table twin." }));
    body.append(ul2);
    body.append(el("h3", { text: "How this page works" }));
    body.append(el("p", { class: "card-sub", text: "The pipeline writes pre-aggregated counts (discipline × year × high-impact × journal × first-author country; plus × funder, × first-author income group and × institution) to dashboard_data.json; this page sums the counts for your selection and divides. No row-level data is shipped. The address bar carries the full selection, so a link reproduces the view. Generated " + DATA.generated_at + "." }));
  }
  function renderFooter() {
    const f = $("footer-body");
    f.replaceChildren();
    const cit = DATA.citation || {};
    f.append(el("p", {}, ["Benchmark run date: ", el("strong", { text: DATA.run_date }), ". Source code: ", el("a", { href: DATA.repo_url, rel: "noopener", text: DATA.repo_url.replace(/^https?:\/\//, "") }),
      " · Data and legacy dashboard: ", el("a", { href: DATA.outputs_repo_url, rel: "noopener", text: DATA.outputs_repo_url.replace(/^https?:\/\//, "") }), " · ", el("a", { href: "legacy.html", text: "static version" })]));
    if (cit.title) f.append(el("p", {}, ["Cite: ", el("em", { text: cit.title }), cit.version ? " (v" + cit.version + ")" : "", cit["date-released"] ? ", " + cit["date-released"] : "", ". ", el("a", { href: DATA.repo_url + "/blob/main/CITATION.cff", rel: "noopener", text: "CITATION.cff" }), cit.license ? " · " + cit.license + " licence." : ""]));
    f.append(el("p", {}, ["Data: OpenAlex, Unpaywall, Crossref, Europe PMC, World Bank. Charts: Plotly. ", el("code", { text: "dashboard_data.json" }), " (", el("a", { href: DATA_URL, text: "download" }), ")"]));
  }

  // ------------------------------------------------------------------ theme
  const THEMES = ["auto", "light", "dark"];
  function applyTheme(theme) {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", theme);
    const btn = $("theme-toggle");
    btn.querySelector(".theme-label").textContent = theme[0].toUpperCase() + theme.slice(1);
    btn.querySelector(".theme-icon").textContent = theme === "dark" ? "●" : theme === "light" ? "○" : "◐";
    btn.title = "Theme: " + theme;
    try { localStorage.setItem("osb-theme", theme); } catch (e) { /* storage unavailable */ }
  }
  function initTheme() {
    let theme = "auto";
    try { theme = localStorage.getItem("osb-theme") || "auto"; } catch (e) { /* ignore */ }
    if (!THEMES.includes(theme)) theme = "auto";
    applyTheme(theme);
    $("theme-toggle").addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "auto";
      applyTheme(THEMES[(THEMES.indexOf(current) + 1) % THEMES.length]);
      if (DATA) { buildSelection(); renderAll(); }
    });
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => { if (DATA && !document.documentElement.getAttribute("data-theme")) renderAll(); };
    if (mq.addEventListener) mq.addEventListener("change", onChange); else if (mq.addListener) mq.addListener(onChange);
  }

  // ------------------------------------------------------------------ boot
  async function boot() {
    initTheme();
    let payload;
    try {
      const res = await fetch(DATA_URL, { cache: "no-cache" });
      if (!res.ok) throw new Error(res.status + " " + res.statusText);
      payload = await res.json();
    } catch (err) {
      const e = $("error"); e.hidden = false;
      e.textContent = "Could not load " + DATA_URL + " (" + err.message + "). Serve this folder over HTTP (e.g. python -m http.server) — browsers block fetch() from file://.";
      return;
    }
    DATA = payload;
    DATA.count_keys.forEach((k, i) => { K[k] = i; });
    if (!DATA.disciplines.length) { $("error").hidden = false; $("error").textContent = "No disciplines in the data file."; return; }
    buildMetrics();
    resetState();
    readHash();
    buildTabs();
    buildSelection();
    buildViewOptions();
    renderMethods();
    renderFooter();
    showView(state.view);
    renderAll();
    window.addEventListener("hashchange", () => { readHash(); buildSelection(); buildViewOptions(); showView(state.view); renderAll(); });
  }
  let resizeTimer = null;
  window.addEventListener("resize", () => { if (!DATA) return; clearTimeout(resizeTimer); resizeTimer = setTimeout(renderAll, 200); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
