#!/usr/bin/env python3
"""Enrich a fully_enriched.csv with OpenAlex work-level metadata via batched DOI lookups.

Why: the benchmark retrieval selects a limited field list and lacks
``open_access.oa_status`` (gold/green/hybrid/bronze/diamond/closed), the work
``type`` (needed to drop datasets, preprints, errata and book chapters from the
paper corpus), preprint locations, author countries and funders. OpenAlex serves
up to 50 DOIs per list request (``filter=doi:a|b|...``) at $0.0001 per request,
so ~180k DOIs cost ~$0.36 and fit the free $1/day budget.

Resumable: results are appended to a JSONL file per batch; re-running skips DOIs
already present. Stops cleanly when the daily budget is nearly exhausted.

Usage:
  python scripts/enrich_openalex_work_metadata.py \
      --input data/full_release/stroke-fully_enriched.csv \
      --output data/enrichment/stroke_work_metadata.jsonl
  python scripts/enrich_openalex_work_metadata.py --to-csv data/enrichment/stroke_work_metadata.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import pandas as pd
import requests

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
SELECT_FIELDS = (
    "id,doi,publication_year,type,open_access,primary_location,locations,"
    "authorships,is_retracted,has_fulltext,funders"
)
BATCH_SIZE = 50
PREPRINT_SERVER_PATTERN = re.compile(
    r"medrxiv|biorxiv|research square|ssrn|preprints\.org|preprints \(|arxiv|"
    r"osf preprints|authorea|europe pmc preprints|chinaxiv|scielo preprints|"
    r"jmir preprints|psyarxiv|sportrxiv|preprint",
    re.IGNORECASE,
)


def normalize_doi(value: object) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().lower()
    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text)
    text = text.removeprefix("doi:").strip()
    return text or None


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def already_done(output: Path) -> Set[str]:
    done: Set[str] = set()
    if output.exists():
        with output.open() as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("doi_norm"):
                    done.add(rec["doi_norm"])
                for miss in rec.get("_missing", []) or []:
                    done.add(miss)
    return done


def flatten_work(work: Dict) -> Dict:
    """Reduce an OpenAlex work to the flat fields the talk analysis needs."""
    oa = work.get("open_access") or {}
    primary = work.get("primary_location") or {}
    primary_source = primary.get("source") or {}
    locations = work.get("locations") or []

    preprint_servers: List[str] = []
    repository_names: List[str] = []
    versions: Set[str] = set()
    for loc in locations:
        src = loc.get("source") or {}
        name = src.get("display_name") or ""
        if loc.get("version"):
            versions.add(loc["version"])
        if src.get("type") == "repository":
            repository_names.append(name)
            if PREPRINT_SERVER_PATTERN.search(name):
                preprint_servers.append(name)
    is_preprint_record = work.get("type") == "preprint" or (
        primary_source.get("type") == "repository" and bool(PREPRINT_SERVER_PATTERN.search(primary_source.get("display_name") or ""))
    )

    countries: List[str] = []
    first_author_country = None
    institutions: List[str] = []
    for i, auth in enumerate(work.get("authorships") or []):
        cs = auth.get("countries") or []
        if i == 0 and cs:
            first_author_country = cs[0]
        countries.extend(cs)
        for inst in auth.get("institutions") or []:
            if inst.get("display_name"):
                institutions.append(inst["display_name"])

    funders = [f.get("display_name") for f in (work.get("funders") or []) if f.get("display_name")]

    return {
        "openalex_id": work.get("id"),
        "doi_norm": normalize_doi(work.get("doi")),
        "publication_year": work.get("publication_year"),
        "work_type": work.get("type"),
        "oa_is_oa": oa.get("is_oa"),
        "oa_status": oa.get("oa_status"),
        "oa_url": oa.get("oa_url"),
        "any_repository_fulltext": oa.get("any_repository_has_fulltext"),
        "primary_source_name": primary_source.get("display_name"),
        "primary_source_type": primary_source.get("type"),
        "primary_source_is_in_doaj": primary_source.get("is_in_doaj"),
        "primary_source_is_oa": primary_source.get("is_oa"),
        "primary_source_host_org": primary_source.get("host_organization_name"),
        "primary_license": primary.get("license"),
        "primary_version": primary.get("version"),
        "n_locations": len(locations),
        "versions": sorted(versions),
        "repository_names": repository_names,
        "preprint_servers": sorted(set(preprint_servers)),
        "has_preprint_version": bool(preprint_servers) and not is_preprint_record,
        "is_preprint_record": bool(is_preprint_record),
        "is_retracted": work.get("is_retracted"),
        "has_fulltext": work.get("has_fulltext"),
        "first_author_country": first_author_country,
        "countries": sorted(set(countries)),
        "n_authors": len(work.get("authorships") or []),
        "institutions": institutions[:10],
        "funders": funders,
        "n_funders": len(funders),
    }


def fetch_batch(session: requests.Session, dois: List[str], mailto: str, api_key: str, timeout: float, max_attempts: int = 4) -> Optional[requests.Response]:
    params = {
        "filter": "doi:" + "|".join(dois),
        "per-page": BATCH_SIZE,
        "select": SELECT_FIELDS,
        "mailto": mailto,
    }
    if api_key:
        params["api_key"] = api_key
    for attempt in range(1, max_attempts + 1):
        try:
            resp = session.get(OPENALEX_WORKS_URL, params=params, timeout=timeout)
        except requests.RequestException as exc:
            logging.warning("Request error (attempt %d): %s", attempt, exc)
            time.sleep(2 * attempt)
            continue
        if resp.status_code == 200:
            return resp
        if resp.status_code == 429:
            remaining = resp.headers.get("X-RateLimit-Remaining")
            reset = resp.headers.get("X-RateLimit-Reset")
            logging.error("429 from OpenAlex (remaining=%s, reset in %ss). Stopping; re-run after reset.", remaining, reset)
            return None
        if resp.status_code == 400:
            # Usually a malformed DOI in the batch; fall back to singles for this batch.
            logging.warning("400 for batch; retrying DOIs one by one")
            return resp
        logging.warning("HTTP %s (attempt %d): %s", resp.status_code, attempt, resp.text[:200])
        time.sleep(2 * attempt)
    return None


def run_enrichment(args: argparse.Namespace) -> int:
    load_env(Path(args.env))
    mailto = os.environ.get("OPENALEX_MAILTO", "")
    api_key = os.environ.get("OPENALEX_API_KEY", "")
    if not mailto:
        logging.error("OPENALEX_MAILTO is required")
        return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    frames = [pd.read_csv(p, usecols=["doi"], low_memory=False) for p in args.input]
    dois = sorted({d for d in (normalize_doi(v) for f in frames for v in f["doi"]) if d})
    done = already_done(output)
    todo = [d for d in dois if d not in done]
    logging.info("%d unique DOIs, %d already enriched, %d to fetch (~%d requests, ~$%.2f)",
                 len(dois), len(done), len(todo), (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE,
                 0.0001 * ((len(todo) + BATCH_SIZE - 1) // BATCH_SIZE))
    if args.limit:
        todo = todo[: args.limit]

    session = requests.Session()
    session.headers["User-Agent"] = f"stroke-open-science-enrich (mailto:{mailto})"
    n_requests = 0
    n_found = 0
    with output.open("a") as out:
        for start in range(0, len(todo), BATCH_SIZE):
            batch = todo[start : start + BATCH_SIZE]
            resp = fetch_batch(session, batch, mailto, api_key, args.timeout)
            if resp is None:
                break
            n_requests += 1
            remaining = resp.headers.get("X-RateLimit-Remaining")
            if resp.status_code == 400:
                results = []
                for doi in batch:
                    single = fetch_batch(session, [doi], mailto, api_key, args.timeout)
                    n_requests += 1
                    if single is not None and single.status_code == 200:
                        results.extend(single.json().get("results") or [])
                    time.sleep(args.delay)
            else:
                results = resp.json().get("results") or []
            found = set()
            for work in results:
                rec = flatten_work(work)
                if rec["doi_norm"]:
                    found.add(rec["doi_norm"])
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            missing = [d for d in batch if d not in found]
            if missing:
                out.write(json.dumps({"_missing": missing}) + "\n")
            out.flush()
            n_found += len(found)
            if n_requests % 50 == 0:
                logging.info("%d requests, %d/%d DOIs done, %d found, budget remaining=%s",
                             n_requests, min(start + BATCH_SIZE, len(todo)), len(todo), n_found, remaining)
            try:
                prepaid_usd = float(resp.headers.get("X-RateLimit-Prepaid-Remaining-USD") or 0)
                if remaining is not None and int(remaining) < args.min_budget_remaining and prepaid_usd < 0.05:
                    logging.warning("Budget nearly exhausted (remaining=%s, prepaid=$%.2f); stopping. Re-run after 00:00 UTC or after topping up.", remaining, prepaid_usd)
                    break
            except ValueError:
                pass
            time.sleep(args.delay)
    logging.info("Done: %d requests, %d works found. Output: %s", n_requests, n_found, output)
    return 0


def jsonl_to_csv(jsonl_path: Path, csv_path: Optional[Path]) -> Path:
    rows = []
    with jsonl_path.open() as fh:
        for line in fh:
            rec = json.loads(line)
            if "_missing" in rec:
                continue
            for key in ("versions", "repository_names", "preprint_servers", "countries", "institutions", "funders"):
                rec[key] = "|".join(rec.get(key) or [])
            rows.append(rec)
    df = pd.DataFrame(rows).drop_duplicates("doi_norm")
    csv_path = csv_path or jsonl_path.with_suffix(".csv")
    df.to_csv(csv_path, index=False)
    logging.info("Wrote %d rows to %s", len(df), csv_path)
    return csv_path


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", nargs="+", help="fully_enriched.csv file(s) to take DOIs from")
    parser.add_argument("--output", help="JSONL output (appended; resumable)")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--delay", type=float, default=0.12, help="seconds between requests")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--limit", type=int, default=0, help="only fetch this many DOIs (testing)")
    parser.add_argument("--min-budget-remaining", type=int, default=150, help="stop when X-RateLimit-Remaining drops below this")
    parser.add_argument("--to-csv", help="convert an existing JSONL to CSV and exit")
    parser.add_argument("--csv-out", help="CSV path for --to-csv")
    args = parser.parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")
    if args.to_csv:
        jsonl_to_csv(Path(args.to_csv), Path(args.csv_out) if args.csv_out else None)
        return 0
    if not args.input or not args.output:
        parser.error("--input and --output are required unless --to-csv is used")
    return run_enrichment(args)


if __name__ == "__main__":
    sys.exit(main())
