#!/usr/bin/env python3
"""Numbers, tables and figures for the WSC 2026 (Seoul) talk on incentives for
open science in stroke research.

Inputs
------
* ``data/full_release/<discipline>-fully_enriched.csv`` - the published June 2026
  benchmark (OpenAlex title-search corpus, 2015-2026, four disciplines).
* ``data/enrichment/<discipline>_work_metadata.csv`` (optional, produced by
  ``scripts/enrich_openalex_work_metadata.py``) - work type, source type, OA
  status (gold/green/hybrid/bronze/diamond/closed), preprint locations,
  first-author country and funders.

Corpus rules (documented here because they drive every number in the talk)
--------------------------------------------------------------------------
* Years 2015-2025. 2026 is a partial year (pull ran June 2026) and is dropped.
  2025 is near-complete but OpenAlex indexing lags, so it is flagged in outputs.
* When enrichment is available the corpus is enriched journal articles and reviews only
  (``work_type in {article, review}`` and ``primary_source_type == journal``, DOI required).
  No-DOI records are dropped: they are mostly conference abstracts. Without enrichment,
  records whose "journal" is a repository or preprint server are dropped by name as a fallback.
* Open access = OpenAlex current ``oa_status`` other than "closed" (falls back to the
  release ``is_oa`` flag only when the status is unknown).
* Code sharing = GitHub / code link / Zenodo / OSF link mentioned by a paper.
* Data sharing = public dataset repository link detected by regex or DataCite.
* Registration = trial / review registry identifier or explicit preregistration
  wording in title+abstract (NCT, ISRCTN, PROSPERO CRD42, ChiCTR, UMIN, ACTRN,
  EudraCT, DRKS, CTRI, IRCT, NTR, osf.io, "preregistered", "registered report").
  Reported among records WITH an abstract, because the denominator matters.
* Preprint = an OpenAlex location on a preprint server for a journal article.

Outputs land in ``talk/outputs/`` : tables/*.csv, numbers.json, figures/*.png|svg.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

DISCIPLINES = ["stroke", "neurology", "neuroscience", "cardiology"]
FOCUS = "stroke"
YEARS = list(range(2015, 2026))
PARTIAL_YEARS = {2025}

# Validated categorical palette (dataviz reference instance), fixed slot order.
SERIES = {"stroke": "#2a78d6", "neurology": "#eb6834", "neuroscience": "#1baf7a", "cardiology": "#eda100"}
# Ordinal blue ramp for OA types (open -> less open), grey for closed.
OA_STATUS_ORDER = ["diamond", "gold", "hybrid", "green", "bronze", "closed"]
OA_STATUS_COLORS = {"diamond": "#0d366b", "gold": "#1c5cab", "hybrid": "#2a78d6", "green": "#5598e7", "bronze": "#9ec5f4", "closed": "#d9d8d4"}
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e6e5e1"

NON_JOURNAL_SOURCE_PATTERN = re.compile(
    r"figshare|zenodo|research square|^pubmed|doaj|ssrn|medrxiv|biorxiv|arxiv|"
    r"preprints|dryad|osf|mendeley data|europe pmc|hal \(|repository|eprints|"
    r"dissertation|thesis|proquest",
    re.IGNORECASE,
)

REGISTRY_PATTERNS = {
    "trial_registry": re.compile(
        r"\bNCT\s?\d{8}\b|\bISRCTN\s?\d{8}\b|\bChiCTR[-\w]*\d{6,}|\bUMIN\s?\d{9}\b|"
        r"\bACTRN\s?\d{14}\b|\bEudraCT\b|\b\d{4}-\d{6}-\d{2}\b|\bDRKS\s?\d{8}\b|"
        r"\bCTRI/\d{4}/\d{2}/\d{6}\b|\bIRCT\w*\d{6,}|\bNTR\s?\d{4,}\b|\bNL\s?\d{4,}\b(?=.*netherlands trial)|"
        r"\bjRCT\w*\d{6,}|\bKCT\s?\d{7}\b|\bclinicaltrials\.gov\b|\bTCTR\d{11}\b|\bPACTR\d{15}\b",
        re.IGNORECASE,
    ),
    "prospero": re.compile(r"\bCRD\s?42\d{6}\b|\bPROSPERO\b", re.IGNORECASE),
    "preregistration_wording": re.compile(
        r"\bpre-?registered\b|\bpre-?registration\b|\bregistered report\b|\bosf\.io/\w+|"
        r"\bprospectively registered\b|\bregistered protocol\b",
        re.IGNORECASE,
    ),
}


def to_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def nonempty(series: pd.Series) -> pd.Series:
    return series.notna() & (series.astype(str).str.strip() != "") & (series.astype(str).str.lower() != "nan")


def load_discipline(discipline: str, release_dir: Path, enrichment_dir: Path) -> pd.DataFrame:
    path = release_dir / f"{discipline}-fully_enriched.csv"
    logging.info("Loading %s", path)
    df = pd.read_csv(path, low_memory=False)
    df["discipline"] = discipline
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["doi_norm"] = df["doi"].astype(str).str.lower().str.replace(r"^https?://(dx\.)?doi\.org/", "", regex=True)
    df.loc[df["doi"].isna(), "doi_norm"] = pd.NA

    enr_path = enrichment_dir / f"{discipline}_work_metadata.csv"
    df["enriched"] = False
    if enr_path.exists():
        enr = pd.read_csv(enr_path, low_memory=False).drop_duplicates("doi_norm")
        keep = [
            "doi_norm", "work_type", "oa_status", "primary_source_name", "primary_source_type",
            "primary_source_is_in_doaj", "has_preprint_version", "is_preprint_record", "preprint_servers",
            "first_author_country", "countries", "funders", "n_funders", "is_retracted", "has_fulltext",
        ]
        enr = enr[[c for c in keep if c in enr.columns]]
        df = df.merge(enr, on="doi_norm", how="left")
        df["enriched"] = df["work_type"].notna()
        logging.info("  enrichment matched %d / %d DOIs", int(df["enriched"].sum()), int(df["doi_norm"].notna().sum()))
    return df


def apply_corpus_rules(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    df = df[df["year"].isin(YEARS)].copy()
    if df["enriched"].any():
        # Keep only enriched journal articles/reviews. Records without a DOI are dropped: they are
        # dominated by conference abstracts (e.g. ISC abstracts in Stroke) that would otherwise be
        # counted as closed journal articles and distort journal-level open-access rates.
        is_article = df["work_type"].isin(["article", "review"]) & (df["primary_source_type"] == "journal")
        df["in_corpus"] = is_article & df["enriched"]
        df["corpus_rule"] = "openalex_type_doi_only"
    else:
        df["in_corpus"] = ~df["journal"].astype(str).str.contains(NON_JOURNAL_SOURCE_PATTERN, na=False)
        df["corpus_rule"] = "source_name_fallback"
    df = df[df["in_corpus"]].copy()
    logging.info("  corpus: %d -> %d records (%s)", before, len(df), df["corpus_rule"].iloc[0] if len(df) else "n/a")

    # Derived flags. One open-access definition throughout: OpenAlex's current oa_status when the
    # record is enriched (anything but "closed"), else the release's is_oa flag.
    release_is_oa = to_bool(df["is_oa"])
    if "oa_status" in df.columns:
        status_known = df["oa_status"].isin(OA_STATUS_ORDER)
        df["is_oa"] = (df["oa_status"].ne("closed") & status_known) | (~status_known & release_is_oa)
    else:
        df["is_oa"] = release_is_oa
    if "oa_status" in df.columns:
        df["oa_status"] = df["oa_status"].where(df["oa_status"].isin(OA_STATUS_ORDER), None)
    df["shares_code"] = nonempty(df["github"]) | nonempty(df["code_link"]) | nonempty(df["zenodo"]) | nonempty(df["osf"])
    df["shares_data"] = to_bool(df["has_public_dataset"]) | nonempty(df["data_link"]) | nonempty(df["dataset_urls"])
    df["shares_any"] = df["shares_code"] | df["shares_data"]
    df["high_impact"] = to_bool(df["high_impact_flag"])
    df["has_abstract"] = nonempty(df["abstract"])
    text = (df["title"].fillna("") + " " + df["abstract"].fillna("")).astype(str)
    for name, pattern in REGISTRY_PATTERNS.items():
        df[f"reg_{name}"] = text.str.contains(pattern, na=False)
    df["registered_any"] = df[[f"reg_{n}" for n in REGISTRY_PATTERNS]].any(axis=1)
    if "has_preprint_version" in df.columns:
        df["has_preprint_version"] = to_bool(df["has_preprint_version"].fillna(False))
    else:
        df["has_preprint_version"] = False
    return df


def rate_table(df: pd.DataFrame, by: List[str]) -> pd.DataFrame:
    grp = df.groupby(by, dropna=False)
    out = grp.agg(
        n=("doi_norm", "size"),
        oa_rate=("is_oa", "mean"),
        code_rate=("shares_code", "mean"),
        data_rate=("shares_data", "mean"),
        any_sharing_rate=("shares_any", "mean"),
        preprint_rate=("has_preprint_version", "mean"),
        high_impact_rate=("high_impact", "mean"),
        n_with_abstract=("has_abstract", "sum"),
    ).reset_index()
    reg = df[df["has_abstract"]].groupby(by, dropna=False).agg(
        registration_rate=("registered_any", "mean"),
        trial_registry_rate=("reg_trial_registry", "mean"),
        prospero_rate=("reg_prospero", "mean"),
        prereg_wording_rate=("reg_preregistration_wording", "mean"),
    ).reset_index()
    out = out.merge(reg, on=by, how="left")
    if "year" in by:
        out["partial_year"] = out["year"].isin(PARTIAL_YEARS)
    return out


def oa_status_table(df: pd.DataFrame, by: List[str]) -> pd.DataFrame:
    sub = df[df["oa_status"].notna()] if "oa_status" in df.columns else df.iloc[0:0]
    if sub.empty:
        return pd.DataFrame()
    ct = pd.crosstab([sub[c] for c in by], sub["oa_status"], normalize="index").reset_index()
    for s in OA_STATUS_ORDER:
        if s not in ct.columns:
            ct[s] = 0.0
    ct["n"] = sub.groupby(by).size().values
    return ct[by + OA_STATUS_ORDER + ["n"]]


# ----------------------------------------------------------------------------- figures
def style_axes(ax, ylabel: str = "", pct: bool = True):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT2, labelsize=11)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    if ylabel:
        ax.set_ylabel(ylabel, color=TEXT2, fontsize=11)
    if pct:
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))


def new_fig(w: float = 12, h: float = 6.75):
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    return fig, ax


def save(fig, out_dir: Path, name: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / f"{name}.png", bbox_inches="tight", facecolor="white")
    fig.savefig(out_dir / f"{name}.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logging.info("  figure %s", name)


def fig_trend_by_discipline(by_year: pd.DataFrame, metric: str, title: str, ylabel: str, out_dir: Path, name: str, ylim: Optional[float] = None):
    fig, ax = new_fig()
    for disc in DISCIPLINES:
        sub = by_year[by_year["discipline"] == disc].sort_values("year")
        if sub.empty:
            continue
        full = sub[~sub["partial_year"]]
        part = sub[sub["partial_year"] | (sub["year"] == full["year"].max())]
        lw = 3.0 if disc == FOCUS else 2.0
        ax.plot(full["year"], full[metric], color=SERIES[disc], linewidth=lw, solid_capstyle="round")
        ax.plot(part["year"], part[metric], color=SERIES[disc], linewidth=lw, linestyle=(0, (2, 2)))
        last = sub.iloc[-1]
        ax.text(last["year"] + 0.15, last[metric], f"{disc}  {last[metric]:.0%}" if ylim is None or ylim > 0.2 else f"{disc}  {last[metric]:.1%}",
                color=SERIES[disc], fontsize=11, va="center", fontweight="bold" if disc == FOCUS else "normal")
    ax.set_xlim(YEARS[0] - 0.3, YEARS[-1] + 2.6)
    ax.set_xticks(YEARS)
    if ylim:
        ax.set_ylim(0, ylim)
    else:
        ax.set_ylim(0, None)
    style_axes(ax, ylabel)
    ax.set_title(title, loc="left", fontsize=15, color=TEXT, fontweight="bold", pad=14)
    fig.text(0.01, -0.02, "Dashed segment: 2025 is a partial year (indexing lag). Source: OpenAlex title search; journal articles and reviews.", color=TEXT2, fontsize=9)
    save(fig, out_dir, name)


def fig_oa_status_stacked(oa_year: pd.DataFrame, out_dir: Path, name: str, title: str):
    if oa_year.empty:
        return
    fig, ax = new_fig()
    years = oa_year["year"].astype(int).values
    bottom = np.zeros(len(years))
    for status in OA_STATUS_ORDER:
        vals = oa_year[status].values
        ax.bar(years, vals, bottom=bottom, color=OA_STATUS_COLORS[status], width=0.8, edgecolor="white", linewidth=1.5, label=status)
        bottom += vals
    ax.set_ylim(0, 1)
    ax.set_xticks(years)
    style_axes(ax, "share of articles")
    ax.legend(ncol=6, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.08), fontsize=10)
    ax.set_title(title, loc="left", fontsize=15, color=TEXT, fontweight="bold", pad=14)
    save(fig, out_dir, name)


def fig_dot_compare(table: pd.DataFrame, label_col: str, metrics: Dict[str, str], title: str, out_dir: Path, name: str, xmax: Optional[float] = None):
    """Horizontal dot plot of the FIRST metric, with the remaining metrics printed as text columns.

    Sharing rates in this corpus are all below 2%, so plotting them as dots next to
    open-access rates (15-100%) produces unreadable overlaps; a text column keeps
    the exact value visible without a second axis.
    """
    cols = list(metrics)
    primary = cols[0]
    extras = cols[1:]
    fig, ax = new_fig(12, 0.5 * len(table) + 2.2)
    table = table.iloc[::-1]
    y = np.arange(len(table))
    ax.hlines(y, 0, table[primary], color=GRID, linewidth=2, zorder=1)
    ax.scatter(table[primary], y, s=110, color="#2a78d6", zorder=3, edgecolor="white", linewidth=1.5)
    for yi, v in zip(y, table[primary]):
        ax.text(v + 0.012, yi, f"{v:.0%}", color=TEXT2, fontsize=9.5, va="center")
    ax.set_yticks(y)
    ax.set_yticklabels([f"{str(l)[:48]}  (n={int(n):,})" for l, n in zip(table[label_col], table["n"])], fontsize=10.5, color=TEXT)
    style_axes(ax, pct=False)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=GRID)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlim(0, 1.08)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xlabel(metrics[primary], color=TEXT2, fontsize=11)
    # Text columns to the right of the plot area.
    for j, col in enumerate(extras):
        xpos = 1.12 + 0.16 * j
        ax.text(xpos, len(table) - 0.35, metrics[col], transform=ax.get_yaxis_transform(), color=TEXT2, fontsize=9.5, ha="left", fontweight="bold")
        for yi, v in zip(y, table[col]):
            ax.text(xpos, yi, f"{v:.1%}", transform=ax.get_yaxis_transform(), color=TEXT, fontsize=10, va="center", ha="left")
    ax.set_ylim(-0.7, len(table) - 0.1)
    ax.set_title(title, loc="left", fontsize=15, color=TEXT, fontweight="bold", pad=14)
    save(fig, out_dir, name)


def fig_registration(by_year: pd.DataFrame, out_dir: Path, name: str):
    fig, ax = new_fig()
    sub = by_year[by_year["discipline"] == FOCUS].sort_values("year")
    for col, lab, color in [("trial_registry_rate", "trial registry ID (NCT, ISRCTN, ...)", "#2a78d6"), ("prospero_rate", "PROSPERO", "#eb6834"), ("prereg_wording_rate", "'preregistered' / registered report / OSF", "#1baf7a")]:
        ax.plot(sub["year"], sub[col], color=color, linewidth=2.5, label=lab)
        last = sub.iloc[-1]
        ax.text(last["year"] + 0.15, last[col], f"{last[col]:.1%}", color=color, fontsize=11, va="center")
    ax.set_xticks(YEARS)
    ax.set_xlim(YEARS[0] - 0.3, YEARS[-1] + 1.2)
    ax.set_ylim(0, None)
    style_axes(ax, "share of stroke articles with an abstract")
    ax.legend(frameon=False, loc="upper left", fontsize=10)
    ax.set_title("Registration signals in stroke abstracts", loc="left", fontsize=15, color=TEXT, fontweight="bold", pad=14)
    fig.text(0.01, -0.02, "Regex on title + abstract; denominators are articles with an abstract in OpenAlex. Understates registration declared only in full text.", color=TEXT2, fontsize=9)
    save(fig, out_dir, name)


def fig_high_impact(hi: pd.DataFrame, out_dir: Path, name: str):
    fig, ax = new_fig(12, 5.5)
    metrics = [("oa_rate", "Open access"), ("data_rate", "Data in a repository"), ("code_rate", "Code / repository link"), ("preprint_rate", "Preprint version"), ("registration_rate", "Registration signal")]
    x = np.arange(len(metrics))
    width = 0.38
    for i, (flag, lab, color) in enumerate([(False, "all other stroke articles", "#9ec5f4"), (True, "high-impact stroke articles", "#2a78d6")]):
        row = hi[hi["high_impact"] == flag].iloc[0]
        vals = [row[m] for m, _ in metrics]
        bars = ax.bar(x + (i - 0.5) * width, vals, width, color=color, label=lab, edgecolor="white", linewidth=1.5)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.0%}" if v >= 0.1 else f"{v:.1%}", ha="center", color=TEXT2, fontsize=9.5)
    ax.set_xticks(x)
    ax.set_xticklabels([l for _, l in metrics], fontsize=11, color=TEXT)
    ax.set_ylim(0, 1)
    style_axes(ax)
    ax.legend(frameon=False, fontsize=10)
    ax.set_title("High-impact stroke articles vs the rest", loc="left", fontsize=15, color=TEXT, fontweight="bold", pad=14)
    fig.text(0.01, -0.03, "High impact: journal impact factor >= 10 or citations in the top 10% of the stroke corpus (all years pooled).", color=TEXT2, fontsize=9)
    save(fig, out_dir, name)


# ----------------------------------------------------------------------------- main
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release-dir", default="data/full_release")
    parser.add_argument("--enrichment-dir", default="data/enrichment")
    parser.add_argument("--out-dir", default="talk/outputs")
    parser.add_argument("--disciplines", nargs="+", default=DISCIPLINES)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")

    out = Path(args.out_dir)
    tables = out / "tables"
    figures = out / "figures"
    tables.mkdir(parents=True, exist_ok=True)

    frames = []
    for disc in args.disciplines:
        df = load_discipline(disc, Path(args.release_dir), Path(args.enrichment_dir))
        frames.append(apply_corpus_rules(df))
    data = pd.concat(frames, ignore_index=True)

    by_year = rate_table(data, ["discipline", "year"])
    overall = rate_table(data, ["discipline"])
    by_year.to_csv(tables / "rates_by_discipline_year.csv", index=False)
    overall.to_csv(tables / "rates_by_discipline.csv", index=False)

    stroke = data[data["discipline"] == FOCUS]
    oa_year = oa_status_table(stroke, ["year"])
    oa_disc = oa_status_table(data, ["discipline"])
    oa_year.to_csv(tables / "stroke_oa_status_by_year.csv", index=False)
    oa_disc.to_csv(tables / "oa_status_by_discipline.csv", index=False)

    hi = rate_table(stroke, ["high_impact"])
    hi.to_csv(tables / "stroke_high_impact_vs_rest.csv", index=False)

    journals = rate_table(stroke, ["journal_norm"]).sort_values("n", ascending=False)
    journals = journals[journals["journal_norm"].notna()].head(15)
    journals.to_csv(tables / "stroke_top_journals.csv", index=False)

    numbers: Dict[str, object] = {
        "corpus_rule": data["corpus_rule"].iloc[0],
        "years": [YEARS[0], YEARS[-1]],
        "partial_years": sorted(PARTIAL_YEARS),
        "n_by_discipline": overall.set_index("discipline")["n"].to_dict(),
        "overall": overall.set_index("discipline").round(4).to_dict(orient="index"),
        "stroke_first_last_year": {
            str(int(r.year)): {"oa_rate": round(r.oa_rate, 4), "code_rate": round(r.code_rate, 4), "data_rate": round(r.data_rate, 4), "preprint_rate": round(r.preprint_rate, 4), "registration_rate": round(r.registration_rate, 4) if pd.notna(r.registration_rate) else None}
            for r in by_year[(by_year["discipline"] == FOCUS) & (by_year["year"].isin([YEARS[0], 2024]))].itertuples()
        },
        "stroke_high_impact_vs_rest": hi.set_index("high_impact").round(4).to_dict(orient="index"),
        "stroke_oa_status_overall": oa_disc[oa_disc["discipline"] == FOCUS].round(4).to_dict(orient="records") if not oa_disc.empty else None,
        "enrichment_coverage": {d: round(float(data[data["discipline"] == d]["enriched"].mean()), 4) for d in args.disciplines},
    }

    if "first_author_country" in stroke.columns and stroke["first_author_country"].notna().any():
        countries = rate_table(stroke[stroke["first_author_country"].notna()], ["first_author_country"]).sort_values("n", ascending=False).head(12)
        countries.to_csv(tables / "stroke_top_first_author_countries.csv", index=False)
        fig_dot_compare(countries, "first_author_country", {"oa_rate": "open access", "data_rate": "data repo", "code_rate": "code link"}, "Stroke articles by first-author country, 2015-2025", figures, "fig08_countries")
        numbers["stroke_top_countries"] = countries.set_index("first_author_country")[["n", "oa_rate", "data_rate", "code_rate"]].round(4).to_dict(orient="index")
    if "funders" in stroke.columns and stroke["funders"].notna().any():
        f = stroke[stroke["funders"].notna()].copy()
        f["funder"] = f["funders"].astype(str).str.split("|")
        f = f.explode("funder")
        f = f[f["funder"].str.len() > 0]
        funders = rate_table(f, ["funder"]).sort_values("n", ascending=False).head(12)
        funders.to_csv(tables / "stroke_top_funders.csv", index=False)
        fig_dot_compare(funders, "funder", {"oa_rate": "open access", "data_rate": "data repo", "code_rate": "code link"}, "Stroke articles by acknowledged funder, 2015-2025", figures, "fig09_funders")
        numbers["stroke_funded_share"] = round(float(stroke["funders"].notna().mean()), 4)

    # Figures
    fig_trend_by_discipline(by_year, "oa_rate", "Open access in stroke vs comparator fields", "share of articles open access", figures, "fig01_oa_trend")
    fig_oa_status_stacked(oa_year, figures, "fig02_stroke_oa_status", "How stroke articles are open: OA status by year")
    fig_trend_by_discipline(by_year, "data_rate", "Data deposited in a public repository", "share of articles", figures, "fig03_data_sharing_trend", ylim=None)
    fig_trend_by_discipline(by_year, "code_rate", "Code or repository link in the article", "share of articles", figures, "fig04_code_sharing_trend", ylim=None)
    fig_trend_by_discipline(by_year, "preprint_rate", "Articles with a preprint version", "share of articles", figures, "fig05_preprint_trend", ylim=None)
    fig_registration(by_year, figures, "fig06_stroke_registration")
    fig_high_impact(hi, figures, "fig07_high_impact_vs_rest")
    fig_dot_compare(journals.head(12), "journal_norm", {"oa_rate": "open access", "data_rate": "data repo", "code_rate": "code link"}, "Where stroke is published: top journals, 2015-2025", figures, "fig10_journals")

    (out / "numbers.json").write_text(json.dumps(numbers, indent=2, default=str))
    logging.info("Wrote %s", out / "numbers.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
