#!/usr/bin/env python3
"""
Build cross-discipline, year-by-year comparison outputs and dashboard.

Input format:
  --inputs stroke=/path/to/stroke_fully_enriched.csv neurology=/path/to/neurology_fully_enriched.csv
"""

from __future__ import annotations

import argparse
import html
import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd


VIRIDIS_HEXES = [
    "#440154",
    "#482878",
    "#3E4989",
    "#31688E",
    "#26828E",
    "#1F9E89",
    "#35B779",
    "#6DCD59",
    "#B4DE2C",
    "#FDE725",
]

METRIC_SPECS = [
    ("papers", "Publication volume", "count", "Annual retrieval volume, shown to keep denominators and field scale visible."),
    (
        "non_oa_open_signal_rate",
        "Signals beyond OA",
        "pct",
        "Repository, preprint, or preregistration evidence, excluding plain open access.",
    ),
    ("oa_rate", "Open-access baseline", "pct", "Share flagged as open access, regardless of richer open-science signals."),
    ("open_material_rate", "Repository and materials", "pct", "Share with repository, code, or data links."),
    ("github_rate", "GitHub trace", "pct", "Share with a GitHub repository signal."),
    ("dataset_rate", "Dataset repository", "pct", "Share with a dataset in a public repository (DataCite, Dryad, Figshare, Dataverse, etc.)."),
    ("preregistered_rate", "Preregistration trace", "pct", "Share with preregistration evidence."),
    ("high_impact_rate", "High-impact concentration", "pct", "Share meeting the benchmark high-impact definition."),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build discipline comparison dashboard from enriched CSV files.")
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="Discipline/path pairs like stroke=data/stroke/fully_enriched.csv",
    )
    parser.add_argument("--out-dir", default="data/dashboard", help="Output directory for summaries and HTML")
    parser.add_argument("--title", default="Open-Science Benchmark by Discipline")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")


def parse_input_pairs(items: List[str]) -> Dict[str, Path]:
    pairs: Dict[str, Path] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid input '{item}'. Expected format discipline=/path/file.csv")
        discipline, raw_path = item.split("=", 1)
        key = discipline.strip().lower()
        path = Path(raw_path).expanduser().resolve()
        if not key:
            raise ValueError(f"Empty discipline key in '{item}'")
        pairs[key] = path
    return pairs


def to_bool_series(series: pd.Series) -> pd.Series:
    def _conv(value: object) -> bool:
        if pd.isna(value):
            return False
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in {"", "none", "nan", "null", "<na>", "n/a"}:
            return False
        if s in {"true", "t", "1", "yes", "y"}:
            return True
        if s in {"false", "f", "0", "no", "n"}:
            return False
        return False

    return series.map(_conv)


def nonblank(series: pd.Series) -> pd.Series:
    cleaned = series.fillna("").astype(str).str.strip().str.lower()
    has_alnum = cleaned.str.contains(r"[a-z0-9]", regex=True, na=False)
    return has_alnum & ~cleaned.isin({"", "none", "nan", "null", "<na>", "n/a"})


def infer_oa_series(df: pd.DataFrame) -> pd.Series:
    explicit_oa = to_bool_series(df.get("is_oa", pd.Series(index=df.index, dtype=object)))
    journal_oa = to_bool_series(df.get("journal_is_oa", pd.Series(index=df.index, dtype=object)))
    has_oa_url = nonblank(df.get("best_oa_location_url", pd.Series(index=df.index, dtype=object)))
    has_oa_license = nonblank(df.get("license_unpaywall", pd.Series(index=df.index, dtype=object)))
    return explicit_oa | journal_oa | has_oa_url | has_oa_license


def prepare_discipline_panel(df: pd.DataFrame, discipline: str) -> pd.DataFrame:
    out = df.copy()

    if "discipline" not in out.columns:
        out["discipline"] = discipline
    else:
        missing = out["discipline"].fillna("").astype(str).str.strip().eq("")
        out.loc[missing, "discipline"] = discipline
        out["discipline"] = out["discipline"].astype(str).str.strip().str.lower()

    out["year"] = pd.to_numeric(out.get("year"), errors="coerce").astype("Int64")
    out = out[out["year"].notna()].copy()

    out["is_oa_bool"] = infer_oa_series(out)
    out["preregistered_bool"] = to_bool_series(out.get("preregistered", pd.Series(index=out.index, dtype=object)))
    out["high_impact_bool"] = to_bool_series(out.get("high_impact_flag", pd.Series(index=out.index, dtype=object)))

    out["has_github"] = nonblank(out.get("github", pd.Series(index=out.index, dtype=object)))
    out["has_zenodo"] = nonblank(out.get("zenodo", pd.Series(index=out.index, dtype=object)))
    out["has_osf"] = nonblank(out.get("osf", pd.Series(index=out.index, dtype=object)))
    out["has_code_link"] = nonblank(out.get("code_link", pd.Series(index=out.index, dtype=object)))
    out["has_data_link"] = nonblank(out.get("data_link", pd.Series(index=out.index, dtype=object)))
    out["has_repo_links"] = nonblank(out.get("repo_links", pd.Series(index=out.index, dtype=object)))
    out["has_preprint"] = nonblank(out.get("preprint", pd.Series(index=out.index, dtype=object)))
    out["has_public_dataset"] = (
        to_bool_series(out.get("has_public_dataset", pd.Series(index=out.index, dtype=object)))
        | nonblank(out.get("dataset_urls", pd.Series(index=out.index, dtype=object)))
    )

    out["has_open_material"] = (
        out["has_github"]
        | out["has_zenodo"]
        | out["has_osf"]
        | out["has_code_link"]
        | out["has_data_link"]
        | out["has_repo_links"]
        | out["has_public_dataset"]
    )

    out["open_science_any"] = (
        out["is_oa_bool"] | out["has_open_material"] | out["preregistered_bool"] | out["has_preprint"]
    )
    out["non_oa_open_signal"] = out["has_open_material"] | out["preregistered_bool"] | out["has_preprint"]

    out["open_science_score"] = pd.to_numeric(out.get("open_science_score"), errors="coerce")
    out["cited_by_count"] = pd.to_numeric(out.get("cited_by_count"), errors="coerce")

    grouped = (
        out.groupby(["discipline", "year"], as_index=False)
        .agg(
            papers=("year", "size"),
            oa_rate=("is_oa_bool", "mean"),
            open_material_rate=("has_open_material", "mean"),
            github_rate=("has_github", "mean"),
            zenodo_rate=("has_zenodo", "mean"),
            osf_rate=("has_osf", "mean"),
            dataset_rate=("has_public_dataset", "mean"),
            preregistered_rate=("preregistered_bool", "mean"),
            preprint_rate=("has_preprint", "mean"),
            high_impact_rate=("high_impact_bool", "mean"),
            non_oa_open_signal_rate=("non_oa_open_signal", "mean"),
            open_science_any_rate=("open_science_any", "mean"),
            mean_open_science_score=("open_science_score", "mean"),
            mean_citations=("cited_by_count", "mean"),
        )
        .sort_values(["discipline", "year"])
    )

    return grouped


def build_overall_summary(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return panel

    weighted = panel.copy()
    rate_cols = [
        "oa_rate",
        "open_material_rate",
        "github_rate",
        "zenodo_rate",
        "osf_rate",
        "dataset_rate",
        "preregistered_rate",
        "preprint_rate",
        "high_impact_rate",
        "non_oa_open_signal_rate",
        "open_science_any_rate",
    ]

    for col in rate_cols:
        weighted[col + "_weighted"] = weighted[col] * weighted["papers"]

    grouped = weighted.groupby("discipline", as_index=False).agg(
        papers=("papers", "sum"),
        years_covered=("year", "nunique"),
        mean_open_science_score=("mean_open_science_score", "mean"),
        mean_citations=("mean_citations", "mean"),
        oa_weighted=("oa_rate_weighted", "sum"),
        open_material_weighted=("open_material_rate_weighted", "sum"),
        github_weighted=("github_rate_weighted", "sum"),
        zenodo_weighted=("zenodo_rate_weighted", "sum"),
        osf_weighted=("osf_rate_weighted", "sum"),
        prereg_weighted=("preregistered_rate_weighted", "sum"),
        preprint_weighted=("preprint_rate_weighted", "sum"),
        high_impact_weighted=("high_impact_rate_weighted", "sum"),
        non_oa_open_signal_weighted=("non_oa_open_signal_rate_weighted", "sum"),
        open_science_any_weighted=("open_science_any_rate_weighted", "sum"),
    )

    denom = grouped["papers"].replace(0, pd.NA)
    grouped["oa_rate"] = grouped["oa_weighted"] / denom
    grouped["open_material_rate"] = grouped["open_material_weighted"] / denom
    grouped["github_rate"] = grouped["github_weighted"] / denom
    grouped["zenodo_rate"] = grouped["zenodo_weighted"] / denom
    grouped["osf_rate"] = grouped["osf_weighted"] / denom
    grouped["preregistered_rate"] = grouped["prereg_weighted"] / denom
    grouped["preprint_rate"] = grouped["preprint_weighted"] / denom
    grouped["high_impact_rate"] = grouped["high_impact_weighted"] / denom
    grouped["non_oa_open_signal_rate"] = grouped["non_oa_open_signal_weighted"] / denom
    grouped["open_science_any_rate"] = grouped["open_science_any_weighted"] / denom

    keep_cols = [
        "discipline",
        "papers",
        "years_covered",
        "oa_rate",
        "open_material_rate",
        "github_rate",
        "zenodo_rate",
        "osf_rate",
        "preregistered_rate",
        "preprint_rate",
        "high_impact_rate",
        "non_oa_open_signal_rate",
        "open_science_any_rate",
        "mean_open_science_score",
        "mean_citations",
    ]
    return grouped[keep_cols].sort_values("papers", ascending=False)


def discipline_label(value: str) -> str:
    return str(value).replace("_", " ").strip().title()


def oxford_join(items: List[str]) -> str:
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def resolve_display_title(requested_title: str, disciplines: List[str]) -> str:
    raw = str(requested_title or "").strip()
    normalized = raw.lower()
    generic = {
        "",
        "open-science benchmark by discipline",
        "stroke vs neuroscience vs neurology vs cardiology",
    }
    if normalized in generic or " vs " in normalized:
        if "stroke" in disciplines:
            return "Open-Science Uptake Across Stroke and Adjacent Fields"
        return "Open-Science Uptake Across Neighboring Disciplines"
    return raw


def format_int(value: object) -> str:
    if pd.isna(value):
        return "NA"
    return f"{int(float(value)):,}"


def format_float(value: object, digits: int = 2) -> str:
    if pd.isna(value):
        return "NA"
    return f"{float(value):,.{digits}f}"


def format_percent(value: object, digits: int = 0) -> str:
    if pd.isna(value):
        return "NA"
    return f"{float(value):.{digits}%}"


def percent_digits_for_series(series: pd.Series) -> int:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return 0
    max_value = float(clean.max())
    span = float(clean.max() - clean.min())
    if max_value <= 0.02 or span <= 0.01:
        return 2
    if max_value <= 0.12 or span <= 0.05:
        return 1
    return 0


def percent_tickformat(digits: int) -> str:
    return f".{max(0, digits)}%"


def format_metric_value(value: object, metric_kind: str, pct_digits: int = 0) -> str:
    if metric_kind == "pct":
        return format_percent(value, digits=pct_digits)
    return format_float(value, 0)


def compute_axis_range(series: pd.Series, metric_kind: str) -> List[float] | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None

    min_value = float(clean.min())
    max_value = float(clean.max())

    if metric_kind == "pct":
        span = max_value - min_value
        if span <= 0:
            pad = max(0.003, max_value * 0.18, 0.003 if max_value <= 0.05 else 0.01)
        else:
            pad = max(span * 0.22, 0.003 if max_value <= 0.05 else span * 0.12)
        lower = max(0.0, min_value - pad)
        upper = min(1.0, max_value + pad)
        if upper <= lower:
            upper = min(1.0, lower + max(0.01, pad))
        return [lower, upper]

    span = max_value - min_value
    if span <= 0:
        pad = max(1.0, abs(max_value) * 0.14)
    else:
        pad = max(span * 0.18, abs(max_value) * 0.04)
    lower = max(0.0, min_value - pad)
    upper = max_value + pad
    if upper <= lower:
        upper = lower + max(1.0, pad)
    return [lower, upper]


def build_palette(disciplines: List[str]) -> Dict[str, str]:
    if not disciplines:
        return {}
    if len(disciplines) == 1:
        return {disciplines[0]: VIRIDIS_HEXES[5]}

    max_idx = len(VIRIDIS_HEXES) - 1
    positions = [round(i * max_idx / (len(disciplines) - 1)) for i in range(len(disciplines))]
    return {discipline: VIRIDIS_HEXES[pos] for discipline, pos in zip(disciplines, positions)}


def build_metric_figure(
    panel: pd.DataFrame,
    metric: str,
    metric_title: str,
    metric_kind: str,
    palette: Dict[str, str],
) -> object:
    import plotly.graph_objects as go

    fig = go.Figure()
    ordered_disciplines = sorted(palette)
    year_min = int(panel["year"].min()) if not panel.empty else 0
    year_max = int(panel["year"].max()) if not panel.empty else 0
    metric_series = pd.to_numeric(panel.get(metric), errors="coerce")
    axis_range = compute_axis_range(metric_series, metric_kind)
    pct_digits = percent_digits_for_series(metric_series) if metric_kind == "pct" else 0

    for discipline in ordered_disciplines:
        sub = panel[panel["discipline"] == discipline].sort_values("year")
        if sub.empty:
            continue

        hovertemplate = (
            f"%{{x}}: %{{y:{percent_tickformat(pct_digits)}}}<extra>" + discipline_label(discipline) + "</extra>"
            if metric_kind == "pct"
            else "%{x}: %{y:,.0f}<extra>" + discipline_label(discipline) + "</extra>"
        )

        fig.add_trace(
            go.Scatter(
                x=sub["year"],
                y=sub[metric],
                mode="lines+markers",
                name=discipline_label(discipline),
                line={"color": palette[discipline], "width": 2.8},
                marker={"size": 7, "color": palette[discipline], "line": {"width": 1.2, "color": "rgba(255,255,255,0.9)"}},
                hovertemplate=hovertemplate,
            )
        )

        last_row = sub.iloc[-1]
        fig.add_trace(
            go.Scatter(
                x=[float(last_row["year"]) + 0.18],
                y=[last_row[metric]],
                mode="text",
                text=[f"{discipline_label(discipline)} {format_metric_value(last_row[metric], metric_kind, pct_digits)}"],
                textposition="middle right",
                textfont={"size": 11, "color": palette[discipline], "family": "Arial, sans-serif"},
                hoverinfo="skip",
                showlegend=False,
                cliponaxis=False,
            )
        )

    yaxis = {
        "title": None,
        "showgrid": True,
        "gridcolor": "rgba(17, 24, 39, 0.065)",
        "gridwidth": 1,
        "zeroline": False,
        "ticks": "outside",
        "ticklen": 4,
        "tickcolor": "rgba(107, 114, 128, 0.75)",
        "tickfont": {"size": 11, "color": "#4b5563"},
    }
    if metric_kind == "pct":
        yaxis["tickformat"] = percent_tickformat(pct_digits)
    if axis_range is not None:
        yaxis["range"] = axis_range

    fig.update_layout(
        template="none",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 36, "r": 118, "t": 6, "b": 34},
        height=292,
        hovermode="x unified",
        showlegend=False,
        font={"family": "Georgia, 'Iowan Old Style', 'Palatino Linotype', serif", "size": 12, "color": "#111827"},
    )
    fig.update_xaxes(
        title=None,
        showgrid=False,
        ticks="outside",
        ticklen=4,
        tickcolor="rgba(107, 114, 128, 0.75)",
        linecolor="rgba(156, 163, 175, 0.55)",
        tickfont={"size": 11, "color": "#4b5563"},
        range=[year_min - 0.1, year_max + 0.65] if year_min and year_max else None,
        showspikes=False,
    )
    fig.update_yaxes(**yaxis)
    return fig


def build_overall_rate_figure(overall_df: pd.DataFrame, palette: Dict[str, str]) -> object:
    import plotly.graph_objects as go

    fig = go.Figure()
    ordered = overall_df.sort_values("non_oa_open_signal_rate", ascending=True).copy()
    y_labels = [discipline_label(v) for v in ordered["discipline"].tolist()]
    max_value = float(ordered["non_oa_open_signal_rate"].max()) if not ordered.empty else 0.0

    for _, row in ordered.iterrows():
        discipline = str(row["discipline"])
        label = discipline_label(discipline)
        value = float(row["non_oa_open_signal_rate"]) if not pd.isna(row["non_oa_open_signal_rate"]) else 0.0
        color = palette.get(discipline, "#1F9E89")

        fig.add_trace(
            go.Scatter(
                x=[0, value],
                y=[label, label],
                mode="lines",
                line={"color": color, "width": 2},
                hoverinfo="skip",
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[value],
                y=[label],
                mode="markers+text",
                marker={"size": 10, "color": color, "line": {"width": 1.1, "color": "rgba(255,255,255,0.92)"}},
                text=[format_percent(value)],
                textposition="middle right",
                textfont={"size": 11, "color": color, "family": "Arial, sans-serif"},
                hovertemplate=f"{label}: %{{x:.0%}}<extra></extra>",
                showlegend=False,
            )
        )

    fig.update_layout(
        template="none",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 132, "r": 72, "t": 8, "b": 26},
        height=max(210, 78 * max(1, len(y_labels))),
        font={"family": "Georgia, 'Iowan Old Style', 'Palatino Linotype', serif", "size": 12, "color": "#111827"},
    )
    fig.update_xaxes(
        title=None,
        tickformat=".0%",
        range=[0, min(1.0, max(0.08, max_value * 1.35))],
        showgrid=True,
        gridcolor="rgba(17, 24, 39, 0.065)",
        zeroline=False,
        tickfont={"size": 11, "color": "#4b5563"},
    )
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=y_labels,
        showgrid=False,
        title=None,
        tickfont={"size": 12, "color": "#374151"},
    )
    return fig


def plotly_fragment(fig: object, include_plotlyjs: bool) -> str:
    import plotly.io as pio

    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs="cdn" if include_plotlyjs else False,
        config={"displayModeBar": False, "responsive": True},
    )


def build_legend_html(palette: Dict[str, str]) -> str:
    items: List[str] = []
    for discipline in sorted(palette):
        items.append(
            (
                '<div class="legend-item">'
                f'<span class="legend-swatch" style="background:{palette[discipline]}"></span>'
                f"<span>{html.escape(discipline_label(discipline))}</span>"
                "</div>"
            )
        )
    return "".join(items)


def build_key_stats_html(panel: pd.DataFrame, overall_df: pd.DataFrame) -> str:
    total_papers = int(panel["papers"].sum())
    disciplines = int(overall_df["discipline"].nunique())
    min_year = int(panel["year"].min())
    max_year = int(panel["year"].max())
    top_rate_row = overall_df.sort_values("non_oa_open_signal_rate", ascending=False).iloc[0]

    stats = [
        ("Disciplines in scope", format_int(disciplines)),
        ("Retrieved papers", format_int(total_papers)),
        ("Observation window", f"{min_year} to {max_year}"),
        (
            "Strongest non-OA signal",
            f"{discipline_label(str(top_rate_row['discipline']))} ({format_percent(top_rate_row['non_oa_open_signal_rate'])})",
        ),
    ]

    blocks = []
    for label, value in stats:
        blocks.append(
            (
                '<div class="stat-block">'
                f'<div class="stat-value">{html.escape(value)}</div>'
                f'<div class="stat-label">{html.escape(label)}</div>'
                "</div>"
            )
        )
    return "".join(blocks)


def build_data_notes_html(panel: pd.DataFrame, overall_df: pd.DataFrame) -> str:
    notes: List[str] = []
    total_papers = int(panel["papers"].sum())
    if total_papers <= 25:
        notes.append(
            f"Thin sample warning: the dashboard currently reflects {total_papers:,} paper"
            + ("" if total_papers == 1 else "s")
            + ". Treat rates as a pipeline check, not a field estimate."
        )
    if overall_df["discipline"].nunique() == 1:
        notes.append("Single-discipline output: cross-discipline comparisons will only become informative once other cohorts finish.")
    if panel["year"].nunique() <= 2:
        notes.append("Year coverage is narrow, so trend lines are descriptive only.")

    if not notes:
        return ""

    note_items = "".join(f"<li>{html.escape(note)}</li>" for note in notes)
    return f'<section class="callout"><h2>Reading Note</h2><ul>{note_items}</ul></section>'


def build_summary_table_html(overall_df: pd.DataFrame, palette: Dict[str, str]) -> str:
    ordered = overall_df.sort_values(["non_oa_open_signal_rate", "papers"], ascending=[False, False]).copy()
    rows: List[str] = []

    for _, row in ordered.iterrows():
        discipline = str(row["discipline"])
        rows.append(
            (
                "<tr>"
                '<td class="discipline-cell">'
                f'<span class="table-swatch" style="background:{palette.get(discipline, "#1F9E89")}"></span>'
                f"{html.escape(discipline_label(discipline))}"
                "</td>"
                f"<td>{format_int(row['papers'])}</td>"
                f"<td>{format_int(row['years_covered'])}</td>"
                f"<td>{format_percent(row['non_oa_open_signal_rate'])}</td>"
                f"<td>{format_percent(row['oa_rate'])}</td>"
                f"<td>{format_percent(row['open_material_rate'])}</td>"
                f"<td>{format_percent(row['github_rate'])}</td>"
                f"<td>{format_percent(row['preregistered_rate'])}</td>"
                f"<td>{format_percent(row['high_impact_rate'])}</td>"
                f"<td>{format_float(row['mean_citations'], 0)}</td>"
                "</tr>"
            )
        )

    return (
        "<table>"
        "<thead><tr>"
        "<th>Discipline</th>"
        "<th>Papers</th>"
        "<th>Years</th>"
        "<th>Non-OA signal</th>"
        "<th>OA</th>"
        "<th>Materials</th>"
        "<th>GitHub</th>"
        "<th>Prereg.</th>"
        "<th>High-impact</th>"
        "<th>Mean cites</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def build_dashboard_html(panel: pd.DataFrame, overall_df: pd.DataFrame, out_path: Path, title: str) -> None:
    try:
        import plotly  # noqa: F401
    except Exception as exc:
        logging.warning("Plotly unavailable; skipping HTML dashboard (%s)", exc)
        return

    disciplines = sorted(panel["discipline"].dropna().astype(str).unique().tolist())
    palette = build_palette(disciplines)
    generated_at = pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC")
    min_year = int(panel["year"].min())
    max_year = int(panel["year"].max())
    total_papers = int(panel["papers"].sum())
    top_rate_row = overall_df.sort_values("non_oa_open_signal_rate", ascending=False).iloc[0]
    display_title = resolve_display_title(title, disciplines)
    discipline_phrase = oxford_join([discipline_label(discipline) for discipline in disciplines])
    subtitle = (
        f"{discipline_phrase}, {min_year} to {max_year}. "
        f"{format_int(total_papers)} retrieved papers with non-OA signals emphasized over plain open access."
    )
    eyebrow = "Cross-discipline open-science benchmark"
    lede = (
        "Trend panels are scaled to the observed spread within each metric so separation is visible. "
        "Use the comparative ledger for absolute cross-metric magnitude; use the charts for relative ordering and change."
    )
    header_note = (
        f"Highest non-OA signal: {discipline_label(str(top_rate_row['discipline']))} "
        f"at {format_percent(top_rate_row['non_oa_open_signal_rate'])}."
    )
    overview_figure = build_overall_rate_figure(overall_df, palette)

    figure_cards: List[str] = []
    include_plotlyjs = True

    overview_html = plotly_fragment(overview_figure, include_plotlyjs=include_plotlyjs)
    include_plotlyjs = False
    figure_cards.append(
        (
            '<section class="chart-card chart-card-wide">'
            '<div class="chart-kicker">Ranked overview</div>'
            "<h2>Where richer open signals concentrate</h2>"
            "<p>Disciplines ordered by repository, preprint, or preregistration evidence, excluding plain OA.</p>"
            f"{overview_html}"
            "</section>"
        )
    )

    for metric, metric_title, metric_kind, metric_note in METRIC_SPECS:
        fig = build_metric_figure(panel, metric, metric_title, metric_kind, palette)
        fig_html = plotly_fragment(fig, include_plotlyjs=include_plotlyjs)
        include_plotlyjs = False
        figure_cards.append(
            (
                '<section class="chart-card">'
                '<div class="chart-kicker">Trend view</div>'
                f"<h2>{html.escape(metric_title)}</h2>"
                f"<p>{html.escape(metric_note)}</p>"
                f"{fig_html}"
                "</section>"
            )
        )

    summary_table_markup = build_summary_table_html(overall_df, palette)
    callout_html = build_data_notes_html(panel, overall_df)
    key_stats_html = build_key_stats_html(panel, overall_df)
    legend_html = build_legend_html(palette)

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(display_title)}</title>
  <style>
    :root {{
      --bg: #f5f2e8;
      --panel: rgba(255, 252, 246, 0.9);
      --ink: #111827;
      --muted: #4b5563;
      --rule: rgba(17, 24, 39, 0.14);
      --soft-rule: rgba(17, 24, 39, 0.08);
      --callout: rgba(31, 158, 137, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(180, 222, 44, 0.11), transparent 28rem),
        radial-gradient(circle at top right, rgba(49, 104, 142, 0.14), transparent 26rem),
        linear-gradient(180deg, #fbfaf7 0%, var(--bg) 100%);
      font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
      line-height: 1.55;
    }}
    main {{
      max-width: 1240px;
      margin: 0 auto;
      padding: 44px 28px 68px;
    }}
    header {{
      display: grid;
      grid-template-columns: minmax(0, 2.25fr) minmax(260px, 1fr);
      gap: 28px;
      align-items: start;
      border-bottom: 1px solid var(--rule);
      padding-bottom: 28px;
    }}
    .eyebrow {{
      display: inline-block;
      margin-bottom: 12px;
      font: 600 0.75rem/1.1 "Arial", sans-serif;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: #31688e;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: clamp(2.1rem, 4vw, 3.4rem);
      line-height: 0.95;
      letter-spacing: -0.03em;
      font-weight: 600;
    }}
    h2 {{
      margin: 0 0 6px;
      font-size: 1.16rem;
      line-height: 1.2;
      font-weight: 600;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.96rem;
    }}
    .subtitle {{
      font: 600 0.95rem/1.35 "Arial", sans-serif;
      letter-spacing: 0.01em;
      color: #1f2937;
      margin-bottom: 10px;
    }}
    .lede {{
      max-width: 62ch;
      font-size: 1.03rem;
    }}
    .meta {{
      display: grid;
      gap: 8px;
      justify-items: end;
      font-size: 0.86rem;
      color: var(--muted);
      text-align: right;
    }}
    .meta-note {{
      max-width: 28ch;
      padding-top: 10px;
      border-top: 1px solid var(--soft-rule);
      font-size: 0.88rem;
    }}
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 18px;
      margin: 28px 0 18px;
    }}
    .stat-block {{
      border-top: 2px solid var(--rule);
      padding-top: 12px;
      min-height: 76px;
    }}
    .stat-value {{
      font-size: 1.16rem;
      font-weight: 600;
      color: var(--ink);
    }}
    .stat-label {{
      font-size: 0.86rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-top: 4px;
    }}
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px 18px;
      margin: 16px 0 0;
    }}
    .legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: #374151;
      font-size: 0.92rem;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.52);
      border: 1px solid rgba(17, 24, 39, 0.05);
    }}
    .legend-swatch {{
      width: 28px;
      height: 4px;
      border-radius: 999px;
      display: inline-block;
    }}
    .callout {{
      margin-top: 22px;
      padding: 16px 18px;
      background: var(--callout);
      border-left: 3px solid #1f9e89;
    }}
    .callout h2 {{
      margin-bottom: 8px;
    }}
    .callout ul {{
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
    }}
    .charts-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 22px;
      margin-top: 30px;
    }}
    .chart-card {{
      background: var(--panel);
      border: 1px solid var(--soft-rule);
      border-radius: 20px;
      padding: 18px 18px 10px;
      box-shadow: 0 14px 32px rgba(17, 24, 39, 0.035);
      position: relative;
      overflow: hidden;
    }}
    .chart-card::before {{
      content: "";
      display: block;
      width: 100%;
      height: 2px;
      border-radius: 999px;
      margin-bottom: 14px;
      background: linear-gradient(90deg, #440154 0%, #1f9e89 52%, #fde725 100%);
      opacity: 0.72;
    }}
    .chart-kicker {{
      margin-bottom: 8px;
      font: 600 0.72rem/1.1 "Arial", sans-serif;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: #31688e;
    }}
    .chart-card-wide {{
      grid-column: 1 / -1;
    }}
    .table-section {{
      margin-top: 34px;
      padding-top: 24px;
      border-top: 1px solid var(--rule);
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95rem;
    }}
    thead th {{
      text-align: left;
      color: var(--muted);
      font-weight: 600;
      padding: 0 10px 10px 0;
      border-bottom: 1px solid var(--rule);
    }}
    tbody td {{
      padding: 11px 10px 11px 0;
      border-bottom: 1px solid var(--soft-rule);
      color: #1f2937;
    }}
    .discipline-cell {{
      display: flex;
      align-items: center;
      gap: 10px;
      white-space: nowrap;
    }}
    .table-swatch {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
      display: inline-block;
      flex: 0 0 auto;
    }}
    .footnote {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 0.88rem;
    }}
    @media (max-width: 980px) {{
      header {{
        grid-template-columns: 1fr;
      }}
      .meta {{
        justify-items: start;
        text-align: left;
      }}
      .charts-grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <section>
        <div class="eyebrow">{html.escape(eyebrow)}</div>
        <h1>{html.escape(display_title)}</h1>
        <div class="subtitle">{html.escape(subtitle)}</div>
        <p class="lede">{html.escape(lede)}</p>
      </section>
      <section class="meta">
        <div>Generated {html.escape(generated_at)}</div>
        <div class="meta-note">{html.escape(header_note)}</div>
      </section>
    </header>

    <section class="stats-grid">{key_stats_html}</section>
    <section class="legend">{legend_html}</section>
    {callout_html}

    <section class="charts-grid">
      {''.join(figure_cards)}
    </section>

    <section class="table-section">
      <h2>Comparative ledger</h2>
      <p>Weighted rates aggregate across the full observation window for each discipline.</p>
      <div class="table-wrap">{summary_table_markup}</div>
      <p class="footnote">Color encoding uses a viridis-derived palette. Non-OA signal excludes plain open access and counts repository, preprint, or preregistration evidence only.</p>
    </section>
  </main>
</body>
</html>
"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")


def empty_year_summary_df() -> pd.DataFrame:
    cols = [
        "discipline",
        "year",
        "papers",
        "oa_rate",
        "open_material_rate",
        "github_rate",
        "zenodo_rate",
        "osf_rate",
        "preregistered_rate",
        "preprint_rate",
        "high_impact_rate",
        "non_oa_open_signal_rate",
        "open_science_any_rate",
        "mean_open_science_score",
        "mean_citations",
    ]
    return pd.DataFrame(columns=cols)


def empty_overall_summary_df() -> pd.DataFrame:
    cols = [
        "discipline",
        "papers",
        "years_covered",
        "oa_rate",
        "open_material_rate",
        "github_rate",
        "zenodo_rate",
        "osf_rate",
        "preregistered_rate",
        "preprint_rate",
        "high_impact_rate",
        "non_oa_open_signal_rate",
        "open_science_any_rate",
        "mean_open_science_score",
        "mean_citations",
    ]
    return pd.DataFrame(columns=cols)


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    inputs = parse_input_pairs(args.inputs)
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    panels: List[pd.DataFrame] = []
    for discipline, path in inputs.items():
        if not path.exists():
            logging.warning("Missing input CSV for %s: %s", discipline, path)
            continue
        logging.info("Loading %s: %s", discipline, path)
        df = pd.read_csv(path, low_memory=False)
        panel = prepare_discipline_panel(df, discipline)
        if panel.empty:
            logging.warning("No usable rows for %s after preprocessing.", discipline)
            continue
        panels.append(panel)

    if not panels:
        logging.warning("No valid discipline inputs were loaded. Writing empty summary files.")
        year_csv = out_dir / "discipline_year_summary.csv"
        overall_csv = out_dir / "discipline_overall_summary.csv"
        empty_year_summary_df().to_csv(year_csv, index=False)
        empty_overall_summary_df().to_csv(overall_csv, index=False)
        return 0

    panel_df = pd.concat(panels, ignore_index=True)
    panel_df = panel_df.sort_values(["discipline", "year"]).reset_index(drop=True)

    year_csv = out_dir / "discipline_year_summary.csv"
    panel_df.to_csv(year_csv, index=False)
    logging.info("Saved year-level summary: %s", year_csv)

    overall_df = build_overall_summary(panel_df)
    overall_csv = out_dir / "discipline_overall_summary.csv"
    overall_df.to_csv(overall_csv, index=False)
    logging.info("Saved overall summary: %s", overall_csv)

    dashboard_html = out_dir / "discipline_dashboard.html"
    build_dashboard_html(panel_df, overall_df, dashboard_html, args.title)
    if dashboard_html.exists():
        logging.info("Saved dashboard HTML: %s", dashboard_html)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
