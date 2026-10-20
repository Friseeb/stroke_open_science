#!/usr/bin/env python3
"""
Pre-aggregate the per-discipline ``fully_enriched.csv`` files into one compact JSON
(``dashboard_data.json``) that the static interactive dashboard (``dashboard/``) recomputes
rates from in the browser.

Counts, never rates, are stored so any filter combination (discipline, year range, journal,
first-author country, funder, high-impact subset) can be re-aggregated client-side without
shipping row-level data.

Grain (per discipline)
  ``cells``   year x high_impact x journal (top-N + "Other") x first-author country (top-N + "Other")
  ``funders`` year x high_impact x funder (top-N + "Other" + "(no funder listed)")

Each row is a flat integer list: the key columns followed by ``COUNT_KEYS`` in order.

Usage:
  python scripts/build_dashboard_data.py --inputs stroke=data/stroke/fully_enriched.csv ... \
      --out data/benchmarks/dashboard/dashboard_data.json [--enrichment-dir data/enrichment]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_discipline_dashboard as dash  # noqa: E402  (sibling module)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 3

OA_STATUS_ORDER = list(dash.OA_STATUS_ORDER)
DAS_ORDER = list(dash.DAS_ORDER)

# Full-text flags recorded by the DAS audit for every audited article (denominator: das_audited).
FULLTEXT_KEYS = ["ft_github", "ft_reg", "ft_supp"]
COUNT_KEYS: List[str] = (
    ["n", "oa"]
    + [f"oa_{s}" for s in OA_STATUS_ORDER]
    + ["code", "data", "material", "preprint", "reg", "n_abs", "das_audited", "das_stmt"]
    + [f"das_{c}" for c in DAS_ORDER]
    + FULLTEXT_KEYS
)
# Schema 3 adds ``trial`` (1 = trial report or secondary analysis of a trial) after ``hi`` in every table.
CELL_KEYS = ["year", "hi", "trial", "journal", "country"]
FUNDER_KEYS = ["year", "hi", "trial", "funder"]
INCOME_KEYS = ["year", "hi", "trial", "income"]
INSTITUTION_KEYS = ["year", "hi", "trial", "institution"]

# World Bank income group of the first author's country (pipeline column first_author_income_group).
INCOME_ORDER = ["high", "upper_middle", "lower_middle", "low"]
INCOME_LABELS = {"high": "High income", "upper_middle": "Upper-middle income",
                 "lower_middle": "Lower-middle income", "low": "Low income"}
INCOME_UNKNOWN = "(unknown)"
NO_INSTITUTION_LABEL = "(no institution listed)"

OTHER_LABEL = "Other"
UNKNOWN_LABEL = "(unknown)"
NO_FUNDER_LABEL = "(no funder listed)"

# Validated categorical set (dataviz validator, light surface #f1f1ef and dark #141414): stroke carries the
# page accent (red); the comparators keep blue / green / yellow. The page maps dark-mode steps itself.
DISCIPLINE_COLORS: Dict[str, str] = {
    "stroke": "#d7263d",
    "neurology": "#2a78d6",
    "neuroscience": "#1baf7a",
    "cardiology": "#eda100",
}
DISCIPLINE_ORDER = ["stroke", "neurology", "neuroscience", "cardiology"]
EXTRA_COLORS = ["#eb6834", "#7b61c9", "#c04d8c", "#5c7f8f", "#8a7a3a"]

# Statuses wear their names' colours (validated categorical set, light surface); the site maps dark-mode steps itself.
OA_STATUS_COLORS: Dict[str, str] = {
    "diamond": "#5598e7", "gold": "#eda100", "hybrid": "#c04d8c",
    "green": "#1baf7a", "bronze": "#9a5a1f", "closed": "#d9d8d4",
}
DAS_COLORS: Dict[str, str] = {
    "repository": "#0d366b", "public_source": "#1c5cab", "controlled_or_restricted": "#2a78d6",
    "on_request": "#5598e7", "in_article": "#9ec5f4", "not_available_or_na": "#cde2fb",
    "other_or_unclear": "#c9c8c4", "no_statement": "#d9d8d4",
}

# Columns pulled from the OpenAlex work-metadata enrichment CSVs (``*_work_metadata.csv``).
ENRICHMENT_COLS = [
    "work_type", "oa_status", "primary_source_type", "primary_source_is_in_doaj",
    "has_preprint_version", "is_preprint_record", "preprint_servers",
    "first_author_country", "countries", "funders", "is_retracted", "has_fulltext",
]

# Columns the aggregation reads from ``fully_enriched.csv`` (others are skipped on load).
NEEDED_COLS = {
    "doi", "doi_norm", "year", "discipline", "journal", "journal_norm", "journal_is_oa",
    "is_oa", "license_unpaywall", "best_oa_location_url",
    "github", "zenodo", "osf", "repo_links", "code_link", "data_link",
    "dataset_urls", "has_public_dataset", "preregistered", "preprint",
    "high_impact_flag", "high_impact_reason", "abstract", "title",
    "work_type", "oa_status", "primary_source_type", "has_preprint_version",
    "first_author_country", "countries", "funders",
    "registration_signal", "registered_any", "in_article_corpus", "corpus_rule", "study_design", "is_trial", "pubmed_trial",
    "das_available", "das_has_statement", "das_primary",
    "das_mentions_github", "das_mentions_trial_registration", "das_mentions_supplement",
    "first_author_income_group", "institutions",
}

METRICS: List[Dict[str, str]] = [
    {"key": "oa", "label": "Open access", "short": "OA",
     "definition": dash.OA_DEFINITION},
    {"key": "data", "label": "Data sharing", "short": "Data",
     "definition": "Share with a dataset in a public repository (DataCite, Dryad, Figshare, Dataverse) "
                   "or a data-repository link found in the title, abstract or metadata."},
    {"key": "code", "label": "Code sharing", "short": "Code",
     "definition": "Share with a GitHub repository or code-repository link."},
    {"key": "material", "label": "Any repository / materials", "short": "Materials",
     "definition": "Share with any repository, code or data link (GitHub, Zenodo, OSF, Crossref "
                   "relations, dataset repositories, LLM-extracted links)."},
    {"key": "preprint", "label": "Preprint version", "short": "Preprint",
     "definition": "Share with a preprint version on a preprint server (OpenAlex locations), falling "
                   "back to a preprint URL/identifier when metadata is missing."},
    {"key": "reg", "label": "Registration signal", "short": "Registered",
     "definition": "Share whose title or abstract cites a trial-registry ID (NCT, ISRCTN, ChiCTR, ...), "
                   "PROSPERO, or preregistration wording (regex). Denominator: papers with an abstract."},
    {"key": "das_stmt", "label": "Data-availability statement (full text)", "short": "Statement", "denominator": "das_audited",
     "definition": "Share of audited open-access full texts (Europe PMC sample) that contain a data-availability "
                   "statement. Denominator: audited papers."},
    {"key": "ft_github", "label": "GitHub in full text", "short": "GitHub (full text)", "denominator": "das_audited",
     "definition": "Share of audited open-access full texts that mention github.com anywhere. Denominator: audited papers; "
                   "a full-text counterpart of the abstract-based code-sharing signal."},
    {"key": "ft_reg", "label": "Trial registration in full text", "short": "Registered (full text)", "denominator": "das_audited",
     "definition": "Share of audited open-access full texts that mention a trial-registry ID, clinicaltrials.gov or "
                   "PROSPERO anywhere. Denominator: audited papers."},
]
# Verified full-text signals used for the commitment index (entity rate / discipline rate, averaged).
COMMITMENT_SIGNALS = [
    {"key": "das_deposit", "label": "Data deposited or public source", "numerators": ["das_repository", "das_public_source"], "denominator": "das_audited"},
    {"key": "ft_github", "label": "GitHub in full text", "numerators": ["ft_github"], "denominator": "das_audited"},
    {"key": "ft_reg", "label": "Trial registration in full text", "numerators": ["ft_reg"], "denominator": "das_audited"},
]

METHODS_NOTES: List[str] = [
    "All sharing and registration signals are lower bounds: they are detected from titles, abstracts, "
    "URLs and bibliographic metadata, so practices not mentioned there are missed.",
    "Rates are computed over journal articles and reviews only (in_article_corpus): OpenAlex type article/review "
    "in a journal source, matched by DOI. Records without a DOI or without an OpenAlex record (for example the "
    "DOI-less conference abstracts published in Stroke) are excluded, as are datasets, preprint records, errata, "
    "book chapters and repository items.",
    "Data-availability statements (DAS) were audited only on the Europe PMC open-access full-text subset "
    "(a per-year sample), so DAS rates are optimistic relative to the whole corpus and refer to the "
    "audited papers, not to all papers.",
    "The most recent year is incomplete: indexing lag and embargoes mean counts and some rates (especially "
    "green OA and preprint links) will change as records are updated. The year filter therefore defaults to "
    "the last complete year (the year before the run year); later years are shaded and can be selected.",
    "Journals and first-author countries outside the per-discipline top lists are folded into “Other”. "
    "Journal names are normalised (case, whitespace) before ranking.",
    "Funders are multi-valued: a paper with three funders is counted once under each. Funder counts therefore "
    "do not sum to the paper total, and a funder filter cannot be combined with journal or country filters.",
    "OA status (diamond, gold, hybrid, green, bronze, closed) is the OpenAlex classification and the OA rate "
    "is derived from it (open = oa_status not closed), so OA rate and 1 − closed agree wherever oa_status is "
    "known; the legacy is_oa / OA-journal / OA-URL / licence inference is used only for papers whose "
    "oa_status is unknown.",
]

ISO2_NAMES: Dict[str, str] = {
    "US": "United States", "GB": "United Kingdom", "CN": "China", "DE": "Germany", "JP": "Japan",
    "CA": "Canada", "IT": "Italy", "FR": "France", "AU": "Australia", "NL": "Netherlands",
    "ES": "Spain", "KR": "South Korea", "CH": "Switzerland", "SE": "Sweden", "BR": "Brazil",
    "IN": "India", "TW": "Taiwan", "BE": "Belgium", "DK": "Denmark", "AT": "Austria",
    "NO": "Norway", "FI": "Finland", "IL": "Israel", "TR": "Turkey", "IR": "Iran", "PL": "Poland",
    "GR": "Greece", "PT": "Portugal", "IE": "Ireland", "SG": "Singapore", "HK": "Hong Kong",
    "MX": "Mexico", "AR": "Argentina", "RU": "Russia", "CZ": "Czechia", "HU": "Hungary",
    "EG": "Egypt", "SA": "Saudi Arabia", "PK": "Pakistan", "TH": "Thailand", "NZ": "New Zealand",
    "ZA": "South Africa", "CL": "Chile", "CO": "Colombia", "NG": "Nigeria", "MY": "Malaysia",
    "ID": "Indonesia", "RO": "Romania", "HR": "Croatia", "RS": "Serbia", "UA": "Ukraine",
    "SK": "Slovakia", "SI": "Slovenia", "VN": "Vietnam", "BD": "Bangladesh", "IQ": "Iraq",
    "AE": "United Arab Emirates", "QA": "Qatar", "JO": "Jordan", "LB": "Lebanon", "TN": "Tunisia",
    "MA": "Morocco", "ET": "Ethiopia", "KE": "Kenya", "GH": "Ghana", "PE": "Peru", "CU": "Cuba",
    "NP": "Nepal", "LK": "Sri Lanka", "EE": "Estonia", "LT": "Lithuania", "LV": "Latvia",
    "BG": "Bulgaria", "IS": "Iceland", "LU": "Luxembourg", "CY": "Cyprus", "MT": "Malta",
}

WS_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pre-aggregate benchmark CSVs into dashboard_data.json.")
    parser.add_argument("--inputs", nargs="+", required=True,
                        help="Discipline/path pairs like stroke=data/stroke/fully_enriched.csv")
    parser.add_argument("--out", default="data/benchmarks/dashboard/dashboard_data.json",
                        help="Output JSON path")
    parser.add_argument("--enrichment-dir", default=None,
                        help="Directory with <discipline>_work_metadata.csv files; left-joined by DOI "
                             "when the main CSV lacks the OpenAlex work-metadata columns")
    parser.add_argument("--site-dir", default=None,
                        help="If given, copy dashboard/ (index.html, app.js, charts.js, styles.css) plus the JSON here")
    parser.add_argument("--top-journals", type=int, default=40)
    parser.add_argument("--top-countries", type=int, default=25)
    parser.add_argument("--top-funders", type=int, default=25)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _series(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return df[col]
    return pd.Series([pd.NA] * len(df), index=df.index, dtype=object)


def _clean_text(series: pd.Series) -> pd.Series:
    s = series.fillna("").astype(str).str.strip()
    return s.replace({"nan": "", "None": "", "<NA>": "", "null": ""})


def _blank_mask(series: pd.Series) -> pd.Series:
    return _clean_text(series).eq("")


def normalize_doi_simple(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    return text


def doi_norm_series(df: pd.DataFrame) -> pd.Series:
    src = df["doi_norm"] if "doi_norm" in df.columns else _series(df, "doi")
    return _clean_text(src).map(normalize_doi_simple)


def normalize_journal(value: Any) -> str:
    text = str(value or "").strip().lower()
    return WS_RE.sub(" ", text)


def read_csv_header(path: Path) -> List[str]:
    return list(pd.read_csv(path, nrows=0).columns)


def load_discipline_csv(path: Path) -> pd.DataFrame:
    """Read only the columns the aggregation needs (abstract/title only when registration flags
    must be derived)."""
    header = read_csv_header(path)
    wanted = set(NEEDED_COLS)
    if "registration_signal" in header or "registered_any" in header:
        wanted -= {"abstract", "title"}
    usecols = [c for c in header if c in wanted]
    return pd.read_csv(path, usecols=usecols, low_memory=False)


# ---------------------------------------------------------------------------
# Enrichment join (same semantics as the OpenAlex metadata backfill: fill blank/missing fields by DOI)
# ---------------------------------------------------------------------------

def enrichment_path_for(enrichment_dir: Path, discipline: str) -> Optional[Path]:
    for name in (f"{discipline}_work_metadata.csv", f"{discipline}-work_metadata.csv"):
        candidate = enrichment_dir / name
        if candidate.exists():
            return candidate
    return None


def apply_enrichment_metadata(df: pd.DataFrame, enrichment_csv: Path) -> pd.DataFrame:
    """Left-join ``ENRICHMENT_COLS`` from a ``*_work_metadata.csv`` keyed by ``doi_norm``. Columns the
    main frame lacks are added; existing columns are filled only where blank. Then derives
    ``in_article_corpus`` (OpenAlex type + journal source) when it is missing."""
    header = read_csv_header(enrichment_csv)
    cols = [c for c in ENRICHMENT_COLS if c in header]
    if "doi_norm" not in header or not cols:
        logging.warning("Enrichment CSV %s has no usable columns; skipping join.", enrichment_csv)
        return df
    meta = pd.read_csv(enrichment_csv, usecols=["doi_norm"] + cols, low_memory=False)
    meta["doi_norm"] = _clean_text(meta["doi_norm"]).map(normalize_doi_simple)
    meta = meta[meta["doi_norm"].ne("")].drop_duplicates(subset=["doi_norm"], keep="first").set_index("doi_norm")

    keys = doi_norm_series(df)
    aligned = meta.reindex(keys.to_numpy())
    aligned.index = df.index
    filled_rows = int(keys.isin(meta.index).sum())
    for col in cols:
        incoming = aligned[col]
        if col not in df.columns:
            df[col] = incoming.to_numpy()
        else:
            blank = _blank_mask(df[col])
            df.loc[blank, col] = incoming[blank].to_numpy()
    logging.info("Enrichment join %s: %d/%d rows matched by DOI (%s)", enrichment_csv.name,
                 filled_rows, len(df), ", ".join(cols))

    if "in_article_corpus" not in df.columns:
        try:
            import search_stroke_dois as pipeline  # heavy module; only needed here
            df = pipeline.apply_corpus_flag(df)
        except Exception as exc:  # pragma: no cover - defensive
            logging.warning("Could not derive in_article_corpus (%s); keeping all rows.", exc)
    return df


def study_design_description() -> str:
    try:
        import search_stroke_dois as pipeline
        return pipeline.STUDY_DESIGN_DESCRIPTION
    except Exception:  # pragma: no cover - defensive
        return "Trials = reports of prospective interventional trials and their secondary analyses, from the title and abstract."


def derive_study_design(df: pd.DataFrame, source_dir: Optional[Path] = None) -> pd.DataFrame:
    """When the CSV predates the study-design stage, classify trials exactly as the pipeline would
    (``apply_study_design_flags``), with the PubMed trial DOIs from ``<source_dir>/pubmed_trial_dois.json``
    when that file exists (otherwise from title + abstract only)."""
    if "is_trial" in df.columns:
        return df
    if "abstract" not in df.columns and "title" not in df.columns:
        return df
    try:
        import search_stroke_dois as pipeline
        dois = None
        if source_dir is not None and (Path(source_dir) / pipeline.PUBMED_TRIAL_DOIS_FILE).exists():
            dois = pipeline.load_pubmed_trial_dois(Path(source_dir) / pipeline.PUBMED_TRIAL_DOIS_FILE)
            logging.info("Using %d PubMed trial DOIs from %s.", len(dois or []), source_dir)
        df = pipeline.apply_study_design_flags(df, dois)
        logging.info("Derived study design from title+abstract for %d rows.", len(df))
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning("Could not derive study design (%s).", exc)
    return df


def derive_registration_flags(df: pd.DataFrame) -> pd.DataFrame:
    """When the CSV predates the regex registration stage but has title/abstract text, compute the
    same flags the pipeline would (``apply_registration_flags``)."""
    if "registration_signal" in df.columns or "registered_any" in df.columns:
        return df
    if "abstract" not in df.columns and "title" not in df.columns:
        return df
    try:
        import search_stroke_dois as pipeline
        df = pipeline.apply_registration_flags(df)
        logging.info("Derived registration flags from title+abstract for %d rows.", len(df))
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning("Could not derive registration flags (%s).", exc)
    return df


# ---------------------------------------------------------------------------
# Row-level flags
# ---------------------------------------------------------------------------

def row_flags(df: pd.DataFrame, discipline: str) -> Dict[str, Any]:
    """Return a dict with the corpus-filtered frame of row-level booleans/categories and
    per-discipline availability flags and totals."""
    out = df.copy()
    total_rows = len(out)

    corpus_rule = "all rows (no in_article_corpus column)"
    if "in_article_corpus" in out.columns:
        in_corpus = dash.to_bool_series(out["in_article_corpus"])
        rules = sorted(set(_clean_text(_series(out, "corpus_rule")).tolist()) - {""})
        corpus_rule = "in_article_corpus (" + (", ".join(rules) if rules else
                                               "OpenAlex type article/review in a journal source, DOI-matched") + ")"
        out = out[in_corpus].copy()
    kept_rows = len(out)

    out["year"] = pd.to_numeric(_series(out, "year"), errors="coerce")
    out = out[out["year"].notna() & (out["year"] >= 1900)].copy()
    out["year"] = out["year"].astype(int)

    flags = pd.DataFrame(index=out.index)
    flags["year"] = out["year"]
    flags["n"] = 1
    flags["hi"] = dash.to_bool_series(_series(out, "high_impact_flag")).astype(int)
    flags["trial"] = dash.to_bool_series(_series(out, "is_trial")).astype(int)
    flags["oa"] = dash.derive_open_access(out).astype(int)

    oa_status = _clean_text(_series(out, "oa_status")).str.lower()
    for status in OA_STATUS_ORDER:
        flags[f"oa_{status}"] = oa_status.eq(status).astype(int)

    has_github = dash.nonblank(_series(out, "github"))
    has_code_link = dash.nonblank(_series(out, "code_link"))
    has_zenodo = dash.nonblank(_series(out, "zenodo"))
    has_osf = dash.nonblank(_series(out, "osf"))
    has_repo_links = dash.nonblank(_series(out, "repo_links"))
    has_data_link = dash.nonblank(_series(out, "data_link"))
    has_dataset = dash.to_bool_series(_series(out, "has_public_dataset")) | dash.nonblank(_series(out, "dataset_urls"))
    flags["code"] = (has_github | has_code_link).astype(int)
    flags["data"] = (has_dataset | has_data_link).astype(int)
    flags["material"] = (has_github | has_code_link | has_zenodo | has_osf | has_repo_links
                         | has_data_link | has_dataset).astype(int)

    preprint_meta_available = "has_preprint_version" in out.columns and out["has_preprint_version"].notna().any()
    if preprint_meta_available:
        flags["preprint"] = dash.to_bool_series(out["has_preprint_version"]).astype(int)
    else:
        flags["preprint"] = dash.nonblank(_series(out, "preprint")).astype(int)

    reg_col = "registration_signal" if "registration_signal" in out.columns else (
        "registered_any" if "registered_any" in out.columns else None)
    registration_available = reg_col is not None
    if registration_available:
        flags["reg"] = dash.to_bool_series(out[reg_col]).astype(int)
        if "abstract" in out.columns:
            flags["n_abs"] = dash.nonblank(out["abstract"]).astype(int)
        else:
            # Abstract text not loaded: the regex ran over every row, so the denominator is every row.
            flags["n_abs"] = 1
    else:
        flags["reg"] = 0
        flags["n_abs"] = 0

    das_available = dash.to_bool_series(_series(out, "das_available"))
    das_primary = _clean_text(_series(out, "das_primary")).str.lower()
    audited = das_available & das_primary.isin(DAS_ORDER)
    flags["das_audited"] = audited.astype(int)
    flags["das_stmt"] = (audited & dash.to_bool_series(_series(out, "das_has_statement"))).astype(int)
    for category in DAS_ORDER:
        flags[f"das_{category}"] = (audited & das_primary.eq(category)).astype(int)
    for key, col in (("ft_github", "das_mentions_github"), ("ft_reg", "das_mentions_trial_registration"),
                     ("ft_supp", "das_mentions_supplement")):
        flags[key] = (audited & dash.to_bool_series(_series(out, col))).astype(int)

    income = _clean_text(_series(out, "first_author_income_group")).str.lower()
    flags["income"] = income.where(income.isin(INCOME_ORDER), INCOME_UNKNOWN)
    income_available = "first_author_income_group" in out.columns and income.isin(INCOME_ORDER).any()

    flags["institutions"] = _clean_text(_series(out, "institutions"))
    institutions_available = "institutions" in out.columns and flags["institutions"].ne("").any()

    if "journal_norm" in out.columns:
        journal_norm = _clean_text(out["journal_norm"]).map(normalize_journal)
    else:
        journal_norm = _clean_text(_series(out, "journal")).map(normalize_journal)
    flags["journal_norm"] = journal_norm.where(journal_norm.ne(""), UNKNOWN_LABEL)
    flags["journal_display"] = _clean_text(_series(out, "journal"))

    country = _clean_text(_series(out, "first_author_country")).str.upper()
    flags["country"] = country.where(country.ne(""), UNKNOWN_LABEL)
    country_available = "first_author_country" in out.columns and country.ne("").any()

    flags["funders"] = _clean_text(_series(out, "funders"))
    funders_available = "funders" in out.columns and flags["funders"].ne("").any()

    available = {
        "oa_status": bool(oa_status.isin(OA_STATUS_ORDER).any()),
        "das": bool(audited.any()),
        "registration": bool(registration_available),
        "preprint": True,
        "preprint_metadata": bool(preprint_meta_available),
        "country": bool(country_available),
        "funders": bool(funders_available),
        "high_impact": bool(flags["hi"].any()),
        "trial": "is_trial" in out.columns,
        "income": bool(income_available),
        "institutions": bool(institutions_available),
        "fulltext": bool(audited.any()),
    }
    totals = {"rows_in_file": int(total_rows), "in_corpus": int(kept_rows),
              "dropped": int(total_rows - kept_rows), "with_year": int(len(flags))}
    return {"flags": flags, "available": available, "totals": totals, "corpus_rule": corpus_rule,
            "high_impact_settings": dash.infer_high_impact_settings(df)}


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

INSTITUTION_ALIASES_FILE = Path(__file__).resolve().parents[1] / "configs" / "institution_aliases.csv"


def read_institution_aliases(path: Optional[Path] = None) -> Dict[str, str]:
    """alias -> canonical institution name (configs/institution_aliases.csv); {} if the file is absent.

    OpenAlex lists some units of one institution as separate institutions (e.g. the Center for Stroke Research
    Berlin and the Berlin Institute of Health inside Charité), so rankings would show the same institution twice."""
    path = INSTITUTION_ALIASES_FILE if path is None else Path(path)
    if not path.exists():
        return {}
    table = pd.read_csv(path, dtype=str).fillna("")
    return {a.strip(): c.strip() for a, c in zip(table["alias"], table["canonical"]) if a.strip() and c.strip()}


def _top_categories(series: pd.Series, top_n: int, exclude: Sequence[str] = ()) -> List[str]:
    counts = series[~series.isin(set(exclude))].value_counts()
    return [str(c) for c in counts.index[:top_n]]


def _fold(series: pd.Series, keep: Sequence[str]) -> pd.Series:
    keep_set = set(keep)
    return series.where(series.isin(keep_set), OTHER_LABEL)


def _rows_from_grouped(grouped: pd.DataFrame, key_cols: List[str]) -> List[List[int]]:
    cols = key_cols + COUNT_KEYS
    return grouped[cols].astype(int).to_numpy().tolist()


def aggregate_discipline(df: pd.DataFrame, discipline: str, *, top_journals: int = 40,
                         top_countries: int = 25, top_funders: int = 25, top_institutions: int = 60,
                         institution_aliases: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Aggregate one discipline's enriched frame into the compact cell/funder tables."""
    prepared = row_flags(df, discipline)
    flags: pd.DataFrame = prepared["flags"]

    # --- journals: top-N by paper count, display name = most frequent raw spelling ---
    journals = _top_categories(flags["journal_norm"], top_journals, exclude=[UNKNOWN_LABEL])
    journal_labels: Dict[str, str] = {}
    if not flags.empty:
        display = (flags[flags["journal_display"].ne("")]
                   .groupby("journal_norm")["journal_display"]
                   .agg(lambda s: s.value_counts().index[0]))
        journal_labels = {j: str(display.get(j, j)) for j in journals}
    journal_list = journals + [OTHER_LABEL]
    journal_index = {j: i for i, j in enumerate(journal_list)}
    journal_folded = _fold(flags["journal_norm"], journals).map(journal_index)

    # --- countries ---
    countries = _top_categories(flags["country"], top_countries, exclude=[UNKNOWN_LABEL])
    country_list = countries + [OTHER_LABEL]
    country_index = {c: i for i, c in enumerate(country_list)}
    country_folded = _fold(flags["country"], countries).map(country_index)
    # World Bank income group per country (the modal group of its papers), for colouring countries on the site
    country_income: Dict[str, str] = {}
    if "income" in flags.columns:
        known = flags[flags["income"].isin(INCOME_ORDER)]
        if len(known):
            country_income = known.groupby("country")["income"].agg(lambda s: s.value_counts().idxmax()).to_dict()

    key_frame = flags[["year", "hi", "trial"] + COUNT_KEYS].copy()
    key_frame["journal"] = journal_folded.astype(int)
    key_frame["country"] = country_folded.astype(int)
    cells = key_frame.groupby(CELL_KEYS, as_index=False)[COUNT_KEYS].sum().sort_values(CELL_KEYS)
    cell_rows = _rows_from_grouped(cells, CELL_KEYS)

    # --- funders (multi-valued) ---
    funder_rows: List[List[int]] = []
    funder_list: List[str] = []
    if prepared["available"]["funders"]:
        exploded = flags[["year", "hi", "trial", "funders"] + COUNT_KEYS].copy()
        exploded["funder"] = exploded["funders"].str.split("|")
        exploded = exploded.explode("funder")
        exploded["funder"] = _clean_text(exploded["funder"])
        exploded["funder"] = exploded["funder"].where(exploded["funder"].ne(""), NO_FUNDER_LABEL)
        top = _top_categories(exploded["funder"], top_funders, exclude=[NO_FUNDER_LABEL])
        funder_list = top + [OTHER_LABEL, NO_FUNDER_LABEL]
        funder_index = {f: i for i, f in enumerate(funder_list)}
        folded = exploded["funder"].where(exploded["funder"].isin(set(top) | {NO_FUNDER_LABEL}), OTHER_LABEL)
        exploded["funder"] = folded.map(funder_index).astype(int)
        funders = exploded.groupby(FUNDER_KEYS, as_index=False)[COUNT_KEYS].sum().sort_values(FUNDER_KEYS)
        funder_rows = _rows_from_grouped(funders, FUNDER_KEYS)

    # --- first-author income group (one value per paper; unknown kept as its own bucket) ---
    income_list = INCOME_ORDER + [INCOME_UNKNOWN]
    income_rows: List[List[int]] = []
    if prepared["available"]["income"]:
        income_index = {g: i for i, g in enumerate(income_list)}
        inc = flags[["year", "hi", "trial", "income"] + COUNT_KEYS].copy()
        inc["income"] = inc["income"].map(income_index).astype(int)
        grouped = inc.groupby(INCOME_KEYS, as_index=False)[COUNT_KEYS].sum().sort_values(INCOME_KEYS)
        income_rows = _rows_from_grouped(grouped, INCOME_KEYS)

    # --- institutions (multi-valued, any author; top-N by audited papers then by volume) ---
    institution_rows: List[List[int]] = []
    institution_list: List[str] = []
    if prepared["available"]["institutions"]:
        exploded = flags[["year", "hi", "trial", "institutions"] + COUNT_KEYS].copy()
        exploded["institution"] = exploded["institutions"].str.split("|")
        exploded = exploded.explode("institution")
        exploded["institution"] = _clean_text(exploded["institution"])
        aliases = read_institution_aliases() if institution_aliases is None else institution_aliases
        if aliases:
            exploded["institution"] = exploded["institution"].replace(aliases)
        # one row per (article, institution): an article listing two units of one institution counts once
        dup = pd.DataFrame({"row": exploded.index.to_numpy(), "inst": exploded["institution"].to_numpy()}).duplicated()
        exploded = exploded[~dup.to_numpy()]
        exploded["institution"] = exploded["institution"].where(exploded["institution"].ne(""), NO_INSTITUTION_LABEL)
        audited_counts = exploded[exploded["das_audited"] > 0]["institution"]
        top = _top_categories(audited_counts, top_institutions, exclude=[NO_INSTITUTION_LABEL])
        if len(top) < top_institutions:
            extra = [i for i in _top_categories(exploded["institution"], top_institutions, exclude=[NO_INSTITUTION_LABEL]) if i not in top]
            top = top + extra[: top_institutions - len(top)]
        institution_list = top + [OTHER_LABEL, NO_INSTITUTION_LABEL]
        inst_index = {i: k for k, i in enumerate(institution_list)}
        folded = exploded["institution"].where(exploded["institution"].isin(set(top) | {NO_INSTITUTION_LABEL}), OTHER_LABEL)
        exploded["institution"] = folded.map(inst_index).astype(int)
        grouped = exploded.groupby(INSTITUTION_KEYS, as_index=False)[COUNT_KEYS].sum().sort_values(INSTITUTION_KEYS)
        institution_rows = _rows_from_grouped(grouped, INSTITUTION_KEYS)

    years = sorted(int(y) for y in flags["year"].unique()) if not flags.empty else []
    return {
        "discipline": discipline,
        "label": dash.discipline_label(discipline),
        "years": years,
        "journals": [{"key": j, "label": journal_labels.get(j, j)} for j in journal_list],
        "countries": [{"key": c, "label": ISO2_NAMES.get(c, c) if c not in (OTHER_LABEL,) else c,
                       "income": country_income.get(c, "") if c != OTHER_LABEL else ""}
                      for c in country_list],
        "funders": funder_list,
        "income_groups": income_list,
        "institutions": institution_list,
        "cells": cell_rows,
        "funder_cells": funder_rows,
        "income_cells": income_rows,
        "institution_cells": institution_rows,
        "available": prepared["available"],
        "totals": prepared["totals"],
        "corpus_rule": prepared["corpus_rule"],
        "high_impact_settings": prepared["high_impact_settings"],
    }


# ---------------------------------------------------------------------------
# Payload assembly
# ---------------------------------------------------------------------------

def read_policy_events(root: Path) -> List[Dict[str, Any]]:
    """Policy milestones drawn as markers on the trend charts (configs/policy_events.json); [] if absent."""
    path = root / "configs" / "policy_events.json"
    if not path.exists():
        return []
    try:
        events = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logging.warning("Could not read %s: %s", path, exc)
        return []
    out: List[Dict[str, Any]] = []
    for e in events if isinstance(events, list) else []:
        if isinstance(e, dict) and isinstance(e.get("year"), int) and e.get("label"):
            out.append({"year": int(e["year"]), "label": str(e["label"]), "short": str(e.get("short") or e["label"]),
                        "detail": str(e.get("detail", "")), "scope": str(e.get("scope", ""))})
    return sorted(out, key=lambda e: e["year"])


def read_citation(root: Path) -> Dict[str, str]:
    """Minimal CITATION.cff reader (title, version, date-released, repository-code, license)."""
    path = root / "CITATION.cff"
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(title|version|date-released|repository-code|license):\s*(.+)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def discipline_palette(disciplines: Sequence[str]) -> Dict[str, str]:
    palette: Dict[str, str] = {}
    extra = iter(EXTRA_COLORS)
    for d in disciplines:
        palette[d] = DISCIPLINE_COLORS.get(d) or next(extra, "#777777")
    return palette


def assemble_payload(aggregates: List[Dict[str, Any]], *, run_date: Optional[str] = None,
                     repo_root: Optional[Path] = None, high_impact_defaults: Optional[Dict[str, float]] = None,
                     top_n: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    repo_root = repo_root or SCRIPT_DIR.parent
    run_date = run_date or dt.date.today().isoformat()
    ordered = sorted(aggregates, key=lambda a: (DISCIPLINE_ORDER.index(a["discipline"])
                                                if a["discipline"] in DISCIPLINE_ORDER else 99, a["discipline"]))
    disciplines = [a["discipline"] for a in ordered]
    palette = discipline_palette(disciplines)
    all_years = sorted({y for a in ordered for y in a["years"]})

    hi_settings: Dict[str, float] = {}
    for a in ordered:
        for key, value in (a.get("high_impact_settings") or {}).items():
            hi_settings.setdefault(key, value)
    for key, value in (high_impact_defaults or {}).items():
        hi_settings.setdefault(key, value)

    run_year = int(run_date[:4])
    # The run year is incomplete and the year before it is partial; both are shown (shaded) in the site.
    # The year-range filter defaults to the last complete year, i.e. run_year - 1 (the data run in 2026
    # defaults to 2015-2025 with 2026 selectable).
    partial_years = [y for y in all_years if y >= run_year - 1]
    complete_years = [y for y in all_years if y < run_year]
    default_year_range = ([complete_years[0], complete_years[-1]] if complete_years
                          else ([all_years[0], all_years[-1]] if all_years else []))
    notes = list(METHODS_NOTES)
    if partial_years:
        notes[3] = (f"{', '.join(str(y) for y in partial_years)} " + ("is" if len(partial_years) == 1 else "are")
                    + " incomplete: indexing lag and embargoes mean counts and some rates (especially green OA "
                      "and preprint links) will change as records are updated.")

    citation = read_citation(repo_root)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_date": run_date,
        "count_keys": COUNT_KEYS,
        "cell_keys": CELL_KEYS,
        "funder_keys": FUNDER_KEYS,
        "income_keys": INCOME_KEYS,
        "institution_keys": INSTITUTION_KEYS,
        "income_order": INCOME_ORDER,
        "income_labels": INCOME_LABELS,
        "fulltext_keys": FULLTEXT_KEYS,
        "commitment_signals": COMMITMENT_SIGNALS,
        "oa_status_order": OA_STATUS_ORDER,
        "oa_status_colors": OA_STATUS_COLORS,
        "das_order": DAS_ORDER,
        "das_labels": dash.DAS_LABELS,
        "das_colors": DAS_COLORS,
        "metrics": METRICS,
        "methods_notes": notes,
        "years": all_years,
        "partial_years": partial_years,
        "default_year_range": default_year_range,
        "top_n": top_n or {"journals": 40, "countries": 25, "funders": 25, "institutions": 60},
        "high_impact": {"settings": hi_settings, "description": dash.high_impact_description(hi_settings)},
        "study_design": {"description": study_design_description()},
        "corpus_rule": {a["discipline"]: a["corpus_rule"] for a in ordered},
        "citation": citation,
        "policy_events": read_policy_events(repo_root),
        "repo_url": citation.get("repository-code", "https://github.com/Friseeb/stroke_open_science"),
        "outputs_repo_url": "https://github.com/Friseeb/stroke_open_science_outputs",
        "disciplines": [
            {
                "key": a["discipline"], "label": a["label"], "color": palette[a["discipline"]],
                "years": a["years"], "journals": a["journals"], "countries": a["countries"],
                "funders": a["funders"], "income_groups": a.get("income_groups", []),
                "institutions": a.get("institutions", []), "available": a["available"], "totals": a["totals"],
                "cells": a["cells"], "funder_cells": a["funder_cells"],
                "income_cells": a.get("income_cells", []), "institution_cells": a.get("institution_cells", []),
            }
            for a in ordered
        ],
    }


def write_payload(payload: Dict[str, Any], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    out_path.write_text(text, encoding="utf-8")
    size = out_path.stat().st_size
    logging.info("Wrote %s (%.2f MB)", out_path, size / 1e6)
    if size > 3_500_000:
        logging.warning("dashboard_data.json is %.2f MB; consider lowering --top-journals/--top-countries.",
                        size / 1e6)
    return size


def copy_site(json_path: Path, site_dir: Path, dashboard_src: Optional[Path] = None) -> List[Path]:
    """Copy the static page (dashboard/) and the JSON into ``site_dir``."""
    dashboard_src = dashboard_src or (SCRIPT_DIR.parent / "dashboard")
    site_dir.mkdir(parents=True, exist_ok=True)
    copied: List[Path] = []
    for name in ("index.html", "app.js", "charts.js", "styles.css"):
        src = dashboard_src / name
        if src.exists():
            shutil.copy2(src, site_dir / name)
            copied.append(site_dir / name)
        else:
            logging.warning("Dashboard asset missing: %s", src)
    target_json = site_dir / "dashboard_data.json"
    if json_path.resolve() != target_json.resolve():
        shutil.copy2(json_path, target_json)
    copied.append(target_json)
    logging.info("Copied site to %s", site_dir)
    return copied


def build_from_inputs(inputs: Dict[str, Path], *, enrichment_dir: Optional[Path] = None,
                      top_journals: int = 40, top_countries: int = 25, top_funders: int = 25,
                      high_impact_defaults: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    aggregates: List[Dict[str, Any]] = []
    for discipline, path in inputs.items():
        if not path.exists():
            logging.warning("Missing input CSV for %s: %s", discipline, path)
            continue
        logging.info("Loading %s: %s", discipline, path)
        df = load_discipline_csv(path)
        df = prepare_frame(df, discipline, enrichment_dir=enrichment_dir, source_dir=path.parent)
        agg = aggregate_discipline(df, discipline, top_journals=top_journals,
                                   top_countries=top_countries, top_funders=top_funders)
        if not agg["cells"]:
            logging.warning("No usable rows for %s; skipping.", discipline)
            continue
        aggregates.append(agg)
    return assemble_payload(aggregates, high_impact_defaults=high_impact_defaults,
                            top_n={"journals": top_journals, "countries": top_countries, "funders": top_funders, "institutions": 60})


def prepare_frame(df: pd.DataFrame, discipline: str, *, enrichment_dir: Optional[Path] = None,
                  source_dir: Optional[Path] = None) -> pd.DataFrame:
    """Optional enrichment join (only when the frame lacks the work-metadata fields) and
    registration-flag derivation for legacy frames."""
    lacks_metadata = "work_type" not in df.columns or _blank_mask(df["work_type"]).all()
    if enrichment_dir is not None and lacks_metadata:
        path = enrichment_path_for(Path(enrichment_dir), discipline)
        if path is None:
            logging.warning("No enrichment CSV for %s in %s", discipline, enrichment_dir)
        else:
            df = apply_enrichment_metadata(df, path)
    df = derive_registration_flags(df)
    df = derive_study_design(df, source_dir)
    return df


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    dash.setup_logging(args.verbose)
    inputs = dash.parse_input_pairs(args.inputs)
    enrichment_dir = Path(args.enrichment_dir).expanduser().resolve() if args.enrichment_dir else None
    payload = build_from_inputs(inputs, enrichment_dir=enrichment_dir, top_journals=args.top_journals,
                                top_countries=args.top_countries, top_funders=args.top_funders)
    out_path = Path(args.out).expanduser().resolve()
    write_payload(payload, out_path)
    if args.site_dir:
        copy_site(out_path, Path(args.site_dir).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
