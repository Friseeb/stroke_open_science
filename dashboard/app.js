/* Stroke Open-Science Benchmark — audit report card (schema v2 payload).
 * Loads dashboard_data.json (pre-aggregated counts) and recomputes every rate client-side for the
 * current selection. One scrolling page: a selection line, the indicator matrix, then figures with
 * captions (trends, data statements, income groups, rankings) and methods. Charts are drawn by
 * charts.js (D3). No server, no build step. */
(function () {
  "use strict";

  const DATA_URL = "dashboard_data.json";
  const MIN_N_RATE = 10;          // below this many papers a rate is not drawn (the cell still shows n)
  // Row layout, read from DATA.cell_keys / income_keys at boot: [year, hi, trial, journal, country, ...counts] and
  // [year, hi, trial, <dim>, ...counts] for the funder / income / institution tables (no trial column before schema 3).
  let CELL_OFFSET = 4;
  let DIM_OFFSET = 3;
  let POS = { trial: -1, journal: 2, country: 3, dim: 2 };

  const VIEWS = [
    ["s1", "Indicators"], ["s2", "Trends"], ["s3", "Data statements"],
    ["s4", "Income groups"], ["s5", "Rankings"], ["s6", "Methods"],
  ];

  // Validated categorical set (light surface #f1f1ef): stroke carries the page accent. Payload colours are
  // overridden by key so older data files render in the same palette; unknown disciplines keep theirs.
  const DISC_COLORS = { stroke: "#d7263d", neurology: "#2a78d6", neuroscience: "#1baf7a", cardiology: "#eda100" };
  // Dark-mode steps of the same hues (validated against #141414).
  const DARK_SERIES = { "#d7263d": "#e8475b", "#2a78d6": "#3987e5", "#eb6834": "#d95926", "#1baf7a": "#199e70", "#eda100": "#c98500",
    "#7b61c9": "#9085e9", "#c04d8c": "#d55181", "#5c7f8f": "#7fa3b3", "#8a7a3a": "#b3a05a" };
  // Ordinal blue ramps (validated), darkest = most open.
  const RAMP5 = { light: ["#0d366b", "#1c5cab", "#2a78d6", "#5598e7", "#86b6ef"], dark: ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4"] };
  const RAMP3 = { light: ["#0d366b", "#2a78d6", "#86b6ef"], dark: ["#184f95", "#3987e5", "#9ec5f4"] };
  const RAMP4 = { light: ["#0d366b", "#1c5cab", "#5598e7", "#86b6ef"], dark: ["#184f95", "#256abf", "#6da7ec", "#9ec5f4"] };

  const OA_ROUTES = [
    { key: "free", label: "Free to author (diamond, green)", statuses: ["diamond", "green"], status: "green" },
    { key: "paid", label: "APC paid (gold, hybrid)", statuses: ["gold", "hybrid"], status: "gold" },
    { key: "bronze", label: "Bronze (free to read, no licence)", statuses: ["bronze"], status: "bronze" },
    { key: "closed", label: "Closed", statuses: ["closed"], neutral: true },
  ];
  // Open-access statuses wear their names' colours (validated as a categorical set on both surfaces; green↔hybrid sits in
  // the 6–8 CVD band, covered by the 2 px gaps, the key row and the labels). Closed is the neutral grey.
  const OA_COLORS = {
    light: { diamond: "#5598e7", gold: "#eda100", hybrid: "#c04d8c", green: "#1baf7a", bronze: "#9a5a1f" },
    dark: { diamond: "#4f95e8", gold: "#c98500", hybrid: "#d85fa3", green: "#199e70", bronze: "#8f4e2b" },
  };
  const oaColor = (status) => (isDark() ? OA_COLORS.dark : OA_COLORS.light)[status] || null;
  const DAS_FIVE = [
    { key: "deposit", label: "Deposited or public source", cats: ["repository", "public_source"] },
    { key: "controlled", label: "Controlled or restricted", cats: ["controlled_or_restricted"] },
    { key: "on_request", label: "On request", cats: ["on_request"] },
    { key: "in_article", label: "In article or supplement", cats: ["in_article"] },
    { key: "na", label: "Not available or unclear", cats: ["not_available_or_na", "other_or_unclear"] },
    { key: "none", label: "No statement", cats: ["no_statement"], neutral: true },
  ];

  // The report card: two groups of rows, in this order.
  const CARD_GROUPS = [
    { label: "From titles, abstracts and metadata · denominator: all papers (registration: papers with an abstract)", keys: ["oa", "data", "code", "reg", "preprint"] },
    { label: "From the full text · denominator: audited open-access articles (Europe PMC sample)", keys: ["das_stmt", "das_deposit", "das_on_request", "ft_github", "ft_reg"] },
  ];
  const CARD_LABELS = { oa: "Open access", data: "Data in a repository", code: "Code link", reg: "Registration signal", preprint: "Preprint version",
    das_stmt: "Data-availability statement", das_deposit: "Data deposited or public source", das_on_request: "Data on request", ft_github: "GitHub in full text", ft_reg: "Trial registration in full text" };
  const CARD_DEFS = { oa: "OpenAlex status is not closed", data: "Dataset in a public repository or a data-repository link", code: "GitHub or code-repository link",
    reg: "Trial-registry ID, PROSPERO or preregistration wording", preprint: "Preprint version among OpenAlex locations",
    das_stmt: "A statement is present", das_deposit: "Statement names a repository deposit or a public dataset", das_on_request: "Statement says the data are available on request",
    ft_github: "github.com anywhere in the text", ft_reg: "Registry ID or clinicaltrials.gov anywhere in the text" };
  const PILL_LABELS = { oa: "Open access", data: "Data", code: "Code", material: "Any repository", reg: "Registration", preprint: "Preprint",
    das_stmt: "Statement", das_deposit: "Deposit", das_on_request: "On request", ft_github: "GitHub", ft_reg: "Registration (full text)" };
  const FIG_ORDER = ["trend", "oa", "hi", "bb", "das", "das-disc", "eq", "eq-ft", "t4", "cm", "journal"];
  const TABLE_ORDER = ["report", "ft", "country", "funder"];

  let DATA = null;
  const K = {};                   // count key -> index within the counts part of a row
  let METRICS = [];               // client metric defs: {key, label, short, definition, numerators, denominator}
  const state = {
    view: "s1",
    disciplines: [], focus: null, yearMin: null, yearMax: null,
    slice: { kind: "", key: "" }, hi: false, design: "all",
    metric: "oa", trendShow: "rate", trendLayout: "overlay", metricIncome: "oa",
    oaGrouping: "route", dasGrouping: "five", dasDenominator: "audited",
    eqSignal: "route", cmEntity: "institutions", cmMin: 50, cmTop: 15, cmSignals: ["das_deposit", "ft_github", "ft_reg"],
    journalMetric: "oa", journalMin: 100, journalTop: 25,
    markers: true,
    // chart forms (every figure offers at least two)
    oaMode: "bars", dasMode: "bars", hiMode: "lines", ftdMode: "dots", eqMode: "bars", t4Layout: "overlay", cmMode: "dots", journalMode: "dots",
    // bubbles through the years
    bbEntity: "countries", bbX: "oa", bbY: "das_stmt", bbTrails: "on", bbYear: null, bbPlaying: false,
    sort: {},
  };
  const FORM_KEYS = ["oaMode", "dasMode", "hiMode", "ftdMode", "eqMode", "t4Layout", "cmMode", "journalMode", "bbEntity", "bbX", "bbY", "bbTrails"];
  const PREV_VALS = new Map();    // last rendered big figures, so a selection change counts up from the previous value

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
    const d = digits !== undefined ? digits : (v > 0 && v < 0.001 ? 2 : v < 0.1 ? 1 : 0);
    return (v * 100).toFixed(d) + "%";
  };
  const fmtX = (v) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : v.toFixed(1) + "×";
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const isDark = () => getComputedStyle(document.documentElement).colorScheme.trim() === "dark";
  const ramp = (r) => (isDark() ? r.dark : r.light);
  const seriesColor = (hex) => (isDark() ? (DARK_SERIES[hex] || hex) : hex);
  const prettyDate = (iso, long) => (iso ? new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: long ? "long" : "short", year: "numeric", timeZone: "UTC" }) : "");

  function discByKey(key) { return DATA.disciplines.find((d) => d.key === key); }
  function focusDisc() { return discByKey(state.focus); }
  function selectedDiscs() { return DATA.disciplines.filter((d) => state.disciplines.includes(d.key)); }
  function yearsInRange() { return DATA.years.filter((y) => y >= state.yearMin && y <= state.yearMax); }
  function discColor(d) { return seriesColor(DISC_COLORS[d.key] || d.color); }

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
  const metricOrNull = (key) => METRICS.find((m) => m.key === key) || null;
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
    if (kind === "funder") return { rows: disc.funder_cells, offset: DIM_OFFSET, pos: POS.dim };
    if (kind === "income") return { rows: disc.income_cells || [], offset: DIM_OFFSET, pos: POS.dim };
    if (kind === "institution") return { rows: disc.institution_cells || [], offset: DIM_OFFSET, pos: POS.dim };
    return { rows: disc.cells, offset: CELL_OFFSET, pos: kind === "country" ? POS.country : POS.journal };
  }
  const hasDesign = () => POS.trial >= 0;
  /** The filters every table shares: year range, high-impact subset and study design (trials or other studies). */
  function keepRow(row) {
    if (row[0] < state.yearMin || row[0] > state.yearMax) return false;
    if (state.hi && row[1] !== 1) return false;
    if (state.design !== "all" && hasDesign() && row[POS.trial] !== (state.design === "trial" ? 1 : 0)) return false;
    return true;
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
      if (!keepRow(row)) continue;
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
    const slicePos = state.slice.kind === "country" ? POS.country : POS.journal;
    if (idx === -1) return groups;
    for (const row of t.rows) {
      const year = row[0];
      if (!keepRow(row)) continue;
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
      if (!keepRow(row)) continue;
      addRow(total, row, CELL_OFFSET);
    }
    return total;
  }
  /** Per-entity by-year counts for a dimension: Map<entityIdx, Map<year, counts>> under the current selection. */
  function aggregateByYearFor(disc, dim) {
    const groups = new Map();
    const t = tableFor(disc, dim);
    const sameTable = (dim === "journal" || dim === "country") && (state.slice.kind === "journal" || state.slice.kind === "country") && state.slice.kind !== dim;
    const idx = sameTable ? sliceIndex(disc) : null;
    const slicePos = state.slice.kind === "country" ? POS.country : POS.journal;
    if (idx === -1) return groups;
    for (const row of t.rows) {
      const year = row[0];
      if (!keepRow(row)) continue;
      if (idx !== null && row[slicePos] !== idx) continue;
      let byYear = groups.get(row[t.pos]);
      if (!byYear) { byYear = new Map(); groups.set(row[t.pos], byYear); }
      let acc = byYear.get(year);
      if (!acc) { acc = emptyCounts(); byYear.set(year, acc); }
      addRow(acc, row, t.offset);
    }
    return groups;
  }
  const seriesFromByYear = (byYear, m) => yearsInRange().map((y) => rate(byYear.get(y), m));

  // ------------------------------------------------------------------ sparklines (word-sized graphics, inline SVG)
  const SVG_NS = "http://www.w3.org/2000/svg";
  function svgEl(tag, attrs) { const n = document.createElementNS(SVG_NS, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); return n; }
  /** values: array of numbers or null (gaps); draws a baseline, a faint area, the line and an emphasised last point. */
  function sparkline(values, color) {
    const w = 100, h = 28, pad = 3;
    const svg = svgEl("svg", { class: "spark", viewBox: "0 0 " + w + " " + h, preserveAspectRatio: "none", "aria-hidden": "true" });
    if (color) svg.style.setProperty("--c", color);
    const pts = values.map((v, i) => (v === null || v === undefined || Number.isNaN(v)) ? null : [i, v]).filter(Boolean);
    if (pts.length < 2) return svg;
    const n = values.length, max = Math.max(...pts.map((p) => p[1]), 1e-9);
    const x = (i) => pad + (i / Math.max(1, n - 1)) * (w - 2 * pad);
    const y = (v) => h - pad - (v / max) * (h - 2 * pad);
    svg.append(svgEl("line", { class: "spark-base", x1: pad, x2: w - pad, y1: h - pad + 0.5, y2: h - pad + 0.5 }));
    const d = pts.map((p, k) => (k === 0 ? "M" : "L") + x(p[0]).toFixed(1) + " " + y(p[1]).toFixed(1)).join(" ");
    svg.append(svgEl("path", { class: "spark-area", d: d + " L" + x(pts[pts.length - 1][0]).toFixed(1) + " " + (h - pad) + " L" + x(pts[0][0]).toFixed(1) + " " + (h - pad) + " Z" }));
    svg.append(svgEl("path", { class: "spark-line", d, "vector-effect": "non-scaling-stroke" }));
    const last = pts[pts.length - 1];
    svg.append(svgEl("circle", { class: "spark-end", cx: x(last[0]).toFixed(1), cy: y(last[1]).toFixed(1), r: 2.6, "vector-effect": "non-scaling-stroke" }));
    return svg;
  }

  // ------------------------------------------------------------------ URL state
  const HASH_KEYS = ["view", "focus", "hi", "design", "metric", "trendShow", "trendLayout", "metricIncome", "oaGrouping", "dasGrouping", "dasDenominator",
    "eqSignal", "cmEntity", "cmMin", "cmTop", "journalMetric", "journalMin", "journalTop", "markers"].concat(FORM_KEYS);
  function writeHash() {
    const p = new URLSearchParams();
    for (const k of HASH_KEYS) p.set(k, String(state[k]));
    p.set("years", state.yearMin + "-" + state.yearMax);
    p.set("disc", state.disciplines.join(","));
    if (state.slice.kind) p.set("slice", state.slice.kind + ":" + state.slice.key);
    p.set("cmSignals", state.cmSignals.join(","));
    if (state.bbYear) p.set("bbYear", String(state.bbYear));
    history.replaceState(null, "", "#" + p.toString());
  }
  function readHash() {
    const h = location.hash.replace(/^#/, "");
    if (!h) return;
    if (/^s[1-6]$/.test(h)) { state.view = h; return; }   // a plain anchor
    const p = new URLSearchParams(h);
    const allDisc = DATA.disciplines.map((d) => d.key);
    const disc = (p.get("disc") || "").split(",").filter((k) => allDisc.includes(k));
    if (disc.length) state.disciplines = allDisc.filter((k) => disc.includes(k));
    if (p.get("focus") && state.disciplines.includes(p.get("focus"))) state.focus = p.get("focus");
    const yrs = (p.get("years") || "").split("-").map(Number);
    if (yrs.length === 2 && yrs.every((y) => DATA.years.includes(y)) && yrs[0] <= yrs[1]) { state.yearMin = yrs[0]; state.yearMax = yrs[1]; }
    if (p.get("hi") === "true") state.hi = true;
    if (["trial", "other"].includes(p.get("design"))) state.design = p.get("design");
    if (p.get("markers") === "false") state.markers = false;
    const slice = (p.get("slice") || "").split(":");
    if (slice.length >= 2 && ["journal", "country", "funder", "income"].includes(slice[0])) state.slice = { kind: slice[0], key: slice.slice(1).join(":") };
    for (const k of ["view", "metric", "trendShow", "trendLayout", "metricIncome", "oaGrouping", "dasGrouping", "dasDenominator", "eqSignal", "cmEntity", "journalMetric"].concat(FORM_KEYS)) {
      if (p.get(k) && /^[a-z]+$/.test(p.get(k))) state[k] = p.get(k);
    }
    for (const k of ["cmMin", "cmTop", "journalMin", "journalTop"]) if (p.get(k) && !Number.isNaN(+p.get(k))) state[k] = +p.get(k);
    if (p.get("bbYear") && DATA.years.includes(+p.get("bbYear"))) state.bbYear = +p.get("bbYear");
    for (const k of ["bbX", "bbY"]) if (!METRICS.some((m) => m.key === state[k])) state[k] = k === "bbX" ? "oa" : "das_stmt";
    const sig = (p.get("cmSignals") || "").split(",").filter(Boolean);
    if (sig.length) state.cmSignals = sig;
    if (!VIEWS.some((v) => v[0] === state.view)) state.view = "s1";
    for (const k of ["metric", "metricIncome", "journalMetric"]) if (!METRICS.some((m) => m.key === state[k])) state[k] = "oa";
  }
  function resetState() {
    state.disciplines = DATA.disciplines.map((d) => d.key);
    state.focus = state.disciplines.includes("stroke") ? "stroke" : state.disciplines[0];
    const dflt = Array.isArray(DATA.default_year_range) && DATA.default_year_range.length === 2 ? DATA.default_year_range : DATA.years;
    state.yearMin = dflt[0]; state.yearMax = dflt[dflt.length - 1];
    state.slice = { kind: "", key: "" }; state.hi = false; state.design = "all";
    state.metric = "oa"; state.trendShow = "rate"; state.trendLayout = "overlay"; state.metricIncome = "oa";
    state.oaGrouping = "route"; state.dasGrouping = "five"; state.dasDenominator = "audited"; state.eqSignal = "route";
    state.cmEntity = "institutions"; state.cmMin = 50; state.cmTop = 15; state.cmSignals = ["das_deposit", "ft_github", "ft_reg"];
    state.journalMetric = "oa"; state.journalMin = 100; state.journalTop = 25;
    state.markers = true;
    Object.assign(state, { oaMode: "bars", dasMode: "bars", hiMode: "lines", ftdMode: "dots", eqMode: "bars", t4Layout: "overlay", cmMode: "dots", journalMode: "dots",
      bbEntity: "countries", bbX: "oa", bbY: "das_stmt", bbTrails: "on", bbYear: null, bbPlaying: false });
    stopPlay();
  }

  // ------------------------------------------------------------------ pills (the one control)
  /** Render a pill group. options: [{value,label,color?,title?}]; isOn(value) -> bool; onPick(value). */
  function pills(id, options, isOn, onPick) {
    const c = $(id);
    c.replaceChildren();
    for (const o of options) {
      const on = isOn(o.value);
      const b = el("button", { type: "button", class: "pill" + (on ? " is-on" : ""), "aria-pressed": String(on), title: o.title || null, "data-value": String(o.value) });
      if (o.color) { b.append(el("span", { class: "dot", "aria-hidden": "true" })); b.style.setProperty("--c", o.color); }
      b.append(el("span", { text: o.label }));
      b.addEventListener("click", () => onPick(o.value, b));
      c.append(b);
    }
  }
  const PILL_GROUPS = [];        // single-value groups bound to a state key: {id, key}
  function pillSelect(id, key, options, parse) {
    if (!PILL_GROUPS.some((g) => g.id === id)) PILL_GROUPS.push({ id, key });
    pills(id, options, (v) => String(state[key]) === String(v), (v) => { state[key] = parse ? parse(v) : v; renderAll(); });
  }
  function syncPillGroup(id, isOn) {
    const c = $(id);
    if (!c) return;
    for (const b of c.children) { const on = isOn(b.dataset.value); b.classList.toggle("is-on", on); b.setAttribute("aria-pressed", String(on)); }
  }
  function syncPills() {
    for (const g of PILL_GROUPS) syncPillGroup(g.id, (v) => String(state[g.key]) === v);
    syncPillGroup("disc-pills", (v) => state.disciplines.includes(v));
    syncPillGroup("cm-signals", (v) => state.cmSignals.includes(v));
    syncPillGroup("hi-pills", (v) => (v === "hi") === state.hi);
    syncPillGroup("design-pills", (v) => v === state.design);
    syncYears();
  }

  // ------------------------------------------------------------------ selection line
  function yearPresets() {
    const all = DATA.years;
    const complete = DATA.default_year_range || [all[0], all[all.length - 1]];
    const presets = [
      { label: complete[0] + "–" + complete[1], min: complete[0], max: complete[1] },
      { label: "Since 2020", min: Math.max(all[0], 2020), max: complete[1] },
      { label: "All years", min: all[0], max: all[all.length - 1] },
    ];
    const seen = new Set();
    return presets.filter((p) => p.min <= p.max && !seen.has(p.min + "-" + p.max) && seen.add(p.min + "-" + p.max));
  }
  function buildSelection() {
    // Years: presets plus a custom range row
    const presets = yearPresets();
    pills("year-pills", presets.map((p) => ({ value: p.min + "-" + p.max, label: p.label })).concat([{ value: "custom", label: "Custom" }]),
      (v) => (v === "custom" ? !$("year-custom").hidden : v === state.yearMin + "-" + state.yearMax),
      (v) => {
        if (v === "custom") { const row = $("year-custom"); row.hidden = !row.hidden; syncYears(); if (!row.hidden) $("year-min").focus(); return; }
        const [a, b] = v.split("-").map(Number); state.yearMin = a; state.yearMax = b; $("year-custom").hidden = true; renderAll();
      });
    const yMin = $("year-min"), yMax = $("year-max");
    const lo = DATA.years[0], hi = DATA.years[DATA.years.length - 1];
    for (const inp of [yMin, yMax]) { inp.min = lo; inp.max = hi; }
    const onYear = () => {
      let a = +yMin.value, b = +yMax.value;
      if (a > b) { if (document.activeElement === yMin) b = a; else a = b; }
      state.yearMin = a; state.yearMax = b;
      renderAll();
    };
    yMin.oninput = onYear; yMax.oninput = onYear;
    if (!document.querySelector(".range-fill")) yMin.parentElement.append(el("span", { class: "range-fill", "aria-hidden": "true" }));
    // Papers
    pills("hi-pills", [{ value: "all", label: "All" }, { value: "hi", label: "High-impact" }], (v) => (v === "hi") === state.hi, (v) => { state.hi = v === "hi"; renderAll(); });
    // Study design: trial reports (and their secondary analyses) or every other paper
    $("design-group").hidden = !hasDesign();
    pills("design-pills", [{ value: "all", label: "All" }, { value: "trial", label: "Trials", title: (DATA.study_design || {}).description || null },
      { value: "other", label: "Other studies" }], (v) => v === state.design, (v) => { state.design = v; renderAll(); });
    // Disciplines (multi)
    pills("disc-pills", DATA.disciplines.map((d) => ({ value: d.key, label: d.label, color: discColor(d) })), (v) => state.disciplines.includes(v), (v) => {
      const next = DATA.disciplines.map((x) => x.key).filter((k) => (k === v ? !state.disciplines.includes(k) : state.disciplines.includes(k)));
      if (!next.length) return;
      state.disciplines = next;
      if (!state.disciplines.includes(state.focus)) state.focus = state.disciplines[0];
      buildFocusSelect(); buildSliceSelect(); renderAll();
    });
    buildFocusSelect();
    $("focus-select").onchange = (e) => { state.focus = e.target.value; buildSliceSelect(); renderAll(); };
    buildSliceSelect();
    $("slice-select").onchange = (e) => {
      const v = e.target.value;
      state.slice = v ? { kind: v.split(":")[0], key: v.slice(v.indexOf(":") + 1) } : { kind: "", key: "" };
      renderAll();
    };
    $("reset-btn").onclick = () => { resetState(); $("year-custom").hidden = true; buildSelection(); buildViewOptions(); renderAll(); };
    $("download-btn").onclick = downloadCsv;
    $("share-btn").onclick = copyLink;
    syncYears();
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
    const cur = state.yearMin + "-" + state.yearMax;
    const anyPreset = [...$("year-pills").children].some((b) => b.dataset.value === cur);
    if (!anyPreset) $("year-custom").hidden = false;
    syncPillGroup("year-pills", (v) => (v === "custom" ? !$("year-custom").hidden || !anyPreset : v === cur));
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
    sel.replaceChildren(el("option", { value: "", text: "Everything in " + d.label.toLowerCase() }));
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
    const what = state.design === "trial" ? "trials" : state.design === "other" ? "non-trial papers" : "papers";
    const parts = [(state.hi ? "high-impact " : "all ") + what];
    if (state.slice.kind) parts.push(sliceLabel());
    parts.push(state.yearMin === state.yearMax ? String(state.yearMin) : state.yearMin + "–" + state.yearMax);
    return parts.join(", ");
  }
  function labelFor(list, key) { const item = list.find((x) => x.key === key); return item ? item.label : key; }

  // ------------------------------------------------------------------ navigation
  function buildNav() {
    const nav = $("topnav");
    nav.replaceChildren();
    for (const [key, label] of VIEWS) {
      const a = el("a", { href: "#" + key, text: label, id: "nav-" + key, "aria-current": "false" });
      a.addEventListener("click", (e) => { e.preventDefault(); showView(key, true); writeHash(); });
      nav.append(a);
    }
    nav.append(el("span", { class: "ind", "aria-hidden": "true" }));
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver((entries) => {
        for (const en of entries) if (en.isIntersecting) { state.view = en.target.id; markNav(); }
      }, { rootMargin: "-35% 0px -55% 0px" });
      for (const [k] of VIEWS) io.observe($(k));
    }
  }
  /** Figures rise into view once, on first scroll into the viewport (no motion under prefers-reduced-motion). */
  function observeReveal() {
    const els = document.querySelectorAll(".sec-head, .report, .stat-grid, .fig");
    els.forEach((e) => e.classList.add("reveal"));
    if (!("IntersectionObserver" in window) || Charts.reduced()) { els.forEach((e) => e.classList.add("is-in")); return; }
    const io = new IntersectionObserver((entries) => {
      for (const en of entries) {
        if (!en.isIntersecting) continue;
        const node = en.target;
        node.classList.add("is-in");
        io.unobserve(node);
        if (node.classList.contains("fig")) { const chart = node.querySelector(".chart"); if (chart) Charts.replay(chart); }
        if (node.classList.contains("report") || node.classList.contains("stat-grid")) countUpAll(node);
      }
    }, { rootMargin: "0px 0px -10% 0px" });
    els.forEach((e) => io.observe(e));
  }
  /** Every big figure inside `root` counts up from zero, staggered left to right. */
  function countUpAll(root) {
    const nodes = [...root.querySelectorAll("[data-value]")];
    nodes.forEach((n, i) => {
      const v = parseFloat(n.dataset.value);
      if (Number.isNaN(v)) return;
      const digits = +n.dataset.digits || 0;
      setTimeout(() => Charts.countUp(n, 0, v, (q) => fmtPct(q, digits)), Math.min(i * 35, 700));
    });
  }
  /** The hero title drifts up slower than the page and fades as the reader leaves it. */
  function heroMotion() {
    if (Charts.reduced()) return;
    const hero = document.querySelector(".hero");
    if (!hero) return;
    const parts = [...hero.children];            // title, eyebrow, standfirst and foot move together, so nothing overlaps
    let ticking = false;
    const update = () => {
      ticking = false;
      const y = window.scrollY, h = hero.offsetHeight || 1;
      const k = Math.min(1, y / (h * 0.8));
      for (const p of parts) { p.style.transform = "translateY(" + (y * 0.18).toFixed(1) + "px)"; p.style.opacity = String(1 - k); }
      const title = hero.querySelector(".display");
      if (title) title.style.scale = (1 - 0.2 * k).toFixed(3);          // the title also shrinks as it goes
      hero.style.setProperty("--py", (y * 0.06).toFixed(1) + "px");
    };
    window.addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
    setTimeout(() => { hero.classList.add("is-settled"); update(); }, 1700);   // load animations done: inline transforms take over
    update();
  }
  /** Section titles arrive large (up to 1.9×) and settle to their real size at the reading line (38 % down the
   *  viewport); above the line they stay at 1×. The note beside the title fades in as the title settles. */
  function titleMotion() {
    if (Charts.reduced()) return;
    const titles = [...document.querySelectorAll(".sec-title")];
    if (!titles.length) return;
    let ticking = false;
    const update = () => {
      ticking = false;
      const vh = window.innerHeight || 900, focus = vh * 0.38;
      for (const h of titles) {
        const r = h.getBoundingClientRect();                     // origin is top-left, so r.top is unaffected by the scale
        if (r.bottom < -300 || r.top > vh + 300) continue;
        const p = r.top > focus ? Math.min(1, (r.top - focus) / (vh - focus)) : 0;   // 0 at the line, 1 at the bottom edge
        const e = p * p;
        h.style.scale = (1 + 0.9 * e).toFixed(3);
        const note = h.parentElement && h.parentElement.querySelector(".sec-note");
        if (note) note.style.opacity = (1 - e).toFixed(3);
      }
    };
    const onScroll = () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    update();
  }
  function markNav() {
    for (const [k] of VIEWS) $("nav-" + k).setAttribute("aria-current", String(k === state.view));
    const cur = $("nav-" + state.view), ind = $("topnav").querySelector(".ind");
    if (cur && ind) { ind.style.left = cur.offsetLeft + "px"; ind.style.width = cur.offsetWidth + "px"; }
  }
  function showView(key, scroll) {
    state.view = key;
    markNav();
    const target = $(key);
    if (scroll && target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      setTimeout(() => target.scrollIntoView({ behavior: "auto", block: "start" }), 700);   // again once charts have sized
    }
  }

  // ------------------------------------------------------------------ per-figure options
  function metricOptions(exclude) {
    return METRICS.filter((m) => !(exclude || []).includes(m.key)).map((m) => ({ value: m.key, label: PILL_LABELS[m.key] || m.short, title: m.label }));
  }
  function buildViewOptions() {
    PILL_GROUPS.length = 0;
    pillSelect("trend-metric", "metric", metricOptions(["material"]));
    pillSelect("trend-show", "trendShow", [{ value: "rate", label: "Rate" }, { value: "count", label: "Count" }]);
    const LINE_FORMS = [{ value: "overlay", label: "Lines" }, { value: "panels", label: "Small multiples" }, { value: "slope", label: "Slope" }];
    const STACK_FORMS = [{ value: "bars", label: "Bars" }, { value: "area", label: "Area" }, { value: "panels", label: "Small multiples" }];
    const DOT_FORMS = [{ value: "dots", label: "Dots" }, { value: "bars", label: "Bars" }];
    pillSelect("trend-layout", "trendLayout", LINE_FORMS);
    pillSelect("oa-mode", "oaMode", STACK_FORMS.concat([{ value: "rain", label: "Raincloud" }]));
    pillSelect("bb-entity", "bbEntity", [{ value: "countries", label: "Countries" }, { value: "journals", label: "Journals" }, { value: "disciplines", label: "Disciplines" }]);
    pillSelect("bb-x", "bbX", metricOptions(["material"]));
    pillSelect("bb-y", "bbY", metricOptions(["material"]));
    pillSelect("bb-trails", "bbTrails", [{ value: "on", label: "On" }, { value: "off", label: "Off" }]);
    $("bb-play").onclick = () => { if (state.bbPlaying) stopPlay(); else startPlay(); };
    $("bb-year").oninput = (e) => { stopPlay(); state.bbYear = +e.target.value; renderBubbles(focusDisc(), false); writeHash(); };
    pillSelect("hi-mode", "hiMode", [{ value: "lines", label: "Lines" }, { value: "gap", label: "Gap" }]);
    pillSelect("das-mode", "dasMode", STACK_FORMS);
    pillSelect("ftd-mode", "ftdMode", DOT_FORMS);
    pillSelect("eq-mode", "eqMode", DOT_FORMS);
    pillSelect("t4-layout", "t4Layout", LINE_FORMS);
    pillSelect("cm-mode", "cmMode", DOT_FORMS);
    pillSelect("journal-mode", "journalMode", DOT_FORMS);
    pillSelect("trend-markers", "markers", [{ value: "true", label: "Shown" }, { value: "false", label: "Hidden" }], (v) => v === "true");
    pillSelect("oa-grouping", "oaGrouping", [{ value: "route", label: "Routes" }, { value: "status", label: "Six statuses" }]);
    pillSelect("das-grouping", "dasGrouping", [{ value: "five", label: "Five classes" }, { value: "eight", label: "Eight categories" }]);
    pillSelect("das-denominator", "dasDenominator", [{ value: "audited", label: "All audited" }, { value: "stmt", label: "With a statement" }]);
    pillSelect("eq-signal", "eqSignal", [{ value: "route", label: "OA route" }].concat(metricOptions(["material"])));
    pillSelect("t4-metric", "metricIncome", metricOptions(["material"]));
    pillSelect("cm-entity", "cmEntity", [{ value: "institutions", label: "Institutions" }, { value: "journals", label: "Journals" }, { value: "funders", label: "Funders" }, { value: "countries", label: "Countries" }]);
    pillSelect("cm-min", "cmMin", [30, 50, 100, 200].map((v) => ({ value: v, label: String(v) })), Number);
    pillSelect("cm-top", "cmTop", [10, 15, 25, 40].map((v) => ({ value: v, label: String(v) })), Number);
    const signals = DATA.commitment_signals || [];
    pills("cm-signals", signals.map((s) => ({ value: s.key, label: PILL_LABELS[s.key] || s.label, title: s.label })), (v) => state.cmSignals.includes(v), (v) => {
      const next = signals.map((x) => x.key).filter((k) => (k === v ? !state.cmSignals.includes(k) : state.cmSignals.includes(k)));
      if (!next.length) return;
      state.cmSignals = next; renderAll();
    });
    pillSelect("journal-metric", "journalMetric", metricOptions(["material"]));
    pillSelect("journal-min", "journalMin", [30, 100, 300, 1000].map((v) => ({ value: v, label: v.toLocaleString("en-US") })), Number);
    pillSelect("journal-top", "journalTop", [15, 25, 40].map((v) => ({ value: v, label: String(v) })), Number);
  }

  // ------------------------------------------------------------------ chart helpers (drawing lives in charts.js)
  /** Caption with its figure (or table) number. */
  function caption(id, key, text, isTable) {
    const n = (isTable ? TABLE_ORDER : FIG_ORDER).indexOf(key) + 1;
    $(id).replaceChildren(el("span", { class: "fno", text: (isTable ? "Table " : "Fig. ") + n }), document.createTextNode(text));
  }
  const exportFor = (id) => Charts.exportBar($(id), DATA ? DATA.run_date : "");
  const keyFor = (id, items) => Charts.key($(id), items);
  const milestones = () => (state.markers ? (DATA.policy_events || []) : []);
  const denomText = (m) => (m.denominator === "das_audited" ? "Denominator: audited open-access full texts." : m.denominator === "n_abs" ? "Denominator: papers with an abstract." : "Denominator: all papers.");
  const pctDigits = (v) => (v > 0 && v < 0.001 ? 2 : v < 0.1 ? 1 : 0);
  /** 100%-stacked classes by year for the focus discipline: shares, counts, the chart, its key and its table. */
  function stackedFor(opts) {
    const t = Charts.theme();
    const years = yearsInRange();
    const agg = aggregateDiscipline(focusDisc());
    const denoms = years.map((y) => (agg.byYear.get(y) ? opts.denomFn(agg.byYear.get(y)) : 0));
    const nonNeutral = opts.classes.filter((c) => !c.neutral).length;
    const colors = ramp(nonNeutral <= 3 ? RAMP3 : RAMP5);
    let ci = 0;
    const classes = opts.classes.map((c) => ({ key: c.key, label: c.label, neutral: !!c.neutral, color: c.neutral ? t.neutral : (c.color || colors[Math.min(ci++, colors.length - 1)]), sum: c.sum }));
    const shares = {}, counts = {};
    for (const c of classes) {
      counts[c.key] = years.map((y) => (agg.byYear.get(y) ? c.sum(agg.byYear.get(y)) : 0));
      shares[c.key] = years.map((y, i) => (denoms[i] >= MIN_N_RATE ? counts[c.key][i] / denoms[i] : null));
    }
    const ok = agg.applicable && denoms.some((v) => v > 0);
    Charts.stacked($(opts.id), { classes, xs: years, shares, counts, denoms: ok ? denoms : [], mode: opts.mode || "bars", partial: DATA.partial_years || [], markers: milestones(), height: opts.height || 400 });
    exportFor(opts.id);
    keyFor(opts.keyId, ok ? classes.map((c) => ({ label: c.label, color: c.color, kind: "rect" })) : []);
    if (!ok) { renderTable(opts.tableId, [], [], {}); return null; }
    const cols = [{ key: "cat", label: "Class" }].concat(years.map((y) => ({ key: "y" + y, label: String(y), fmt: "pct" })));
    const rows = classes.map((c) => { const o = { cat: c.label }; years.forEach((y, i) => { o["y" + y] = shares[c.key][i]; }); return o; });
    rows.push(Object.assign({ cat: "n (denominator)" }, Object.fromEntries(years.map((y, i) => ["y" + y, denoms[i]]))));
    renderTable(opts.tableId, cols, rows, { sortable: false, rowFmt: (row) => (row.cat === "n (denominator)" ? "int" : null) });
    return { denomTotal: denoms.reduce((a, b) => a + b, 0) };
  }

  // ------------------------------------------------------------------ render: everything, every time
  function renderAll() {
    writeHash();
    const d = focusDisc();
    document.documentElement.style.setProperty("--accent", discColor(d));
    syncPills();
    const note = [];
    if (state.slice.kind === "funder" || state.slice.kind === "income") note.push("Slicing by " + (state.slice.kind === "funder" ? "funder" : "income group") + ": journal and country breakdowns are discipline-wide for this slice.");
    if (state.slice.kind === "funder") note.push("A paper counts once under each listed funder.");
    if (state.hi) note.push("High-impact: " + (DATA.high_impact && DATA.high_impact.description ? DATA.high_impact.description : "journal IF or top citation decile."));
    $("filter-note").textContent = note.join(" ");
    renderHero();
    renderReport(d);
    renderTrendChart({ id: "trend-chart", tableId: "trend-table", titleId: "trend-title", subId: "trend-sub", keyId: "trend-key", fig: "trend", metricKey: state.metric, compare: "disciplines", layout: state.trendLayout, show: state.trendShow, d, height: 440 });
    renderOa(d);
    renderTrendChart({ id: "hi-chart", tableId: "hi-table", titleId: "hi-title", subId: "hi-sub", keyId: "hi-key", fig: "hi", metricKey: state.metric, compare: "subset", layout: state.hiMode === "gap" ? "gap" : "overlay", show: "rate", d, height: 360 });
    renderBubbles(d, false);
    renderDas(d);
    renderFtTable(d);
    renderIncome(d);
    renderTrendChart({ id: "t4-chart", tableId: "t4-table", titleId: "t4-title", subId: "t4-sub", keyId: "t4-key", fig: "t4", metricKey: state.metricIncome, compare: "income", layout: state.t4Layout, show: "rate", d, height: 400 });
    renderCommitment(d);
    renderJournals(d);
    renderGeo(d);
    markNav();
  }

  // ------------------------------------------------------------------ hero + edition
  function renderHero() {
    const total = DATA.disciplines.reduce((s, d) => s + ((d.totals && d.totals.in_corpus) || 0), 0);
    const y = DATA.years;
    $("hero-eyebrow").textContent = "Edition " + prettyDate(DATA.run_date, true) + " · " + fmtInt(total) + " articles · " + DATA.disciplines.length + " disciplines · " + y[0] + "–" + y[y.length - 1];
    const sel = $("edition");
    sel.textContent = cap(selectionLabel());
    sel.onclick = (e) => { e.preventDefault(); $("controls").scrollIntoView({ behavior: "smooth", block: "start" }); };
  }
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);

  // ------------------------------------------------------------------ 01 report card
  function renderReport(d) {
    const discs = selectedDiscs();
    const aggs = discs.map((x) => ({ d: x, a: aggregateDiscipline(x) }));
    const root = $("report-card");
    root.replaceChildren();
    root.style.setProperty("--cols", String(discs.length));
    root.append(el("div", { class: "rc-corner", role: "columnheader", text: "Indicator · rate, trend by year, numerator of denominator" }));
    for (const { d: x, a } of aggs) {
      const h = el("div", { class: "rc-head" + (x.key === state.focus ? " is-focus" : ""), role: "columnheader" });
      h.style.setProperty("--c", discColor(x));
      h.append(el("div", { class: "rc-disc" }, [el("span", { class: "dot", "aria-hidden": "true" }), el("span", { text: x.label })]));
      h.append(el("div", { class: "rc-n", text: a.applicable ? fmtInt(a.total[K.n]) + " papers · " + fmtInt(a.total[K.das_audited]) + " audited" : "slice not available" }));
      root.append(h);
    }
    for (const g of CARD_GROUPS) {
      root.append(el("div", { class: "rc-group", text: g.label }));
      for (const key of g.keys) {
        const m = metricOrNull(key);
        if (!m) continue;
        const active = state.metric === key;
        const name = el("div", { class: "rc-name", role: "rowheader" });
        name.append(el("button", { type: "button", class: "rc-pick", "aria-pressed": String(active), title: "Draw this indicator in Trends",
          onclick: () => { state.metric = key; renderAll(); } }, [el("span", { class: "sq", "aria-hidden": "true" }), el("span", { text: CARD_LABELS[key] || m.label })]));
        name.append(el("div", { class: "rc-def", text: CARD_DEFS[key] || m.definition }));
        root.append(name);
        for (const { d: x, a } of aggs) {
          const ok = a.applicable && metricAvailable(x, key);
          const v = ok ? rate(a.total, m) : null;
          const cell = el("div", { class: "rc-cell" + (x.key === state.focus ? " is-focus" : "") + (v === null ? " is-na" : ""), role: "cell" });
          cell.style.setProperty("--c", discColor(x));
          const valEl = el("div", { class: "rc-val", text: v === null ? (ok ? "—" : "n/a") : fmtPct(v) });
          if (v !== null) { valEl.dataset.value = String(v); valEl.dataset.digits = String(pctDigits(v)); }
          const pk = x.key + "|" + key, prev = PREV_VALS.get(pk);
          if (v !== null && prev !== undefined && prev !== null && prev !== v) Charts.countUp(valEl, prev, v, (q) => fmtPct(q, pctDigits(v)));
          PREV_VALS.set(pk, v);
          cell.append(valEl);
          if (v !== null) { const s = seriesFromByYear(a.byYear, m); if (s.some((p) => p !== null)) cell.append(sparkline(s, discColor(x))); }
          const nText = !a.applicable ? "slice not available" : !ok ? "not in this dataset" : v === null ? "fewer than " + MIN_N_RATE + " papers" : fmtInt(numer(a.total, m)) + " of " + fmtInt(denom(a.total, m));
          cell.append(el("div", { class: "rc-n", text: nText }));
          if (v !== null) cell.title = x.label + " · " + (CARD_LABELS[key] || m.label) + ": " + fmtPct(v, 1) + " (" + nText + ")";
          root.append(cell);
        }
      }
    }
    [...root.children].forEach((c, i) => c.style.setProperty("--i", String(i)));
    const others = discs.filter((x) => x.key !== d.key).map((x) => x.label.toLowerCase());
    $("s1-note").textContent = d.label + (others.length ? " against " + others.join(", ") : "") + ": " + selectionLabel() + ". Rates below " + MIN_N_RATE + " papers are not shown.";
    caption("s1-caption", "report", "Each cell shows the rate for the selection, its year-by-year trend and the numerator of the denominator. Full-text rows refer to the audited open-access sample only. The marked indicator is drawn in Trends.", true);
  }

  // ------------------------------------------------------------------ trend charts (disciplines, all vs high-impact, income groups)
  function renderTrendChart(o) {
    const t = Charts.theme();
    const d = o.d;
    const years = yearsInRange();
    const m = metric(o.metricKey);
    const asCount = o.show === "count";
    const series = [];
    if (o.compare === "disciplines") {
      for (const x of selectedDiscs()) {
        if (!metricAvailable(x, m.key)) continue;
        const a = aggregateDiscipline(x);
        if (a.applicable) series.push({ key: x.key, label: x.label, color: discColor(x), byYear: a.byYear, emphasis: x.key === d.key });
      }
    } else if (o.compare === "income") {
      const colors = ramp(RAMP4);
      (DATA.income_order || []).forEach((g, i) => {
        const idx = (d.income_groups || []).indexOf(g);
        if (idx < 0) return;
        const byYear = new Map();
        for (const row of d.income_cells || []) {
          if (!keepRow(row) || row[POS.dim] !== idx) continue;
          let acc = byYear.get(row[0]); if (!acc) { acc = emptyCounts(); byYear.set(row[0], acc); }
          addRow(acc, row, DIM_OFFSET);
        }
        series.push({ key: g, label: (DATA.income_labels || {})[g] || g, color: colors[i], byYear, emphasis: false });
      });
    } else if (o.compare === "subset") {
      const saved = state.hi;
      for (const [hi, label, color] of [[false, "All papers", t.neutral], [true, "High-impact", discColor(d)]]) {
        state.hi = hi;
        const a = aggregateDiscipline(d);
        if (a.applicable) series.push({ key: hi ? "hi" : "all", label, color, byYear: a.byYear, emphasis: hi });
      }
      state.hi = saved;
    }
    const value = (s, y) => (asCount ? (s.byYear.get(y) ? numer(s.byYear.get(y), m) : null) : rate(s.byYear.get(y), m));
    const data = series.map((s) => ({ key: s.key, label: s.label, color: s.color, emphasis: s.emphasis,
      values: years.map((y) => value(s, y)), ns: years.map((y) => (s.byYear.get(y) ? denom(s.byYear.get(y), m) : 0)) }));
    const drawn = data.filter((s) => s.values.some((v) => v !== null));
    Charts.lineChart($(o.id), { series: data, xs: years, fmt: asCount ? "int" : "pct", partial: DATA.partial_years || [], markers: milestones(), layout: o.layout, height: o.height || 420 });
    exportFor(o.id);
    keyFor(o.keyId, drawn.map((s) => ({ label: s.label, color: s.color })));
    const sel = selectionLabel();
    const base = o.compare === "disciplines" ? m.label + " by year" : o.compare === "income" ? m.label + " by year and income group" : m.label + ": all " + d.label.toLowerCase() + " papers against the high-impact subset";
    const form = o.layout === "panels" ? ", one panel each" : o.layout === "slope" ? ", first year to last" : o.layout === "gap" ? ", the gap by year" : "";
    $(o.titleId).textContent = base + form;
    const source = "Source: OpenAlex, Unpaywall, Crossref" + (m.denominator === "das_audited" ? ", Europe PMC full texts" : "") + ".";
    caption(o.subId, o.fig, drawn.length ? cap(sel) + ". " + (asCount ? "Counts." : denomText(m)) + (o.layout === "panels" ? " Shared scale; the other series are ghosted in grey. " : " ") + source : cap(sel) + " · no data.");
    const cols = [{ key: "label", label: "Series" }].concat(years.map((y) => ({ key: "y" + y, label: String(y), fmt: asCount ? "int" : "pct" })));
    renderTable(o.tableId, cols, drawn.map((s) => { const x = { label: s.label }; years.forEach((y, i) => { x["y" + y] = s.values[i]; }); return x; }), { sortable: false });
  }

  // ------------------------------------------------------------------ full text vs abstract
  function renderFtTable(d) {
    const rows = [];
    for (const x of selectedDiscs()) {
      const a = aggregateDiscipline(x);
      if (!a.applicable) continue;
      rows.push({ label: x.label, n: a.total[K.das_audited], code_abs: rate(a.total, "code"), code_ft: rate(a.total, "ft_github"), reg_abs: rate(a.total, "reg"), reg_ft: rate(a.total, "ft_reg"), stmt: rate(a.total, "das_stmt") });
    }
    renderTable("ft-table", [
      { key: "label", label: "Discipline" }, { key: "n", label: "Audited", fmt: "int" },
      { key: "code_abs", label: "Code, abstract", fmt: "pct" }, { key: "code_ft", label: "GitHub, full text", fmt: "pct" },
      { key: "reg_abs", label: "Registration, abstract", fmt: "pct" }, { key: "reg_ft", label: "Registration, full text", fmt: "pct" },
      { key: "stmt", label: "Statement", fmt: "pct" },
    ], rows, { sortable: false });
    caption("ft-sub", "ft", "What titles, abstracts and metadata miss: the same signal read from the abstract and from the audited full text, per discipline. " + cap(selectionLabel()) + ".", true);
  }

  // ------------------------------------------------------------------ open access
  function oaClasses(grouping) {
    if (grouping === "status") return DATA.oa_status_order.map((s) => ({ key: s, label: s[0].toUpperCase() + s.slice(1), sum: (c) => c[K["oa_" + s]], neutral: s === "closed", color: oaColor(s) }));
    return OA_ROUTES.map((r) => ({ key: r.key, label: r.label, sum: (c) => r.statuses.reduce((s, st) => s + c[K["oa_" + st]], 0), neutral: !!r.neutral, color: r.status ? oaColor(r.status) : null }));
  }
  function renderOa(d) {
    // the raincloud needs the full width: both figures of the row go wide while it is on
    for (const id of ["oa-chart", "hi-chart"]) { const fig = $(id).closest(".fig"); if (fig) fig.classList.toggle("is-wide", state.oaMode === "rain"); }
    if (state.oaMode === "rain") return renderOaRain(d);
    const classes = oaClasses(state.oaGrouping);
    const res = stackedFor({ id: "oa-chart", tableId: "oa-table", keyId: "oa-key", classes, denomFn: oaKnown, mode: state.oaMode, height: 360 });
    $("oa-title").textContent = (state.oaGrouping === "status" ? "Open-access status by year, " : "Open-access route by year, ") + d.label.toLowerCase();
    caption("oa-sub", "oa", res ? fmtInt(res.denomTotal) + " papers with a known status. " + cap(selectionLabel()) + ". Shares of papers with a known OpenAlex status." : "No OA-status data for this selection.");
  }

  /** Raincloud: per year, the spread of open-access rates across journals (one drop per journal, sized by papers,
   *  coloured by its dominant route), the density as a half-cloud and the median as a tick. */
  function renderOaRain(d) {
    const t = Charts.theme();
    const years = yearsInRange();
    const byYear = aggregateByYearFor(d, "journal");
    const routeColor = { free: oaColor("green"), paid: oaColor("gold"), bronze: oaColor("bronze"), closed: t.neutral };
    const routeLabel = { free: "free to author", paid: "APC paid", bronze: "bronze", closed: "closed" };
    const groups = {}; years.forEach((yr) => { groups[yr] = []; });
    const MIN_J = 30;
    const matrix = [];
    for (const [idx, m] of byYear.entries()) {
      const j = d.journals[idx];
      if (!j || j.key === "Other") continue;
      const row = { label: j.label };
      for (const yr of years) {
        const c = m.get(yr);
        if (!c || oaKnown(c) < MIN_J) { row["y" + yr] = null; continue; }
        const shares = OA_ROUTES.map((r) => [r.key, r.statuses.reduce((s, st) => s + c[K["oa_" + st]], 0) / oaKnown(c)]);
        const dom = shares.slice().sort((a, b) => b[1] - a[1])[0][0];
        const v = rate(c, "oa");
        row["y" + yr] = v;
        if (v !== null) groups[yr].push({ key: j.key, label: j.label, value: v, n: c[K.n], color: routeColor[dom], sub: "mostly " + routeLabel[dom] + " (" + shares.map((s) => routeLabel[s[0]] + " " + fmtPct(s[1], 0)).join(", ") + ")" });
      }
      matrix.push(row);
    }
    Charts.raincloud($("oa-chart"), { years, groups, partial: DATA.partial_years || [], valueLabel: "open access" });
    exportFor("oa-chart");
    keyFor("oa-key", OA_ROUTES.map((r) => ({ label: "Mostly " + routeLabel[r.key], color: routeColor[r.key], kind: "line" })));
    $("oa-title").textContent = "Open-access rate across journals by year, " + d.label.toLowerCase();
    const nJ = new Set(years.flatMap((yr) => groups[yr].map((p) => p.key))).size;
    caption("oa-sub", "oa", nJ + " journals with at least " + MIN_J + " papers of known status in a year. " + cap(selectionLabel()) + ". One row per year: the cloud is the density of open-access rates across journals, each drop below it a journal sized by its papers that year and coloured by its dominant route, the bar the interquartile range and the tick the median (value at right).");
    renderTable("oa-table", [{ key: "label", label: "Journal" }].concat(years.map((yr) => ({ key: "y" + yr, label: String(yr), fmt: "pct" }))), matrix, { sortable: false });
  }

  // ------------------------------------------------------------------ bubbles through the years (Rosling)
  let playTimer = null;
  function stopPlay() { if (playTimer) clearInterval(playTimer); playTimer = null; state.bbPlaying = false; const b = $("bb-play"); if (b) b.textContent = "Play"; }
  function startPlay() {
    stopPlay();
    const years = yearsInRange();
    if (years.length < 2) return;
    state.bbPlaying = true; $("bb-play").textContent = "Pause";
    if (state.bbYear === years[years.length - 1]) state.bbYear = years[0];
    renderBubbles(focusDisc(), true);
    playTimer = setInterval(() => {
      const ys = yearsInRange();
      const i = ys.indexOf(state.bbYear);
      if (i < 0 || i === ys.length - 1) { stopPlay(); return; }
      state.bbYear = ys[i + 1];
      renderBubbles(focusDisc(), true);
      writeHash();
    }, 1100);
  }
  function bubbleFrames(d) {
    const t = Charts.theme();
    const years = yearsInRange();
    const mx = metric(state.bbX), my = metric(state.bbY);
    const frames = {}; years.forEach((yr) => { frames[yr] = []; });
    const push = (yr, key, label, counts, color, group, pinned) => {
      const vx = rate(counts, mx), vy = rate(counts, my);
      if (vx === null || vy === null) return;
      frames[yr].push({ key, label, x: vx, y: vy, size: counts[K.n], color, group, pinned });
    };
    let keyItems = [];
    if (state.bbEntity === "disciplines") {
      for (const xd of selectedDiscs()) {
        if (!metricAvailable(xd, mx.key) || !metricAvailable(xd, my.key)) continue;
        const a = aggregateDiscipline(xd);
        if (!a.applicable) continue;
        for (const yr of years) { const c = a.byYear.get(yr); if (c) push(yr, xd.key, xd.label, c, discColor(xd), null, true); }
        keyItems.push({ label: xd.label, color: discColor(xd) });
      }
    } else if (metricAvailable(d, mx.key) && metricAvailable(d, my.key)) {
      const dim = state.bbEntity === "journals" ? "journal" : "country";
      const list = dim === "journal" ? d.journals : d.countries;
      const byYear = aggregateByYearFor(d, dim);
      const colors = ramp(RAMP4);
      const order = DATA.income_order || [];
      for (const [idx, m] of byYear.entries()) {
        const item = list[idx];
        if (!item || item.key === "Other") continue;
        const gi = dim === "country" ? order.indexOf(item.income || "") : -1;
        const color = dim === "country" ? (gi >= 0 ? colors[gi] : t.neutral) : discColor(d);
        const group = dim === "country" ? (gi >= 0 ? (DATA.income_labels || {})[item.income] : "income group unknown") : null;
        for (const yr of years) { const c = m.get(yr); if (c) push(yr, item.key, item.label, c, color, group, false); }
      }
      if (dim === "country") keyItems = order.map((g, i) => ({ label: (DATA.income_labels || {})[g] || g, color: colors[i] })).concat([{ label: "Income group unknown", color: t.neutral }]);
    }
    return { years, frames, mx, my, keyItems };
  }
  function renderBubbles(d, playing) {
    const { years, frames, mx, my, keyItems } = bubbleFrames(d);
    if (!years.includes(state.bbYear)) state.bbYear = years[years.length - 1];
    Charts.bubbles($("bb-chart"), { frames, years, year: state.bbYear, xFmt: "pct", yFmt: "pct", xLabel: mx.label + " →", yLabel: my.label + " ↑", trails: state.bbTrails === "on", labels: state.bbEntity === "disciplines" ? 8 : 7, playing, partial: DATA.partial_years || [], height: 520 });
    exportFor("bb-chart");
    keyFor("bb-key", keyItems);
    const entity = { countries: "first-author countries", journals: "journals", disciplines: "disciplines" }[state.bbEntity];
    $("bb-title").textContent = my.label + " against " + mx.label.toLowerCase() + ", " + entity + (state.bbEntity === "disciplines" ? "" : ", " + d.label.toLowerCase());
    const slider = $("bb-year");
    slider.min = years[0]; slider.max = years[years.length - 1]; slider.value = state.bbYear;
    $("bb-readout").textContent = String(state.bbYear);
    const n = (frames[state.bbYear] || []).length;
    caption("bb-sub", "bb", n + " bubbles in " + state.bbYear + ", area = papers that year; the largest carry labels and trails. " + cap(selectionLabel()) + ". Across: " + mx.label.toLowerCase() + " (" + denomText(mx).toLowerCase().replace(/\.$/, "") + "); up: " + my.label.toLowerCase() + " (" + denomText(my).toLowerCase().replace(/\.$/, "") + "). Entities with fewer than " + MIN_N_RATE + " papers in a year are hidden; press Play to move through the years.");
    renderTable("bb-table", [{ key: "label", label: state.bbEntity === "journals" ? "Journal" : state.bbEntity === "countries" ? "Country" : "Discipline" }, { key: "size", label: "Papers " + state.bbYear, fmt: "int" }, { key: "x", label: mx.label, fmt: "pct" }, { key: "y", label: my.label, fmt: "pct" }, { key: "group", label: "Group" }],
      (frames[state.bbYear] || []).slice().sort((a, b) => b.size - a.size).map((p) => ({ label: p.label, size: p.size, x: p.x, y: p.y, group: p.group || "" })), { sortable: false });
  }

  // ------------------------------------------------------------------ data statements
  function dasClasses(grouping, denominator) {
    const neutralOut = denominator === "stmt";
    if (grouping === "eight") return DATA.das_order.filter((c) => !(neutralOut && c === "no_statement")).map((c) => ({ key: c, label: (DATA.das_labels || {})[c] || c, sum: (x) => x[K["das_" + c]], neutral: c === "no_statement" }));
    return DAS_FIVE.filter((c) => !(neutralOut && c.neutral)).map((c) => ({ key: c.key, label: c.label, sum: (x) => c.cats.reduce((s, k) => s + x[K["das_" + k]], 0), neutral: !!c.neutral }));
  }
  const SIG = [["das_stmt", "Statement"], ["das_deposit", "Deposit"], ["das_on_request", "On request"], ["ft_github", "GitHub"], ["ft_reg", "Registration"]];
  function renderDas(d) {
    const denomFn = state.dasDenominator === "stmt" ? ((x) => x[K.das_stmt]) : ((x) => x[K.das_audited]);
    const classes = dasClasses(state.dasGrouping, state.dasDenominator);
    const mode = state.dasGrouping === "eight" ? "panels" : state.dasMode;   // eight classes are only honest as small multiples
    const res = stackedFor({ id: "das-chart", tableId: "das-table", keyId: "das-key", classes, denomFn, mode, height: 420 });
    $("das-title").textContent = "Statements by year, " + d.label.toLowerCase() + (mode === "panels" ? ", one panel per class" : "");
    caption("das-sub", "das", res
      ? fmtInt(res.denomTotal) + (state.dasDenominator === "stmt" ? " audited articles with a statement. " : " audited open-access full texts. ") + cap(selectionLabel()) + ". Source: Europe PMC full texts, classified by the pipeline."
      : "No audited papers in this selection.");
    // By discipline: a dot plot, one row per indicator, one dot per discipline
    const discs = selectedDiscs().map((x) => ({ x, a: aggregateDiscipline(x) })).filter((o) => o.a.applicable && o.a.total[K.das_audited] >= MIN_N_RATE);
    Charts.dotPlot($("das-disc-chart"), { rows: SIG.map((s) => ({ key: s[0], label: s[1], points: discs.map((o) => ({ key: o.x.key, label: o.x.label, color: discColor(o.x), value: rate(o.a.total, s[0]), n: o.a.total[K.das_audited] })) })),
      fmt: "pct", mode: state.ftdMode, emphasisKey: d.key });
    exportFor("das-disc-chart");
    keyFor("das-disc-key", discs.map((o) => ({ label: o.x.label, color: discColor(o.x), kind: state.ftdMode === "bars" ? "rect" : "line" })));
    $("das-disc-title").textContent = "Full-text indicators by discipline";
    caption("das-disc-sub", "das-disc", "Audited open-access full texts, pooled. " + cap(selectionLabel()) + ". The labelled value is " + d.label.toLowerCase() + "'s; the grey bar spans the lowest to the highest discipline.");
    renderTable("das-disc-table", [{ key: "label", label: "Discipline" }, { key: "n", label: "Audited", fmt: "int" }].concat(SIG.map((s) => ({ key: s[0], label: s[1], fmt: "pct" }))),
      discs.map((o) => Object.assign({ label: o.x.label, n: o.a.total[K.das_audited] }, Object.fromEntries(SIG.map((s) => [s[0], rate(o.a.total, s[0])])))), { sortable: false });
  }

  // ------------------------------------------------------------------ 04 income groups
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
  function renderIncome(d) {
    const t = Charts.theme();
    const grid = $("income-grid");
    grid.replaceChildren();
    const groups = d.available.income ? incomeAggregates(d) : [];
    if (!groups.length) {
      grid.append(el("div", { class: "stat is-na" }, [el("div", { class: "stat-label", text: "Income group" }), el("div", { class: "stat-val", text: "n/a" }), el("div", { class: "stat-sub", text: "first_author_income_group is not in this dataset" })]));
      Charts.dotPlot($("eq-chart"), { rows: [] }); Charts.dotPlot($("eq-ft-chart"), { rows: [] }); renderTable("eq-table", [], [], {}); renderTable("eq-ft-table", [], [], {});
      $("eq-title").textContent = "By income group"; caption("eq-sub", "eq", "No income-group data."); caption("eq-ft-sub", "eq-ft", "No income-group data.");
      return;
    }
    const totalN = groups.reduce((s, g) => s + g.counts[K.n], 0);
    for (const g of groups) {
      const share = g.counts[K.n] / totalN;
      const val = el("div", { class: "stat-val", text: fmtPct(share) });
      val.dataset.value = String(share); val.dataset.digits = String(pctDigits(share));
      const pk = "income|" + d.key + "|" + g.key, prev = PREV_VALS.get(pk);
      if (prev !== undefined && prev !== share) Charts.countUp(val, prev, share, (q) => fmtPct(q, pctDigits(share)));
      PREV_VALS.set(pk, share);
      const cell = el("div", { class: "stat" }, [
        el("div", { class: "stat-label", text: g.label }), val,
        el("div", { class: "stat-sub", text: fmtInt(g.counts[K.n]) + " papers · open access " + fmtPct(rate(g.counts, "oa")) + " · statement " + fmtPct(rate(g.counts, "das_stmt")) }),
      ]);
      const bar = el("div", { class: "stat-bar" }, el("span")); bar.firstChild.style.width = clamp(share * 100, 0, 100) + "%"; bar.style.setProperty("--c", t.ink); cell.append(bar);
      grid.append(cell);
    }
    const labels = groups.map((g) => g.label.replace(" income", ""));
    if (state.eqSignal === "route") {
      const classes = oaClasses("route").map((c) => ({ key: c.key, label: c.label, neutral: !!c.neutral, color: c.neutral ? t.neutral : c.color, sum: c.sum }));
      const denoms = groups.map((g) => oaKnown(g.counts));
      const shares = {}, counts = {};
      for (const c of classes) { counts[c.key] = groups.map((g) => c.sum(g.counts)); shares[c.key] = groups.map((g, i) => (denoms[i] >= MIN_N_RATE ? counts[c.key][i] / denoms[i] : null)); }
      Charts.stacked($("eq-chart"), { classes, xs: labels, shares, counts, denoms, mode: state.eqMode === "area" ? "bars" : state.eqMode, height: 340 });
      exportFor("eq-chart");
      keyFor("eq-key", classes.map((c) => ({ label: c.label, color: c.color, kind: "rect" })));
      $("eq-title").textContent = "Open-access route by income group";
      caption("eq-sub", "eq", "Papers with a known status. " + cap(selectionLabel()) + ".");
      renderTable("eq-table", [{ key: "label", label: "Income group" }, { key: "n", label: "Papers", fmt: "int" }].concat(classes.map((c) => ({ key: c.key, label: c.label, fmt: "pct" }))),
        groups.map((g, i) => Object.assign({ label: g.label, n: g.counts[K.n] }, Object.fromEntries(classes.map((c) => [c.key, shares[c.key][i]])))), { sortable: false });
    } else {
      const m = metric(state.eqSignal);
      const vals = groups.map((g) => rate(g.counts, m));
      Charts.dotPlot($("eq-chart"), { rows: groups.map((g, i) => ({ key: g.key, label: g.label, points: [{ key: "v", label: m.label, color: g.color, value: vals[i], n: denom(g.counts, m) }] })), fmt: "pct", mode: state.eqMode === "bars" ? "bars" : "dots", emphasisKey: "v" });
      exportFor("eq-chart");
      keyFor("eq-key", []);
      $("eq-title").textContent = m.label + " by income group";
      caption("eq-sub", "eq", cap(selectionLabel()) + ". " + denomText(m));
      renderTable("eq-table", [{ key: "label", label: "Income group" }, { key: "n", label: "Denominator", fmt: "int" }, { key: "v", label: m.label, fmt: "pct" }],
        groups.map((g, i) => ({ label: g.label, n: denom(g.counts, m), v: vals[i] })), { sortable: false });
    }
    // Full-text indicators by income group: dot plot, one row per indicator, one dot per group (ordinal blues)
    const audited = groups.filter((g) => g.counts[K.das_audited] >= MIN_N_RATE);
    Charts.dotPlot($("eq-ft-chart"), { rows: d.available.das ? SIG.map((s) => ({ key: s[0], label: s[1], points: audited.map((g) => ({ key: g.key, label: g.label, color: g.color, value: rate(g.counts, s[0]), n: g.counts[K.das_audited] })) })) : [],
      fmt: "pct", mode: state.ftdMode });
    exportFor("eq-ft-chart");
    keyFor("eq-ft-key", audited.map((g) => ({ label: g.label, color: g.color, kind: state.ftdMode === "bars" ? "rect" : "line" })));
    caption("eq-ft-sub", "eq-ft", d.available.das ? "Audited open-access full texts. " + cap(selectionLabel()) + ". The labelled value is the highest group." : "No data-availability audit in this dataset.");
    renderTable("eq-ft-table", [{ key: "label", label: "Income group" }, { key: "n", label: "Audited", fmt: "int" }].concat(SIG.map((s) => ({ key: s[0], label: s[1], fmt: "pct" }))),
      groups.map((g) => Object.assign({ label: g.label, n: g.counts[K.das_audited] }, Object.fromEntries(SIG.map((s) => [s[0], rate(g.counts, s[0])])))), { sortable: false });
  }

  // ------------------------------------------------------------------ 05 rankings
  function signalRate(counts, s) {
    const d = counts[K[s.denominator]] || 0;
    if (!d) return null;
    return s.numerators.reduce((a, k) => a + (counts[K[k]] || 0), 0) / d;
  }
  function renderCommitment(d) {
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
        items.push({ label: item.label || key, n: c[K.n], n_audited: nAud, index: ratios.reduce((a, b) => a + b, 0) / Math.max(1, ratios.length),
          das_deposit: signalRate(c, (DATA.commitment_signals || [])[0]), ft_github: rate(c, "ft_github"), ft_reg: rate(c, "ft_reg"), on_request: rate(c, "das_on_request"), stmt: rate(c, "das_stmt") });
      }
    }
    items.sort((a, b) => b.index - a.index || b.n_audited - a.n_audited);
    const top = items.slice(0, state.cmTop);
    Charts.rankDots($("cm-chart"), { items: top.map((i) => ({ key: i.label, label: i.label, value: i.index, rows: [{ value: fmtInt(i.n_audited), label: "audited" }, { value: fmtPct(i.das_deposit, 1), label: "deposit / public source" }, { value: fmtPct(i.ft_github, 1), label: "GitHub in full text" }, { value: fmtPct(i.ft_reg, 1), label: "registration in full text" }] })),
      fmt: "x", reference: { value: 1, label: d.label + " average" }, color: discColor(d), mode: state.cmMode, valueLabel: "commitment index", xMax: Math.max(2, ...top.map((i) => i.index)) * 1.12 });
    exportFor("cm-chart");
    const entityLabel = { institutions: "Institutions", journals: "Journals", funders: "Funders", countries: "First-author countries" }[entity];
    $("cm-title").textContent = entityLabel + " ranked on the commitment index, " + d.label.toLowerCase();
    caption("cm-sub", "cm", available
      ? "Entity rate divided by the " + d.label.toLowerCase() + " rate, averaged over the chosen indicators (" + signals.map((s, i) => fmtPct(baseRates[i], 1)).join(" / ") + " discipline-wide). " + items.length + " entries with at least " + state.cmMin + " audited articles. " + cap(selectionLabel()) + "."
      : "This view needs the data-availability audit" + (entity === "institutions" ? " and the institutions column" : "") + " in the dataset.");
    renderTable("cm-table", [
      { key: "label", label: entity === "countries" ? "Country" : entity === "funders" ? "Funder" : entity === "journals" ? "Journal" : "Institution" },
      { key: "n_audited", label: "Audited", fmt: "int" }, { key: "n", label: "Papers", fmt: "int" },
      { key: "index", label: "Index", fmt: "x", bar: true }, { key: "das_deposit", label: "Deposit / public source", fmt: "pct" },
      { key: "ft_github", label: "GitHub (full text)", fmt: "pct" }, { key: "ft_reg", label: "Registration (full text)", fmt: "pct" },
      { key: "on_request", label: "On request", fmt: "pct" }, { key: "stmt", label: "Statement", fmt: "pct" },
    ], items, { sortable: true, color: discColor(d), name: "commitment", defaultSort: { key: "index", dir: "desc" }, barKey: "index" });
  }
  function renderJournals(d) {
    const m = metric(state.journalMetric);
    const groups = aggregateBy(d, "journal");
    const byYear = aggregateByYearFor(d, "journal");
    const items = [];
    for (const [idx, c] of groups.entries()) {
      const j = d.journals[idx];
      if (!j || j.key === "Other" || c[K.n] < state.journalMin) continue;
      const row = { label: j.label, n: c[K.n], v: rate(c, m), dn: denom(c, m), trend: byYear.get(idx) ? seriesFromByYear(byYear.get(idx), m) : null };
      for (const x of METRICS) row[x.key] = metricAvailable(d, x.key) ? rate(c, x) : null;
      items.push(row);
    }
    const plotted = items.filter((i) => i.v !== null).sort((a, b) => b.v - a.v).slice(0, state.journalTop);
    Charts.rankDots($("journal-chart"), { items: plotted.map((i) => ({ key: i.label, label: i.label, value: i.v, rows: [{ value: fmtInt(i.dn), label: "papers (denominator)" }] })),
      fmt: "pct", color: discColor(d), mode: state.journalMode, valueLabel: m.label, xMax: Math.min(1.06, Math.max(0.0001, ...plotted.map((i) => i.v)) * 1.15) });
    exportFor("journal-chart");
    $("journal-title").textContent = "Journals by " + m.label.toLowerCase() + ", " + d.label.toLowerCase();
    caption("journal-sub", "journal", items.length ? plotted.length + " of " + items.length + " journals with at least " + state.journalMin + " papers. " + cap(selectionLabel()) + ". " + denomText(m) : "No journal reaches " + state.journalMin + " papers under this selection.");
    const cols = [{ key: "label", label: "Journal" }, { key: "n", label: "Papers", fmt: "int" }, { key: "trend", label: m.short + " by year", fmt: "spark" }].concat(METRICS.filter((x) => x.key !== "material" && metricAvailable(d, x.key)).map((x) => ({ key: x.key, label: x.short, fmt: "pct", bar: x.key === m.key })));
    renderTable("journal-table", cols, items, { sortable: true, color: discColor(d), name: "journals", defaultSort: { key: m.key, dir: "desc" }, barKey: m.key });
  }
  function dimRows(d, groups, list, labelOf, byYear) {
    const rows = [];
    for (const [idx, c] of groups.entries()) {
      const item = list[idx];
      if (!item) continue;
      const row = { label: labelOf(item), other: (item.key || item) === "Other" || item === "(no funder listed)", n: c[K.n],
        trend: byYear && byYear.get(idx) ? seriesFromByYear(byYear.get(idx), metric("oa")) : null };
      for (const m of METRICS) row[m.key] = metricAvailable(d, m.key) ? rate(c, m) : null;
      rows.push(row);
    }
    return rows;
  }
  function dimCols(d, first) {
    return [{ key: "label", label: first }, { key: "n", label: "Papers", fmt: "int" }, { key: "trend", label: "OA by year", fmt: "spark" }]
      .concat(METRICS.filter((m) => m.key !== "material" && metricAvailable(d, m.key)).map((m) => ({ key: m.key, label: m.short, fmt: "pct", bar: m.key === "oa" })));
  }
  function renderGeo(d) {
    $("country-fig").hidden = !d.available.country;
    $("funder-fig").hidden = !d.available.funders;
    if (d.available.country) {
      const rows = dimRows(d, aggregateBy(d, "country"), d.countries, (c) => (c.key === "Other" ? "Other countries" : c.label), aggregateByYearFor(d, "country"));
      $("country-title").textContent = "First-author countries, " + d.label.toLowerCase();
      renderTable("country-table", dimCols(d, "Country"), rows, { sortable: true, color: discColor(d), name: "countries", barKey: "oa" });
      caption("country-sub", "country", "Top " + (DATA.top_n.countries || "") + " by volume. " + cap(selectionLabel()) + ". Full-text columns: share of audited papers.", true);
    }
    if (d.available.funders) {
      const rows = dimRows(d, aggregateBy(d, "funder"), d.funders, (f) => (f === "Other" ? "Other funders" : f), aggregateByYearFor(d, "funder"));
      $("funder-title").textContent = "Funders, " + d.label.toLowerCase();
      renderTable("funder-table", dimCols(d, "Funder"), rows, { sortable: true, color: discColor(d), name: "funders", barKey: "oa" });
      caption("funder-sub", "funder", "Top " + (DATA.top_n.funders || "") + " by volume; a paper counts once per funder. " + (state.hi ? "High-impact papers" : "All papers") + ", " + state.yearMin + "–" + state.yearMax + ".", true);
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
        if (Array.isArray(va) || Array.isArray(vb)) return 0;
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
      if (o.sortable && c.fmt !== "spark") {
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
        if (fmt === "spark") {
          const td = el("td", { class: "spark-cell" });
          if (Array.isArray(v) && v.some((p) => p !== null)) td.append(sparkline(v, o.color));
          row.append(td);
          continue;
        }
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
    const header = ["discipline", "year", "subset", "design", "slice"].concat(DATA.count_keys).concat(METRICS.map((m) => m.key + "_rate"));
    const lines = [header.join(",")];
    const q = (s) => '"' + String(s).replace(/"/g, '""') + '"';
    for (const d of selectedDiscs()) {
      const agg = aggregateDiscipline(d);
      if (!agg.applicable) continue;
      for (const y of years) {
        const c = agg.byYear.get(y);
        if (!c) continue;
        const rates = METRICS.map((m) => { const dn = denom(c, m); return dn ? (numer(c, m) / dn).toFixed(4) : ""; });
        lines.push([d.key, y, state.hi ? "high_impact" : "all", state.design, q(state.slice.kind ? state.slice.kind + ":" + state.slice.key : "all")].concat(c).concat(rates).join(","));
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

  // ------------------------------------------------------------------ 06 methods + footer
  function renderMethods() {
    const body = $("methods-body");
    body.replaceChildren();
    const block = (title, node) => { body.append(el("h4", { text: title }), el("div", { class: "mbody" }, node)); };
    const dl = el("dl");
    for (const m of METRICS) dl.append(el("dt", { text: m.label }), el("dd", { text: m.definition }));
    if (DATA.study_design) dl.append(el("dt", { text: "Trials" }), el("dd", { text: DATA.study_design.description }));
    dl.append(el("dt", { text: "OA route" }), el("dd", { text: "Free to author = OpenAlex diamond or green; APC paid = gold or hybrid; bronze = free to read without a licence; closed. Shares use papers with a known status as the denominator." }));
    dl.append(el("dt", { text: "Audited sample" }), el("dd", { text: "The data-availability audit covers a per-year sample of open-access articles with full text in Europe PMC, so every full-text rate is optimistic relative to the whole corpus and refers to audited papers only. Groups with fewer than " + MIN_N_RATE + " audited papers are not drawn." }));
    dl.append(el("dt", { text: "Statement classes" }), el("dd", { text: "Five ordered classes for the chart: deposited or public source (repository, public_source); controlled or restricted; on request; in article or supplement; not available or unclear (not_available_or_na, other_or_unclear); plus no statement. The eight underlying categories are available as small multiples and in every table." }));
    dl.append(el("dt", { text: "Commitment index" }), el("dd", { text: "For an institution, journal, funder or first-author country: the mean over the selected verified full-text indicators (data deposited or public source in the statement; GitHub mentioned in the full text; trial registration mentioned in the full text) of the entity's rate divided by the discipline-wide rate under the same selection. 1.0 is the discipline average. Only entities with at least the chosen number of audited articles are ranked; small counts are noisy." }));
    dl.append(el("dt", { text: "Income group" }), el("dd", { text: "World Bank classification of the first author's country (high, upper-middle, lower-middle, low), from the pipeline's country-income configuration; unknown when the country is missing or unclassified." }));
    dl.append(el("dt", { text: "High-impact subset" }), el("dd", { text: (DATA.high_impact && DATA.high_impact.description) || "" }));
    if ((DATA.policy_events || []).length) dl.append(el("dt", { text: "Policy milestones" }), el("dd", { text: DATA.policy_events.map((e) => e.year + ": " + e.label).join(". ") + ". Drawn at the start of the year on the by-year charts; hover a label for the detail." }));
    block("Definitions", dl);
    const ul1 = el("ul");
    for (const d of DATA.disciplines) ul1.append(el("li", { text: d.label + ": " + fmtInt(d.totals.in_corpus) + " articles and reviews kept of " + fmtInt(d.totals.rows_in_file) + " retrieved records (" + fmtInt(d.totals.dropped) + " excluded; rule: " + (DATA.corpus_rule[d.key] || "n/a") + "). Years " + d.years[0] + "–" + d.years[d.years.length - 1] + "." }));
    block("Corpus", ul1);
    const ul2 = el("ul");
    for (const n of DATA.methods_notes) ul2.append(el("li", { text: n }));
    ul2.append(el("li", { text: "Rates are not drawn for cells with fewer than " + MIN_N_RATE + " papers. Colours: open-access statuses wear their names (diamond blue, gold, hybrid pink, green, bronze) and routes take the colour of their main status; the ordered data-statement classes use one blue ramp (darkest = most open); closed / no statement are a neutral grey; one fixed colour per discipline, the focus discipline carrying the page accent. Every chart has a table twin, at least two forms, and PNG / SVG export (exports use a system sans)." }));
    block("Reading notes", ul2);
    block("How this page works", el("p", { text: "The pipeline writes pre-aggregated counts (discipline × year × high-impact × journal × first-author country; plus × funder, × first-author income group and × institution) to dashboard_data.json; this page sums the counts for your selection and divides. No row-level data is shipped. The address bar carries the full selection, so a link reproduces the view. Generated " + DATA.generated_at + "." }));
  }
  function renderFooter() {
    const f = $("footer-body");
    f.replaceChildren();
    const cit = DATA.citation || {};
    const left = el("div");
    left.append(el("p", {}, ["Edition " + prettyDate(DATA.run_date, true) + ". ", el("a", { href: DATA.repo_url, rel: "noopener", text: "Source code" }), " · ", el("a", { href: DATA.outputs_repo_url, rel: "noopener", text: "Data releases" }), " · ", el("a", { href: "legacy.html", text: "Static version" }), " · ", el("a", { href: DATA_URL, text: "dashboard_data.json" })]));
    left.append(el("p", { text: "Data: OpenAlex, Unpaywall, Crossref, Europe PMC, World Bank. Charts: D3, drawn by hand." }));
    const right = el("div");
    if (cit.title) right.append(el("p", {}, ["Cite: ", el("em", { text: cit.title }), cit.version ? " (v" + cit.version + ")" : "", cit["date-released"] ? ", " + cit["date-released"] : "", ". ", el("a", { href: DATA.repo_url + "/blob/main/CITATION.cff", rel: "noopener", text: "CITATION.cff" }), cit.license ? " · " + cit.license + " licence." : ""]));
    f.append(left, right);
  }

  // ------------------------------------------------------------------ theme
  const THEMES = ["auto", "light", "dark"];
  function applyTheme(theme) {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", theme);
    const btn = $("theme-toggle");
    btn.textContent = theme[0].toUpperCase() + theme.slice(1);
    btn.title = "Colour theme: " + theme + " (click to change)";
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
    const ck = DATA.cell_keys || ["year", "hi", "journal", "country"], dk = DATA.income_keys || ["year", "hi", "income"];
    CELL_OFFSET = ck.length; DIM_OFFSET = dk.length;
    POS = { trial: ck.indexOf("trial"), journal: ck.indexOf("journal"), country: ck.indexOf("country"), dim: dk.length - 1 };
    DATA.count_keys.forEach((k, i) => { K[k] = i; });
    if (!DATA.disciplines.length) { $("error").hidden = false; $("error").textContent = "No disciplines in the data file."; return; }
    buildMetrics();
    resetState();
    readHash();
    buildNav();
    buildSelection();
    buildViewOptions();
    renderMethods();
    renderFooter();
    renderAll();
    observeReveal();
    heroMotion();
    titleMotion();
    if (state.view !== "s1") showView(state.view, true);
    window.addEventListener("hashchange", () => { readHash(); buildSelection(); buildViewOptions(); renderAll(); showView(state.view, true); });
  }
  let resizeTimer = null;
  window.addEventListener("resize", () => { if (!DATA) return; clearTimeout(resizeTimer); resizeTimer = setTimeout(renderAll, 200); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
