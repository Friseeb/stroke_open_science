/* Open-Science Benchmark — interactive static dashboard.
 * Loads dashboard_data.json (pre-aggregated counts) and recomputes every rate client-side
 * for the current filter selection. No server, no build step. */
(function () {
  "use strict";

  const DATA_URL = "dashboard_data.json";
  const MIN_N_RATE = 10;        // below this many papers a rate is not drawn (tiles still show n)
  const MIN_N_JOURNAL = 30;     // journals need this many papers under the current filters to be plotted
  const CELL_OFFSET = 4;        // [year, hi, journal, country, ...counts]
  const FUNDER_OFFSET = 3;      // [year, hi, funder, ...counts]

  let DATA = null;
  const K = {};                 // count key -> index within the counts part of a row
  const state = {
    disciplines: [],            // selected discipline keys (ordered as in DATA)
    focus: null,
    yearMin: null,
    yearMax: null,
    journal: "",                // journal key (normalised name) or ""
    country: "",                // ISO2 or "Other" or ""
    funder: "",                 // funder name or ""
    hi: false,
    metric: "oa",
    sort: {},                   // per-table sort state
  };

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
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

  function tokens() {
    const cs = getComputedStyle(document.documentElement);
    const get = (name) => cs.getPropertyValue(name).trim();
    return {
      ink: get("--ink"), ink2: get("--ink-2"), ink3: get("--ink-3"), grid: get("--grid"),
      border: get("--border"), surface: get("--surface"), surface2: get("--surface-2"), font: get("--font"),
    };
  }

  function discByKey(key) { return DATA.disciplines.find((d) => d.key === key); }
  function focusDisc() { return discByKey(state.focus); }
  function selectedDiscs() { return DATA.disciplines.filter((d) => state.disciplines.includes(d.key)); }
  function yearsInRange() { return DATA.years.filter((y) => y >= state.yearMin && y <= state.yearMax); }

  // ------------------------------------------------------------------ aggregation
  function emptyCounts() { return new Array(DATA.count_keys.length).fill(0); }
  function addRow(acc, row, offset) { for (let i = 0; i < acc.length; i++) acc[i] += row[offset + i]; }

  function indexOfKey(list, key, prop) {
    if (!key) return null;
    const i = list.findIndex((item) => (prop ? item[prop] : item) === key);
    return i < 0 ? -1 : i;
  }

  /** Index filters for a discipline; -1 for a dimension means "requested value not present here". */
  function filtersFor(disc) {
    return {
      journal: indexOfKey(disc.journals, state.journal, "key"),
      country: indexOfKey(disc.countries, state.country, "key"),
      funder: indexOfKey(disc.funders, state.funder),
    };
  }

  /** Aggregate counts by year for one discipline under the current filters.
   *  Returns {byYear: Map<year, counts>, total: counts, applicable: bool}. */
  function aggregateDiscipline(disc, opts) {
    const o = Object.assign({ ignoreJournal: false, ignoreCountry: false }, opts);
    const f = filtersFor(disc);
    const byYear = new Map();
    const total = emptyCounts();
    const funderMode = state.funder !== "";
    if ((funderMode && f.funder === -1) ||
        (!o.ignoreJournal && f.journal === -1) || (!o.ignoreCountry && f.country === -1)) {
      return { byYear, total, applicable: false };
    }
    const rows = funderMode ? disc.funder_cells : disc.cells;
    const offset = funderMode ? FUNDER_OFFSET : CELL_OFFSET;
    for (const row of rows) {
      const year = row[0];
      if (year < state.yearMin || year > state.yearMax) continue;
      if (state.hi && row[1] !== 1) continue;
      if (funderMode) {
        if (row[2] !== f.funder) continue;
      } else {
        if (!o.ignoreJournal && f.journal !== null && row[2] !== f.journal) continue;
        if (!o.ignoreCountry && f.country !== null && row[3] !== f.country) continue;
      }
      let acc = byYear.get(year);
      if (!acc) { acc = emptyCounts(); byYear.set(year, acc); }
      addRow(acc, row, offset);
      addRow(total, row, offset);
    }
    return { byYear, total, applicable: true };
  }

  /** Aggregate counts grouped by one key dimension (journal or country index) for the focus discipline. */
  function aggregateByDimension(disc, dim) {
    const f = filtersFor(disc);
    const groups = new Map();
    const pos = dim === "journal" ? 2 : 3;
    for (const row of disc.cells) {
      const year = row[0];
      if (year < state.yearMin || year > state.yearMax) continue;
      if (state.hi && row[1] !== 1) continue;
      if (dim !== "journal" && f.journal !== null && row[2] !== f.journal) continue;
      if (dim !== "country" && f.country !== null && row[3] !== f.country) continue;
      let acc = groups.get(row[pos]);
      if (!acc) { acc = emptyCounts(); groups.set(row[pos], acc); }
      addRow(acc, row, CELL_OFFSET);
    }
    return groups;
  }

  function aggregateByFunder(disc) {
    const groups = new Map();
    for (const row of disc.funder_cells) {
      const year = row[0];
      if (year < state.yearMin || year > state.yearMax) continue;
      if (state.hi && row[1] !== 1) continue;
      let acc = groups.get(row[2]);
      if (!acc) { acc = emptyCounts(); groups.set(row[2], acc); }
      addRow(acc, row, FUNDER_OFFSET);
    }
    return groups;
  }

  function rate(counts, key) {
    if (!counts) return null;
    const denomKey = key === "reg" ? "n_abs" : "n";
    const denom = counts[K[denomKey]];
    if (!denom || denom < MIN_N_RATE) return null;
    return counts[K[key]] / denom;
  }
  function rateN(counts, key) { return counts ? counts[K[key === "reg" ? "n_abs" : "n"]] : 0; }

  function oaKnown(counts) { return DATA.oa_status_order.reduce((s, st) => s + counts[K["oa_" + st]], 0); }

  function metricAvailable(key) {
    if (key === "reg") return selectedDiscs().some((d) => d.available.registration);
    return true;
  }

  // ------------------------------------------------------------------ filter UI
  function buildFilters() {
    // Discipline chips
    const chips = $("discipline-chips");
    chips.replaceChildren();
    for (const d of DATA.disciplines) {
      const input = el("input", { type: "checkbox", id: "chip-" + d.key, checked: state.disciplines.includes(d.key) ? "" : null });
      const chip = el("label", { class: "chip" + (state.disciplines.includes(d.key) ? " is-on" : ""), for: "chip-" + d.key },
        [input, el("span", { class: "swatch", "aria-hidden": "true" }), el("span", { text: d.label })]);
      chip.style.setProperty("--c", d.color);
      input.addEventListener("change", () => {
        const on = input.checked;
        const next = DATA.disciplines.map((x) => x.key).filter((k) => (k === d.key ? on : state.disciplines.includes(k)));
        if (!next.length) { input.checked = true; return; }   // keep at least one
        state.disciplines = next;
        chip.classList.toggle("is-on", on);
        if (!state.disciplines.includes(state.focus)) state.focus = state.disciplines[0];
        buildFocusSelect();
        buildDimensionSelects();
        renderAll();
      });
      chips.append(chip);
    }
    buildFocusSelect();

    // Year range
    const yMin = $("year-min"), yMax = $("year-max");
    const lo = DATA.years[0], hi = DATA.years[DATA.years.length - 1];
    for (const inp of [yMin, yMax]) { inp.min = lo; inp.max = hi; }
    yMin.value = state.yearMin; yMax.value = state.yearMax;
    const onYear = () => {
      let a = +yMin.value, b = +yMax.value;
      if (a > b) { if (document.activeElement === yMin) b = a; else a = b; }
      state.yearMin = a; state.yearMax = b;
      yMin.value = a; yMax.value = b;
      updateYearReadout();
      renderAll();
    };
    yMin.addEventListener("input", onYear);
    yMax.addEventListener("input", onYear);
    const fill = el("span", { class: "range-fill", "aria-hidden": "true" });
    yMin.parentElement.append(fill);
    updateYearReadout();

    buildDimensionSelects();
    $("journal-select").addEventListener("change", (e) => { state.journal = e.target.value; syncExclusive(); renderAll(); });
    $("country-select").addEventListener("change", (e) => { state.country = e.target.value; syncExclusive(); renderAll(); });
    $("funder-select").addEventListener("change", (e) => { state.funder = e.target.value; syncExclusive(); renderAll(); });

    $("hi-all").addEventListener("click", () => setHi(false));
    $("hi-only").addEventListener("click", () => setHi(true));

    // Metric picker
    const ms = $("metric-select");
    ms.replaceChildren();
    for (const m of DATA.metrics) ms.append(el("option", { value: m.key, text: m.label }));
    ms.value = state.metric;
    ms.addEventListener("change", (e) => { state.metric = e.target.value; renderTrend(); });

    $("reset-btn").addEventListener("click", () => { resetState(); buildFilters(); renderAll(); });
    $("download-btn").addEventListener("click", downloadCsv);
    $("focus-select").addEventListener("change", (e) => {
      state.focus = e.target.value;
      buildDimensionSelects();
      renderAll();
    });
  }

  function updateYearReadout() {
    $("year-readout").textContent = state.yearMin === state.yearMax ? String(state.yearMin) : state.yearMin + "–" + state.yearMax;
    const lo = DATA.years[0], hi = DATA.years[DATA.years.length - 1];
    const fill = document.querySelector(".range-fill");
    if (fill && hi > lo) {
      const a = (state.yearMin - lo) / (hi - lo) * 100, b = (state.yearMax - lo) / (hi - lo) * 100;
      fill.style.left = a + "%"; fill.style.width = (b - a) + "%";
    }
  }

  function buildFocusSelect() {
    const sel = $("focus-select");
    sel.replaceChildren();
    for (const d of selectedDiscs()) sel.append(el("option", { value: d.key, text: d.label }));
    sel.value = state.focus;
  }

  function fillSelect(sel, placeholder, options, current) {
    sel.replaceChildren(el("option", { value: "", text: placeholder }));
    for (const o of options) sel.append(el("option", { value: o.value, text: o.label }));
    sel.value = options.some((o) => o.value === current) ? current : "";
    return sel.value;
  }

  function buildDimensionSelects() {
    const d = focusDisc();
    const top = DATA.top_n || {};
    state.journal = fillSelect($("journal-select"), "All journals",
      d.journals.map((j) => ({ value: j.key, label: j.key === "Other" ? "Other (outside top " + (top.journals || "") + ")" : j.label })), state.journal);
    const countryOpts = d.available.country
      ? d.countries.map((c) => ({ value: c.key, label: c.key === "Other" ? "Other countries" : c.label + (c.label !== c.key ? " (" + c.key + ")" : "") }))
      : [];
    state.country = fillSelect($("country-select"), d.available.country ? "All countries" : "Not available", countryOpts, state.country);
    const funderOpts = d.available.funders
      ? d.funders.map((f) => ({ value: f, label: f === "Other" ? "Other funders (outside top " + (top.funders || "") + ")" : f }))
      : [];
    state.funder = fillSelect($("funder-select"), d.available.funders ? "All funders" : "Not available", funderOpts, state.funder);
    $("country-select").disabled = !d.available.country;
    $("funder-select").disabled = !d.available.funders;
    syncExclusive();
  }

  /** Funder filter cannot combine with journal/country (different aggregate); disable accordingly. */
  function syncExclusive() {
    const d = focusDisc();
    const funderMode = state.funder !== "";
    const dimMode = state.journal !== "" || state.country !== "";
    $("journal-select").disabled = funderMode;
    $("country-select").disabled = funderMode || !d.available.country;
    $("funder-select").disabled = dimMode || !d.available.funders;
    const note = $("filter-note");
    if (funderMode) {
      note.textContent = "Funder filter active: papers are counted once under each listed funder, so the journal and country breakdowns are unavailable until the funder filter is cleared.";
    } else if (dimMode) {
      note.textContent = "Journal / country filter active: the funder table shows discipline-wide figures for the selected years and subset.";
    } else {
      note.textContent = "";
    }
  }

  function setHi(on) {
    state.hi = on;
    $("hi-all").classList.toggle("is-active", !on); $("hi-all").setAttribute("aria-pressed", String(!on));
    $("hi-only").classList.toggle("is-active", on); $("hi-only").setAttribute("aria-pressed", String(on));
    renderAll();
  }

  function resetState() {
    state.disciplines = DATA.disciplines.map((d) => d.key);
    state.focus = state.disciplines.includes("stroke") ? "stroke" : state.disciplines[0];
    state.yearMin = DATA.years[0];
    state.yearMax = DATA.years[DATA.years.length - 1];
    state.journal = ""; state.country = ""; state.funder = ""; state.hi = false; state.metric = "oa";
    $("hi-all").classList.add("is-active"); $("hi-all").setAttribute("aria-pressed", "true");
    $("hi-only").classList.remove("is-active"); $("hi-only").setAttribute("aria-pressed", "false");
    const old = document.querySelector(".range-fill"); if (old) old.remove();
  }

  function selectionLabel() {
    const parts = [];
    parts.push(state.hi ? "high-impact subset" : "all papers");
    if (state.journal) parts.push(labelFor(focusDisc().journals, state.journal));
    if (state.country) parts.push(labelFor(focusDisc().countries, state.country));
    if (state.funder) parts.push(state.funder);
    parts.push(state.yearMin === state.yearMax ? String(state.yearMin) : state.yearMin + "–" + state.yearMax);
    return parts.join(" · ");
  }
  function labelFor(list, key) { const item = list.find((x) => x.key === key); return item ? item.label : key; }

  // ------------------------------------------------------------------ Plotly helpers
  function baseLayout(t) {
    return {
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: t.font, color: t.ink2, size: 12 },
      margin: { l: 52, r: 24, t: 12, b: 44 },
      xaxis: { gridcolor: "rgba(0,0,0,0)", linecolor: t.border, zeroline: false, tickfont: { color: t.ink3 }, fixedrange: true },
      yaxis: { gridcolor: t.grid, zeroline: false, tickfont: { color: t.ink3 }, fixedrange: true },
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
    div.classList.remove("chart-empty");
    if (!traces.length) {
      Plotly.purge(div);
      div.replaceChildren(el("div", { class: "chart-empty", text: "No data for this selection." }));
      return;
    }
    if (div.querySelector(".chart-empty")) div.replaceChildren();
    Plotly.react(div, traces, layout, PLOT_CONFIG);
  }

  function partialYearShapes(t, years) {
    const partial = (DATA.partial_years || []).filter((y) => years.includes(y));
    if (!partial.length) return { shapes: [], annotations: [] };
    const x0 = Math.min(...partial) - 0.5, x1 = Math.max(...partial) + 0.5;
    return {
      shapes: [{ type: "rect", xref: "x", yref: "paper", x0, x1, y0: 0, y1: 1, fillcolor: t.surface2, opacity: 0.7, line: { width: 0 }, layer: "below" }],
      annotations: [{ xref: "x", yref: "paper", x: (x0 + x1) / 2, y: 1, yanchor: "bottom", text: "incomplete", showarrow: false, font: { color: t.ink3, size: 11 } }],
    };
  }

  // ------------------------------------------------------------------ renderers
  function renderAll() {
    // Decide card visibility first so chart widths are measured against the final grid layout.
    const d = focusDisc();
    $("das-card").hidden = !d.available.das;
    $("country-card").hidden = !d.available.country;
    $("funder-card").hidden = !d.available.funders;
    for (const grid of document.querySelectorAll(".grid-2")) {
      const visible = [...grid.children].filter((c) => !c.hidden).length;
      grid.classList.toggle("is-single", visible <= 1);
    }
    renderTiles();
    renderTrend();
    renderOaStatus();
    renderDas();
    renderJournals();
    renderCountries();
    renderFunders();
  }

  function renderTiles() {
    const d = focusDisc();
    const agg = aggregateDiscipline(d);
    const c = agg.total;
    const n = c[K.n];
    const tiles = $("tiles");
    tiles.replaceChildren();
    const mk = (label, value, sub, frac, na) => {
      const tile = el("div", { class: "tile" + (na ? " is-na" : "") }, [
        el("div", { class: "tile-label", text: label }),
        el("div", { class: "tile-value", text: value }),
        el("div", { class: "tile-sub", text: sub }),
      ]);
      if (frac !== null && frac !== undefined) {
        const bar = el("div", { class: "tile-bar" }, el("span"));
        bar.firstChild.style.width = clamp(frac * 100, 0, 100) + "%";
        bar.style.setProperty("--c", d.color);
        tile.append(bar);
      }
      return tile;
    };
    tiles.append(mk("Papers · " + d.label, fmtInt(n), agg.applicable ? selectionLabel() : "selection not available for " + d.label, null, !agg.applicable));
    for (const m of DATA.metrics) {
      if (m.key === "material") continue;
      const available = m.key !== "reg" || d.available.registration;
      const r = available ? rate(c, m.key) : null;
      const denom = rateN(c, m.key);
      const sub = !available ? "not in this dataset" : (m.key === "reg" ? "of " + fmtInt(denom) + " with abstract" : fmtInt(c[K[m.key]]) + " of " + fmtInt(denom));
      tiles.append(mk(m.label, fmtPct(r), sub, r, r === null));
    }
    if (d.available.das && c[K.das_audited] > 0) {
      const r = c[K.das_stmt] / c[K.das_audited];
      tiles.append(mk("Has data statement", fmtPct(r), "of " + fmtInt(c[K.das_audited]) + " audited (OA full text)", r, false));
    }
  }

  function renderTrend() {
    const t = tokens();
    const years = yearsInRange();
    const metric = DATA.metrics.find((m) => m.key === state.metric) || DATA.metrics[0];
    const discs = selectedDiscs();
    const traces = [], annotations = [], tableRows = [];
    for (const d of discs) {
      if (metric.key === "reg" && !d.available.registration) continue;
      const agg = aggregateDiscipline(d);
      if (!agg.applicable) continue;
      const ys = years.map((y) => rate(agg.byYear.get(y), metric.key));
      const ns = years.map((y) => rateN(agg.byYear.get(y), metric.key));
      if (ys.every((v) => v === null)) continue;
      const isFocus = d.key === state.focus;
      traces.push({
        type: "scatter", mode: "lines+markers", name: d.label, x: years, y: ys, customdata: ns,
        line: { color: d.color, width: isFocus ? 3 : 2, shape: "linear" },
        marker: { size: isFocus ? 8 : 6, color: d.color, line: { color: t.surface, width: 2 } },
        opacity: isFocus ? 1 : 0.8, connectgaps: false,
        hovertemplate: "%{y:.1%} · n = %{customdata:,}<extra>" + d.label + "</extra>",
      });
      let last = ys.length - 1; while (last >= 0 && ys[last] === null) last--;
      if (last >= 0) annotations.push({
        x: years[last], y: ys[last], xanchor: "left", yanchor: "middle", xshift: 8, text: d.label, showarrow: false,
        font: { color: t.ink2, size: 12, weight: isFocus ? 600 : 400 },
      });
      tableRows.push({ label: d.label, ys, ns });
    }
    const layout = baseLayout(t);
    const partial = partialYearShapes(t, years);
    Object.assign(layout, {
      showlegend: traces.length >= 2,
      margin: { l: 52, r: 110, t: 20, b: 48 },
      hovermode: "x unified",
      yaxis: Object.assign(layout.yaxis, { tickformat: ".0%", rangemode: "tozero", title: { text: metric.label, font: { color: t.ink3, size: 12 } } }),
      xaxis: Object.assign(layout.xaxis, { dtick: tickStep("trend-chart", years.length), tickangle: 0, range: [years[0] - 0.4, years[years.length - 1] + 0.4] }),
      annotations: annotations.concat(partial.annotations),
      shapes: partial.shapes,
    });
    plot("trend-chart", traces, layout);
    $("trend-title").textContent = metric.label + " by year";
    $("trend-sub").textContent = metric.definition + " Selection: " + selectionLabel() + ". Points with fewer than " + MIN_N_RATE + " papers are omitted.";
    // Table view
    const cols = [{ key: "label", label: "Discipline" }].concat(years.map((y) => ({ key: "y" + y, label: String(y), fmt: "pct" })));
    const rows = tableRows.map((r) => { const o = { label: r.label }; years.forEach((y, i) => { o["y" + y] = r.ys[i]; }); return o; });
    renderTable("trend-table", cols, rows, { sortable: false });
  }

  function renderStacked(opts) {
    // opts: {id, titleId, subId, cardId, order, labels, colors, prefix, denomFn, title, subtitle, available}
    const card = $(opts.cardId);
    if (!opts.available) { card.hidden = true; return; }
    card.hidden = false;
    const t = tokens();
    const d = focusDisc();
    const years = yearsInRange();
    const agg = aggregateDiscipline(d);
    const shares = {}, counts = {}, denoms = years.map((y) => (agg.byYear.get(y) ? opts.denomFn(agg.byYear.get(y)) : 0));
    const anyDenom = denoms.some((v) => v > 0);
    if (!agg.applicable || !anyDenom) {
      plot(opts.id, [], {});
      $(opts.subId).textContent = opts.subtitleEmpty;
      renderTable(opts.tableId, [], [], {});
      return;
    }
    const traces = [];
    const darkIdx = new Set([0, 1, 2]); // first three ramp steps are dark: white labels
    opts.order.forEach((cat, idx) => {
      shares[cat] = years.map((y, i) => (denoms[i] ? (agg.byYear.get(y)[K[opts.prefix + cat]] / denoms[i]) : null));
      counts[cat] = years.map((y) => (agg.byYear.get(y) ? agg.byYear.get(y)[K[opts.prefix + cat]] : 0));
      traces.push({
        type: "bar", name: opts.labels[cat] || cat, x: years, y: shares[cat], customdata: counts[cat],
        marker: { color: opts.colors[cat], line: { color: t.surface, width: 2 } },
        text: shares[cat].map((v) => (v !== null && v >= 0.07 ? fmtPct(v, 0) : "")),
        textposition: "inside", insidetextanchor: "middle",
        insidetextfont: { color: darkIdx.has(idx) ? "#ffffff" : "#1d1d1b", size: 11 },
        hovertemplate: "%{y:.1%} · %{customdata:,} papers<extra>" + (opts.labels[cat] || cat) + "</extra>",
      });
    });
    const layout = baseLayout(t);
    // Category x-axis: shapes/annotations in category-index coordinates.
    const partialIdx = years.map((y, i) => ((DATA.partial_years || []).includes(y) ? i : -1)).filter((i) => i >= 0);
    const shapes = [], annotations = [];
    if (partialIdx.length) {
      const x0 = Math.min(...partialIdx) - 0.5, x1 = Math.max(...partialIdx) + 0.5;
      shapes.push({ type: "rect", xref: "x", yref: "paper", x0, x1, y0: 0, y1: 1, fillcolor: t.surface2, opacity: 0.7, line: { width: 0 }, layer: "below" });
      annotations.push({ xref: "x", yref: "paper", x: (x0 + x1) / 2, y: 1, yanchor: "bottom", text: "incomplete", showarrow: false, font: { color: t.ink3, size: 11 } });
    }
    Object.assign(layout, {
      barmode: "stack", bargap: 0.28,
      margin: { l: 52, r: 16, t: 20, b: 80 },
      legend: Object.assign(layout.legend, { y: -0.2, traceorder: "normal" }),
      yaxis: Object.assign(layout.yaxis, { tickformat: ".0%", range: [0, 1.0001] }),
      xaxis: Object.assign(layout.xaxis, { type: "category", tickvals: years.filter((y, i) => i % tickStep(opts.id, years.length) === 0), tickangle: 0 }),
      shapes, annotations,
      uniformtext: { mode: "hide", minsize: 10 },
    });
    plot(opts.id, traces, layout);
    const totalDenom = denoms.reduce((a, b) => a + b, 0);
    $(opts.titleId).textContent = opts.title + " · " + d.label;
    $(opts.subId).textContent = opts.subtitle(totalDenom);
    const cols = [{ key: "cat", label: "Category" }].concat(years.map((y) => ({ key: "y" + y, label: String(y), fmt: "pct" })));
    const rows = opts.order.map((cat) => { const o = { cat: opts.labels[cat] || cat }; years.forEach((y, i) => { o["y" + y] = shares[cat][i]; }); return o; });
    rows.push(Object.assign({ cat: "n (denominator)" }, Object.fromEntries(years.map((y, i) => ["y" + y, denoms[i]]))));
    renderTable(opts.tableId, cols, rows, { sortable: false, rowFmt: (row) => (row.cat === "n (denominator)" ? "int" : null) });
  }

  function renderOaStatus() {
    const d = focusDisc();
    renderStacked({
      id: "oa-chart", titleId: "oa-title", subId: "oa-sub", cardId: "oa-card", tableId: "oa-table",
      order: DATA.oa_status_order, labels: Object.fromEntries(DATA.oa_status_order.map((s) => [s, s[0].toUpperCase() + s.slice(1)])),
      colors: DATA.oa_status_colors, prefix: "oa_", denomFn: oaKnown,
      title: "Open-access status by year",
      subtitle: (n) => "OpenAlex OA status as a share of papers with a known status (" + fmtInt(n) + "). " + selectionLabel() + ".",
      subtitleEmpty: "No OA-status data for this selection.",
      available: d.available.oa_status,
    });
  }

  function renderDas() {
    const d = focusDisc();
    renderStacked({
      id: "das-chart", titleId: "das-title", subId: "das-sub", cardId: "das-card", tableId: "das-table",
      order: DATA.das_order, labels: DATA.das_labels, colors: DATA.das_colors, prefix: "das_",
      denomFn: (c) => c[K.das_audited],
      title: "Data-availability statements by year",
      subtitle: (n) => "Primary category of the data-availability statement in " + fmtInt(n) + " audited open-access full texts (Europe PMC sample). " + selectionLabel() + ".",
      subtitleEmpty: "No audited papers in this selection.",
      available: d.available.das,
    });
  }

  function renderJournals() {
    const t = tokens();
    const d = focusDisc();
    const card = $("journal-card");
    if (state.funder !== "") {
      card.hidden = false;
      plot("journal-chart", [], {});
      $("journal-sub").textContent = "Journal breakdown is unavailable while a funder filter is active.";
      renderTable("journal-table", [], [], {});
      return;
    }
    card.hidden = false;
    const groups = aggregateByDimension(d, "journal");
    const items = [];
    for (const [idx, c] of groups.entries()) {
      const j = d.journals[idx];
      if (!j || j.key === "Other") continue;
      if (c[K.n] < MIN_N_JOURNAL) continue;
      items.push({ label: j.label, n: c[K.n], oa: rate(c, "oa"), data: rate(c, "data"), code: rate(c, "code"), preprint: rate(c, "preprint") });
    }
    items.sort((a, b) => (b.oa || 0) - (a.oa || 0));
    const narrow = isNarrow("journal-chart");
    const metrics = narrow ? [["oa", "Open access", "x"]] : [["oa", "Open access", "x"], ["data", "Data sharing", "x2"], ["code", "Code sharing", "x3"]];
    const traces = [];
    const labels = items.map((i) => i.label).reverse();   // Plotly draws categorical y bottom-up
    const maxData = Math.max(0.0001, ...items.map((i) => i.data || 0), ...items.map((i) => i.code || 0));
    for (const [key, name, xaxis] of metrics) {
      const vals = items.map((i) => i[key]).reverse();
      const ns = items.map((i) => i.n).reverse();
      traces.push({
        type: "bar", orientation: "h", x: vals, y: labels, xaxis, yaxis: "y", width: 0.12, showlegend: false,
        marker: { color: t.border }, hoverinfo: "skip",
      });
      traces.push({
        type: "scatter", mode: "markers+text", x: vals, y: labels, xaxis, yaxis: "y", name, showlegend: false,
        customdata: ns, marker: { size: 9, color: d.color, line: { color: t.surface, width: 2 } },
        text: vals.map((v) => fmtPct(v, key === "oa" ? 0 : 1)), textposition: "middle right", textfont: { color: t.ink2, size: 11 },
        hovertemplate: "%{x:.1%} · n = %{customdata:,}<extra>" + name + " · %{y}</extra>",
      });
    }
    const height = Math.max(240, 24 * items.length + 90);
    const layout = baseLayout(t);
    const axisBase = { zeroline: false, gridcolor: t.grid, tickfont: { color: t.ink3, size: 11 }, fixedrange: true, side: "top", tickformat: ".0%" };
    Object.assign(layout, {
      height, showlegend: false, margin: { l: 10, r: 24, t: 44, b: 16 },
      yaxis: { automargin: true, tickfont: { color: t.ink2, size: 12 }, fixedrange: true, gridcolor: "rgba(0,0,0,0)" },
      xaxis: Object.assign({}, axisBase, { domain: [0, narrow ? 1 : 0.36], range: [0, 1.15], anchor: "y", title: { text: "Open access", font: { color: t.ink2, size: 12 } } }),
      xaxis2: Object.assign({}, axisBase, { domain: [0.42, 0.69], range: [0, maxData * 1.6], anchor: "y", title: { text: "Data sharing", font: { color: t.ink2, size: 12 } }, tickformat: ".1%" }),
      xaxis3: Object.assign({}, axisBase, { domain: [0.75, 1], range: [0, maxData * 1.6], anchor: "y", title: { text: "Code sharing", font: { color: t.ink2, size: 12 } }, tickformat: ".1%" }),
      hovermode: "closest",
    });
    plot("journal-chart", traces, layout);
    $("journal-title").textContent = "Journals · " + d.label;
    $("journal-sub").textContent = items.length
      ? items.length + " journals with at least " + MIN_N_JOURNAL + " papers (" + selectionLabel() + "), sorted by open-access rate. Top-" + (DATA.top_n.journals || "") + " journals by volume only; others are folded into “Other”." + (narrow ? " Data and code columns are in the table view on small screens." : "")
      : "No journal reaches " + MIN_N_JOURNAL + " papers under this selection.";
    renderTable("journal-table", [
      { key: "label", label: "Journal" }, { key: "n", label: "Papers", fmt: "int" }, { key: "oa", label: "OA", fmt: "pct", bar: true },
      { key: "data", label: "Data", fmt: "pct" }, { key: "code", label: "Code", fmt: "pct" }, { key: "preprint", label: "Preprint", fmt: "pct" },
    ], items, { sortable: true, color: d.color, name: "journals" });
  }

  function dimensionTableRows(d, groups, list, labelOf) {
    const rows = [];
    for (const [idx, c] of groups.entries()) {
      const item = list[idx];
      if (!item) continue;
      rows.push({
        label: labelOf(item), other: (item.key || item) === "Other" || item === "(no funder listed)",
        n: c[K.n], oa: rate(c, "oa"), data: rate(c, "data"), code: rate(c, "code"), preprint: rate(c, "preprint"),
        reg: d.available.registration ? rate(c, "reg") : null,
      });
    }
    return rows;
  }

  const DIM_COLUMNS = (d, first) => [
    { key: "label", label: first }, { key: "n", label: "Papers", fmt: "int" },
    { key: "oa", label: "OA", fmt: "pct", bar: true }, { key: "data", label: "Data", fmt: "pct" },
    { key: "code", label: "Code", fmt: "pct" }, { key: "preprint", label: "Preprint", fmt: "pct" },
  ].concat(d.available.registration ? [{ key: "reg", label: "Registered", fmt: "pct" }] : []);

  function renderCountries() {
    const d = focusDisc();
    const card = $("country-card");
    if (!d.available.country) { card.hidden = true; return; }
    card.hidden = false;
    $("country-title").textContent = "First-author countries · " + d.label;
    if (state.funder !== "") {
      $("country-sub").textContent = "Country breakdown is unavailable while a funder filter is active.";
      renderTable("country-table", [], [], {});
      return;
    }
    const groups = aggregateByDimension(d, "country");
    const rows = dimensionTableRows(d, groups, d.countries, (c) => (c.key === "Other" ? "Other countries" : c.label));
    $("country-sub").textContent = "Top-" + (DATA.top_n.countries || "") + " first-author countries by volume; " + selectionLabel() + (state.country ? " (country filter ignored here)" : "") + ". Click a column to sort.";
    renderTable("country-table", DIM_COLUMNS(d, "Country"), rows, { sortable: true, color: d.color, name: "countries" });
  }

  function renderFunders() {
    const d = focusDisc();
    const card = $("funder-card");
    if (!d.available.funders) { card.hidden = true; return; }
    card.hidden = false;
    const groups = aggregateByFunder(d);
    const rows = dimensionTableRows(d, groups, d.funders, (f) => (f === "Other" ? "Other funders" : f));
    $("funder-title").textContent = "Funders · " + d.label;
    const scope = (state.journal || state.country) ? " Journal/country filters do not apply to funders." : "";
    $("funder-sub").textContent = "Top-" + (DATA.top_n.funders || "") + " funders by volume (a paper counts once under each listed funder); " + (state.hi ? "high-impact subset" : "all papers") + ", " + state.yearMin + "–" + state.yearMax + "." + scope;
    renderTable("funder-table", DIM_COLUMNS(d, "Funder"), rows, { sortable: true, color: d.color, name: "funders" });
  }

  // ------------------------------------------------------------------ tables
  function renderTable(containerId, cols, rows, opts) {
    const container = $(containerId);
    container.replaceChildren();
    if (!cols.length || !rows.length) return;
    const o = Object.assign({ sortable: false, color: null, name: containerId, rowFmt: null }, opts);
    let sortKey = null, sortDir = "desc";
    if (o.sortable) {
      const saved = state.sort[o.name] || { key: "n", dir: "desc" };
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
    const maxBar = Math.max(0.0001, ...rows.map((r) => (typeof r.oa === "number" ? r.oa : 0)));
    for (const r of rows) {
      const row = el("tr", { class: r.other ? "is-other" : null });
      const forced = o.rowFmt ? o.rowFmt(r) : null;
      for (const c of cols) {
        const v = r[c.key];
        const fmt = forced || c.fmt;
        const text = fmt === "pct" ? fmtPct(v) : fmt === "int" ? fmtInt(v) : (v === null || v === undefined ? "—" : String(v));
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

  // ------------------------------------------------------------------ CSV download
  function downloadCsv() {
    const years = yearsInRange();
    const header = ["discipline", "year", "subset", "journal", "first_author_country", "funder"].concat(DATA.count_keys)
      .concat(DATA.metrics.map((m) => m.key + "_rate"));
    const lines = [header.join(",")];
    const q = (s) => '"' + String(s).replace(/"/g, '""') + '"';
    for (const d of selectedDiscs()) {
      const agg = aggregateDiscipline(d);
      if (!agg.applicable) continue;
      for (const y of years) {
        const c = agg.byYear.get(y);
        if (!c) continue;
        const rates = DATA.metrics.map((m) => {
          const denom = c[K[m.key === "reg" ? "n_abs" : "n"]];
          return denom ? (c[K[m.key]] / denom).toFixed(4) : "";
        });
        lines.push([d.key, y, state.hi ? "high_impact" : "all", q(state.journal || "all"), q(state.country || "all"), q(state.funder || "all")]
          .concat(c).concat(rates).join(","));
      }
    }
    const blob = new Blob([lines.join("\n") + "\n"], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: "open_science_selection_" + DATA.run_date + ".csv" });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // ------------------------------------------------------------------ methods + footer
  function renderMethods() {
    const body = $("methods-body");
    body.replaceChildren();
    body.append(el("h3", { text: "Metric definitions" }));
    const dl = el("dl");
    for (const m of DATA.metrics) { dl.append(el("dt", { text: m.label }), el("dd", { text: m.definition })); }
    dl.append(el("dt", { text: "OA status" }), el("dd", { text: "OpenAlex classification (diamond, gold, hybrid, green, bronze, closed); shares use papers with a known status as the denominator." }));
    dl.append(el("dt", { text: "Data-availability statement" }), el("dd", { text: "Primary category of the statement found in the full text of audited open-access articles (Europe PMC); categories: " + DATA.das_order.map((c) => DATA.das_labels[c] || c).join(", ") + "." }));
    dl.append(el("dt", { text: "High-impact subset" }), el("dd", { text: DATA.high_impact.description }));
    body.append(dl);
    body.append(el("h3", { text: "Corpus" }));
    const ul1 = el("ul");
    for (const d of DATA.disciplines) {
      ul1.append(el("li", { text: d.label + ": " + fmtInt(d.totals.in_corpus) + " articles/reviews kept of " + fmtInt(d.totals.rows_in_file) + " retrieved records (" + fmtInt(d.totals.dropped) + " excluded; rule: " + (DATA.corpus_rule[d.key] || "n/a") + "). Years " + d.years[0] + "–" + d.years[d.years.length - 1] + "." }));
    }
    body.append(ul1);
    body.append(el("h3", { text: "Reading notes" }));
    const ul2 = el("ul");
    for (const n of DATA.methods_notes) ul2.append(el("li", { text: n }));
    ul2.append(el("li", { text: "Rates are not drawn for cells with fewer than " + MIN_N_RATE + " papers; journals need at least " + MIN_N_JOURNAL + " papers under the current filters to appear in the journal chart." }));
    body.append(ul2);
    body.append(el("h3", { text: "How this page works" }));
    body.append(el("p", { class: "card-sub", text: "The pipeline writes pre-aggregated counts (discipline × year × high-impact × journal × first-author country, plus discipline × year × high-impact × funder) to dashboard_data.json; this page sums the counts for your selection and divides. No row-level data is shipped. Generated " + DATA.generated_at + "." }));
  }

  function renderFooter() {
    const f = $("footer-body");
    f.replaceChildren();
    const cit = DATA.citation || {};
    f.append(el("p", {}, ["Benchmark run date: ", el("strong", { text: DATA.run_date }), ". Source code: ",
      el("a", { href: DATA.repo_url, rel: "noopener", text: DATA.repo_url.replace(/^https?:\/\//, "") }),
      " · Data and legacy dashboard: ", el("a", { href: DATA.outputs_repo_url, rel: "noopener", text: DATA.outputs_repo_url.replace(/^https?:\/\//, "") }),
      " · ", el("a", { href: "legacy.html", text: "static version" })]));
    if (cit.title) {
      f.append(el("p", {}, ["Cite: ", el("em", { text: cit.title }), cit.version ? " (v" + cit.version + ")" : "", cit["date-released"] ? ", " + cit["date-released"] : "", ". ",
        el("a", { href: DATA.repo_url + "/blob/main/CITATION.cff", rel: "noopener", text: "CITATION.cff" }), cit.license ? " · " + cit.license + " licence." : ""]));
    }
    f.append(el("p", {}, ["Data: OpenAlex, Unpaywall, Crossref, Europe PMC. Charts: Plotly. ", el("code", { text: "dashboard_data.json" }), " (", el("a", { href: DATA_URL, text: "download" }), ")"]));
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
      const next = THEMES[(THEMES.indexOf(current) + 1) % THEMES.length];
      applyTheme(next);
      if (DATA) renderAll();
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
      const e = $("error");
      e.hidden = false;
      e.textContent = "Could not load " + DATA_URL + " (" + err.message + "). Serve this folder over HTTP (e.g. python -m http.server) — browsers block fetch() from file://.";
      return;
    }
    DATA = payload;
    DATA.count_keys.forEach((k, i) => { K[k] = i; });
    if (!DATA.disciplines.length) { $("error").hidden = false; $("error").textContent = "No disciplines in the data file."; return; }
    resetState();
    buildFilters();
    renderMethods();
    renderFooter();
    renderAll();
    if (!metricAvailable("reg")) {
      const opt = $("metric-select").querySelector('option[value="reg"]');
      if (opt) opt.disabled = true;
    }
  }

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    if (!DATA) return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(renderAll, 200);
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
