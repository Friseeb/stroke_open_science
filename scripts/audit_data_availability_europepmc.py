#!/usr/bin/env python3
"""Audit data-availability statements (DAS) in open-access stroke articles via Europe PMC.

Why: repository links detectable from titles, abstracts and metadata are a lower
bound for data sharing. The data-availability statement in the full text is where
authors actually say what they share. No stroke-specific DAS audit exists in the
literature (see talk/evidence_brief.md), so this script produces one.

Scope and bias: Europe PMC full text is available only for the open-access subset
(PMC/Europe PMC OA). Open-access articles are, if anything, MORE likely to share,
so the result is an optimistic estimate for stroke as a whole. Say so on the slide.

Stages (all resumable, all free, no API key):
  1. search   - Europe PMC REST search, one query per year, cursor pagination,
                writes data/das_audit/articles.csv
  2. fetch    - fullTextXML per PMCID; extracts only the DAS / code-availability
                sections and a few flags; appends to data/das_audit/statements.jsonl
  3. classify - regex classification of each statement into categories; writes
                tables and a figure under talk/outputs/das_audit/

Usage:
  python scripts/audit_data_availability_europepmc.py search --years 2016 2025
  python scripts/audit_data_availability_europepmc.py fetch
  python scripts/audit_data_availability_europepmc.py classify
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import pandas as pd
import requests

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
STROKE_TITLE_QUERY = (
    '(TITLE:"stroke" OR TITLE:"ischemic stroke" OR TITLE:"ischaemic stroke" OR TITLE:"hemorrhagic stroke" '
    'OR TITLE:"transient ischemic attack" OR TITLE:"transient ischaemic attack" OR TITLE:"cerebral infarction" '
    'OR TITLE:"intracerebral hemorrhage" OR TITLE:"intracerebral haemorrhage" OR TITLE:"cerebrovascular accident")'
)
ARTICLE_FILTER = '(PUB_TYPE:"journal article" OR PUB_TYPE:"research-article") AND OPEN_ACCESS:y AND SRC:MED AND HAS_FT:y'

DAS_SEC_TYPES = {"data-availability", "data-availability-statement", "data-availability-statements", "availability-of-data", "data-sharing", "code-availability", "availability"}
DAS_SENTENCE_PATTERN = re.compile(
    r"(data|datasets?|materials?)[^.;]{0,100}(support(ing)? the (findings|results|conclusions)|used (and/or |and |or )?analy[sz]ed|generated (and|or) analy[sz]ed|"
    r"of (this|the present|the current) study)[^.;]{0,160}(available|shared|accessible|deposited|provided|obtained)|"
    r"(available|obtained) from the corresponding author|data (sharing|availability) statement|"
    r"(will|can|may) be (made )?available (up)?on (reasonable )?request|(are|is) available (up)?on (reasonable |justified )?request|"
    r"data (are|is) not publicly available|no data(sets)? (were|was|are|is) (generated|used|created|analy[sz]ed)|"
    r"data sharing (is )?not applicable|supplied regarding data availability|"
    r"(make|made) (the |all |our )?(data|datasets?|study materials?)[^.;]{0,80}available to (any|other|qualified) researcher|"
    r"will not be made available to other researchers|without undue reservation|"
    r"requests? to access the data(set)? (may|can|should) be (sent|directed|made)|"
    r"(anonymi[sz]ed |de-?identified |individual participant )?data (will|can|may|could) be (shared|provided|obtained|made available|released) (up)?on (reasonable |justified )?request|"
    r"(data|datasets?) and (materials?|code) (are|is|were) (publicly |freely )?available (at|from|in|through)|"
    r"(seeking|requesting) access to the (data|dataset)|formal data (sharing|use|access) agreement",
    re.I,
)
DAS_TITLE_PATTERN = re.compile(r"(data|code|material|software)\s+(and\s+\w+\s+)?(availability|sharing|access|statement)|availability\s+of\s+(the\s+)?(data|code|supporting)|data\s+statement", re.I)

# Classification patterns (multi-label). Order in PRIMARY_PRIORITY resolves to one label.
PATTERNS: Dict[str, re.Pattern] = {
    # Authors deposited their own data/code somewhere public.
    "repository": re.compile(
        r"zenodo|figshare|dryad|osf\.io|open science framework|github\.com|gitlab|bitbucket|dbgap|openneuro|synapse\.org|"
        r"mendeley data|vivli|yoda project|virtual international stroke trials archive|clinicalstudydatarequest|"
        r"dataverse|\bgeo\b accession|\bgse\d{4,}|arrayexpress|\bsra\b|ega-|european genome-phenome|physionet|"
        r"\bnda\b|nimh data archive|openicpsr|icpsr|zivahub|re3data|doi\.org/10\.5281|doi\.org/10\.6084|"
        r"doi\.org/10\.5061|deposited (in|at|to|with) (a |the )?(public )?(repositor|archive|database)|"
        r"(are|is|have been|has been) (publicly |openly |freely )?available (at|in|from|through|via) (the )?(https?://|www\.)|"
        r"supplemental file|supplementary (data )?file",
        re.I,
    ),
    # Secondary analysis of an existing public or third-party dataset (not the authors' deposit).
    "public_source": re.compile(
        r"uk ?biobank|biobank|nhanes|nhird|national health insurance (research )?database|charls|mimic-?i{1,3}v?|eicu|"
        r"global burden of disease|\bgbd\b|hcup|nationwide inpatient sample|national inpatient sample|\bseer\b|medicare|cprd|"
        r"get with the guidelines|\bnis\b|nsqip|\bvista\b|publicly available (from|at|on|through|via|database|dataset|data ?set)|"
        r"(data|dataset)s? (are|is|were|was) (publicly |freely )?available (from|at) (the )?(official )?\w[\w\s-]{0,40}(website|portal|database|platform|registry)|"
        r"third[- ]party (data|database)|open[- ]access database|public (database|dataset|registry|data ?source)",
        re.I,
    ),
    "on_request": re.compile(
        r"(up)?on (reasonable |justified |formal |written )?request|by request|available from the corresponding author|"
        r"contact(ing)? the (corresponding |first |senior |main )?author|available upon|request to the (corresponding |first )?author|"
        r"from the authors? (up)?on|made available by the authors|available (by|with|through|via) the (corresponding |main |first |senior )?author|"
        r"without undue reservation|to any qualified researcher|available to any researcher|available to other researchers|"
        r"may be (sent|directed|requested|obtained)|requests? (to access|for) (the )?data|on asking|via connecting with|"
        r"(shared|provided|released|obtained) (up)?on (reasonable |justified )?request",
        re.I,
    ),
    "in_article": re.compile(
        r"(included|contained|presented|provided|available) (with)?in (this|the) (published )?(article|manuscript|paper|study)|"
        r"within the (article|manuscript|paper)|supplementa(l|ry) (material|information|file|data|table|appendix)|supporting information|"
        r"all (relevant )?data are (within|in) the (paper|manuscript)",
        re.I,
    ),
    "controlled_or_restricted": re.compile(
        r"restrictions? apply|not publicly available|cannot be (made )?(publicly )?(available|shared)|not permitted|"
        r"ethical (restriction|reason|approval)|privacy|confidential|data protection|gdpr|ethics committee|"
        r"institutional (review board|policy)|patient (consent|privacy)|data (use|sharing|access|transfer) agreement|"
        r"controlled access|regulatory|governance|licen[cs]e|restricted to|approval (of|by|from) the|subject to (the following )?(license|restriction)|"
        r"by law|legal (restriction|reason)|consent was not (sought|obtained)",
        re.I,
    ),
    "not_available_or_na": re.compile(
        r"no (new |additional )?data(sets)? (were|was|are|is) (generated|created|analy[sz]ed|used|available)|not applicable|"
        r"no data (are|is|was|were) (available|used)|data sharing (is )?not applicable|will not be (made )?(available|shared)|"
        r"not available|data are unavailable|no additional data",
        re.I,
    ),
    "code_shared": re.compile(r"(code|script|software|analysis pipeline)s? (is|are|were|will be|have been) (publicly |freely |openly )?(available|shared|deposited|released)|github\.com|gitlab|zenodo", re.I),
}
PRIMARY_PRIORITY = ["repository", "public_source", "controlled_or_restricted", "on_request", "in_article", "not_available_or_na"]


# ----------------------------------------------------------------------------- stage 1: search
def search_year(session: requests.Session, year: int, delay: float) -> List[Dict]:
    query = f"{STROKE_TITLE_QUERY} AND {ARTICLE_FILTER} AND FIRST_PDATE:[{year}-01-01 TO {year}-12-31]"
    cursor = "*"
    rows: List[Dict] = []
    while True:
        resp = session.get(f"{BASE}/search", params={"query": query, "format": "json", "resultType": "lite", "pageSize": 1000, "cursorMark": cursor}, timeout=90)
        resp.raise_for_status()
        payload = resp.json()
        for hit in payload.get("resultList", {}).get("result", []):
            rows.append({
                "pmcid": hit.get("pmcid"), "pmid": hit.get("pmid"), "doi": (hit.get("doi") or "").lower(),
                "year": year, "journal": hit.get("journalTitle"), "title": hit.get("title"),
                "pub_type": "|".join(hit.get("pubTypeList", {}).get("pubType", [])) if isinstance(hit.get("pubTypeList"), dict) else "",
                "is_oa": hit.get("isOpenAccess"), "cited_by": hit.get("citedByCount"),
            })
        nxt = payload.get("nextCursorMark")
        if not nxt or nxt == cursor or not payload.get("resultList", {}).get("result"):
            break
        cursor = nxt
        time.sleep(delay)
    logging.info("%d: %d articles (hitCount=%s)", year, len(rows), payload.get("hitCount"))
    return rows


def stage_search(args: argparse.Namespace) -> None:
    out = Path(args.data_dir) / "articles.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    rows: List[Dict] = []
    y0, y1 = args.years
    for year in range(y0, y1 + 1):
        rows.extend(search_year(session, year, args.delay))
    df = pd.DataFrame(rows)
    df = df[df["pmcid"].notna()].drop_duplicates("pmcid")
    df.to_csv(out, index=False)
    logging.info("Wrote %d articles with a PMCID to %s", len(df), out)


# ----------------------------------------------------------------------------- stage 2: fetch
def _text(el: ET.Element) -> str:
    return re.sub(r"\s+", " ", " ".join(el.itertext())).strip()


def extract_statements(xml_text: str) -> Dict:
    """Return DAS-related sections from a JATS XML document."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError:
        return {"parse_error": True}
    statements: List[Dict] = []
    seen: Set[str] = set()

    def consider(el: ET.Element, how: str, label: str):
        txt = _text(el)
        if not txt or txt in seen or len(txt) > 6000:
            return
        seen.add(txt)
        statements.append({"how": how, "label": label[:120], "text": txt})

    for sec in root.iter("sec"):
        sec_type = (sec.get("sec-type") or "").lower()
        title_el = sec.find("title")
        title = _text(title_el) if title_el is not None else ""
        if sec_type in DAS_SEC_TYPES or any(t in sec_type for t in ("availab", "data-sharing")):
            consider(sec, "sec-type", sec_type or title)
        elif title and DAS_TITLE_PATTERN.search(title) and len(title) < 90:
            consider(sec, "sec-title", title)
    for tag in ("notes", "fn", "custom-meta", "supplementary-material", "ack", "statement"):
        for el in root.iter(tag):
            attrs = " ".join(f"{k}={v}" for k, v in el.attrib.items()).lower()
            title_el = el.find("title")
            title = _text(title_el) if title_el is not None else ""
            meta_name = el.find("meta-name")
            label = _text(meta_name) if meta_name is not None else ""
            if "availab" in attrs or "data-sharing" in attrs or (title and DAS_TITLE_PATTERN.search(title)) or (label and DAS_TITLE_PATTERN.search(label)):
                consider(el, tag, attrs or title or label)
            elif tag in ("fn", "notes", "ack"):
                txt = _text(el)
                if DAS_SENTENCE_PATTERN.search(txt) and len(txt) < 1500:
                    consider(el, f"{tag}-sentence", "unmarked DAS in " + tag)
    # Last resort: a paragraph that starts like a DAS, or any paragraph containing a
    # DAS-style sentence (AHA journals place the statement unmarked at the start of Methods).
    if not statements:
        for p in root.iter("p"):
            txt = _text(p)
            if re.match(r"^(data|code) (availability|sharing)( statement)?[:.]", txt, re.I) or re.match(r"^availability of data", txt, re.I):
                consider(p, "p-prefix", txt[:40])
                continue
            m = DAS_SENTENCE_PATTERN.search(txt)
            if m:
                start_idx = txt.rfind(". ", 0, m.start())
                start_idx = 0 if start_idx < 0 else start_idx + 2
                end_idx = txt.find(". ", m.end())
                end_idx = len(txt) if end_idx < 0 else end_idx + 1
                sentence = txt[start_idx:end_idx]
                if 20 < len(sentence) < 700 and sentence not in seen:
                    seen.add(sentence)
                    statements.append({"how": "p-sentence", "label": "unmarked DAS sentence", "text": sentence})
    body_text = _text(root)
    flags = {
        "mentions_trial_registration": bool(re.search(r"\bNCT\d{8}\b|ISRCTN\d{8}|ChiCTR|clinicaltrials\.gov|PROSPERO|CRD42\d{6}", body_text)),
        "mentions_github": "github.com" in body_text.lower(),
        "mentions_supplement": bool(re.search(r"supplementa(l|ry)", body_text, re.I)),
        "n_chars": len(body_text),
    }
    return {"statements": statements, "flags": flags}


def already_fetched(path: Path) -> Set[str]:
    done: Set[str] = set()
    if path.exists():
        with path.open() as fh:
            for line in fh:
                try:
                    done.add(json.loads(line)["pmcid"])
                except Exception:
                    continue
    return done


def stage_fetch(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    articles = pd.read_csv(data_dir / "articles.csv")
    out = data_dir / "statements.jsonl"
    done = already_fetched(out)
    if args.refetch_missing and out.exists():
        # Re-fetch records that returned 200 but yielded no statement (parser improved since).
        keep, redo = [], set()
        with out.open() as fh:
            for line in fh:
                rec = json.loads(line)
                if rec.get("http") == 200 and not rec.get("statements"):
                    redo.add(rec["pmcid"])
                else:
                    keep.append(line)
        out.write_text("".join(keep))
        done -= redo
        logging.info("Re-fetching %d records that had no statement", len(redo))
    if args.sample_per_year:
        articles = (articles.groupby("year", group_keys=False)
                    .apply(lambda g: g.sample(n=min(len(g), args.sample_per_year), random_state=args.seed)))
        logging.info("Sampled up to %d articles per year -> %d", args.sample_per_year, len(articles))
    todo = [p for p in articles["pmcid"].dropna().tolist() if p not in done]
    if args.limit:
        todo = todo[: args.limit]
    logging.info("%d articles, %d fetched, %d to fetch", len(articles), len(done), len(todo))
    session = requests.Session()
    session.headers["User-Agent"] = "stroke-open-science-das-audit (mailto:sfridma@uwo.ca)"
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def fetch_one(pmcid: str) -> Dict:
        rec: Dict = {"pmcid": pmcid}
        try:
            resp = session.get(f"{BASE}/{pmcid}/fullTextXML", timeout=90)
            if resp.status_code == 200 and resp.text.strip():
                rec.update(extract_statements(resp.text))
                rec["http"] = 200
            else:
                rec["http"] = resp.status_code
        except requests.RequestException as exc:
            rec["http"] = "error"
            rec["error"] = str(exc)[:200]
            time.sleep(5)
        time.sleep(args.delay)
        return rec

    n_ok = n_err = 0
    with out.open("a") as fh, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(fetch_one, p) for p in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            rec = fut.result()
            if rec.get("http") == 200:
                n_ok += 1
            else:
                n_err += 1
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if i % 200 == 0:
                fh.flush()
                logging.info("%d/%d fetched (ok=%d, err=%d)", i, len(todo), n_ok, n_err)
    logging.info("Fetch done: ok=%d err=%d -> %s", n_ok, n_err, out)


# ----------------------------------------------------------------------------- stage 3: classify
REFUSAL_PATTERN = re.compile(r"will not be (made )?(available|shared)|no data(sets)? (were|was|are|is) (generated|used|created)|data sharing (is )?not applicable|no additional data", re.I)


def classify_text(text: str) -> Dict[str, object]:
    labels = {name: bool(p.search(text)) for name, p in PATTERNS.items()}
    if REFUSAL_PATTERN.search(text) and not labels["repository"] and not labels["public_source"]:
        primary = "not_available_or_na"
    else:
        primary = next((name for name in PRIMARY_PRIORITY if labels[name]), "other_or_unclear")
    return {**{f"lab_{k}": v for k, v in labels.items()}, "primary": primary}


def stage_classify(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    articles = pd.read_csv(data_dir / "articles.csv")
    rows: List[Dict] = []
    with (data_dir / "statements.jsonl").open() as fh:
        for line in fh:
            rec = json.loads(line)
            if rec.get("http") != 200:
                rows.append({"pmcid": rec["pmcid"], "fetched": False})
                continue
            stmts = [st for st in (rec.get("statements") or []) if len(re.sub(r"(?i)(data|code)? ?(availability|sharing)( statement)?|availability of data( and materials?)?", "", st["text"]).strip()) > 15]
            das_text = " || ".join(st["text"] for st in stmts)
            row = {"pmcid": rec["pmcid"], "fetched": True, "has_das": bool(stmts), "n_statements": len(stmts), "das_chars": len(das_text), "das_text": das_text[:2000], **(rec.get("flags") or {})}
            if stmts:
                row.update(classify_text(das_text))
            rows.append(row)
    df = articles.merge(pd.DataFrame(rows), on="pmcid", how="left")
    df["fetched"] = df["fetched"].fillna(False).astype(bool)
    fetched = df[df["fetched"]].copy()
    fetched["has_das"] = fetched["has_das"].fillna(False).astype(bool)
    fetched["primary"] = fetched["primary"].fillna("no_statement")
    out_dir = Path(args.out_dir)
    (out_dir / "tables").mkdir(parents=True, exist_ok=True)
    fetched.drop(columns=["das_text"]).to_csv(out_dir / "tables" / "das_audit_articles.csv", index=False)
    fetched[["pmcid", "year", "journal", "primary", "das_text"]].to_csv(out_dir / "tables" / "das_audit_statements.csv", index=False)

    cats = ["no_statement", "not_available_or_na", "in_article", "on_request", "controlled_or_restricted", "public_source", "repository", "other_or_unclear"]
    by_year = pd.crosstab(fetched["year"], fetched["primary"], normalize="index").reindex(columns=cats, fill_value=0.0)
    by_year["n"] = fetched.groupby("year").size()
    by_year.to_csv(out_dir / "tables" / "das_primary_by_year.csv")
    overall = fetched["primary"].value_counts(normalize=True).reindex(cats, fill_value=0.0)
    labs = {c: float(fetched[c].fillna(False).astype(bool).mean()) for c in fetched.columns if c.startswith("lab_")}
    by_journal = fetched.groupby("journal").agg(n=("pmcid", "size"), has_das=("has_das", "mean"), repository=("primary", lambda s: (s == "repository").mean()), on_request=("primary", lambda s: (s == "on_request").mean())).sort_values("n", ascending=False).head(20)
    by_journal.to_csv(out_dir / "tables" / "das_by_journal_top20.csv")
    summary = {
        "n_articles_searched": int(len(df)), "n_fetched": int(len(fetched)), "years": [int(fetched["year"].min()), int(fetched["year"].max())],
        "has_das_rate": float(fetched["has_das"].mean()), "primary_overall": {k: round(float(v), 4) for k, v in overall.items()},
        "multilabel_rates_all_fetched": {k: round(v, 4) for k, v in labs.items()},
        "scope_note": "Open-access full text in Europe PMC only; optimistic relative to all stroke articles.",
    }
    (out_dir / "das_audit_summary.json").write_text(json.dumps(summary, indent=2))
    logging.info("Summary: %s", json.dumps(summary["primary_overall"]))
    logging.info("has_das_rate=%.3f over %d fetched articles", summary["has_das_rate"], len(fetched))

    # Figure: stacked shares by year.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    colors = {"repository": "#0d366b", "public_source": "#1c5cab", "controlled_or_restricted": "#2a78d6", "on_request": "#86b6ef", "in_article": "#cde2fb", "not_available_or_na": "#e6e5e1", "other_or_unclear": "#f0efec", "no_statement": "#d9d8d4"}
    nice = {"repository": "authors' deposit in a repository", "public_source": "public or third-party dataset", "controlled_or_restricted": "controlled / restricted", "on_request": "on request", "in_article": "in article or supplement", "not_available_or_na": "not available / N/A", "other_or_unclear": "other / unclear", "no_statement": "no statement found"}
    order = ["repository", "public_source", "controlled_or_restricted", "on_request", "in_article", "not_available_or_na", "other_or_unclear", "no_statement"]
    fig, ax = plt.subplots(figsize=(12, 6.75), dpi=150)
    years = by_year.index.astype(int).values
    bottom = np.zeros(len(years))
    for c in order:
        vals = by_year[c].values
        ax.bar(years, vals, bottom=bottom, color=colors[c], width=0.8, edgecolor="white", linewidth=1.5, label=nice[c])
        bottom += vals
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_ylim(0, 1)
    ax.set_xticks(years)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.tick_params(colors="#52514e", labelsize=11)
    ax.set_title("What stroke data-availability statements actually say", loc="left", fontsize=15, fontweight="bold", pad=14)
    ax.legend(ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.08), fontsize=10)
    fig.text(0.01, -0.06, f"Open-access stroke articles with full text in Europe PMC, n={len(fetched):,}. Regex classification of the data-availability section; one primary label per article.", color="#52514e", fontsize=9)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "figures" / "fig11_das_audit.png", bbox_inches="tight", facecolor="white")
    fig.savefig(out_dir / "figures" / "fig11_das_audit.svg", bbox_inches="tight", facecolor="white")
    logging.info("Wrote tables and figure under %s", out_dir)


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["search", "fetch", "classify"])
    parser.add_argument("--data-dir", default="data/das_audit")
    parser.add_argument("--out-dir", default="talk/outputs/das_audit")
    parser.add_argument("--years", nargs=2, type=int, default=[2016, 2025])
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=5, help="parallel full-text fetches")
    parser.add_argument("--sample-per-year", type=int, default=0, help="random sample size per year (0 = all)")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--refetch-missing", action="store_true", help="re-fetch records that had no statement (after parser changes)")
    args = parser.parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")
    {"search": stage_search, "fetch": stage_fetch, "classify": stage_classify}[args.stage](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
