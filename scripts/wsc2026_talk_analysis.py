#!/usr/bin/env python3
"""Numbers, tables and figures for the WSC 2026 (Seoul) talk on incentives for
open science in stroke research.

Input: one pipeline ``fully_enriched.csv`` per discipline, as written by
``scripts/search_stroke_dois.py``. No enrichment join and no re-derivation here: the
corpus flag (``in_article_corpus``), OpenAlex work metadata (``oa_status``,
``has_preprint_version``, ``first_author_country``, ``funders``), registration
flags (``registration_signal``) and the data-availability audit (``das_*``) all
come from the pipeline. A legacy release that predates a flag gets it computed
by the pipeline's own function (same code path as the dashboard builder).

Corpus rules (documented here because they drive every number in the talk)
--------------------------------------------------------------------------
* Years 2015-2025. 2026 is a partial year (pull ran June 2026) and is dropped.
  2025 is near-complete but OpenAlex indexing lags, so it is flagged in outputs.
* Corpus = ``in_article_corpus`` (OpenAlex type article/review in a journal source,
  DOI required; conference abstracts without a DOI are out).
* Open access = the one definition in ``build_discipline_dashboard.derive_open_access``
  (OpenAlex ``oa_status`` known and not "closed"; legacy inference only when unknown).
* Code sharing = GitHub / code link / Zenodo / OSF link mentioned by a paper.
* Data sharing = public dataset repository link detected by regex or DataCite.
* Registration = ``registration_signal`` (trial / review registry identifier or explicit
  preregistration wording in title+abstract), reported among records WITH an abstract.
* Preprint = ``has_preprint_version`` (an OpenAlex location on a preprint server).
* Data-availability statements = the pipeline's Europe PMC audit (``das_available``,
  ``das_has_statement``, ``das_primary``), open-access full text only. The audit also flags
  whether the whole full text mentions GitHub or a trial registration (``das_mentions_*``):
  the full-text estimates of code sharing and registration for the audited sample.
* Equity = ``first_author_income_group`` (World Bank, via the pipeline config). Open-access
  routes are split into free-to-author (diamond, green), paid (gold, hybrid) and other (bronze).
* Commitment league tables (institutions, journals, funders, countries) use only verified,
  full-text signals from the audited sample: repository deposit or public-source reuse in the
  DAS, GitHub in the full text, trial registration in the full text. Minimum n audited applies.

Usage:
  python scripts/wsc2026_talk_analysis.py --inputs stroke=data/talk/stroke/fully_enriched.csv \
      neurology=... neuroscience=... cardiology=...
  python scripts/wsc2026_talk_analysis.py --input-dir data/talk    # <dir>/<discipline>/fully_enriched.csv

Outputs land in ``talk/outputs/``: tables/*.csv, numbers.json, figures/*.png|svg and
``das_audit/`` (tables, summary, fig11).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_discipline_dashboard as dash  # noqa: E402  (sibling module: one OA definition, bool/blank helpers)

DISCIPLINES = ["stroke", "neurology", "neuroscience", "cardiology"]
FOCUS = "stroke"
YEARS = list(range(2015, 2026))
PARTIAL_YEARS = {2025}

# Validated categorical palette (dataviz reference instance), fixed slot order.
SERIES = {"stroke": "#2a78d6", "neurology": "#eb6834", "neuroscience": "#1baf7a", "cardiology": "#eda100"}
# Ordinal blue ramp for OA types (open -> less open), grey for closed.
OA_STATUS_ORDER = list(dash.OA_STATUS_ORDER)
OA_STATUS_COLORS = {"diamond": "#0d366b", "gold": "#1c5cab", "hybrid": "#2a78d6", "green": "#5598e7", "bronze": "#9ec5f4", "closed": "#d9d8d4"}
DAS_ORDER = list(dash.DAS_ORDER)
DAS_COLORS = {"repository": "#0d366b", "public_source": "#1c5cab", "controlled_or_restricted": "#2a78d6", "on_request": "#86b6ef",
              "in_article": "#cde2fb", "not_available_or_na": "#e6e5e1", "other_or_unclear": "#f0efec", "no_statement": "#d9d8d4"}
DAS_LABELS = {"repository": "authors' deposit in a repository", "public_source": "public or third-party dataset",
              "controlled_or_restricted": "controlled / restricted", "on_request": "on request", "in_article": "in article or supplement",
              "not_available_or_na": "not available / N/A", "other_or_unclear": "other / unclear", "no_statement": "no statement found"}
INCOME_ORDER = ["high", "upper_middle", "lower_middle", "low"]
INCOME_LABELS = {"high": "high income", "upper_middle": "upper-middle income", "lower_middle": "lower-middle income", "low": "low income"}
# Who pays to be read: free-to-author routes vs article-processing-charge routes.
OA_ROUTE = {"diamond": "free", "green": "free", "gold": "paid", "hybrid": "paid", "bronze": "other", "closed": "closed"}
OA_ROUTE_ORDER = ["free", "paid", "other", "closed"]
OA_ROUTE_COLORS = {"free": "#0d366b", "paid": "#5598e7", "other": "#cde2fb", "closed": "#d9d8d4"}
OA_ROUTE_LABELS = {"free": "free to author (diamond, green)", "paid": "APC paid (gold, hybrid)", "other": "bronze (free to read, no licence)", "closed": "closed"}
MIN_N_AUDITED = 30
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e6e5e1"

REG_COLS = {"trial_registry": "reg_trial_registry", "prospero": "reg_prospero", "preregistration_wording": "reg_preregistration_wording"}


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    return df[name] if name in df.columns else pd.Series(pd.NA, index=df.index, dtype=object)


def _clean(series: pd.Series) -> pd.Series:
    s = series.fillna("").astype(str).str.strip()
    return s.replace({"nan": "", "None": "", "<NA>": ""})


# ----------------------------------------------------------------------------- loading
def load_discipline(discipline: str, path: Path) -> pd.DataFrame:
    logging.info("Loading %s", path)
    df = pd.read_csv(path, low_memory=False)
    df["discipline"] = discipline
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")

    missing = [c for c in ("in_article_corpus", "registration_signal") if c not in df.columns]
    if missing:
        # Legacy release: derive the flags with the pipeline's own functions (same as the dashboard builder).
        import search_stroke_dois as pipeline  # heavy import, only on demand

        if "in_article_corpus" not in df.columns:
            df = pipeline.apply_corpus_flag(df)
        if "registration_signal" not in df.columns:
            df = pipeline.apply_registration_flags(df)
        logging.info("  %s lacked %s; derived with the pipeline functions", path.name, ", ".join(missing))

    has_meta = _clean(_col(df, "work_type")).ne("")
    logging.info("  %d rows, OpenAlex work metadata on %d (%.1f%%), DAS audited on %d",
                 len(df), int(has_meta.sum()), 100 * has_meta.mean() if len(df) else 0,
                 int(dash.to_bool_series(_col(df, "das_available")).sum()))
    return df


def apply_corpus_rules(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    df = df[df["year"].isin(YEARS)].copy()
    rules = sorted(set(_clean(_col(df, "corpus_rule")).tolist()) - {""})
    df["corpus_rule"] = rules[0] if len(rules) == 1 else ("|".join(rules) if rules else "in_article_corpus")
    df = df[dash.to_bool_series(df["in_article_corpus"])].copy()
    logging.info("  corpus: %d -> %d records (%s)", before, len(df), df["corpus_rule"].iloc[0] if len(df) else "n/a")

    # Derived flags from pipeline columns only.
    df["is_oa"] = dash.derive_open_access(df)
    status = _clean(_col(df, "oa_status")).str.lower()
    df["oa_status"] = status.where(status.isin(OA_STATUS_ORDER), None)
    df["shares_code"] = dash.nonblank(_col(df, "github")) | dash.nonblank(_col(df, "code_link")) | dash.nonblank(_col(df, "zenodo")) | dash.nonblank(_col(df, "osf"))
    df["shares_data"] = dash.to_bool_series(_col(df, "has_public_dataset")) | dash.nonblank(_col(df, "data_link")) | dash.nonblank(_col(df, "dataset_urls"))
    df["shares_any"] = df["shares_code"] | df["shares_data"]
    df["high_impact"] = dash.to_bool_series(_col(df, "high_impact_flag"))
    df["has_abstract"] = dash.nonblank(_col(df, "abstract"))
    for name, col in REG_COLS.items():
        df[f"reg_{name}"] = dash.to_bool_series(_col(df, col))
    df["registered_any"] = dash.to_bool_series(_col(df, "registration_signal"))
    df["has_preprint_version"] = dash.to_bool_series(_col(df, "has_preprint_version"))
    df["enriched"] = _clean(_col(df, "work_type")).ne("")

    das_primary = _clean(_col(df, "das_primary")).str.lower()
    df["das_audited"] = dash.to_bool_series(_col(df, "das_available")) & das_primary.isin(DAS_ORDER)
    df["das_primary"] = das_primary.where(df["das_audited"], None)
    df["das_has_statement"] = df["das_audited"] & dash.to_bool_series(_col(df, "das_has_statement"))
    df["das_deposit"] = df["das_audited"] & df["das_primary"].isin(["repository", "public_source"])
    df["das_repository"] = df["das_audited"] & df["das_primary"].eq("repository")
    df["das_on_request"] = df["das_audited"] & df["das_primary"].eq("on_request")
    df["ft_github"] = df["das_audited"] & dash.to_bool_series(_col(df, "das_mentions_github"))
    df["ft_registration"] = df["das_audited"] & dash.to_bool_series(_col(df, "das_mentions_trial_registration"))

    income = _clean(_col(df, "first_author_income_group")).str.lower()
    df["income_group"] = income.where(income.isin(INCOME_ORDER), None)
    df["oa_route"] = df["oa_status"].map(OA_ROUTE).where(df["oa_status"].notna(), None)
    df["oa_free_route"] = df["oa_route"].eq("free")
    df["oa_paid_route"] = df["oa_route"].eq("paid")
    return df


def rate_table(df: pd.DataFrame, by: List[str]) -> pd.DataFrame:
    grp = df.groupby(by, dropna=False)
    out = grp.agg(
        n=("doi", "size"),
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
    sub = df[df["oa_status"].notna()]
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


def fig_stacked_by_year(table: pd.DataFrame, order: List[str], colors: Dict[str, str], labels: Dict[str, str], title: str,
                        out_dir: Path, name: str, ylabel: str = "share of articles", footnote: str = "", legend_cols: int = 6):
    if table.empty:
        return
    fig, ax = new_fig()
    years = table["year"].astype(int).values
    bottom = np.zeros(len(years))
    for cat in order:
        vals = table[cat].values if cat in table.columns else np.zeros(len(years))
        ax.bar(years, vals, bottom=bottom, color=colors.get(cat, "#999"), width=0.8, edgecolor="white", linewidth=1.5, label=labels.get(cat, cat))
        bottom += vals
    ax.set_ylim(0, 1)
    ax.set_xticks(years)
    style_axes(ax, ylabel)
    ax.legend(ncol=legend_cols, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.08), fontsize=10)
    ax.set_title(title, loc="left", fontsize=15, color=TEXT, fontweight="bold", pad=14)
    if footnote:
        fig.text(0.01, -0.06, footnote, color=TEXT2, fontsize=9)
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


# ----------------------------------------------------------------------------- DAS audit outputs
def das_outputs(stroke: pd.DataFrame, out_dir: Path) -> Optional[Dict[str, object]]:
    """Tables, summary and fig11 for the data-availability audit (pipeline ``das_*`` columns)."""
    audited = stroke[stroke["das_audited"]].copy()
    if audited.empty:
        logging.warning("No DAS-audited stroke rows; skipping the DAS outputs (run the pipeline with --das-audit-sample-per-year / --das-audit-all).")
        return None
    tables = out_dir / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    audited["year"] = audited["year"].astype(int)
    by_year = pd.crosstab(audited["year"], audited["das_primary"], normalize="index").reindex(columns=DAS_ORDER, fill_value=0.0)
    by_year["n"] = audited.groupby("year").size()
    by_year.to_csv(tables / "das_primary_by_year.csv")
    overall = audited["das_primary"].value_counts(normalize=True).reindex(DAS_ORDER, fill_value=0.0)
    by_journal = (audited.groupby("journal_norm")
                  .agg(n=("doi", "size"), has_das=("das_has_statement", "mean"),
                       repository=("das_primary", lambda s: (s == "repository").mean()),
                       on_request=("das_primary", lambda s: (s == "on_request").mean()))
                  .sort_values("n", ascending=False).head(20))
    by_journal.to_csv(tables / "das_by_journal_top20.csv")
    audited[["doi", "das_pmcid", "year", "journal", "das_primary", "das_has_statement"]].to_csv(tables / "das_audit_articles.csv", index=False)
    summary = {
        "n_audited": int(len(audited)),
        "n_in_corpus": int(len(stroke)),
        "years": [int(audited["year"].min()), int(audited["year"].max())],
        "has_das_rate": round(float(audited["das_has_statement"].mean()), 4),
        "primary_overall": {k: round(float(v), 4) for k, v in overall.items()},
        "scope_note": "Open-access full text in Europe PMC only; optimistic relative to all stroke articles.",
        "source": "pipeline DAS audit (search_stroke_dois.py --das-audit-*)",
    }
    (out_dir / "das_audit_summary.json").write_text(json.dumps(summary, indent=2))
    logging.info("DAS: has_das_rate=%.3f over %d audited articles; %s", summary["has_das_rate"], len(audited), json.dumps(summary["primary_overall"]))
    fig_stacked_by_year(by_year.reset_index(), DAS_ORDER, DAS_COLORS, DAS_LABELS,
                        "What stroke data-availability statements actually say", out_dir / "figures", "fig11_das_audit",
                        ylabel="share of audited articles", legend_cols=4,
                        footnote=f"Open-access stroke articles with full text in Europe PMC, n={len(audited):,}. Regex classification of the data-availability section; one primary label per article.")
    return summary


def fig_commitment(table: pd.DataFrame, label_col: str, title: str, out_dir: Path, name: str):
    """Horizontal bars of the commitment index (1 = stroke average) with the three signal rates as text."""
    table = table.iloc[::-1]
    fig, ax = new_fig(12, 0.5 * len(table) + 2.2)
    y = np.arange(len(table))
    ax.barh(y, table["commitment_index"], color="#2a78d6", height=0.6, edgecolor="white")
    ax.axvline(1.0, color=TEXT2, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(1.0, len(table) - 0.3, "stroke average", color=TEXT2, fontsize=9, ha="center")
    for yi, v in zip(y, table["commitment_index"]):
        ax.text(v + 0.05, yi, f"{v:.1f}x", color=TEXT2, fontsize=9.5, va="center")
    ax.set_yticks(y)
    ax.set_yticklabels([f"{str(l)[:46]}  (n={int(n):,})" for l, n in zip(table[label_col], table["n"])], fontsize=10.5, color=TEXT)
    style_axes(ax, pct=False)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=GRID)
    ax.set_xlim(0, max(3.0, float(table["commitment_index"].max()) * 1.25))
    ax.set_xlabel("commitment index: mean of (entity rate / stroke rate) over data deposit, GitHub, registration", color=TEXT2, fontsize=10)
    for j, (col, lab) in enumerate([("das_deposit_rate", "data deposit"), ("ft_github_rate", "GitHub"), ("ft_registration_rate", "registration")]):
        xpos = 1.04 + 0.14 * j
        ax.text(xpos, len(table) - 0.35, lab, transform=ax.get_yaxis_transform(), color=TEXT2, fontsize=9.5, ha="left", fontweight="bold")
        for yi, v in zip(y, table[col]):
            ax.text(xpos, yi, f"{v:.0%}", transform=ax.get_yaxis_transform(), color=TEXT, fontsize=10, va="center", ha="left")
    ax.set_ylim(-0.7, len(table) - 0.1)
    ax.set_title(title, loc="left", fontsize=15, color=TEXT, fontweight="bold", pad=14)
    fig.text(0.01, -0.02, "Verified in full text (Europe PMC open-access sample): data deposited or public source in the DAS, GitHub mentioned, trial registration mentioned.", color=TEXT2, fontsize=9)
    save(fig, out_dir, name)


def das_by_discipline(data: pd.DataFrame, tables: Path) -> Optional[Dict[str, object]]:
    """Cross-discipline data-availability audit: primary category shares and full-text signals."""
    audited = data[data["das_audited"]]
    if audited.empty:
        return None
    shares = pd.crosstab(audited["discipline"], audited["das_primary"], normalize="index").reindex(columns=DAS_ORDER, fill_value=0.0)
    rates = audited.groupby("discipline").agg(n_audited=("doi", "size"), das_statement_rate=("das_has_statement", "mean"),
                                              das_deposit_rate=("das_deposit", "mean"), das_on_request_rate=("das_on_request", "mean"),
                                              ft_github_rate=("ft_github", "mean"), ft_registration_rate=("ft_registration", "mean"),
                                              code_abstract_rate=("shares_code", "mean"))
    table = rates.join(shares.add_prefix("share_"))
    table = table.reindex([d for d in DISCIPLINES if d in table.index] + [d for d in table.index if d not in DISCIPLINES])
    table.to_csv(tables / "das_by_discipline.csv")
    recent = audited[audited["year"] >= 2022]
    recent_rates = recent.groupby("discipline").agg(n_audited=("doi", "size"), das_statement_rate=("das_has_statement", "mean"),
                                                    das_deposit_rate=("das_deposit", "mean"), das_on_request_rate=("das_on_request", "mean"),
                                                    ft_github_rate=("ft_github", "mean"), ft_registration_rate=("ft_registration", "mean"))
    recent_rates.to_csv(tables / "das_by_discipline_2022_2025.csv")
    return {"all_years": table.round(4).to_dict(orient="index"), "2022_2025": recent_rates.round(4).to_dict(orient="index")}


# ----------------------------------------------------------------------------- equity and commitment
def equity_outputs(stroke: pd.DataFrame, tables: Path, figures: Path) -> Optional[Dict[str, object]]:
    """Open-access route and full-text sharing signals by first-author income group (stroke)."""
    sub = stroke[stroke["income_group"].notna()]
    if sub.empty:
        logging.warning("No first_author_income_group values; skipping the equity outputs.")
        return None
    grp = sub.groupby("income_group")
    table = grp.agg(n=("doi", "size"), oa_rate=("is_oa", "mean"), oa_free_route_rate=("oa_free_route", "mean"),
                    oa_paid_route_rate=("oa_paid_route", "mean"), high_impact_rate=("high_impact", "mean"),
                    n_audited=("das_audited", "sum")).reindex(INCOME_ORDER)
    route = pd.crosstab(sub["income_group"], sub["oa_route"], normalize="index").reindex(index=INCOME_ORDER, columns=OA_ROUTE_ORDER, fill_value=0.0)
    table = table.join(route.add_prefix("route_"))
    audited = sub[sub["das_audited"]]
    if not audited.empty:
        a = audited.groupby("income_group").agg(
            das_statement_rate=("das_has_statement", "mean"), das_deposit_rate=("das_deposit", "mean"),
            das_repository_rate=("das_repository", "mean"), das_public_source_rate=("das_primary", lambda s: s.eq("public_source").mean()),
            das_on_request_rate=("das_on_request", "mean"), ft_github_rate=("ft_github", "mean"), ft_registration_rate=("ft_registration", "mean"),
        ).reindex(INCOME_ORDER)
        table = table.join(a)
    table.index.name = "income_group"
    table.to_csv(tables / "stroke_equity_by_income_group.csv")
    share = sub["income_group"].value_counts(normalize=True).reindex(INCOME_ORDER, fill_value=0.0)

    # fig12: OA route stacked by income group
    fig, ax = new_fig(12, 5.5)
    x = np.arange(len(INCOME_ORDER))
    bottom = np.zeros(len(INCOME_ORDER))
    for r in OA_ROUTE_ORDER:
        vals = route[r].values
        ax.bar(x, vals, bottom=bottom, color=OA_ROUTE_COLORS[r], width=0.7, edgecolor="white", linewidth=1.5, label=OA_ROUTE_LABELS[r])
        for xi, (b, v) in enumerate(zip(bottom, vals)):
            if v >= 0.06:
                ax.text(xi, b + v / 2, f"{v:.0%}", ha="center", va="center", color="white" if r in ("free", "paid") else TEXT, fontsize=10)
        bottom += vals
    ax.set_xticks(x)
    ax.set_xticklabels([f"{INCOME_LABELS[g]}\n(n={int(table.loc[g, 'n']):,})" for g in INCOME_ORDER], fontsize=10.5, color=TEXT)
    ax.set_ylim(0, 1)
    style_axes(ax, "share of stroke articles")
    ax.legend(ncol=2, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), fontsize=10)
    ax.set_title("Who pays to be read: open-access route by first-author income group", loc="left", fontsize=15, color=TEXT, fontweight="bold", pad=14)
    fig.text(0.01, -0.12, "Stroke articles 2015-2025 with a first-author country in OpenAlex; World Bank income groups. Free = diamond or green; paid = gold or hybrid (APC).", color=TEXT2, fontsize=9)
    save(fig, figures, "fig12_oa_route_by_income")

    out: Dict[str, object] = {
        "share_of_corpus": {g: round(float(share[g]), 4) for g in INCOME_ORDER},
        "by_group": table.round(4).to_dict(orient="index"),
    }
    # fig13: full-text sharing signals by income group (audited sample)
    if not audited.empty and "ft_github_rate" in table.columns:
        metrics = [("das_deposit_rate", "data deposited or public source (DAS)"), ("das_on_request_rate", "data 'on request' (DAS)"),
                   ("ft_github_rate", "GitHub in full text"), ("ft_registration_rate", "trial registration in full text")]
        fig, ax = new_fig(12, 5.5)
        width = 0.2
        colors = ["#0d366b", "#2a78d6", "#86b6ef", "#cde2fb"]
        for i, g in enumerate(INCOME_ORDER):
            vals = [float(table.loc[g, m]) if pd.notna(table.loc[g, m]) else 0.0 for m, _ in metrics]
            bars = ax.bar(np.arange(len(metrics)) + (i - 1.5) * width, vals, width, color=colors[i], edgecolor="white", linewidth=1.2,
                          label=f"{INCOME_LABELS[g]} (n audited={int(table.loc[g, 'n_audited']):,})")
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, v + 0.005, f"{v:.1%}", ha="center", color=TEXT2, fontsize=8.5)
        ax.set_xticks(np.arange(len(metrics)))
        ax.set_xticklabels([l for _, l in metrics], fontsize=10.5, color=TEXT)
        ax.set_ylim(0, None)
        style_axes(ax)
        ax.legend(frameon=False, fontsize=9.5)
        ax.set_title("Sharing in the full text, by first-author income group", loc="left", fontsize=15, color=TEXT, fontweight="bold", pad=14)
        fig.text(0.01, -0.03, "Open-access stroke articles with full text in Europe PMC (audited sample). Optimistic relative to all stroke articles.", color=TEXT2, fontsize=9)
        save(fig, figures, "fig13_fulltext_sharing_by_income")
    return out


COMMITMENT_SIGNALS = ["das_deposit_rate", "ft_github_rate", "ft_registration_rate"]
INSTITUTION_ALIASES = Path(__file__).resolve().parents[1] / "configs" / "institution_aliases.csv"


def read_institution_aliases(path: Path = INSTITUTION_ALIASES) -> Dict[str, str]:
    """alias -> canonical institution name; {} when the file is absent."""
    if not path.exists():
        return {}
    t = pd.read_csv(path, dtype=str).fillna("")
    return {a.strip(): c.strip() for a, c in zip(t["alias"], t["canonical"]) if a.strip() and c.strip()}


def commitment_table(audited: pd.DataFrame, key: str, baseline: pd.DataFrame, min_n: int = MIN_N_AUDITED) -> pd.DataFrame:
    """Verified full-text signals per entity (one row per audited article per entity).

    ``commitment_index`` = mean over the three signals of (entity rate / stroke-wide rate), so a
    rare signal (data deposit, about 3%) weighs as much as a common one (trial registration in the
    full text, about 15%). 1.0 = the stroke average; 2.0 = twice the average on each signal."""
    grp = audited.groupby(key)
    table = grp.agg(n_audited=("doi", "size"), das_statement_rate=("das_has_statement", "mean"),
                    das_deposit_rate=("das_deposit", "mean"), das_repository_rate=("das_repository", "mean"),
                    das_on_request_rate=("das_on_request", "mean"), ft_github_rate=("ft_github", "mean"),
                    ft_registration_rate=("ft_registration", "mean"), oa_free_route_rate=("oa_free_route", "mean"))
    table = table[table["n_audited"] >= min_n].copy()
    base = {s: float(baseline[s.replace("_rate", "")].mean()) for s in COMMITMENT_SIGNALS}
    ratios = pd.concat([(table[s] / base[s]) if base[s] > 0 else pd.Series(0.0, index=table.index) for s in COMMITMENT_SIGNALS], axis=1)
    table["commitment_index"] = ratios.mean(axis=1).round(2)
    return table.sort_values(["commitment_index", "n_audited"], ascending=[False, False])


def commitment_outputs(stroke: pd.DataFrame, tables: Path, figures: Path) -> Optional[Dict[str, object]]:
    audited = stroke[stroke["das_audited"]].copy()
    if audited.empty:
        return None
    out: Dict[str, object] = {"min_n_audited": MIN_N_AUDITED, "n_audited": int(len(audited))}
    # institutions: one row per (article, institution); an institution gets credit for any author.
    inst_col = _clean(_col(audited, "institutions"))
    if inst_col.ne("").any():
        inst = audited[inst_col.ne("")].copy()
        inst["institution"] = inst_col[inst_col.ne("")].str.split("|")
        inst = inst.explode("institution")
        inst = inst[inst["institution"].str.len() > 0]
        # units of one institution that OpenAlex lists separately (configs/institution_aliases.csv, shared with the
        # dashboard builder) are merged, and an article listing two units counts once
        aliases = read_institution_aliases()
        if aliases:
            inst["institution"] = inst["institution"].str.strip().replace(aliases)
            inst = inst[~pd.DataFrame({"row": inst.index.to_numpy(), "inst": inst["institution"].to_numpy()}).duplicated().to_numpy()]
        t = commitment_table(inst, "institution", audited)
        t.to_csv(tables / "stroke_commitment_institutions.csv")
        out["institutions_top"] = t.head(15).round(4).to_dict(orient="index")
        top = t.head(15).reset_index().rename(columns={"n_audited": "n"})
        if not top.empty:
            fig_commitment(top, "institution", f"Most committed institutions in stroke (>= {MIN_N_AUDITED} audited articles)", figures, "fig14_commitment_institutions")
    for key, name in [("journal_norm", "journals"), ("first_author_country", "countries")]:
        col = _clean(_col(audited, key))
        sub = audited[col.ne("")].copy()
        sub[key] = col[col.ne("")]
        t = commitment_table(sub, key, audited)
        t.to_csv(tables / f"stroke_commitment_{name}.csv")
        out[f"{name}_top"] = t.head(15).round(4).to_dict(orient="index")
    funders_col = _clean(_col(audited, "funders"))
    if funders_col.ne("").any():
        f = audited[funders_col.ne("")].copy()
        f["funder"] = funders_col[funders_col.ne("")].str.split("|")
        f = f.explode("funder")
        f = f[f["funder"].str.len() > 0]
        t = commitment_table(f, "funder", audited)
        t.to_csv(tables / "stroke_commitment_funders.csv")
        out["funders_top"] = t.head(15).round(4).to_dict(orient="index")
    # Full-text vs abstract-based estimates for the audited sample (how much the abstract undercounts).
    out["baseline_rates"] = {s: round(float(audited[s.replace("_rate", "")].mean()), 4) for s in COMMITMENT_SIGNALS}
    out["fulltext_vs_abstract"] = {
        "code_abstract_rate": round(float(audited["shares_code"].mean()), 4),
        "code_fulltext_github_rate": round(float(audited["ft_github"].mean()), 4),
        "registration_abstract_rate": round(float(audited.loc[audited["has_abstract"], "registered_any"].mean()), 4) if audited["has_abstract"].any() else None,
        "registration_fulltext_rate": round(float(audited["ft_registration"].mean()), 4),
    }
    return out


# ----------------------------------------------------------------------------- main
def parse_inputs(args: argparse.Namespace) -> Dict[str, Path]:
    inputs: Dict[str, Path] = {}
    for item in args.inputs or []:
        if "=" not in item:
            raise SystemExit(f"--inputs expects discipline=path, got {item!r}")
        disc, path = item.split("=", 1)
        inputs[disc.strip()] = Path(path).expanduser()
    if not inputs:
        for disc in args.disciplines:
            inputs[disc] = Path(args.input_dir) / disc / "fully_enriched.csv"
    missing = [str(p) for p in inputs.values() if not p.exists()]
    if missing:
        raise SystemExit("Missing pipeline output(s): " + ", ".join(missing))
    return inputs


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inputs", nargs="+", help="discipline=path/to/fully_enriched.csv (pipeline output)")
    parser.add_argument("--input-dir", default="data/talk", help="Used when --inputs is absent: <dir>/<discipline>/fully_enriched.csv")
    parser.add_argument("--disciplines", nargs="+", default=DISCIPLINES)
    parser.add_argument("--out-dir", default="talk/outputs")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")

    inputs = parse_inputs(args)
    out = Path(args.out_dir)
    tables = out / "tables"
    figures = out / "figures"
    tables.mkdir(parents=True, exist_ok=True)

    frames = []
    for disc, path in inputs.items():
        frames.append(apply_corpus_rules(load_discipline(disc, path)))
    data = pd.concat(frames, ignore_index=True)
    disciplines = [d for d in DISCIPLINES if d in inputs] + [d for d in inputs if d not in DISCIPLINES]

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
        "corpus_rule": sorted(set(data["corpus_rule"])),
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
        "metadata_coverage": {d: round(float(data[data["discipline"] == d]["enriched"].mean()), 4) for d in disciplines},
    }

    country = _clean(_col(stroke, "first_author_country"))
    if country.ne("").any():
        sub = stroke[country.ne("")]
        countries = rate_table(sub, ["first_author_country"]).sort_values("n", ascending=False).head(12)
        countries.to_csv(tables / "stroke_top_first_author_countries.csv", index=False)
        fig_dot_compare(countries, "first_author_country", {"oa_rate": "open access", "data_rate": "data repo", "code_rate": "code link"}, "Stroke articles by first-author country, 2015-2025", figures, "fig08_countries")
        numbers["stroke_top_countries"] = countries.set_index("first_author_country")[["n", "oa_rate", "data_rate", "code_rate"]].round(4).to_dict(orient="index")
    funders_col = _clean(_col(stroke, "funders"))
    if funders_col.ne("").any():
        f = stroke[funders_col.ne("")].copy()
        f["funder"] = funders_col[funders_col.ne("")].str.split("|")
        f = f.explode("funder")
        f = f[f["funder"].str.len() > 0]
        funders = rate_table(f, ["funder"]).sort_values("n", ascending=False).head(12)
        funders.to_csv(tables / "stroke_top_funders.csv", index=False)
        fig_dot_compare(funders, "funder", {"oa_rate": "open access", "data_rate": "data repo", "code_rate": "code link"}, "Stroke articles by acknowledged funder, 2015-2025", figures, "fig09_funders")
        numbers["stroke_funded_share"] = round(float(funders_col.ne("").mean()), 4)

    das_summary = das_outputs(stroke, out / "das_audit")
    if das_summary:
        numbers["stroke_das_audit"] = das_summary
    das_disc = das_by_discipline(data, tables)
    if das_disc:
        numbers["das_by_discipline"] = das_disc
    equity = equity_outputs(stroke, tables, figures)
    if equity:
        numbers["stroke_equity"] = equity
    commitment = commitment_outputs(stroke, tables, figures)
    if commitment:
        numbers["stroke_commitment"] = commitment

    # Figures
    fig_trend_by_discipline(by_year, "oa_rate", "Open access in stroke vs comparator fields", "share of articles open access", figures, "fig01_oa_trend")
    fig_stacked_by_year(oa_year, OA_STATUS_ORDER, OA_STATUS_COLORS, {s: s for s in OA_STATUS_ORDER}, "How stroke articles are open: OA status by year", figures, "fig02_stroke_oa_status")
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
