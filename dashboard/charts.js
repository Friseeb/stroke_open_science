/* charts.js — hand-drawn SVG charts for the benchmark, on D3 v7.
 * Tufte: range-frame axes, no gridlines, direct labels, small multiples with ghosted context, slopegraphs,
 * dot plots instead of grouped bars, 2px surface gaps instead of strokes. Every chart keeps its <svg> between
 * renders so a selection change animates (lines morph, bars grow, dots slide); motion is off under
 * prefers-reduced-motion. One tooltip for the page; every value is also in the table twin. */
window.Charts = (function () {
  "use strict";

  const FONT = '"Instrument Sans", "Helvetica Neue", Helvetica, Arial, sans-serif';
  const SVG_NS = "http://www.w3.org/2000/svg";
  const reduced = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const DUR = () => (reduced() ? 0 : 650);
  const EASE = d3.easeCubicOut;

  function theme() {
    const cs = getComputedStyle(document.documentElement);
    const g = (n) => cs.getPropertyValue(n).trim();
    return { ink: g("--ink"), ink2: g("--ink-2"), ink3: g("--ink-3"), grid: g("--grid"), hair: g("--hair"), bg: g("--bg"),
      surface2: g("--surface-2"), accent: g("--accent"), neutral: g("--neutral-mark") };
  }
  const fmtPct = (v, d) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : (v * 100).toFixed(d === undefined ? (v > 0 && v < 0.001 ? 2 : v < 0.1 ? 1 : 0) : d) + "%";
  const fmtInt = (v) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : Math.round(v).toLocaleString("en-US");
  const fmtX = (v) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : v.toFixed(1) + "×";
  const formatter = (kind) => (kind === "int" ? fmtInt : kind === "x" ? fmtX : kind === "pct1" ? (v) => fmtPct(v, 1) : fmtPct);
  /** Axis tick labels. Percent ticks keep as many decimals as the scale needs: a 0-0.6% axis must not read 0%, 0%, 1%. */
  const tickFormat = (kind, scale) => {
    if (kind === "int") return d3.format("~s");
    if (kind === "x") return (v) => v + "×";
    const ticks = scale ? scale.ticks(4) : [];
    const step = ticks.length > 1 ? Math.abs(ticks[1] - ticks[0]) * 100 : 1;
    const digits = step >= 1 ? 0 : step >= 0.1 ? 1 : 2;
    return (v) => (v * 100).toFixed(digits) + "%";
  };
  const textW = (s, size) => String(s || "").length * (size || 12) * 0.56;   // good enough for layout decisions
  const onDark = (hex) => { try { return d3.hcl(hex).l < 62; } catch (e) { return true; } };
  const truncate = (s, max) => (s.length > max ? s.slice(0, Math.max(1, max - 1)) + "…" : s);

  // ------------------------------------------------------------------ frame + layers
  /** The chart's <svg>, kept between renders so the same form morphs; a different form (`kind`) starts from a clean plot. */
  function frame(el, height, m, kind) {
    const width = Math.max(320, el.clientWidth || 800);
    let svg = d3.select(el).select("svg.ch");
    let fresh = svg.empty();
    if (fresh) { el.replaceChildren(); svg = d3.select(el).append("svg").attr("class", "ch"); }
    if (kind && svg.attr("data-kind") !== kind) { svg.selectAll("*").remove(); svg.attr("data-kind", kind); fresh = true; }
    svg.attr("viewBox", `0 0 ${width} ${height}`).attr("width", width).attr("height", height)
      .style("font-family", FONT).style("display", "block").style("max-width", "100%").style("height", "auto");
    let g = svg.select("g.plot");
    if (g.empty()) g = svg.append("g").attr("class", "plot");
    g.attr("transform", `translate(${m.left},${m.top})`);
    return { el, svg, g, width, height, m, iw: Math.max(10, width - m.left - m.right), ih: Math.max(10, height - m.top - m.bottom), fresh };
  }
  function layer(parent, name) { let l = parent.select("g." + name); if (l.empty()) l = parent.append("g").attr("class", name); return l; }
  function empty(el, text) { el.replaceChildren(); const d = document.createElement("div"); d.className = "chart-empty"; d.textContent = text || "No data for this selection."; el.append(d); }
  function hasSvg(el) { return !!el.querySelector("svg.ch"); }

  // ------------------------------------------------------------------ tooltip (one for the page)
  let tipEl = null;
  function tip() {
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.className = "ch-tip"; tipEl.hidden = true; tipEl.setAttribute("role", "status"); document.body.appendChild(tipEl); }
    return tipEl;
  }
  function showTip(evt, title, rows) {
    const t = tip();
    t.replaceChildren();
    if (title) { const h = document.createElement("div"); h.className = "ch-tip-title"; h.textContent = title; t.append(h); }
    for (const r of rows) {
      const row = document.createElement("div"); row.className = "ch-tip-row";
      const key = document.createElement("span"); key.className = "ch-tip-key" + (r.kind === "rect" ? " is-rect" : ""); key.style.background = r.color || "transparent";
      const val = document.createElement("strong"); val.textContent = r.value;
      const lab = document.createElement("span"); lab.className = "ch-tip-label"; lab.textContent = r.label;
      row.append(key, val, lab);
      if (r.sub) { const s = document.createElement("span"); s.className = "ch-tip-sub"; s.textContent = r.sub; row.append(s); }
      t.append(row);
    }
    t.hidden = false;
    moveTip(evt);
  }
  function moveTip(evt) {
    const t = tip(), pad = 14;
    const r = t.getBoundingClientRect();
    let x = evt.clientX + pad, y = evt.clientY + pad;
    if (x + r.width > innerWidth - 8) x = evt.clientX - r.width - pad;
    if (y + r.height > innerHeight - 8) y = evt.clientY - r.height - pad;
    t.style.left = Math.max(4, x) + "px"; t.style.top = Math.max(4, y) + "px";
  }
  function hideTip() { if (tipEl) tipEl.hidden = true; }

  // ------------------------------------------------------------------ axes (range frames: the line spans the data, nothing more)
  function yAxis(g, y, t, fmt, n) {
    const ax = layer(g, "yaxis");
    const ticks = y.ticks(n || 4);
    const lines = ax.selectAll("line.frame").data([0]);
    lines.enter().append("line").attr("class", "frame").merge(lines)
      .attr("x1", 0).attr("x2", 0).attr("y1", y(ticks[ticks.length - 1])).attr("y2", y(ticks[0])).attr("stroke", t.hair).attr("stroke-width", 1);
    const tk = ax.selectAll("g.tick").data(ticks, (d) => d);
    tk.exit().remove();
    const te = tk.enter().append("g").attr("class", "tick");
    te.append("line").attr("x1", -4).attr("x2", 0).attr("stroke", t.hair);
    te.append("text").attr("x", -9).attr("dy", "0.32em").attr("text-anchor", "end").attr("font-size", 11).attr("fill", t.ink3);
    const tm = te.merge(tk);
    tm.attr("transform", (d) => `translate(0,${y(d)})`);
    tm.select("text").text(fmt);
  }
  function xAxisBand(g, xs, xOf, ih, iw, t, every) {
    const ax = layer(g, "xaxis");
    const base = ax.selectAll("line.base").data([0]);
    base.enter().append("line").attr("class", "base").merge(base).attr("x1", 0).attr("x2", iw).attr("y1", ih + 0.5).attr("y2", ih + 0.5).attr("stroke", t.hair);
    const lab = ax.selectAll("text.xl").data(xs, (d) => d);
    lab.exit().remove();
    lab.enter().append("text").attr("class", "xl").attr("text-anchor", "middle").attr("font-size", 11).attr("fill", t.ink3).merge(lab)
      .attr("x", (d) => xOf(d)).attr("y", ih + 18).text((d, i) => (i % (every || 1) === 0 ? d : ""));
  }
  function partialBand(g, partial, xs, xOf, bw, ih, t) {
    const b = layer(g, "partial");
    const p = (partial || []).filter((y) => xs.includes(y));
    const d = p.length ? [p] : [];
    const r = b.selectAll("rect").data(d);
    r.exit().remove();
    r.enter().append("rect").attr("fill", t.surface2).merge(r)
      .attr("x", (p) => xOf(Math.min(...p)) - bw / 2).attr("width", (p) => xOf(Math.max(...p)) - xOf(Math.min(...p)) + bw).attr("y", -10).attr("height", ih + 10);
    const l = b.selectAll("text").data(d);
    l.exit().remove();
    l.enter().append("text").attr("font-size", 10).attr("fill", t.ink3).attr("text-anchor", "middle").merge(l)
      .attr("x", (p) => (xOf(Math.min(...p)) + xOf(Math.max(...p))) / 2).attr("y", -14).text("incomplete");
  }
  function milestones(g, markers, xs, xOf, bw, ih, iw, t) {
    const m = layer(g, "milestones");
    const data = iw < 560 ? [] : (markers || []).filter((e) => xs.includes(e.year));
    const grp = m.selectAll("g.ms").data(data, (d) => d.year);
    grp.exit().remove();
    const ge = grp.enter().append("g").attr("class", "ms");
    ge.append("line").attr("stroke", t.hair).attr("stroke-width", 1);
    ge.append("text").attr("font-size", 10).attr("fill", t.ink3).attr("dx", 4);
    ge.append("title");
    const gm = ge.merge(grp);
    gm.attr("transform", (d) => `translate(${xOf(d.year) - bw / 2},0)`);
    gm.select("line").attr("y1", -4).attr("y2", ih);
    gm.select("text").attr("y", (d, i) => -8 - 12 * (i % 2)).text((d) => d.short);
    gm.select("title").text((d) => d.label + (d.detail ? " — " + d.detail : ""));
  }
  /** Spread labels vertically so none overlap; items carry .y (desired) and get .ly (placed). */
  function spread(items, gap, lo, hi) {
    items.sort((a, b) => a.y - b.y);
    for (const it of items) it.ly = Math.min(hi, Math.max(lo, it.y));
    for (let i = 1; i < items.length; i++) if (items[i].ly - items[i - 1].ly < gap) items[i].ly = items[i - 1].ly + gap;
    const over = items.length ? items[items.length - 1].ly - hi : 0;
    if (over > 0) for (const it of items) it.ly -= over;
    for (let i = items.length - 2; i >= 0; i--) if (items[i + 1].ly - items[i].ly < gap) items[i].ly = items[i + 1].ly - gap;
    return items;
  }
  function pathTween(sel, d, dur) {
    const old = sel.attr("d");
    if (old === d) return;
    const count = (s) => (s ? (s.match(/[-\d.]+/g) || []).length : -1);
    if (old && count(old) === count(d) && dur > 0) sel.transition("morph").duration(dur).ease(EASE).attr("d", d);
    else sel.attr("d", d);
  }
  function drawOn(sel, dur) {   // entrance: the line draws itself from left to right (a named transition, so a morph cannot cancel it)
    if (!dur) return;
    sel.each(function () {
      const len = this.getTotalLength();
      const clear = function () { d3.select(this).attr("stroke-dasharray", null).attr("stroke-dashoffset", null); };
      d3.select(this).attr("stroke-dasharray", len + " " + len).attr("stroke-dashoffset", len)
        .transition("draw").duration(dur * 1.4).ease(d3.easeCubicInOut).attr("stroke-dashoffset", 0).on("end", clear).on("interrupt", clear);
    });
  }

  // ------------------------------------------------------------------ line chart (overlay | panels | slope | gap)
  /** o = { series:[{key,label,color,values:[v|null],ns:[n],emphasis}], xs:[years], fmt, yMax, partial, markers, layout, height } */
  function lineChart(el, o) {
    const series = o.series.filter((s) => s.values.some((v) => v !== null && v !== undefined));
    if (!series.length) { empty(el); return; }
    if (o.layout === "panels" && series.length >= 2) return panels(el, o, series);
    if (o.layout === "slope" && o.xs.length >= 2) return slope(el, o, series);
    const t = theme(), fmt = formatter(o.fmt), dur = DUR();
    const labelW = Math.min(170, Math.round((el.clientWidth || 800) * 0.38), Math.max(...series.map((s) => textW(s.label, 12))) + 60);
    const m = { top: 30, right: labelW, bottom: 32, left: 44 };
    const F = frame(el, o.height || 420, m, o.layout === "gap" ? "gap" : "line");
    const xs = o.xs;
    const x = d3.scaleLinear().domain([xs[0] - 0.4, xs[xs.length - 1] + 0.4]).range([0, F.iw]);
    const vmax = o.yMax || Math.min(o.fmt === "int" ? Infinity : 1, Math.max(1e-9, ...series.flatMap((s) => s.values.filter((v) => v !== null))) * 1.08);
    const y = d3.scaleLinear().domain([0, vmax]).nice(4).range([F.ih, 0]);
    const slot = F.iw / Math.max(1, xs.length - 1);
    partialBand(F.g, o.partial, xs, x, slot, F.ih, t);
    milestones(F.g, o.markers, xs, x, slot, F.ih, F.iw, t);
    yAxis(F.g, y, t, tickFormat(o.fmt, y), 4);
    xAxisBand(F.g, xs, x, F.ih, F.iw, t, slot < 26 ? 3 : slot < 44 ? 2 : 1);
    const data = series.map((s) => ({ key: s.key, label: s.label, color: s.color, emphasis: !!s.emphasis, pts: xs.map((xv, i) => ({ x: xv, v: s.values[i], n: s.ns ? s.ns[i] : null })) }));
    const line = d3.line().defined((d) => d.v !== null && d.v !== undefined).x((d) => x(d.x)).y((d) => y(d.v));

    if (o.layout === "gap" && data.length === 2) {
      // Dumbbell per year: the two series as dot pairs joined by a hairline; the gap is the message.
      layer(F.g, "lines").selectAll("*").remove();
      const G = layer(F.g, "gap");
      const pairs = xs.map((xv, i) => ({ x: xv, a: data[0].pts[i].v, b: data[1].pts[i].v, na: data[0].pts[i].n, nb: data[1].pts[i].n })).filter((p) => p.a !== null && p.b !== null);
      const con = G.selectAll("line.con").data(pairs, (d) => d.x);
      con.exit().remove();
      con.enter().append("line").attr("class", "con").attr("stroke", t.ink3).attr("stroke-width", 1.5).attr("x1", (d) => x(d.x)).attr("x2", (d) => x(d.x)).attr("y1", F.ih).attr("y2", F.ih).merge(con)
        .transition().duration(dur).ease(EASE).attr("x1", (d) => x(d.x)).attr("x2", (d) => x(d.x)).attr("y1", (d) => y(d.a)).attr("y2", (d) => y(d.b));
      for (const [k, which] of [[0, "a"], [1, "b"]]) {
        const dots = G.selectAll("circle.d" + k).data(pairs, (d) => d.x);
        dots.exit().remove();
        dots.enter().append("circle").attr("class", "d" + k).attr("r", 5).attr("fill", data[k].color).attr("stroke", t.bg).attr("stroke-width", 2).attr("cx", (d) => x(d.x)).attr("cy", F.ih).merge(dots)
          .transition().duration(dur).ease(EASE).attr("cx", (d) => x(d.x)).attr("cy", (d) => y(d[which]));
      }
      const last = pairs[pairs.length - 1];
      const placedG = last ? spread([{ k: 0, v: last.a, s: data[0], y: y(last.a) }, { k: 1, v: last.b, s: data[1], y: y(last.b) }], 15, 6, F.ih - 4) : [];
      const lab = layer(F.g, "labels").selectAll("text.end").data(placedG, (d) => d.k);
      lab.exit().remove();
      lab.enter().append("text").attr("class", "end").attr("font-size", 12).attr("dy", "0.32em").merge(lab)
        .attr("x", x(last.x) + 12).attr("y", (d) => d.ly).attr("fill", t.ink)
        .each(function (d) { const s = d3.select(this); s.selectAll("*").remove(); s.append("tspan").attr("font-weight", 500).text(fmt(d.v)); s.append("tspan").attr("fill", t.ink3).text(" " + d.s.label); });
      el.__replay = () => {
        const d = DUR(); if (!d) return;
        G.selectAll("line.con").attr("y1", F.ih).attr("y2", F.ih).transition("enter").duration(d).delay((q, i) => i * 40).ease(EASE).attr("y1", (q) => y(q.a)).attr("y2", (q) => y(q.b));
        G.selectAll("circle.d0").attr("cy", F.ih).transition("enter").duration(d).delay((q, i) => i * 40).ease(EASE).attr("cy", (q) => y(q.a));
        G.selectAll("circle.d1").attr("cy", F.ih).transition("enter").duration(d).delay((q, i) => i * 40).ease(EASE).attr("cy", (q) => y(q.b));
        F.g.selectAll("g.labels text.end").style("opacity", 0).transition("enter").delay(d + pairs.length * 40).duration(400).style("opacity", 1);
      };
      hoverX(F, xs, x, (i, evt) => {
        const p = pairs.find((q) => q.x === xs[i]); if (!p) return null;
        return { title: String(xs[i]), rows: [{ value: fmt(p.b), label: data[1].label, color: data[1].color, sub: "n = " + fmtInt(p.nb) }, { value: fmt(p.a), label: data[0].label, color: data[0].color, sub: "n = " + fmtInt(p.na) }, { value: fmt(p.b - p.a), label: "gap", color: "transparent" }] };
      }, t, y, data.map((d) => ({ color: d.color, at: (i) => d.pts[i].v })));
      return;
    }
    layer(F.g, "gap").selectAll("*").remove();
    const L = layer(F.g, "lines").selectAll("path.line").data(data, (d) => d.key);
    L.exit().transition().duration(dur).style("opacity", 0).remove();
    const Le = L.enter().append("path").attr("class", "line").attr("fill", "none").attr("stroke-linejoin", "round").attr("stroke-linecap", "round");
    Le.attr("d", (d) => line(d.pts)).call(drawOn, F.fresh ? dur : 0);
    Le.merge(L).attr("stroke", (d) => d.color).attr("stroke-width", (d) => (d.emphasis ? 2.5 : 2)).each(function (d) { pathTween(d3.select(this), line(d.pts), dur); });
    // end dots and direct labels (value, then name in grey): selective, one per series
    const ends = data.map((d) => { let i = d.pts.length - 1; while (i >= 0 && d.pts[i].v === null) i--; return i >= 0 ? { key: d.key, label: d.label, color: d.color, x: d.pts[i].x, v: d.pts[i].v, y: y(d.pts[i].v) } : null; }).filter(Boolean);
    const dots = layer(F.g, "dots").selectAll("circle.end").data(ends, (d) => d.key);
    dots.exit().remove();
    dots.enter().append("circle").attr("class", "end").attr("r", 4.5).attr("stroke", t.bg).attr("stroke-width", 2).attr("cx", (d) => x(d.x)).attr("cy", (d) => d.y).merge(dots)
      .attr("fill", (d) => d.color).transition().duration(dur).ease(EASE).attr("cx", (d) => x(d.x)).attr("cy", (d) => d.y);
    const placed = spread(ends.map((e) => Object.assign({}, e)), 15, 6, F.ih - 4);
    const lab = layer(F.g, "labels").selectAll("text.end").data(placed, (d) => d.key);
    lab.exit().remove();
    const le = lab.enter().append("text").attr("class", "end").attr("font-size", 12).attr("dy", "0.32em").attr("x", (d) => x(d.x) + 11).attr("y", (d) => d.ly);
    le.merge(lab).each(function (d) { const s = d3.select(this); s.selectAll("*").remove(); s.append("tspan").attr("fill", t.ink).attr("font-weight", 500).text(fmt(d.v)); s.append("tspan").attr("fill", t.ink3).text(" " + d.label); })
      .transition().duration(dur).ease(EASE).attr("x", (d) => x(d.x) + 11).attr("y", (d) => d.ly);
    const leaders = layer(F.g, "leaders").selectAll("line").data(placed.filter((d) => Math.abs(d.ly - d.y) > 4), (d) => d.key);
    leaders.exit().remove();
    leaders.enter().append("line").attr("stroke", t.hair).merge(leaders).attr("x1", (d) => x(d.x) + 5).attr("y1", (d) => d.y).attr("x2", (d) => x(d.x) + 9).attr("y2", (d) => d.ly);
    hoverX(F, xs, x, (i) => {
      const rows = data.map((d) => ({ value: fmt(d.pts[i].v), v: d.pts[i].v, label: d.label, color: d.color, sub: d.pts[i].n ? "n = " + fmtInt(d.pts[i].n) : "" })).filter((r) => r.v !== null).sort((a, b) => b.v - a.v);
      return rows.length ? { title: String(xs[i]), rows } : null;
    }, t, y, data.map((d) => ({ color: d.color, at: (i) => d.pts[i].v })));
    el.__replay = () => {
      const d = DUR(); if (!d) return;
      F.g.selectAll("g.lines path.line").call(drawOn, d);
      F.g.selectAll("g.dots circle.end, g.labels text.end, g.leaders line").style("opacity", 0).transition("enter").delay(d * 1.1).duration(400).style("opacity", 1);
    };
  }
  /** Crosshair + one tooltip for every series at the nearest x. */
  function hoverX(F, xs, x, rowsAt, t, y, marks) {
    const H = layer(F.g, "hover");
    let cross = H.select("line.cross");
    if (cross.empty()) cross = H.append("line").attr("class", "cross").attr("stroke", t.ink3).attr("stroke-width", 1).style("opacity", 0);
    cross.attr("y1", 0).attr("y2", F.ih);
    const hd = H.selectAll("circle.h").data(marks, (d, i) => i);
    hd.exit().remove();
    hd.enter().append("circle").attr("class", "h").attr("r", 5).attr("stroke", t.bg).attr("stroke-width", 2).merge(hd).attr("fill", (d) => d.color).style("opacity", 0);
    let hit = H.select("rect.hit");
    if (hit.empty()) hit = H.append("rect").attr("class", "hit").attr("fill", "transparent");
    hit.attr("x", -10).attr("y", -20).attr("width", F.iw + 20).attr("height", F.ih + 40).style("cursor", "crosshair")
      .on("pointermove", (evt) => {
        const [px] = d3.pointer(evt, F.g.node());
        let best = 0, bd = Infinity;
        xs.forEach((xv, i) => { const d = Math.abs(x(xv) - px); if (d < bd) { bd = d; best = i; } });
        const r = rowsAt(best, evt);
        if (!r) { hideTip(); cross.style("opacity", 0); H.selectAll("circle.h").style("opacity", 0); return; }
        cross.attr("x1", x(xs[best])).attr("x2", x(xs[best])).style("opacity", 1);
        H.selectAll("circle.h").attr("cx", x(xs[best])).attr("cy", (d) => { const v = d.at(best); return v === null || v === undefined ? -100 : y(v); }).style("opacity", (d) => { const v = d.at(best); return v === null || v === undefined ? 0 : 1; });
        showTip(evt, r.title, r.rows);
      })
      .on("pointerleave", () => { hideTip(); cross.style("opacity", 0); H.selectAll("circle.h").style("opacity", 0); });
  }
  /** Small multiples: one panel per series, the others ghosted in grey behind it, shared scale. */
  function panels(el, o, series) {
    const t = theme(), fmt = formatter(o.fmt), dur = DUR();
    const width = Math.max(320, el.clientWidth || 800);
    const n = series.length, cols = width < 560 ? 1 : n <= 4 ? 2 : 3, rows = Math.ceil(n / cols);
    const ph = 190, gapX = 36, gapY = 44;
    const m = { top: 28, right: 12, bottom: 30, left: 44 };
    const F = frame(el, m.top + rows * ph + (rows - 1) * gapY + m.bottom, m, "panels");
    const pw = (F.iw - (cols - 1) * gapX) / cols;
    const xs = o.xs;
    const vmax = o.yMax || Math.min(o.fmt === "int" ? Infinity : 1, Math.max(1e-9, ...series.flatMap((s) => s.values.filter((v) => v !== null))) * 1.08);
    const y = d3.scaleLinear().domain([0, vmax]).nice(3).range([ph, 0]);
    const x = d3.scaleLinear().domain([xs[0] - 0.3, xs[xs.length - 1] + 0.3]).range([0, pw]);
    const line = d3.line().defined((d) => d.v !== null && d.v !== undefined).x((d) => x(d.x)).y((d) => y(d.v));
    const pts = (s) => xs.map((xv, i) => ({ x: xv, v: s.values[i] }));
    // remove overlay layers if the chart switched form
    for (const name of ["lines", "dots", "labels", "leaders", "hover", "gap", "partial", "milestones", "yaxis", "xaxis", "slope"]) layer(F.g, name).selectAll("*").remove();
    const P = layer(F.g, "panels").selectAll("g.panel").data(series, (d) => d.key);
    P.exit().remove();
    const Pe = P.enter().append("g").attr("class", "panel").style("opacity", 0);
    Pe.append("text").attr("class", "title").attr("font-size", 13).attr("font-weight", 500).attr("y", -10);
    Pe.append("g").attr("class", "ghosts");
    Pe.append("path").attr("class", "line").attr("fill", "none").attr("stroke-width", 2).attr("stroke-linejoin", "round").attr("stroke-linecap", "round");
    Pe.append("circle").attr("class", "end").attr("r", 4).attr("stroke-width", 2);
    Pe.append("text").attr("class", "val").attr("font-size", 12).attr("font-weight", 500).attr("dy", "0.32em");
    Pe.append("line").attr("class", "base");
    Pe.append("g").attr("class", "yt");
    Pe.append("g").attr("class", "xt");
    const Pm = Pe.merge(P);
    Pm.transition().duration(dur).style("opacity", 1);
    Pm.attr("transform", (d, i) => `translate(${(i % cols) * (pw + gapX)},${Math.floor(i / cols) * (ph + gapY)})`);
    Pm.select("text.title").attr("fill", t.ink).text((d) => d.label);
    Pm.select("line.base").attr("x1", 0).attr("x2", pw).attr("y1", ph + 0.5).attr("y2", ph + 0.5).attr("stroke", t.hair);
    Pm.each(function (d, i) {
      const g = d3.select(this);
      const gh = g.select("g.ghosts").selectAll("path").data(series.filter((s) => s.key !== d.key), (s) => s.key);
      gh.exit().remove();
      gh.enter().append("path").attr("fill", "none").attr("stroke", t.grid).attr("stroke-width", 1.5).merge(gh).each(function (s) { pathTween(d3.select(this), line(pts(s)), dur); });
      const p = pts(d);
      pathTween(g.select("path.line").attr("stroke", d.color), line(p), dur);
      let li = p.length - 1; while (li >= 0 && p[li].v === null) li--;
      if (li >= 0) {
        g.select("circle.end").attr("fill", d.color).attr("stroke", t.bg).transition().duration(dur).ease(EASE).attr("cx", x(p[li].x)).attr("cy", y(p[li].v));
        g.select("text.val").attr("fill", t.ink).text(fmt(p[li].v)).transition().duration(dur).ease(EASE).attr("x", x(p[li].x) - 8).attr("y", y(p[li].v) - 12).attr("text-anchor", "end");
      }
      // ticks: y labels in the first column only, x labels first and last year
      const yt = g.select("g.yt").selectAll("text").data(i % cols === 0 ? y.ticks(3) : []);
      yt.exit().remove();
      yt.enter().append("text").attr("font-size", 10).attr("fill", t.ink3).attr("text-anchor", "end").attr("dy", "0.32em").merge(yt).attr("x", -8).attr("y", (v) => y(v)).text(tickFormat(o.fmt, y));
      const xt = g.select("g.xt").selectAll("text").data([xs[0], xs[xs.length - 1]]);
      xt.exit().remove();
      xt.enter().append("text").attr("font-size", 10).attr("fill", t.ink3).merge(xt).attr("x", (v) => x(v)).attr("y", ph + 16).attr("text-anchor", (v, k) => (k === 0 ? "start" : "end")).text((v) => v);
    });
    el.__replay = () => {
      const d = DUR(); if (!d) return;
      Pm.each(function (s, i) {
        const g = d3.select(this);
        g.select("path.line").transition("draw").delay(i * 140).duration(0).on("end", function () { d3.select(this).call(drawOn, d); });
        g.selectAll("g.ghosts path, circle.end, text.val").style("opacity", 0).transition("enter").delay(i * 140 + d).duration(400).style("opacity", 1);
      });
    };
    // a shared hit layer per panel: hovering a panel reads that series at the nearest year
    Pm.each(function (d) {
      const g = d3.select(this);
      let hit = g.select("rect.hit");
      if (hit.empty()) hit = g.append("rect").attr("class", "hit").attr("fill", "transparent");
      hit.attr("x", 0).attr("y", -16).attr("width", pw).attr("height", ph + 20)
        .on("pointermove", (evt) => { const [px] = d3.pointer(evt, this); let best = 0, bd = Infinity; xs.forEach((xv, k) => { const dd = Math.abs(x(xv) - px); if (dd < bd) { bd = dd; best = k; } });
          const rows = series.map((s) => ({ value: fmt(s.values[best]), v: s.values[best], label: s.label, color: s.key === d.key ? s.color : t.grid, sub: s.ns && s.ns[best] ? "n = " + fmtInt(s.ns[best]) : "" })).filter((r) => r.v !== null).sort((a, b) => b.v - a.v);
          if (rows.length) showTip(evt, String(xs[best]), rows); else hideTip(); })
        .on("pointerleave", hideTip);
    });
  }
  /** Slopegraph: first year to last year, one line per series, labelled at both ends. */
  function slope(el, o, series) {
    const t = theme(), fmt = formatter(o.fmt), dur = DUR();
    const labelW = Math.min(190, Math.max(...series.map((s) => textW(s.label, 12))) + 64);
    const m = { top: 36, right: labelW, bottom: 20, left: labelW };
    const F = frame(el, o.height || 420, m, "slope");
    const xs = o.xs;
    const items = series.map((s) => { let a = 0; while (a < s.values.length && s.values[a] === null) a++; let b = s.values.length - 1; while (b >= 0 && s.values[b] === null) b--; return a < b ? { key: s.key, label: s.label, color: s.color, emphasis: !!s.emphasis, x0: xs[a], x1: xs[b], v0: s.values[a], v1: s.values[b] } : null; }).filter(Boolean);
    if (!items.length) { empty(el); return; }
    const vmax = o.yMax || Math.min(o.fmt === "int" ? Infinity : 1, Math.max(1e-9, ...items.flatMap((d) => [d.v0, d.v1])) * 1.08);
    const y = d3.scaleLinear().domain([0, vmax]).range([F.ih, 0]);
    const x0 = 0, x1 = F.iw;
    for (const name of ["lines", "dots", "labels", "leaders", "hover", "gap", "partial", "milestones", "yaxis", "xaxis", "panels"]) layer(F.g, name).selectAll("*").remove();
    const S = layer(F.g, "slope");
    const frames = S.selectAll("line.col").data([x0, x1]);
    frames.enter().append("line").attr("class", "col").attr("stroke", t.hair).merge(frames).attr("x1", (d) => d).attr("x2", (d) => d).attr("y1", 0).attr("y2", F.ih);
    const heads = S.selectAll("text.head").data([{ x: x0, l: String(items[0].x0), a: "end" }, { x: x1, l: String(items[0].x1), a: "start" }]);
    heads.enter().append("text").attr("class", "head").attr("font-size", 11).attr("fill", t.ink3).merge(heads).attr("x", (d) => d.x + (d.a === "end" ? -10 : 10)).attr("y", -16).attr("text-anchor", (d) => d.a).text((d) => d.l);
    const ln = S.selectAll("line.sl").data(items, (d) => d.key);
    ln.exit().transition().duration(dur).style("opacity", 0).remove();
    ln.enter().append("line").attr("class", "sl").attr("stroke-linecap", "round").attr("x1", x0).attr("x2", x1).attr("y1", (d) => y(d.v0)).attr("y2", (d) => y(d.v0)).merge(ln)
      .attr("stroke", (d) => d.color).attr("stroke-width", (d) => (d.emphasis ? 2.5 : 2))
      .transition().duration(dur).ease(EASE).attr("y1", (d) => y(d.v0)).attr("y2", (d) => y(d.v1));
    for (const [side, xv, vk] of [["a", x0, "v0"], ["b", x1, "v1"]]) {
      const dots = S.selectAll("circle." + side).data(items, (d) => d.key);
      dots.exit().remove();
      dots.enter().append("circle").attr("class", side).attr("r", 4.5).attr("stroke", t.bg).attr("stroke-width", 2).attr("cx", xv).attr("cy", (d) => y(d[vk])).merge(dots).attr("fill", (d) => d.color)
        .transition().duration(dur).ease(EASE).attr("cy", (d) => y(d[vk]));
      const placed = spread(items.map((d) => ({ key: d.key, label: d.label, v: d[vk], y: y(d[vk]) })), 15, 6, F.ih - 4);
      const lab = S.selectAll("text.l" + side).data(placed, (d) => d.key);
      lab.exit().remove();
      lab.enter().append("text").attr("class", "l" + side).attr("font-size", 12).attr("dy", "0.32em").attr("x", xv + (side === "a" ? -11 : 11)).attr("text-anchor", side === "a" ? "end" : "start").attr("y", (d) => d.ly).merge(lab)
        .each(function (d) { const s = d3.select(this); s.selectAll("*").remove(); if (side === "a") { s.append("tspan").attr("fill", t.ink3).text(d.label + " "); s.append("tspan").attr("fill", t.ink).attr("font-weight", 500).text(fmt(d.v)); } else { s.append("tspan").attr("fill", t.ink).attr("font-weight", 500).text(fmt(d.v)); s.append("tspan").attr("fill", t.ink3).text(" " + d.label); } })
        .transition().duration(dur).ease(EASE).attr("y", (d) => d.ly);
    }
    el.__replay = () => {
      const d = DUR(); if (!d) return;
      S.selectAll("line.sl").attr("y2", (q) => y(q.v0)).transition("enter").duration(d * 1.3).ease(EASE).attr("y2", (q) => y(q.v1));
      S.selectAll("circle.b, text.lb").style("opacity", 0).transition("enter").delay(d * 1.1).duration(400).style("opacity", 1);
    };
    S.selectAll("line.sl").on("pointermove", (evt, d) => showTip(evt, d.label, [{ value: fmt(d.v1), label: String(d.x1), color: d.color }, { value: fmt(d.v0), label: String(d.x0), color: d.color }, { value: (d.v1 - d.v0 >= 0 ? "+" : "") + fmt(d.v1 - d.v0), label: "change", color: "transparent" }])).on("pointerleave", hideTip).style("cursor", "crosshair");
  }

  // ------------------------------------------------------------------ 100% stacked (bars | area | panels)
  /** o = { classes:[{key,label,color,neutral}], xs:[years|labels], shares:{key:[v|null]}, counts:{key:[n]}, denoms:[n], mode, partial, markers, height, fmt } */
  function stacked(el, o) {
    const t = theme(), dur = DUR(), fmt = formatter("pct");
    const xs = o.xs, numeric = typeof xs[0] === "number";
    if (!o.denoms.some((d) => d > 0)) { empty(el); return; }
    if (o.mode === "panels") return stackedPanels(el, o);
    const narrow = (el.clientWidth || 800) < 560;          // phones: the key row carries identity, no end labels
    const labelW = narrow ? 16 : Math.min(190, Math.max(...o.classes.map((c) => textW(c.label, 11))) + 64);
    const m = { top: 30, right: labelW, bottom: 32, left: 44 };
    const F = frame(el, o.height || 400, m, o.mode === "area" ? "area" : "stacked");
    const x = d3.scaleBand().domain(xs).range([0, F.iw]).paddingInner(0.35).paddingOuter(0.15);
    const xc = (v) => x(v) + x.bandwidth() / 2;
    const bw = Math.min(40, x.bandwidth());
    const every = x.step() < 24 ? 3 : x.step() < 40 ? 2 : 1;
    const y = d3.scaleLinear().domain([0, 1]).range([F.ih, 0]);
    const stackAt = (i) => { let cum = 0; return o.classes.map((c) => { const v = o.shares[c.key][i]; const s = { key: c.key, label: c.label, color: c.neutral ? t.neutral : c.color, neutral: !!c.neutral, v: v === null ? 0 : v, y0: cum, n: (o.counts[c.key] || [])[i] || 0, x: xs[i], i }; cum += s.v; s.y1 = cum; return s; }); };
    const cols = xs.map((_, i) => ({ x: xs[i], i, segs: o.denoms[i] > 0 ? stackAt(i) : [] }));
    if (numeric) partialBand(F.g, o.partial, xs, xc, x.bandwidth() + x.step() * 0.35, F.ih, t); else layer(F.g, "partial").selectAll("*").remove();
    if (numeric) milestones(F.g, o.markers, xs, xc, x.step(), F.ih, F.iw, t); else layer(F.g, "milestones").selectAll("*").remove();
    yAxis(F.g, y, t, (v) => Math.round(v * 100) + "%", 4);
    xAxisBand(F.g, xs, xc, F.ih, F.iw, t, every);
    for (const name of ["areas", "panels", "lines", "dots", "hover"]) layer(F.g, name).selectAll("*").remove();
    const C = layer(F.g, "bars").selectAll("g.col").data(cols, (d) => d.x);
    C.exit().remove();
    const Cm = C.enter().append("g").attr("class", "col").merge(C).attr("transform", (d) => `translate(${xc(d.x) - bw / 2},0)`);
    if (o.mode === "area") {
      Cm.selectAll("*").remove();
      const A = layer(F.g, "areas");
      const xl = numeric ? d3.scaleLinear().domain([xs[0], xs[xs.length - 1]]).range([xc(xs[0]), xc(xs[xs.length - 1])]) : xc;
      const area = d3.area().x((d) => xl(d.x)).y0((d) => y(d.y0)).y1((d) => y(d.y1)).defined((d) => d.def);
      const series = o.classes.map((c, k) => ({ key: c.key, label: c.label, color: c.neutral ? t.neutral : c.color, pts: cols.map((col) => { const s = col.segs[k]; return s ? { x: col.x, y0: s.y0, y1: s.y1, def: true } : { x: col.x, y0: 0, y1: 0, def: false }; }) }));
      const P = A.selectAll("path.area").data(series, (d) => d.key);
      P.exit().remove();
      P.enter().append("path").attr("class", "area").attr("stroke", t.bg).attr("stroke-width", 2).style("opacity", 0).merge(P).attr("fill", (d) => d.color)
        .each(function (d) { pathTween(d3.select(this), area(d.pts), dur); }).transition().duration(dur).style("opacity", 1);
      A.selectAll("path.area").on("pointermove", (evt, d) => { const [px] = d3.pointer(evt, F.g.node()); let best = 0, bd = Infinity; xs.forEach((xv, i) => { const dd = Math.abs(xc(xv) - px); if (dd < bd) { bd = dd; best = i; } });
        const col = cols[best]; if (!col.segs.length) return hideTip(); showTip(evt, String(col.x), col.segs.slice().reverse().map((s) => ({ value: fmt(s.v), label: s.label, color: s.color, kind: "rect", sub: fmtInt(s.n) + " of " + fmtInt(o.denoms[best]) }))); }).on("pointerleave", hideTip);
    } else {
      layer(F.g, "areas").selectAll("*").remove();
      const R = Cm.selectAll("rect.seg").data((d) => d.segs, (s) => s.key);
      R.exit().remove();
      const Re = R.enter().append("rect").attr("class", "seg").attr("x", 0).attr("width", bw).attr("y", F.ih).attr("height", 0);
      Re.merge(R).attr("fill", (s) => s.color).transition().duration(dur).ease(EASE).delay((s, k) => (F.fresh ? k * 40 : 0))
        .attr("y", (s) => y(s.y1) + 1).attr("height", (s) => Math.max(0, y(s.y0) - y(s.y1) - 2));
      // in-segment labels only where they fit; everything else lives in the tooltip and the table
      const T = Cm.selectAll("text.seg").data((d) => d.segs.filter((s) => (y(s.y0) - y(s.y1)) >= 16 && bw >= 30 && s.v >= 0.06), (s) => s.key);
      T.exit().remove();
      T.enter().append("text").attr("class", "seg").attr("font-size", 10.5).attr("text-anchor", "middle").attr("dy", "0.32em").attr("x", bw / 2).style("pointer-events", "none").merge(T)
        .attr("fill", (s) => (s.neutral ? t.ink : onDark(s.color) ? "#ffffff" : t.ink)).text((s) => Math.round(s.v * 100) + "%")
        .transition().duration(dur).ease(EASE).attr("y", (s) => (y(s.y0) + y(s.y1)) / 2);
      Cm.selectAll("rect.seg").on("pointermove", (evt, s) => { d3.select(evt.currentTarget).attr("stroke", t.ink).attr("stroke-width", 1); showTip(evt, String(s.x), [{ value: fmt(s.v), label: s.label, color: s.color, kind: "rect", sub: fmtInt(s.n) + " of " + fmtInt(o.denoms[s.i]) }]); })
        .on("pointerleave", (evt) => { d3.select(evt.currentTarget).attr("stroke", null); hideTip(); });
    }
    el.__replay = () => {
      const d = DUR(); if (!d) return;
      if (o.mode === "area") {
        let clip = F.svg.select("defs clipPath.wipe");
        if (clip.empty()) clip = F.svg.insert("defs", ":first-child").append("clipPath").attr("class", "wipe").attr("id", "wipe-" + (el.id || Math.random().toString(36).slice(2)));
        let r = clip.select("rect"); if (r.empty()) r = clip.append("rect");
        r.attr("x", -2).attr("y", -20).attr("height", F.ih + 40).attr("width", 0).transition("enter").duration(d * 1.6).ease(d3.easeCubicInOut).attr("width", F.iw + 4);
        layer(F.g, "areas").attr("clip-path", "url(#" + clip.attr("id") + ")");
      } else {
        F.g.selectAll("g.bars rect.seg").attr("y", F.ih).attr("height", 0).transition("enter").duration(d).delay((q) => q.i * 45).ease(EASE)
          .attr("y", (q) => y(q.y1) + 1).attr("height", (q) => Math.max(0, y(q.y0) - y(q.y1) - 2));
        F.g.selectAll("g.bars text.seg").style("opacity", 0).transition("enter").delay((q) => q.i * 45 + d).duration(300).style("opacity", 1);
      }
      F.g.selectAll("g.labels text.cl").style("opacity", 0).transition("enter").delay(d * 1.4).duration(400).style("opacity", 1);
    };
    // direct labels for the last column at the right edge (legend still present in the key row)
    const lastCol = narrow ? null : cols.slice().reverse().find((c) => c.segs.length);
    const lab = layer(F.g, "labels").selectAll("text.cl").data(lastCol ? spread(lastCol.segs.filter((s) => s.v > 0.015).map((s) => ({ key: s.key, label: s.label, v: s.v, y: (y(s.y0) + y(s.y1)) / 2 })), 14, 6, F.ih - 4) : [], (d) => d.key);
    lab.exit().remove();
    lab.enter().append("text").attr("class", "cl").attr("font-size", 11).attr("dy", "0.32em").attr("x", F.iw + 10).attr("y", (d) => d.ly).merge(lab)
      .each(function (d) { const s = d3.select(this); s.selectAll("*").remove(); s.append("tspan").attr("fill", t.ink).attr("font-weight", 500).text(fmt(d.v)); s.append("tspan").attr("fill", t.ink3).text(" " + d.label); })
      .transition().duration(dur).ease(EASE).attr("x", F.iw + 10).attr("y", (d) => d.ly);
  }
  /** One small panel per class, shared scale, each in its own colour (the honest form for many classes). */
  function stackedPanels(el, o) {
    const t = theme();
    const series = o.classes.map((c) => ({ key: c.key, label: c.label, color: c.neutral ? t.neutral : c.color, values: o.shares[c.key], ns: o.denoms }));
    const numeric = typeof o.xs[0] === "number";
    if (!numeric) { empty(el, "Small multiples need a year axis."); return; }
    for (const name of ["bars", "areas", "labels", "yaxis", "xaxis", "partial", "milestones"]) { const svg = el.querySelector("svg.ch"); if (svg) d3.select(svg).select("g." + name).selectAll("*").remove(); }
    return panels(el, { xs: o.xs, fmt: "pct", yMax: o.yMax }, series);
  }

  // ------------------------------------------------------------------ dot plot (rows × points) — replaces grouped bars
  /** o = { rows:[{key,label,points:[{key,label,color,value,n}]}], fmt, xMax, mode:'dots'|'bars', emphasisKey, height } */
  function dotPlot(el, o) {
    const rows = o.rows.filter((r) => r.points.some((p) => p.value !== null && p.value !== undefined));
    if (!rows.length) { empty(el); return; }
    const t = theme(), fmt = formatter(o.fmt), dur = DUR();
    const nPts = Math.max(...rows.map((r) => r.points.length));
    const rowH = o.mode === "bars" ? nPts * 11 + 18 : 40;
    const labelW = Math.min(200, Math.max(...rows.map((r) => textW(r.label, 13))) + 20);
    const m = { top: 10, right: 56, bottom: 30, left: labelW };
    const F = frame(el, m.top + rows.length * rowH + m.bottom, m, o.mode === "bars" ? "dotbars" : "dots");
    const xmax = o.xMax || Math.max(1e-9, ...rows.flatMap((r) => r.points.map((p) => p.value || 0))) * 1.12;
    const x = d3.scaleLinear().domain([0, Math.min(1, xmax)]).nice(4).range([0, F.iw]);
    const ticks = x.ticks(4);
    const ax = layer(F.g, "xaxis");
    const base = ax.selectAll("line.base").data([0]);
    base.enter().append("line").attr("class", "base").merge(base).attr("x1", x(ticks[0])).attr("x2", x(ticks[ticks.length - 1])).attr("y1", F.ih + 0.5).attr("y2", F.ih + 0.5).attr("stroke", t.hair);
    const tk = ax.selectAll("text").data(ticks, (d) => d);
    tk.exit().remove();
    tk.enter().append("text").attr("font-size", 11).attr("fill", t.ink3).attr("text-anchor", "middle").merge(tk).attr("x", (d) => x(d)).attr("y", F.ih + 18).text(tickFormat(o.fmt, x));
    const R = layer(F.g, "rows").selectAll("g.row").data(rows, (d) => d.key);
    R.exit().transition().duration(dur).style("opacity", 0).remove();
    const Re = R.enter().append("g").attr("class", "row").style("opacity", 0);
    Re.append("text").attr("class", "lab").attr("font-size", 13).attr("x", -14).attr("text-anchor", "end").attr("dy", "0.32em");
    Re.append("line").attr("class", "rule");
    Re.append("line").attr("class", "range");
    const Rm = Re.merge(R);
    Rm.transition().duration(dur).style("opacity", 1).attr("transform", (d, i) => `translate(0,${i * rowH + rowH / 2})`);
    Rm.select("text.lab").attr("fill", t.ink).text((d) => d.label);
    Rm.select("line.rule").attr("x1", 0).attr("x2", F.iw).attr("y1", 0.5).attr("y2", 0.5).attr("stroke", t.grid);
    Rm.each(function (d) {
      const g = d3.select(this);
      const pts = d.points.filter((p) => p.value !== null && p.value !== undefined);
      if (o.mode === "bars") {
        g.select("line.range").attr("x1", 0).attr("x2", 0);
        g.selectAll("circle.pt, text.v").remove();
        const B = g.selectAll("rect.bar").data(d.points, (p) => p.key);
        B.exit().remove();
        B.enter().append("rect").attr("class", "bar").attr("height", 9).attr("width", 0).merge(B).attr("fill", (p) => p.color).attr("y", (p, k) => -rowH / 2 + 8 + k * 11)
          .transition().duration(dur).ease(EASE).attr("width", (p) => (p.value === null ? 0 : Math.max(0, x(p.value))));
        g.selectAll("rect.bar").on("pointermove", (evt, p) => showTip(evt, d.label, [{ value: fmt(p.value), label: p.label, color: p.color, kind: "rect", sub: p.n ? "n = " + fmtInt(p.n) : "" }])).on("pointerleave", hideTip);
        return;
      }
      g.selectAll("rect.bar").remove();
      const lo = Math.min(...pts.map((p) => p.value)), hi = Math.max(...pts.map((p) => p.value));
      g.select("line.range").attr("stroke", t.ink3).attr("stroke-width", 1.5).transition().duration(dur).ease(EASE).attr("x1", x(lo)).attr("x2", x(hi));
      const P = g.selectAll("circle.pt").data(d.points, (p) => p.key);
      P.exit().remove();
      P.enter().append("circle").attr("class", "pt").attr("r", 5.5).attr("stroke", t.bg).attr("stroke-width", 2).attr("cx", 0).merge(P).attr("fill", (p) => p.color).style("opacity", (p) => (p.value === null ? 0 : 1))
        .transition().duration(dur).ease(EASE).attr("cx", (p) => (p.value === null ? 0 : x(p.value)));
      // one value label per row: the emphasised point (or the maximum)
      const em = pts.find((p) => p.key === o.emphasisKey) || pts.reduce((a, b) => (b.value > a.value ? b : a), pts[0]);
      const V = g.selectAll("text.v").data(em ? [em] : [], (p) => p.key);
      V.exit().remove();
      V.enter().append("text").attr("class", "v").attr("font-size", 11).attr("fill", t.ink).attr("font-weight", 500).attr("dy", "0.32em").attr("y", -12).attr("text-anchor", "middle").merge(V)
        .text((p) => fmt(p.value)).transition().duration(dur).ease(EASE).attr("x", (p) => x(p.value));
      g.selectAll("circle.pt").on("pointermove", (evt, p) => showTip(evt, d.label, pts.slice().sort((a, b) => b.value - a.value).map((q) => ({ value: fmt(q.value), label: q.label, color: q.color, sub: q.n ? "n = " + fmtInt(q.n) : "" })))).on("pointerleave", hideTip);
    });
    el.__replay = () => {
      const d = DUR(); if (!d) return;
      Rm.each(function (row, i) {
        const g = d3.select(this);
        g.selectAll("circle.pt").attr("cx", 0).transition("enter").delay(i * 60).duration(d).ease(EASE).attr("cx", (p) => (p.value === null ? 0 : x(p.value)));
        g.selectAll("rect.bar").attr("width", 0).transition("enter").delay(i * 60).duration(d).ease(EASE).attr("width", (p) => (p.value === null ? 0 : Math.max(0, x(p.value))));
        g.select("line.range").attr("x2", (q) => +g.select("line.range").attr("x1")).transition("enter").delay(i * 60).duration(d).ease(EASE).attr("x2", function () { const pts = row.points.filter((p) => p.value !== null); return pts.length ? x(Math.max(...pts.map((p) => p.value))) : 0; });
        g.selectAll("text.v").style("opacity", 0).transition("enter").delay(i * 60 + d).duration(300).style("opacity", 1);
      });
    };
  }

  // ------------------------------------------------------------------ ranked dots (one value per row, sorted)
  /** o = { items:[{key,label,value,n,sub}], fmt, xMax, reference:{value,label}, color, mode:'dots'|'bars', labelWidth, height } */
  function rankDots(el, o) {
    const items = o.items.filter((d) => d.value !== null && d.value !== undefined);
    if (!items.length) { empty(el); return; }
    const t = theme(), fmt = formatter(o.fmt), dur = DUR();
    const rowH = 26;
    const width = Math.max(320, el.clientWidth || 800);
    const labelW = Math.min(o.labelWidth || 300, Math.max(120, Math.round(width * 0.34)));
    const m = { top: 26, right: 64, bottom: 8, left: labelW };
    const F = frame(el, m.top + items.length * rowH + m.bottom, m, "rank");
    const xmax = o.xMax || Math.max(1e-9, ...items.map((d) => d.value), o.reference ? o.reference.value * 1.3 : 0) * 1.08;
    const x = d3.scaleLinear().domain([0, xmax]).range([0, F.iw]);
    const maxChars = Math.floor(labelW / 7.2);
    const ref = layer(F.g, "ref").selectAll("g").data(o.reference ? [o.reference] : []);
    ref.exit().remove();
    const re = ref.enter().append("g");
    re.append("line").attr("stroke", t.ink3).attr("stroke-width", 1);
    re.append("text").attr("font-size", 10).attr("fill", t.ink3).attr("text-anchor", "middle").attr("y", -10);
    const rm = re.merge(ref);
    rm.select("line").transition().duration(dur).attr("x1", (d) => x(d.value)).attr("x2", (d) => x(d.value)).attr("y1", -4).attr("y2", F.ih);
    rm.select("text").text((d) => d.label).transition().duration(dur).attr("x", (d) => x(d.value));
    const R = layer(F.g, "rows").selectAll("g.row").data(items, (d) => d.key || d.label);
    R.exit().transition().duration(dur).style("opacity", 0).remove();
    const Re = R.enter().append("g").attr("class", "row").style("opacity", 0).attr("transform", (d, i) => `translate(0,${i * rowH + rowH / 2})`);
    Re.append("text").attr("class", "lab").attr("font-size", 12.5).attr("x", -12).attr("text-anchor", "end").attr("dy", "0.32em");
    Re.append("title");
    Re.append("line").attr("class", "stem").attr("stroke", t.grid).attr("x1", 0).attr("x2", 0).attr("y1", 0.5).attr("y2", 0.5);
    Re.append("path").attr("class", "bar");
    Re.append("circle").attr("class", "pt").attr("r", 5).attr("stroke", t.bg).attr("stroke-width", 2).attr("cx", 0);
    Re.append("text").attr("class", "v").attr("font-size", 11.5).attr("dy", "0.32em").attr("x", 0);
    const Rm = Re.merge(R);
    Rm.transition().duration(dur).ease(EASE).style("opacity", 1).attr("transform", (d, i) => `translate(0,${i * rowH + rowH / 2})`);
    Rm.select("text.lab").attr("fill", t.ink).text((d) => truncate(d.label, maxChars));
    Rm.select("title").text((d) => d.label);
    const bars = o.mode === "bars";
    const barPath = (w) => { const h = 12, r = 4; w = Math.max(0, w); return w < r ? `M0,${-h / 2}h${w}v${h}h${-w}z` : `M0,${-h / 2}h${w - r}a${r},${r} 0 0 1 ${r},${r}v${h - 2 * r}a${r},${r} 0 0 1 ${-r},${r}h${-(w - r)}z`; };
    Rm.select("line.stem").style("opacity", bars ? 0 : 1).transition().duration(dur).ease(EASE).attr("x2", (d) => x(d.value));
    Rm.select("path.bar").attr("fill", o.color).style("opacity", bars ? 1 : 0).transition().duration(dur).ease(EASE).attrTween("d", function (d) { const from = this.__w || 0, to = x(d.value); this.__w = to; return (k) => barPath(from + (to - from) * k); });
    Rm.select("circle.pt").attr("fill", o.color).style("opacity", bars ? 0 : 1).transition().duration(dur).ease(EASE).attr("cx", (d) => x(d.value));
    Rm.select("text.v").attr("fill", t.ink2).text((d) => fmt(d.value)).transition().duration(dur).ease(EASE).attr("x", (d) => x(d.value) + 11);
    Rm.on("pointermove", (evt, d) => showTip(evt, d.label, [{ value: fmt(d.value), label: o.valueLabel || "", color: o.color }].concat((d.rows || []).map((r) => ({ value: r.value, label: r.label, color: "transparent" }))))).on("pointerleave", hideTip).style("cursor", "default");
    el.__replay = () => {
      const d = DUR(); if (!d) return;
      Rm.style("opacity", 0).transition("enter").delay((q, i) => i * 30).duration(400).style("opacity", 1);
      Rm.select("line.stem").attr("x2", 0).transition("enter").delay((q, i) => i * 30).duration(d).ease(EASE).attr("x2", (q) => x(q.value));
      Rm.select("circle.pt").attr("cx", 0).transition("enter").delay((q, i) => i * 30).duration(d).ease(EASE).attr("cx", (q) => x(q.value));
      Rm.select("path.bar").each(function (q) { this.__w = 0; }).attr("d", barPath(0)).transition("enter").delay((q, i) => i * 30).duration(d).ease(EASE).attrTween("d", function (q) { const to = x(q.value); this.__w = to; return (k) => barPath(to * k); });
      Rm.select("text.v").style("opacity", 0).transition("enter").delay((q, i) => i * 30 + d).duration(300).style("opacity", 1);
    };
  }

  // ------------------------------------------------------------------ raincloud (one row per year: cloud above, rain below, median and IQR on the baseline)
  /** o = { years:[...], groups:{year:[{key,label,value,n,color,sub}]}, partial, valueLabel } — values in [0,1] */
  function raincloud(el, o) {
    const t = theme(), fmt = formatter("pct"), dur = DUR();
    const have = o.years.filter((yr) => (o.groups[yr] || []).length);
    if (!have.length) { empty(el); return; }
    const rowH = 50, cloudH = 24, rainH = 18;
    const m = { top: 14, right: 64, bottom: 30, left: 56 };
    const F = frame(el, m.top + have.length * rowH + m.bottom, m, "rain");
    const x = d3.scaleLinear().domain([0, 1]).range([0, F.iw]);
    const base = (yr) => have.indexOf(yr) * rowH + cloudH + 4;        // the baseline between cloud and rain
    for (const name of ["bars", "areas", "panels", "lines", "dots", "labels", "hover", "gap", "milestones", "yaxis", "partial"]) layer(F.g, name).selectAll("*").remove();
    // x axis along the bottom (range frame), plus faint guides at 50 % and 100 %
    const ax = layer(F.g, "xaxis");
    const ticks = [0, 0.25, 0.5, 0.75, 1];
    const bl = ax.selectAll("line.base").data([0]);
    bl.enter().append("line").attr("class", "base").merge(bl).attr("x1", 0).attr("x2", F.iw).attr("y1", F.ih + 0.5).attr("y2", F.ih + 0.5).attr("stroke", t.hair);
    const tk = ax.selectAll("text.xl").data(ticks, (d) => "p" + d);
    tk.exit().remove();
    tk.enter().append("text").attr("class", "xl").attr("font-size", 11).attr("fill", t.ink3).attr("text-anchor", "middle").merge(tk).attr("x", (d) => x(d)).attr("y", F.ih + 18).text((d) => Math.round(d * 100) + "%");
    const gl = ax.selectAll("line.guide").data([0.5, 1]);
    gl.enter().append("line").attr("class", "guide").attr("stroke", t.grid).merge(gl).attr("x1", (d) => x(d)).attr("x2", (d) => x(d)).attr("y1", 0).attr("y2", F.ih);
    // density with reflection at the bounds (Epanechnikov), each cloud scaled to the same height
    const grid = d3.range(0, 1.0001, 0.01);
    const kde = (vals, h) => { const ext = vals.concat(vals.map((v) => -v), vals.map((v) => 2 - v)); return grid.map((g) => [g, d3.sum(ext, (v) => { const u = (g - v) / h; return Math.abs(u) <= 1 ? 0.75 * (1 - u * u) / h : 0; }) / vals.length]); };
    const dens = {}, dmax = {};
    // the fully open journals pile up at 100 %; the cloud is scaled to the density away from that edge and the spike plateaus
    for (const yr of have) { const vals = o.groups[yr].map((p) => p.value); if (vals.length >= 4) { dens[yr] = kde(vals, 0.06); const body = dens[yr].filter((d) => d[0] <= 0.94).map((d) => d[1]); dmax[yr] = Math.max(1e-9, ...(body.length ? body : dens[yr].map((d) => d[1]))); } }
    const cloud = (yr) => d3.area().x((d) => x(d[0])).y0(() => base(yr)).y1((d) => base(yr) - Math.min(cloudH, (d[1] / dmax[yr]) * cloudH * 0.9)).curve(d3.curveBasis)(dens[yr]);
    // rows: year, count, partial shading
    const R = layer(F.g, "rows").selectAll("g.row").data(have, (d) => d);
    R.exit().remove();
    const Re = R.enter().append("g").attr("class", "row");
    Re.append("rect").attr("class", "shade").attr("x", -m.left + 4).attr("height", rowH).attr("fill", t.surface2).style("opacity", 0);
    Re.append("line").attr("class", "rule").attr("stroke", t.grid);
    Re.append("text").attr("class", "yr").attr("font-size", 13).attr("font-weight", 500).attr("fill", t.ink).attr("text-anchor", "end").attr("x", -14).attr("dy", "0.32em");
    Re.append("text").attr("class", "n").attr("font-size", 10).attr("fill", t.ink3).attr("text-anchor", "end").attr("x", -14);
    Re.append("path").attr("class", "cloud").attr("fill", t.ink3).attr("fill-opacity", 0.16).attr("stroke", t.ink3).attr("stroke-width", 1);
    Re.append("line").attr("class", "iqr").attr("stroke", t.ink2).attr("stroke-width", 2.5).attr("stroke-linecap", "round");
    Re.append("line").attr("class", "med").attr("stroke", t.ink).attr("stroke-width", 2);
    Re.append("text").attr("class", "medv").attr("font-size", 11).attr("font-weight", 500).attr("fill", t.ink).attr("dy", "0.32em").attr("x", F.iw + 10);
    Re.append("text").attr("class", "inc").attr("font-size", 10).attr("fill", t.ink3).attr("x", F.iw + 10).text("incomplete");
    const Rm = Re.merge(R);
    Rm.attr("transform", (yr) => `translate(0,${base(yr)})`);
    Rm.select("rect.shade").attr("y", -cloudH - 4).attr("width", F.iw + m.left + m.right - 8).style("opacity", (yr) => ((o.partial || []).includes(yr) ? 0.7 : 0));
    Rm.select("line.rule").attr("x1", 0).attr("x2", F.iw).attr("y1", 0.5).attr("y2", 0.5);
    Rm.select("text.yr").text((yr) => yr);
    Rm.select("text.n").attr("y", 13).text((yr) => o.groups[yr].length + " journals");
    Rm.select("path.cloud").attr("transform", (yr) => `translate(0,${-base(yr)})`).each(function (yr) { if (dens[yr]) pathTween(d3.select(this), cloud(yr), dur); else d3.select(this).attr("d", null); });
    const q = (yr, k) => d3.quantile(o.groups[yr].map((p) => p.value).sort(d3.ascending), k);
    Rm.select("line.iqr").transition("move").duration(dur).ease(EASE).attr("x1", (yr) => x(q(yr, 0.25))).attr("x2", (yr) => x(q(yr, 0.75))).attr("y1", 0).attr("y2", 0);
    Rm.select("line.med").transition("move").duration(dur).ease(EASE).attr("x1", (yr) => x(q(yr, 0.5))).attr("x2", (yr) => x(q(yr, 0.5))).attr("y1", -7).attr("y2", 7);
    Rm.select("text.medv").text((yr) => fmt(q(yr, 0.5)));
    Rm.select("text.inc").attr("y", 14).style("opacity", (yr) => ((o.partial || []).includes(yr) ? 1 : 0));
    // the rain: one drop per journal below the baseline, jittered deterministically by key
    const seed = (k) => { let h = 2166136261; for (const ch of String(k)) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); } return ((h >>> 0) % 1000) / 1000; };
    const nMax = Math.max(1, ...have.flatMap((yr) => o.groups[yr].map((p) => p.n)));
    const r = d3.scaleSqrt().domain([0, nMax]).range([1.8, 5.5]);
    const pts = have.flatMap((yr) => o.groups[yr].map((p) => Object.assign({}, p, { yr, id: yr + "|" + p.key, cy: base(yr) + 5 + seed(p.key) * rainH })));
    const D = layer(F.g, "drops").selectAll("circle").data(pts, (d) => d.id);
    D.exit().transition().duration(dur / 2).style("opacity", 0).remove();
    const De = D.enter().append("circle").attr("cx", (d) => x(d.value)).attr("cy", (d) => d.cy).attr("r", 0).attr("stroke", t.bg).attr("stroke-width", 1);
    De.merge(D).attr("fill", (d) => d.color).attr("fill-opacity", 0.9).transition("move").duration(dur).ease(EASE).attr("cx", (d) => x(d.value)).attr("cy", (d) => d.cy).attr("r", (d) => r(d.n));
    layer(F.g, "drops").selectAll("circle").on("pointermove", (evt, d) => { d3.select(evt.currentTarget).attr("stroke", t.ink); showTip(evt, d.label, [{ value: fmt(d.value), label: o.valueLabel || "open access", color: d.color }, { value: fmtInt(d.n), label: "papers in " + d.yr, color: "transparent" }].concat(d.sub ? [{ value: "", label: d.sub, color: "transparent" }] : [])); })
      .on("pointerleave", (evt) => { d3.select(evt.currentTarget).attr("stroke", t.bg); hideTip(); });
    el.__replay = () => {
      const d = DUR(); if (!d) return;
      layer(F.g, "drops").selectAll("circle").attr("cy", (q2) => base(q2.yr) - 10).attr("r", (q2) => r(q2.n)).transition("move").delay((q2) => have.indexOf(q2.yr) * 70 + seed(q2.key + q2.yr) * 500).duration(d).ease(d3.easeBounceOut).attr("cy", (q2) => q2.cy);
      Rm.select("path.cloud").style("opacity", 0).transition("enter").delay((yr) => have.indexOf(yr) * 70).duration(600).style("opacity", 1);
      Rm.selectAll("line.iqr, line.med, text.medv").style("opacity", 0).transition("enter").delay((yr) => have.indexOf(yr) * 70 + 500).duration(400).style("opacity", 1);
    };
  }

  // ------------------------------------------------------------------ bubbles through the years (Rosling)
  /** o = { frames:{year:[{key,label,x,y,size,color,group}]}, years, year, xFmt, yFmt, xLabel, yLabel, trails, labels, playing, height } */
  function bubbles(el, o) {
    const t = theme(), fx = formatter(o.xFmt || "pct"), fy = formatter(o.yFmt || "pct");
    const dur = o.playing ? 900 : DUR();
    const all = o.years.flatMap((yr) => o.frames[yr] || []);
    if (!all.length) { empty(el); return; }
    const m = { top: 28, right: 32, bottom: 48, left: 56 };
    const F = frame(el, o.height || 520, m, "bubbles");
    const cap = (f) => (f === "int" ? Infinity : 1);
    const x = d3.scaleLinear().domain([0, Math.min(cap(o.xFmt), d3.max(all, (d) => d.x) * 1.08)]).nice(4).range([0, F.iw]);
    const y = d3.scaleLinear().domain([0, Math.min(cap(o.yFmt), d3.max(all, (d) => d.y) * 1.08)]).nice(4).range([F.ih, 0]);
    const r = d3.scaleSqrt().domain([0, d3.max(all, (d) => d.size)]).range([3, Math.max(14, Math.min(36, F.iw / 13))]);
    yAxis(F.g, y, t, tickFormat(o.yFmt || "pct", y), 4);
    const ax = layer(F.g, "xaxis");
    const xt = x.ticks(4);
    const base = ax.selectAll("line.base").data([0]);
    base.enter().append("line").attr("class", "base").merge(base).attr("x1", x(xt[0])).attr("x2", x(xt[xt.length - 1])).attr("y1", F.ih + 0.5).attr("y2", F.ih + 0.5).attr("stroke", t.hair);
    const tk = ax.selectAll("text.xl").data(xt, (d) => d);
    tk.exit().remove();
    tk.enter().append("text").attr("class", "xl").attr("font-size", 11).attr("fill", t.ink3).attr("text-anchor", "middle").merge(tk).attr("x", (d) => x(d)).attr("y", F.ih + 18).text(tickFormat(o.xFmt || "pct", x));
    const titles = layer(F.g, "axtitles").selectAll("text").data([{ k: "x", s: o.xLabel }, { k: "y", s: o.yLabel }], (d) => d.k);
    titles.enter().append("text").attr("font-size", 11.5).attr("fill", t.ink2).merge(titles)
      .attr("x", (d) => (d.k === "x" ? F.iw : -40)).attr("y", (d) => (d.k === "x" ? F.ih + 38 : -12)).attr("text-anchor", (d) => (d.k === "x" ? "end" : "start")).text((d) => d.s);
    // the year, large and quiet, behind the data
    let wm = layer(F.g, "wm").select("text");
    if (wm.empty()) wm = layer(F.g, "wm").append("text").attr("font-family", '"Instrument Serif", "Times New Roman", serif').attr("text-anchor", "end");
    wm.attr("x", F.iw - 6).attr("y", F.ih - 14).attr("font-size", Math.min(170, F.ih * 0.42)).attr("fill", t.grid).text(o.year);
    const cur = (o.frames[o.year] || []).slice().sort((a, b) => b.size - a.size);
    const nLab = o.labels || 6;
    const labelled = cur.slice(0, nLab).concat(cur.filter((d) => d.pinned && !cur.slice(0, nLab).includes(d)));
    // trails: the path of each labelled bubble from the first year to the current one (all of them would be noise)
    const T = layer(F.g, "trails").selectAll("path").data(o.trails ? labelled : [], (d) => d.key);
    T.exit().remove();
    const trail = (d) => { const pts = o.years.filter((yr) => yr <= o.year).map((yr) => (o.frames[yr] || []).find((p) => p.key === d.key)).filter(Boolean); return pts.length >= 2 ? d3.line().x((p) => x(p.x)).y((p) => y(p.y))(pts) : null; };
    T.enter().append("path").attr("fill", "none").attr("stroke-width", 1).attr("stroke-opacity", 0.4).merge(T).attr("stroke", (d) => d.color).each(function (d) { const p = trail(d); if (p) pathTween(d3.select(this), p, dur); else d3.select(this).attr("d", null); });
    const B = layer(F.g, "bubbles").selectAll("circle").data(cur, (d) => d.key);
    B.exit().transition("move").duration(dur / 2).attr("r", 0).remove();
    const Be = B.enter().append("circle").attr("cx", (d) => x(d.x)).attr("cy", (d) => y(d.y)).attr("r", 0).attr("stroke", t.bg).attr("stroke-width", 1.5);
    Be.merge(B).attr("fill", (d) => d.color).attr("fill-opacity", 0.82).transition("move").duration(dur).ease(o.playing ? d3.easeCubicInOut : EASE).attr("cx", (d) => x(d.x)).attr("cy", (d) => y(d.y)).attr("r", (d) => r(d.size));
    // labels: to the right of the bubble unless that runs off the frame; nudged apart vertically when they collide
    const side = (d) => (x(d.x) + r(d.size) + 6 + textW(d.label, 11) > F.iw + m.right - 6 ? -1 : 1);
    const placed = spread(labelled.map((d) => Object.assign({}, d, { y: y(d.y) })), 13, 4, F.ih - 4);
    const L = layer(F.g, "labels").selectAll("text").data(placed, (d) => d.key);
    L.exit().remove();
    L.enter().append("text").attr("font-size", 11).attr("fill", t.ink).attr("dy", "0.32em").attr("x", (d) => x(d.x) + side(d) * (r(d.size) + 5)).attr("y", (d) => d.ly).style("opacity", 0).merge(L)
      .text((d) => d.label).attr("text-anchor", (d) => (side(d) < 0 ? "end" : "start"))
      .transition("move").duration(dur).ease(o.playing ? d3.easeCubicInOut : EASE).attr("x", (d) => x(d.x) + side(d) * (r(d.size) + 5)).attr("y", (d) => d.ly).style("opacity", 1);
    // a partial year says so under the watermark
    const note = layer(F.g, "wm").selectAll("text.note").data((o.partial || []).includes(o.year) ? [0] : []);
    note.exit().remove();
    note.enter().append("text").attr("class", "note").attr("font-size", 11).attr("fill", t.ink3).attr("text-anchor", "end").merge(note).attr("x", F.iw - 8).attr("y", F.ih - 2).text("incomplete year");
    layer(F.g, "bubbles").selectAll("circle").on("pointermove", (evt, d) => { d3.select(evt.currentTarget).attr("stroke", t.ink).attr("fill-opacity", 1); showTip(evt, d.label + " · " + o.year, [{ value: fy(d.y), label: o.yLabel, color: d.color }, { value: fx(d.x), label: o.xLabel, color: d.color }, { value: fmtInt(d.size), label: "papers", color: "transparent" }].concat(d.group ? [{ value: "", label: d.group, color: "transparent" }] : [])); })
      .on("pointerleave", (evt) => { d3.select(evt.currentTarget).attr("stroke", t.bg).attr("fill-opacity", 0.82); hideTip(); });
    el.__replay = () => {
      const d = DUR(); if (!d) return;
      layer(F.g, "bubbles").selectAll("circle").attr("r", 0).transition("move").delay((q, i) => i * 25).duration(d).ease(d3.easeBackOut.overshoot(1.4)).attr("r", (q) => r(q.size));
      layer(F.g, "labels").selectAll("text").style("opacity", 0).transition("enter").delay(d).duration(400).style("opacity", 1);
    };
  }

  // ------------------------------------------------------------------ key (legend) row — always present for ≥ 2 series
  function key(el, items) {
    if (!el) return;
    el.replaceChildren();
    if (!items || items.length < 2) { el.hidden = true; return; }
    el.hidden = false;
    for (const it of items) {
      const span = document.createElement("span"); span.className = "key-item";
      const sw = document.createElement("span"); sw.className = "key-swatch" + (it.kind === "rect" ? " is-rect" : ""); sw.style.background = it.color;
      const lab = document.createElement("span"); lab.textContent = it.label;
      span.append(sw, lab); el.append(span);
    }
  }

  // ------------------------------------------------------------------ export (SVG as drawn; PNG via canvas at 2×)
  function markup(svgNode, bg) {
    const clone = svgNode.cloneNode(true);
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.querySelectorAll("g.hover, rect.hit").forEach((n) => n.remove());
    const w = +svgNode.getAttribute("width"), h = +svgNode.getAttribute("height");
    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("width", w); rect.setAttribute("height", h); rect.setAttribute("fill", bg);
    clone.insertBefore(rect, clone.firstChild);
    return new XMLSerializer().serializeToString(clone);
  }
  function download(el, fmt, name) {
    const svgNode = el.querySelector("svg.ch");
    if (!svgNode) return;
    const t = theme();
    const text = markup(svgNode, t.bg);
    const save = (blob, ext) => { const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = name + "." + ext; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1500); };
    if (fmt === "svg") { save(new Blob([text], { type: "image/svg+xml;charset=utf-8" }), "svg"); return; }
    const img = new Image();
    const w = +svgNode.getAttribute("width"), h = +svgNode.getAttribute("height");
    img.onload = () => { const c = document.createElement("canvas"); c.width = w * 2; c.height = h * 2; const ctx = c.getContext("2d"); ctx.scale(2, 2); ctx.drawImage(img, 0, 0); c.toBlob((b) => b && save(b, "png"), "image/png"); };
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(text);
  }
  function exportBar(el, name) {
    let bar = el.nextElementSibling;
    if (!(bar && bar.classList.contains("export"))) {
      bar = document.createElement("div"); bar.className = "export";
      for (const f of ["png", "svg"]) { const b = document.createElement("button"); b.type = "button"; b.textContent = f.toUpperCase(); b.title = "Download this chart as " + f.toUpperCase(); b.addEventListener("click", () => download(el, f, (el.dataset.exportName || el.id) + "_" + (name || ""))); bar.append(b); }
      el.insertAdjacentElement("afterend", bar);
    }
    bar.hidden = !hasSvg(el);
    return bar;
  }

  // ------------------------------------------------------------------ number tween for the matrix
  function countUp(node, from, to, fmt) {
    const dur = DUR();
    if (!dur || from === null || from === undefined || to === null || to === undefined) { node.textContent = fmt(to); return; }
    d3.select(node).transition().duration(dur).ease(EASE).tween("text", function () { const i = d3.interpolateNumber(from, to); return (k) => { this.textContent = fmt(i(k)); }; });
  }

  /** Build the chart in `el` from nothing (called once, when it first scrolls into view). */
  function replay(el) { if (el && typeof el.__replay === "function") el.__replay(); }

  return { lineChart, stacked, dotPlot, rankDots, raincloud, bubbles, key, exportBar, download, countUp, replay, theme, hideTip, reduced };
})();
