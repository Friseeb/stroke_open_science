#!/usr/bin/env python3
"""
Build cross-discipline, year-by-year comparison dashboard with rich insights.

Input format:
  --inputs stroke=/path/to/stroke_fully_enriched.csv neurology=/path/to/neurology_fully_enriched.csv
"""

from __future__ import annotations

import argparse
import html
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VIRIDIS_HEXES = [
    "#440154", "#482878", "#3E4989", "#31688E",
    "#26828E", "#1F9E89", "#35B779", "#6DCD59",
    "#B4DE2C", "#FDE725",
]

# Composite open-science index weights (sum to 1.0)
COMPOSITE_WEIGHTS: Dict[str, float] = {
    "oa_rate": 0.20,
    "open_material_rate": 0.25,
    "dataset_rate": 0.20,
    "github_rate": 0.10,
    "preregistered_rate": 0.15,
    "preprint_rate": 0.10,
}

METRIC_SPECS = [
    ("composite_index", "Open-science composite index (0–100)", "score",
     "Weighted composite of OA, materials, dataset, GitHub, preregistration, and preprints. Higher = more open."),
    ("non_oa_open_signal_rate", "Signals beyond open access", "pct",
     "Repository, preprint, or preregistration evidence, excluding plain open access."),
    ("oa_rate", "Open-access rate", "pct",
     "Share flagged as open access, regardless of richer open-science signals."),
    ("open_material_rate", "Repository and materials", "pct",
     "Share with any repository, code, or data link."),
    ("github_rate", "GitHub trace", "pct",
     "Share with a GitHub repository signal."),
    ("dataset_rate", "Dataset repository", "pct",
     "Share with a dataset in a public repository (DataCite, Dryad, Figshare, Dataverse)."),
    ("preregistered_rate", "Preregistration trace", "pct",
     "Share with preregistration evidence."),
    ("preprint_rate", "Preprint trace", "pct",
     "Share with a preprint server URL or identifier."),
]

PLATFORM_METRICS = [
    ("github_rate", "GitHub"),
    ("zenodo_rate", "Zenodo"),
    ("osf_rate", "OSF"),
]

GAP_METRICS = [
    ("oa_rate", "Open access"),
    ("open_material_rate", "Repository / materials"),
    ("dataset_rate", "Dataset sharing"),
    ("github_rate", "GitHub"),
    ("preregistered_rate", "Preregistration"),
    ("preprint_rate", "Preprint"),
    ("composite_index_pct", "Composite index"),
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build discipline comparison dashboard.")
    parser.add_argument("--inputs", nargs="+", required=True,
                        help="Discipline/path pairs like stroke=data/stroke/fully_enriched.csv")
    parser.add_argument("--out-dir", default="data/dashboard")
    parser.add_argument("--title", default="Open-Science Benchmark by Discipline")
    parser.add_argument("--focus-discipline", default="stroke",
                        help="Discipline to highlight in gap tracker (default: stroke)")
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


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def to_bool_series(series: pd.Series) -> pd.Series:
    def _conv(value: object) -> bool:
        if pd.isna(value):
            return False
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in {"", "none", "nan", "null", "<na>", "n/a"}:
            return False
        return s in {"true", "t", "1", "yes", "y"}
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


def discipline_label(value: str) -> str:
    return str(value).replace("_", " ").strip().title()


def oxford_join(items: List[str]) -> str:
    cleaned = [str(i).strip() for i in items if str(i).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def format_int(value: object) -> str:
    if pd.isna(value):
        return "NA"
    return f"{int(float(value)):,}"


def format_percent(value: object, digits: int = 0) -> str:
    if pd.isna(value):
        return "NA"
    return f"{float(value):.{digits}%}"


def format_float(value: object, digits: int = 2) -> str:
    if pd.isna(value):
        return "NA"
    return f"{float(value):,.{digits}f}"


def percent_digits_for_series(series: pd.Series) -> int:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return 0
    span = float(clean.max() - clean.min())
    max_val = float(clean.max())
    if max_val <= 0.02 or span <= 0.01:
        return 2
    if max_val <= 0.12 or span <= 0.05:
        return 1
    return 0


def percent_tickformat(digits: int) -> str:
    return f".{max(0, digits)}%"


def compute_axis_range(series: pd.Series, metric_kind: str) -> Optional[List[float]]:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    min_v, max_v = float(clean.min()), float(clean.max())
    if metric_kind == "pct":
        span = max_v - min_v
        pad = max(span * 0.22, 0.003 if max_v <= 0.05 else span * 0.12) if span > 0 else max(0.003, max_v * 0.18)
        return [max(0.0, min_v - pad), min(1.0, max_v + pad)]
    if metric_kind == "score":
        span = max_v - min_v
        pad = max(span * 0.15, 2.0) if span > 0 else max(2.0, max_v * 0.1)
        return [max(0.0, min_v - pad), min(100.0, max_v + pad)]
    span = max_v - min_v
    pad = max(span * 0.18, abs(max_v) * 0.04) if span > 0 else max(1.0, abs(max_v) * 0.14)
    return [max(0.0, min_v - pad), max_v + pad]


def build_palette(disciplines: List[str]) -> Dict[str, str]:
    if not disciplines:
        return {}
    if len(disciplines) == 1:
        return {disciplines[0]: VIRIDIS_HEXES[5]}
    max_idx = len(VIRIDIS_HEXES) - 1
    positions = [round(i * max_idx / (len(disciplines) - 1)) for i in range(len(disciplines))]
    return {d: VIRIDIS_HEXES[p] for d, p in zip(disciplines, positions)}


def resolve_display_title(requested_title: str, disciplines: List[str]) -> str:
    raw = str(requested_title or "").strip()
    normalized = raw.lower()
    generic = {"", "open-science benchmark by discipline", "stroke vs neuroscience vs neurology vs cardiology"}
    if normalized in generic or " vs " in normalized:
        if "stroke" in disciplines:
            return "Open-Science Uptake Across Stroke and Adjacent Fields"
        return "Open-Science Uptake Across Neighboring Disciplines"
    return raw


# ---------------------------------------------------------------------------
# Panel computation
# ---------------------------------------------------------------------------

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
        out["has_github"] | out["has_zenodo"] | out["has_osf"]
        | out["has_code_link"] | out["has_data_link"]
        | out["has_repo_links"] | out["has_public_dataset"]
    )
    out["open_science_any"] = out["is_oa_bool"] | out["has_open_material"] | out["preregistered_bool"] | out["has_preprint"]
    out["non_oa_open_signal"] = out["has_open_material"] | out["preregistered_bool"] | out["has_preprint"]
    out["open_science_score"] = pd.to_numeric(out.get("open_science_score"), errors="coerce")
    out["cited_by_count"] = pd.to_numeric(out.get("cited_by_count"), errors="coerce")

    # --- Full-cohort year aggregation ---
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

    # --- Composite index (0–100) per year ---
    def _composite(row: pd.Series) -> float:
        score = 0.0
        for col, weight in COMPOSITE_WEIGHTS.items():
            val = pd.to_numeric(row.get(col), errors="coerce")
            if pd.notna(val):
                score += float(val) * weight * 100
        return round(score, 2)

    grouped["composite_index"] = grouped.apply(_composite, axis=1)

    # --- High-impact subset year aggregation ---
    hi = out[out["high_impact_bool"]].copy()
    if len(hi) > 0:
        hi_grouped = (
            hi.groupby(["discipline", "year"], as_index=False)
            .agg(
                hi_papers=("year", "size"),
                hi_oa_rate=("is_oa_bool", "mean"),
                hi_open_material_rate=("has_open_material", "mean"),
                hi_github_rate=("has_github", "mean"),
                hi_dataset_rate=("has_public_dataset", "mean"),
                hi_preregistered_rate=("preregistered_bool", "mean"),
                hi_preprint_rate=("has_preprint", "mean"),
            )
        )
        grouped = grouped.merge(hi_grouped, on=["discipline", "year"], how="left")
    else:
        for col in ["hi_papers", "hi_oa_rate", "hi_open_material_rate",
                    "hi_github_rate", "hi_dataset_rate", "hi_preregistered_rate", "hi_preprint_rate"]:
            grouped[col] = pd.NA

    return grouped


def build_overall_summary(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return panel

    rate_cols = [
        "oa_rate", "open_material_rate", "github_rate", "zenodo_rate", "osf_rate",
        "dataset_rate", "preregistered_rate", "preprint_rate", "high_impact_rate",
        "non_oa_open_signal_rate", "open_science_any_rate",
    ]
    hi_cols = ["hi_oa_rate", "hi_open_material_rate", "hi_github_rate",
               "hi_dataset_rate", "hi_preregistered_rate", "hi_preprint_rate"]

    weighted = panel.copy()
    for col in rate_cols:
        if col in weighted.columns:
            weighted[col + "_weighted"] = weighted[col] * weighted["papers"]

    hi_available = all(c in panel.columns for c in hi_cols)
    if hi_available:
        for col in hi_cols:
            hi_papers = weighted.get("hi_papers", pd.Series(dtype=float)).fillna(0)
            weighted[col + "_weighted"] = weighted[col] * hi_papers

    agg_dict: Dict[str, Tuple] = {
        "papers": ("papers", "sum"),
        "years_covered": ("year", "nunique"),
        "mean_open_science_score": ("mean_open_science_score", "mean"),
        "mean_citations": ("mean_citations", "mean"),
        "composite_index": ("composite_index", "mean"),
    }
    if hi_available:
        agg_dict["hi_papers_total"] = ("hi_papers", "sum")

    for col in rate_cols:
        if col + "_weighted" in weighted.columns:
            agg_dict[col + "_sum"] = (col + "_weighted", "sum")

    if hi_available:
        for col in hi_cols:
            agg_dict[col + "_sum"] = (col + "_weighted", "sum")

    grouped = weighted.groupby("discipline", as_index=False).agg(**agg_dict)

    denom = grouped["papers"].replace(0, pd.NA)
    for col in rate_cols:
        sum_col = col + "_sum"
        if sum_col in grouped.columns:
            grouped[col] = grouped[sum_col] / denom

    if hi_available:
        hi_denom = grouped.get("hi_papers_total", pd.Series(dtype=float)).replace(0, pd.NA)
        for col in hi_cols:
            sum_col = col + "_sum"
            if sum_col in grouped.columns:
                grouped[col] = grouped[sum_col] / hi_denom

    grouped["composite_index_pct"] = grouped["composite_index"] / 100.0

    keep = ["discipline", "papers", "years_covered", "composite_index", "composite_index_pct",
            "oa_rate", "open_material_rate", "github_rate", "zenodo_rate", "osf_rate",
            "dataset_rate", "preregistered_rate", "preprint_rate", "high_impact_rate",
            "non_oa_open_signal_rate", "open_science_any_rate",
            "mean_open_science_score", "mean_citations"]
    if hi_available:
        keep += hi_cols

    keep = [c for c in keep if c in grouped.columns]
    return grouped[keep].sort_values("composite_index", ascending=False)


# ---------------------------------------------------------------------------
# Trend slopes
# ---------------------------------------------------------------------------

def compute_trend_slopes(panel_df: pd.DataFrame, n_years: int = 5) -> Dict[str, Dict[str, Optional[float]]]:
    """Linear slope (pp/year) per discipline × metric over last n_years."""
    try:
        import numpy as np
    except ImportError:
        return {}

    max_year = int(panel_df["year"].max())
    recent = panel_df[panel_df["year"] >= max_year - n_years + 1].copy()
    metrics = ["oa_rate", "open_material_rate", "github_rate", "dataset_rate",
               "preregistered_rate", "preprint_rate", "non_oa_open_signal_rate", "composite_index"]
    slopes: Dict[str, Dict[str, Optional[float]]] = {}
    for discipline in panel_df["discipline"].unique():
        sub = recent[recent["discipline"] == discipline].sort_values("year")
        slopes[str(discipline)] = {}
        for metric in metrics:
            y = pd.to_numeric(sub.get(metric), errors="coerce").values
            x = sub["year"].astype(float).values
            valid = ~__import__("numpy").isnan(y)
            if valid.sum() >= 2:
                slope = float(__import__("numpy").polyfit(x[valid], y[valid], 1)[0])
                slopes[str(discipline)][metric] = slope
            else:
                slopes[str(discipline)][metric] = None
    return slopes


# ---------------------------------------------------------------------------
# Narrative auto-summary
# ---------------------------------------------------------------------------

def build_narrative_summary(
    panel_df: pd.DataFrame,
    overall_df: pd.DataFrame,
    slopes: Dict[str, Dict[str, Optional[float]]],
    focus: str = "stroke",
) -> str:
    if overall_df.empty:
        return ""

    focus = focus.lower()
    disciplines = sorted(overall_df["discipline"].astype(str).unique().tolist())
    has_focus = focus in disciplines

    sentences: List[str] = []

    # --- Total scope ---
    total_papers = int(panel_df["papers"].sum())
    min_yr = int(panel_df["year"].min())
    max_yr = int(panel_df["year"].max())
    n_disc = len(disciplines)
    sentences.append(
        f"This benchmark covers {total_papers:,} retrieved papers across "
        f"{n_disc} discipline{'s' if n_disc != 1 else ''} ({oxford_join([discipline_label(d) for d in disciplines])}) "
        f"from {min_yr} to {max_yr}."
    )

    # --- Composite index for focus discipline ---
    if has_focus:
        focus_row = overall_df[overall_df["discipline"] == focus]
        if not focus_row.empty:
            ci = focus_row["composite_index"].iloc[0]
            best_row = overall_df.sort_values("composite_index", ascending=False).iloc[0]
            best_d = str(best_row["discipline"])
            best_ci = float(best_row["composite_index"])
            rank = int(overall_df["composite_index"].rank(ascending=False).loc[focus_row.index[0]])
            gap = best_ci - float(ci)
            if best_d == focus:
                sentences.append(
                    f"{discipline_label(focus)} leads all disciplines with a composite open-science index "
                    f"of {ci:.0f}/100."
                )
            else:
                sentences.append(
                    f"{discipline_label(focus)} ranks {rank}{_ordinal_suffix(rank)} of {n_disc} disciplines "
                    f"with a composite open-science index of {ci:.0f}/100, "
                    f"{gap:.0f} points behind {discipline_label(best_d)} ({best_ci:.0f}/100)."
                )

    # --- OA trend ---
    if has_focus and "oa_rate" in panel_df.columns:
        focus_years = panel_df[panel_df["discipline"] == focus].sort_values("year")
        if len(focus_years) >= 2:
            oa_start = focus_years.iloc[0]["oa_rate"]
            oa_end = focus_years.iloc[-1]["oa_rate"]
            yr_start = int(focus_years.iloc[0]["year"])
            yr_end = int(focus_years.iloc[-1]["year"])
            if pd.notna(oa_start) and pd.notna(oa_end):
                change = (float(oa_end) - float(oa_start)) * 100
                direction = "rose" if change >= 0 else "fell"
                sentences.append(
                    f"{discipline_label(focus)}'s open-access rate {direction} "
                    f"from {float(oa_start):.0%} ({yr_start}) to {float(oa_end):.0%} ({yr_end}), "
                    f"a {abs(change):.0f} pp {'gain' if change >= 0 else 'decline'} over {yr_end - yr_start} years."
                )

    # --- Data sharing leader ---
    if "dataset_rate" in overall_df.columns:
        best_data = overall_df.sort_values("dataset_rate", ascending=False).iloc[0]
        best_data_d = str(best_data["discipline"])
        best_data_r = float(best_data["dataset_rate"])
        sentences.append(
            f"{discipline_label(best_data_d)} leads in dataset sharing at {best_data_r:.0%}."
        )

    # --- Preregistration rarity ---
    if "preregistered_rate" in overall_df.columns:
        max_prereg = float(overall_df["preregistered_rate"].max())
        if max_prereg < 0.05:
            sentences.append(
                f"Preregistration remains rare across all disciplines (peak {max_prereg:.1%}), "
                f"representing the largest structural gap in open-science practice."
            )

    # --- High-impact vs all ---
    if has_focus and "hi_dataset_rate" in overall_df.columns:
        focus_row = overall_df[overall_df["discipline"] == focus]
        if not focus_row.empty:
            hi_dr = focus_row["hi_dataset_rate"].iloc[0]
            all_dr = focus_row["dataset_rate"].iloc[0]
            if pd.notna(hi_dr) and pd.notna(all_dr) and float(all_dr) > 0:
                ratio = float(hi_dr) / float(all_dr)
                sentences.append(
                    f"In {discipline_label(focus)}, high-impact papers show "
                    f"{float(hi_dr):.0%} dataset sharing vs {float(all_dr):.0%} for the full cohort "
                    f"({ratio:.1f}× higher), suggesting a visibility gradient in data-sharing practice."
                )

    # --- Trend sentence ---
    focus_slopes = slopes.get(focus, {})
    if focus_slopes:
        improving = [m for m, s in focus_slopes.items() if s is not None and s > 0.002]
        if improving:
            names = [n for m, n, *_ in METRIC_SPECS if m in improving][:3]
            if names:
                sentences.append(
                    f"Positive trends over the most recent 5 years: {oxford_join(names)}."
                )

    return " ".join(sentences)


def _ordinal_suffix(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


# ---------------------------------------------------------------------------
# Plotly helpers
# ---------------------------------------------------------------------------

def plotly_fragment(fig: object, include_plotlyjs: bool) -> str:
    import plotly.io as pio
    return pio.to_html(
        fig, full_html=False,
        include_plotlyjs="cdn" if include_plotlyjs else False,
        config={"displayModeBar": False, "responsive": True},
    )


# ---------------------------------------------------------------------------
# Plotly figures
# ---------------------------------------------------------------------------

def build_metric_figure(
    panel: pd.DataFrame,
    metric: str,
    metric_title: str,
    metric_kind: str,
    palette: Dict[str, str],
) -> object:
    import plotly.graph_objects as go

    fig = go.Figure()
    ordered = sorted(palette)
    year_min = int(panel["year"].min()) if not panel.empty else 2015
    year_max = int(panel["year"].max()) if not panel.empty else 2024
    metric_series = pd.to_numeric(panel.get(metric), errors="coerce")
    axis_range = compute_axis_range(metric_series, metric_kind)
    pct_digits = percent_digits_for_series(metric_series) if metric_kind == "pct" else 0

    for discipline in ordered:
        sub = panel[panel["discipline"] == discipline].sort_values("year")
        if sub.empty:
            continue

        if metric_kind == "pct":
            hover = "%{x}: %{y:" + percent_tickformat(pct_digits) + "}<extra>" + discipline_label(discipline) + "</extra>"
        elif metric_kind == "score":
            hover = "%{x}: %{y:.1f}<extra>" + discipline_label(discipline) + "</extra>"
        else:
            hover = "%{x}: %{y:,.0f}<extra>" + discipline_label(discipline) + "</extra>"

        fig.add_trace(go.Scatter(
            x=sub["year"], y=sub[metric],
            mode="lines+markers",
            name=discipline_label(discipline),
            line={"color": palette[discipline], "width": 2.8},
            marker={"size": 7, "color": palette[discipline], "line": {"width": 1.2, "color": "rgba(255,255,255,0.9)"}},
            hovertemplate=hover,
        ))

        last_row = sub.iloc[-1]
        if metric_kind == "pct":
            label_val = format_percent(last_row[metric], pct_digits)
        elif metric_kind == "score":
            label_val = f"{float(last_row[metric]):.0f}" if pd.notna(last_row[metric]) else ""
        else:
            label_val = format_float(last_row[metric], 0)

        fig.add_trace(go.Scatter(
            x=[float(last_row["year"]) + 0.18], y=[last_row[metric]],
            mode="text",
            text=[f"{discipline_label(discipline)} {label_val}"],
            textposition="middle right",
            textfont={"size": 10, "color": palette[discipline], "family": "Arial, sans-serif"},
            hoverinfo="skip", showlegend=False, cliponaxis=False,
        ))

    yaxis: Dict = {
        "title": None, "showgrid": True, "gridcolor": "rgba(17,24,39,0.065)",
        "zeroline": False, "ticks": "outside", "ticklen": 4,
        "tickcolor": "rgba(107,114,128,0.75)", "tickfont": {"size": 11, "color": "#4b5563"},
    }
    if metric_kind == "pct":
        yaxis["tickformat"] = percent_tickformat(pct_digits)
    if axis_range:
        yaxis["range"] = axis_range

    fig.update_layout(
        template="none", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 36, "r": 118, "t": 6, "b": 56},
        height=310, hovermode="x unified", showlegend=False,
        font={"family": "Georgia,'Iowan Old Style','Palatino Linotype',serif", "size": 12, "color": "#111827"},
    )
    fig.update_xaxes(
        title=None, showgrid=False, ticks="outside", ticklen=4,
        tickcolor="rgba(107,114,128,0.75)", linecolor="rgba(156,163,175,0.55)",
        tickfont={"size": 11, "color": "#4b5563"},
        range=[year_min - 0.1, year_max + 0.75],
        rangeslider={"visible": True, "thickness": 0.08, "bgcolor": "rgba(17,24,39,0.04)"},
    )
    fig.update_yaxes(**yaxis)
    return fig


def build_heatmap_figure(overall_df: pd.DataFrame, palette: Dict[str, str]) -> object:
    import plotly.graph_objects as go

    metrics = [
        ("composite_index", "Composite\nindex", "score"),
        ("oa_rate", "Open\naccess", "pct"),
        ("open_material_rate", "Repository\n& materials", "pct"),
        ("dataset_rate", "Dataset\nsharing", "pct"),
        ("github_rate", "GitHub", "pct"),
        ("preregistered_rate", "Prereg.", "pct"),
        ("preprint_rate", "Preprint", "pct"),
    ]

    disciplines = overall_df["discipline"].astype(str).tolist()
    z_vals, text_vals = [], []

    for _, row in overall_df.iterrows():
        row_z, row_t = [], []
        for col, _, kind in metrics:
            val = pd.to_numeric(row.get(col), errors="coerce")
            if pd.isna(val):
                row_z.append(0.0)
                row_t.append("—")
            elif kind == "pct":
                row_z.append(float(val) * 100)
                row_t.append(f"{float(val):.0%}")
            else:
                row_z.append(float(val))
                row_t.append(f"{float(val):.0f}")
        z_vals.append(row_z)
        text_vals.append(row_t)

    col_labels = [label.replace("\n", "<br>") for _, label, _ in metrics]
    row_labels = [discipline_label(d) for d in disciplines]

    fig = go.Figure(go.Heatmap(
        z=z_vals,
        x=col_labels,
        y=row_labels,
        text=text_vals,
        texttemplate="%{text}",
        textfont={"size": 13, "color": "white", "family": "Arial, sans-serif"},
        colorscale="Viridis",
        showscale=True,
        colorbar={"title": {"text": "Value", "font": {"size": 11}},
                  "thickness": 14, "len": 0.8, "tickfont": {"size": 10}},
        hovertemplate="%{y} · %{x}: %{text}<extra></extra>",
        zmin=0, zmax=100,
    ))

    fig.update_layout(
        template="none", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 10, "r": 80, "t": 10, "b": 10},
        height=max(220, 80 * max(1, len(disciplines))),
        font={"family": "Georgia,'Iowan Old Style','Palatino Linotype',serif", "color": "#111827"},
    )
    fig.update_xaxes(side="top", tickfont={"size": 11, "color": "#374151"}, tickangle=0)
    fig.update_yaxes(tickfont={"size": 12, "color": "#374151"})
    return fig


def build_platform_figure(panel_df: pd.DataFrame, palette: Dict[str, str]) -> object:
    import plotly.graph_objects as go

    overall = (
        panel_df.groupby("discipline", as_index=False)
        .apply(lambda g: pd.Series({
            col: float((g[col] * g["papers"]).sum()) / max(1, g["papers"].sum())
            for col, _ in PLATFORM_METRICS if col in g.columns
        }))
        .reset_index(drop=True)
    )
    if "discipline" not in overall.columns:
        overall = panel_df.groupby("discipline", as_index=False)[[col for col, _ in PLATFORM_METRICS if col in panel_df.columns]].mean()

    disciplines = sorted(palette.keys())
    fig = go.Figure()

    platform_colors = ["#31688E", "#1F9E89", "#6DCD59"]
    for i, (col, label) in enumerate(PLATFORM_METRICS):
        if col not in overall.columns:
            continue
        y_vals = [float(overall[overall["discipline"] == d][col].iloc[0])
                  if len(overall[overall["discipline"] == d]) > 0 else 0.0
                  for d in disciplines]
        fig.add_trace(go.Bar(
            name=label,
            x=[discipline_label(d) for d in disciplines],
            y=y_vals,
            marker_color=platform_colors[i % len(platform_colors)],
            text=[f"{v:.1%}" for v in y_vals],
            textposition="outside",
            textfont={"size": 10},
            hovertemplate=f"{label}: %{{y:.1%}}<extra></extra>",
        ))

    fig.update_layout(
        barmode="group", template="none",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 36, "r": 20, "t": 6, "b": 36},
        height=280,
        legend={"orientation": "h", "y": -0.18, "x": 0.5, "xanchor": "center",
                "font": {"size": 11}},
        font={"family": "Georgia,'Iowan Old Style','Palatino Linotype',serif", "color": "#111827"},
    )
    fig.update_yaxes(tickformat=".0%", showgrid=True, gridcolor="rgba(17,24,39,0.07)", zeroline=False)
    fig.update_xaxes(showgrid=False)
    return fig


def build_highimpact_comparison_figure(overall_df: pd.DataFrame, palette: Dict[str, str]) -> object:
    import plotly.graph_objects as go

    hi_cols = ["hi_oa_rate", "hi_open_material_rate", "hi_dataset_rate",
               "hi_github_rate", "hi_preregistered_rate"]
    all_cols = ["oa_rate", "open_material_rate", "dataset_rate",
                "github_rate", "preregistered_rate"]
    labels = ["Open access", "Materials", "Dataset", "GitHub", "Prereg."]

    has_hi = all(c in overall_df.columns for c in hi_cols)
    disciplines = sorted(palette.keys())
    fig = go.Figure()

    for discipline in disciplines:
        row = overall_df[overall_df["discipline"] == discipline]
        if row.empty:
            continue
        row = row.iloc[0]

        all_vals = [float(pd.to_numeric(row.get(c), errors="coerce") or 0) for c in all_cols]
        fig.add_trace(go.Bar(
            name=f"{discipline_label(discipline)} — All",
            x=labels, y=all_vals,
            marker_color=palette[discipline],
            opacity=0.55,
            text=[f"{v:.0%}" for v in all_vals],
            textposition="outside", textfont={"size": 9},
            hovertemplate="%{x}: %{y:.1%}<extra>" + discipline_label(discipline) + " (all)</extra>",
        ))

        if has_hi:
            hi_vals = [float(pd.to_numeric(row.get(c), errors="coerce") or 0) for c in hi_cols]
            fig.add_trace(go.Bar(
                name=f"{discipline_label(discipline)} — High-impact",
                x=labels, y=hi_vals,
                marker_color=palette[discipline],
                opacity=1.0,
                marker_pattern_shape="/",
                text=[f"{v:.0%}" for v in hi_vals],
                textposition="outside", textfont={"size": 9},
                hovertemplate="%{x}: %{y:.1%}<extra>" + discipline_label(discipline) + " (high-impact)</extra>",
            ))

    fig.update_layout(
        barmode="group", template="none",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 36, "r": 20, "t": 6, "b": 36},
        height=320,
        legend={"orientation": "h", "y": -0.24, "x": 0.5, "xanchor": "center",
                "font": {"size": 10}, "traceorder": "normal"},
        font={"family": "Georgia,'Iowan Old Style','Palatino Linotype',serif", "color": "#111827"},
    )
    fig.update_yaxes(tickformat=".0%", showgrid=True, gridcolor="rgba(17,24,39,0.07)", zeroline=False)
    fig.update_xaxes(showgrid=False)
    return fig


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def build_legend_html(palette: Dict[str, str]) -> str:
    items: List[str] = []
    for discipline in sorted(palette):
        items.append(
            f'<div class="legend-item">'
            f'<span class="legend-swatch" style="background:{palette[discipline]}"></span>'
            f"<span>{html.escape(discipline_label(discipline))}</span>"
            f"</div>"
        )
    return "".join(items)


def build_key_stats_html(panel: pd.DataFrame, overall_df: pd.DataFrame,
                          slopes: Dict, focus: str = "stroke") -> str:
    total_papers = int(panel["papers"].sum())
    disciplines = int(overall_df["discipline"].nunique())
    min_year = int(panel["year"].min())
    max_year = int(panel["year"].max())

    best_ci_row = overall_df.sort_values("composite_index", ascending=False).iloc[0]
    best_ci_d = str(best_ci_row["discipline"])
    best_ci_v = float(best_ci_row["composite_index"])

    focus_row = overall_df[overall_df["discipline"] == focus.lower()]
    focus_ci = float(focus_row["composite_index"].iloc[0]) if not focus_row.empty else None

    slope_label = "—"
    focus_slopes = slopes.get(focus.lower(), {})
    ci_slope = focus_slopes.get("composite_index")
    if ci_slope is not None:
        sign = "+" if ci_slope >= 0 else ""
        slope_label = f"{sign}{ci_slope:.1f} pts/yr ({discipline_label(focus)})"

    stats = [
        ("Retrieved papers", format_int(total_papers)),
        ("Disciplines", format_int(disciplines)),
        ("Observation window", f"{min_year}–{max_year}"),
        ("Top composite index", f"{discipline_label(best_ci_d)} ({best_ci_v:.0f}/100)"),
        (f"{discipline_label(focus)} index" if focus_ci else "Composite index",
         f"{focus_ci:.0f}/100" if focus_ci else "NA"),
        ("Recent index trend", slope_label),
    ]

    blocks = []
    for label, value in stats:
        blocks.append(
            f'<div class="stat-block">'
            f'<div class="stat-value">{html.escape(value)}</div>'
            f'<div class="stat-label">{html.escape(label)}</div>'
            f"</div>"
        )
    return "".join(blocks)


def build_gap_tracker_html(overall_df: pd.DataFrame, palette: Dict[str, str],
                            focus: str = "stroke") -> str:
    focus = focus.lower()
    focus_row = overall_df[overall_df["discipline"] == focus]
    if focus_row.empty:
        return ""

    focus_row = focus_row.iloc[0]
    items: List[str] = []

    for col, label in GAP_METRICS:
        if col not in overall_df.columns:
            continue
        focus_val = pd.to_numeric(focus_row.get(col), errors="coerce")
        if pd.isna(focus_val):
            continue

        all_vals = pd.to_numeric(overall_df[col], errors="coerce").dropna()
        if all_vals.empty:
            continue

        best_val = float(all_vals.max())
        focus_val = float(focus_val)
        best_disc_row = overall_df.loc[all_vals.idxmax()]
        best_disc = str(best_disc_row["discipline"])

        if col == "composite_index":
            focus_pct = focus_val / 100.0
            best_pct = best_val / 100.0
            focus_str = f"{focus_val:.0f}/100"
            best_str = f"{best_val:.0f}/100"
        else:
            focus_pct = focus_val
            best_pct = best_val
            focus_str = f"{focus_val:.1%}"
            best_str = f"{best_val:.1%}"

        gap_pct = best_pct - focus_pct
        bar_fill = focus_pct / best_pct if best_pct > 0 else 1.0
        bar_fill = min(1.0, max(0.0, bar_fill))
        focus_color = palette.get(focus, "#1F9E89")

        is_leader = (best_disc == focus)
        badge = (
            '<span class="gap-badge gap-leader">Leader</span>'
            if is_leader else
            f'<span class="gap-badge">−{gap_pct:.1%} vs {discipline_label(best_disc)} ({best_str})</span>'
        )

        items.append(
            f'<div class="gap-row">'
            f'<div class="gap-label">{html.escape(label)}</div>'
            f'<div class="gap-bar-wrap">'
            f'<div class="gap-bar-fill" style="width:{bar_fill*100:.1f}%;background:{focus_color}"></div>'
            f'</div>'
            f'<div class="gap-value">{html.escape(focus_str)}</div>'
            f'{badge}'
            f'</div>'
        )

    if not items:
        return ""

    return (
        f'<div class="gap-tracker">'
        f'<h3>{html.escape(discipline_label(focus))} vs field leaders</h3>'
        f'{"".join(items)}'
        f'</div>'
    )


def build_summary_table_html(overall_df: pd.DataFrame, palette: Dict[str, str]) -> str:
    ordered = overall_df.sort_values("composite_index", ascending=False).copy()
    rows: List[str] = []

    for _, row in ordered.iterrows():
        discipline = str(row["discipline"])
        rows.append(
            "<tr>"
            '<td class="discipline-cell">'
            f'<span class="table-swatch" style="background:{palette.get(discipline, "#1F9E89")}"></span>'
            f"{html.escape(discipline_label(discipline))}"
            "</td>"
            f"<td><strong>{format_int(row.get('composite_index'))} <span style='color:#9ca3af;font-weight:400'>/100</span></strong></td>"
            f"<td>{format_int(row.get('papers'))}</td>"
            f"<td>{format_percent(row.get('oa_rate'))}</td>"
            f"<td>{format_percent(row.get('open_material_rate'))}</td>"
            f"<td>{format_percent(row.get('dataset_rate'))}</td>"
            f"<td>{format_percent(row.get('github_rate'))}</td>"
            f"<td>{format_percent(row.get('preregistered_rate'))}</td>"
            f"<td>{format_percent(row.get('preprint_rate'))}</td>"
            f"<td>{format_float(row.get('mean_citations'), 0)}</td>"
            "</tr>"
        )

    return (
        "<table>"
        "<thead><tr>"
        "<th>Discipline</th><th>Index</th><th>Papers</th>"
        "<th>OA</th><th>Materials</th><th>Dataset</th>"
        "<th>GitHub</th><th>Prereg.</th><th>Preprint</th><th>Mean cites</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def build_data_notes_html(panel: pd.DataFrame, overall_df: pd.DataFrame) -> str:
    notes: List[str] = []
    total_papers = int(panel["papers"].sum())
    if total_papers <= 25:
        notes.append(f"Thin sample: {total_papers:,} papers. Treat rates as pipeline checks, not field estimates.")
    if overall_df["discipline"].nunique() == 1:
        notes.append("Single-discipline mode — cross-field comparisons will only appear once other cohorts finish.")
    if panel["year"].nunique() <= 2:
        notes.append("Year coverage is narrow; trend lines are descriptive only.")
    if not notes:
        return ""
    return (
        '<section class="callout">'
        "<h2>Reading note</h2>"
        f"<ul>{''.join(f'<li>{html.escape(n)}</li>' for n in notes)}</ul>"
        "</section>"
    )


# ---------------------------------------------------------------------------
# Main dashboard builder
# ---------------------------------------------------------------------------

def build_dashboard_html(
    panel: pd.DataFrame, overall_df: pd.DataFrame,
    out_path: Path, title: str, focus_discipline: str = "stroke",
) -> None:
    try:
        import plotly  # noqa: F401
    except Exception as exc:
        logging.warning("Plotly unavailable; skipping HTML dashboard (%s)", exc)
        return

    disciplines = sorted(panel["discipline"].dropna().astype(str).unique().tolist())
    palette = build_palette(disciplines)
    slopes = compute_trend_slopes(panel)
    generated_at = pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC")
    display_title = resolve_display_title(title, disciplines)
    total_papers = int(panel["papers"].sum())
    min_year = int(panel["year"].min())
    max_year = int(panel["year"].max())
    discipline_phrase = oxford_join([discipline_label(d) for d in disciplines])

    narrative = build_narrative_summary(panel, overall_df, slopes, focus=focus_discipline)
    callout_html = build_data_notes_html(panel, overall_df)
    key_stats_html = build_key_stats_html(panel, overall_df, slopes, focus=focus_discipline)
    legend_html = build_legend_html(palette)
    gap_html = build_gap_tracker_html(overall_df, palette, focus=focus_discipline)
    summary_table_markup = build_summary_table_html(overall_df, palette)

    include_plotlyjs = True
    figure_sections: List[str] = []

    # --- Heatmap ---
    heatmap_fig = build_heatmap_figure(overall_df, palette)
    heatmap_html = plotly_fragment(heatmap_fig, include_plotlyjs=include_plotlyjs)
    include_plotlyjs = False
    figure_sections.append(
        '<section class="section-block">'
        '<div class="section-header"><div class="section-kicker">At a glance</div>'
        '<h2>Cross-discipline open-science snapshot</h2>'
        '<p>Full-period weighted averages per discipline. Composite index (0–100) combines OA, materials, data, GitHub, preregistration, and preprints.</p></div>'
        f'<div class="chart-full">{heatmap_html}</div>'
        '</section>'
    )

    # --- Platform breakdown + High-impact comparison ---
    platform_fig = build_platform_figure(panel, palette)
    platform_html = plotly_fragment(platform_fig, include_plotlyjs=False)

    hi_fig = build_highimpact_comparison_figure(overall_df, palette)
    hi_html = plotly_fragment(hi_fig, include_plotlyjs=False)

    figure_sections.append(
        '<section class="section-block">'
        '<div class="section-header"><div class="section-kicker">Deep dives</div>'
        '<h2>Repository platforms and high-impact papers</h2></div>'
        '<div class="charts-2col">'
        '<div class="chart-card">'
        '<div class="chart-kicker">Platform breakdown</div>'
        '<h3>Where researchers deposit code &amp; data</h3>'
        f'<p>Share of papers with a GitHub, Zenodo, or OSF link.</p>{platform_html}</div>'
        '<div class="chart-card">'
        '<div class="chart-kicker">High-impact vs all papers</div>'
        '<h3>Do high-impact papers share more?</h3>'
        f'<p>Solid bars = all papers; hatched = high-impact subset (IF ≥ 10 or citation ≥ 90th pct).</p>{hi_html}</div>'
        '</div></section>'
    )

    # --- Gap tracker ---
    if gap_html:
        figure_sections.append(
            '<section class="section-block">'
            '<div class="section-header"><div class="section-kicker">Positioning</div>'
            f'<h2>{html.escape(discipline_label(focus_discipline))} vs field leaders</h2>'
            '<p>Each bar shows where the focus discipline sits relative to the field-leading discipline on that metric.</p></div>'
            f'{gap_html}'
            '</section>'
        )

    # --- Trend charts ---
    trend_cards: List[str] = []
    for metric, metric_title, metric_kind, metric_note in METRIC_SPECS:
        if metric not in panel.columns:
            continue
        fig = build_metric_figure(panel, metric, metric_title, metric_kind, palette)
        fig_html = plotly_fragment(fig, include_plotlyjs=False)
        trend_cards.append(
            f'<div class="chart-card">'
            f'<div class="chart-kicker">Trend · {html.escape(metric_title)}</div>'
            f"<p>{html.escape(metric_note)}</p>"
            f"{fig_html}"
            f"</div>"
        )

    if trend_cards:
        figure_sections.append(
            '<section class="section-block">'
            '<div class="section-header"><div class="section-kicker">Year-by-year trends</div>'
            '<h2>How practices are changing over time</h2>'
            '<p>Click legend entries to show/hide disciplines. Drag the range selector below each chart to zoom.</p></div>'
            f'<div class="charts-grid">{"".join(trend_cards)}</div>'
            '</section>'
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(display_title)}</title>
  <style>
    :root {{
      --bg: #f5f2e8;
      --panel: rgba(255,252,246,0.92);
      --ink: #111827;
      --muted: #4b5563;
      --rule: rgba(17,24,39,0.14);
      --soft-rule: rgba(17,24,39,0.07);
      --accent: #31688e;
      --callout-bg: rgba(31,158,137,0.07);
      --callout-border: #1f9e89;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      color: var(--ink);
      background: radial-gradient(circle at top left, rgba(180,222,44,0.10), transparent 28rem),
                  radial-gradient(circle at top right, rgba(49,104,142,0.13), transparent 26rem),
                  linear-gradient(180deg, #fbfaf7 0%, var(--bg) 100%);
      font-family: Georgia,"Iowan Old Style","Palatino Linotype",serif;
      line-height: 1.55;
    }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 48px 28px 80px; }}

    /* ── Hero ── */
    .hero {{
      border-bottom: 1px solid var(--rule);
      padding-bottom: 32px;
      margin-bottom: 32px;
    }}
    .eyebrow {{
      display: inline-block;
      margin-bottom: 14px;
      font: 600 0.72rem/1 "Arial",sans-serif;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--accent);
    }}
    h1 {{
      font-size: clamp(2rem,4vw,3.2rem);
      line-height: 1.0;
      letter-spacing: -0.03em;
      font-weight: 700;
      margin-bottom: 16px;
    }}
    .hero-meta {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 24px;
      align-items: start;
      margin-top: 12px;
    }}
    .narrative {{
      font-size: 1.05rem;
      color: #1f2937;
      line-height: 1.65;
      max-width: 80ch;
    }}
    .generated-at {{
      font-size: 0.82rem;
      color: var(--muted);
      white-space: nowrap;
      padding-top: 6px;
    }}

    /* ── Key stats ── */
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit,minmax(160px,1fr));
      gap: 18px;
      margin: 28px 0;
    }}
    .stat-block {{
      border-top: 2px solid var(--rule);
      padding-top: 12px;
    }}
    .stat-value {{
      font-size: 1.15rem;
      font-weight: 700;
      color: var(--ink);
      margin-bottom: 4px;
    }}
    .stat-label {{
      font-size: 0.80rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.07em;
    }}

    /* ── Legend ── */
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 16px;
      margin: 16px 0 0;
    }}
    .legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: #374151;
      font-size: 0.90rem;
      padding: 5px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.55);
      border: 1px solid rgba(17,24,39,0.06);
    }}
    .legend-swatch {{
      width: 26px;
      height: 4px;
      border-radius: 999px;
    }}

    /* ── Callout ── */
    .callout {{
      margin: 20px 0;
      padding: 14px 18px;
      background: var(--callout-bg);
      border-left: 3px solid var(--callout-border);
      border-radius: 0 6px 6px 0;
    }}
    .callout h2 {{ font-size: 0.95rem; margin-bottom: 6px; }}
    .callout ul {{ padding-left: 18px; color: var(--muted); font-size: 0.93rem; }}

    /* ── Sections ── */
    .section-block {{
      margin-top: 52px;
    }}
    .section-header {{
      margin-bottom: 20px;
      border-bottom: 1px solid var(--soft-rule);
      padding-bottom: 12px;
    }}
    .section-kicker {{
      font: 600 0.70rem/1 "Arial",sans-serif;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 8px;
    }}
    .section-header h2 {{
      font-size: 1.55rem;
      letter-spacing: -0.02em;
      margin-bottom: 6px;
    }}
    .section-header p {{
      font-size: 0.95rem;
      color: var(--muted);
      max-width: 70ch;
    }}

    /* ── Chart containers ── */
    .chart-full {{ width: 100%; }}
    .charts-2col {{
      display: grid;
      grid-template-columns: repeat(2,minmax(0,1fr));
      gap: 22px;
      margin-top: 0;
    }}
    .charts-grid {{
      display: grid;
      grid-template-columns: repeat(2,minmax(0,1fr));
      gap: 22px;
    }}
    .chart-card {{
      background: var(--panel);
      border: 1px solid var(--soft-rule);
      border-radius: 18px;
      padding: 18px 18px 12px;
      box-shadow: 0 12px 28px rgba(17,24,39,0.032);
      position: relative;
      overflow: hidden;
    }}
    .chart-card::before {{
      content: "";
      display: block;
      width: 100%;
      height: 2px;
      border-radius: 999px;
      margin-bottom: 12px;
      background: linear-gradient(90deg,#440154 0%,#1f9e89 52%,#fde725 100%);
      opacity: 0.65;
    }}
    .chart-kicker {{
      font: 600 0.68rem/1 "Arial",sans-serif;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 6px;
    }}
    .chart-card h3 {{
      font-size: 1.05rem;
      margin-bottom: 4px;
    }}
    .chart-card p {{
      font-size: 0.90rem;
      color: var(--muted);
      margin-bottom: 4px;
      max-width: 52ch;
    }}

    /* ── Gap tracker ── */
    .gap-tracker {{ margin-top: 4px; }}
    .gap-tracker h3 {{
      font-size: 1.02rem;
      margin-bottom: 16px;
      color: var(--ink);
    }}
    .gap-row {{
      display: grid;
      grid-template-columns: 180px 1fr 70px 200px;
      align-items: center;
      gap: 12px;
      padding: 10px 0;
      border-bottom: 1px solid var(--soft-rule);
    }}
    .gap-label {{
      font-size: 0.92rem;
      color: #374151;
      font-weight: 600;
    }}
    .gap-bar-wrap {{
      height: 8px;
      background: rgba(17,24,39,0.07);
      border-radius: 999px;
      overflow: hidden;
    }}
    .gap-bar-fill {{
      height: 100%;
      border-radius: 999px;
      transition: width 0.3s;
    }}
    .gap-value {{
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--ink);
      text-align: right;
    }}
    .gap-badge {{
      font-size: 0.80rem;
      padding: 3px 9px;
      border-radius: 999px;
      background: rgba(49,104,142,0.09);
      color: #31688e;
      white-space: nowrap;
    }}
    .gap-leader {{
      background: rgba(31,158,137,0.12);
      color: #1f9e89;
    }}

    /* ── Summary table ── */
    .table-section {{
      margin-top: 48px;
      padding-top: 24px;
      border-top: 1px solid var(--rule);
    }}
    .table-section h2 {{
      font-size: 1.4rem;
      margin-bottom: 6px;
    }}
    .table-section > p {{
      font-size: 0.93rem;
      color: var(--muted);
      margin-bottom: 16px;
    }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.94rem; }}
    thead th {{
      text-align: left;
      color: var(--muted);
      font-weight: 600;
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
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
      width: 10px; height: 10px;
      border-radius: 999px;
      flex: 0 0 auto;
    }}
    .footnote {{
      margin-top: 16px;
      color: var(--muted);
      font-size: 0.86rem;
    }}

    /* ── Responsive ── */
    @media (max-width: 900px) {{
      .charts-2col, .charts-grid {{ grid-template-columns: 1fr; }}
      .hero-meta {{ grid-template-columns: 1fr; }}
      .gap-row {{ grid-template-columns: 140px 1fr 60px; }}
      .gap-badge {{ display: none; }}
    }}
  </style>
</head>
<body>
<main>

  <header class="hero">
    <div class="eyebrow">Cross-discipline open-science benchmark</div>
    <h1>{html.escape(display_title)}</h1>
    <div class="hero-meta">
      <p class="narrative">{html.escape(narrative)}</p>
      <div class="generated-at">Generated {html.escape(generated_at)}</div>
    </div>
  </header>

  <div class="stats-grid">{key_stats_html}</div>
  <div class="legend">{legend_html}</div>
  {callout_html}

  {''.join(figure_sections)}

  <section class="table-section">
    <h2>Comparative ledger</h2>
    <p>Weighted rates across the full observation window, ranked by composite open-science index.</p>
    <div class="table-wrap">{summary_table_markup}</div>
    <p class="footnote">
      Composite index = weighted average of OA (20%), repository/materials (25%), dataset sharing (20%),
      GitHub (10%), preregistration (15%), and preprints (10%), scaled 0–100.
      High-impact: IF ≥ 10 or citation ≥ 90th percentile within discipline-year.
      Color palette: viridis-derived.
    </p>
  </section>

</main>
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")


# ---------------------------------------------------------------------------
# Summary CSV schemas
# ---------------------------------------------------------------------------

def empty_year_summary_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "discipline", "year", "papers", "oa_rate", "open_material_rate",
        "github_rate", "zenodo_rate", "osf_rate", "dataset_rate",
        "preregistered_rate", "preprint_rate", "high_impact_rate",
        "non_oa_open_signal_rate", "open_science_any_rate",
        "mean_open_science_score", "mean_citations", "composite_index",
    ])


def empty_overall_summary_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "discipline", "papers", "years_covered", "composite_index",
        "oa_rate", "open_material_rate", "github_rate", "zenodo_rate",
        "osf_rate", "dataset_rate", "preregistered_rate", "preprint_rate",
        "high_impact_rate", "non_oa_open_signal_rate", "open_science_any_rate",
        "mean_open_science_score", "mean_citations",
    ])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

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
        logging.warning("No valid discipline inputs. Writing empty summary files.")
        empty_year_summary_df().to_csv(out_dir / "discipline_year_summary.csv", index=False)
        empty_overall_summary_df().to_csv(out_dir / "discipline_overall_summary.csv", index=False)
        return 0

    panel_df = pd.concat(panels, ignore_index=True).sort_values(["discipline", "year"]).reset_index(drop=True)

    year_csv = out_dir / "discipline_year_summary.csv"
    panel_df.to_csv(year_csv, index=False)
    logging.info("Saved year-level summary: %s", year_csv)

    overall_df = build_overall_summary(panel_df)
    overall_csv = out_dir / "discipline_overall_summary.csv"
    overall_df.to_csv(overall_csv, index=False)
    logging.info("Saved overall summary: %s", overall_csv)

    focus = getattr(args, "focus_discipline", "stroke")
    dashboard_html = out_dir / "discipline_dashboard.html"
    build_dashboard_html(panel_df, overall_df, dashboard_html, args.title, focus_discipline=focus)
    if dashboard_html.exists():
        logging.info("Saved dashboard HTML: %s", dashboard_html)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
