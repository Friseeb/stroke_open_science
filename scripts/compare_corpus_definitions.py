#!/usr/bin/env python3
"""
Contrast two corpus definitions on the metadata-level open-science indicators.

Both inputs are pipeline outputs (``fully_enriched.csv``), typically the benchmark corpus (OpenAlex title
search) and a wider pull of the same discipline and year (``--openalex-search-field title_and_abstract``).
Rows are reduced to the article corpus and flagged exactly as the dashboard does (``build_dashboard_data``),
so the rates match the site's definitions. Full-text indicators are left out: they need the audit.

Usage:
  python scripts/compare_corpus_definitions.py --a "title=data/benchmarks/stroke/fully_enriched.csv" \
      --b "title+abstract=data/sensitivity/stroke_tab_2024/fully_enriched.csv" --year 2024 \
      --out talk/outputs/tables/corpus_sensitivity_2024.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_dashboard_data as bdd  # noqa: E402

INDICATORS: List[Tuple[str, str, str]] = [
    # (label, numerator count key, denominator count key)
    ("Open access", "oa", "n"),
    ("  diamond", "oa_diamond", "n"), ("  gold", "oa_gold", "n"), ("  hybrid", "oa_hybrid", "n"),
    ("  green", "oa_green", "n"), ("  bronze", "oa_bronze", "n"), ("  closed", "oa_closed", "n"),
    ("Data in a repository", "data", "n"),
    ("Code link", "code", "n"),
    ("Any repository / materials", "material", "n"),
    ("Preprint version", "preprint", "n"),
    ("Registration signal (of papers with an abstract)", "reg", "n_abs"),
]


def parse_spec(spec: str) -> Tuple[str, Path]:
    if "=" not in spec:
        raise SystemExit(f"--a/--b take label=path, got {spec!r}")
    label, path = spec.split("=", 1)
    return label.strip(), Path(path).expanduser()


def load(label: str, path: Path, year: int | None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = bdd.load_discipline_csv(path)
    df = bdd.prepare_frame(df, label)
    flags = bdd.row_flags(df, label)["flags"]
    if year is not None:
        flags = flags[flags["year"] == year]
    kept = df.loc[flags.index] if flags.index.isin(df.index).all() else df
    return flags, kept


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", required=True, help="label=path of the first corpus (fully_enriched.csv)")
    ap.add_argument("--b", required=True, help="label=path of the second corpus")
    ap.add_argument("--year", type=int, default=None, help="restrict both to one publication year")
    ap.add_argument("--out", default=None, help="CSV to write the comparison table to")
    args = ap.parse_args(argv)
    la, pa = parse_spec(args.a)
    lb, pb = parse_spec(args.b)
    fa, da = load(la, pa, args.year)
    fb, db = load(lb, pb, args.year)
    doi_a = set(bdd.doi_norm_series(da).loc[fa.index]) if "doi" in da.columns else set()
    doi_b = set(bdd.doi_norm_series(db).loc[fb.index]) if "doi" in db.columns else set()
    doi_a.discard(""); doi_b.discard("")
    both = doi_a & doi_b
    rows = [{"indicator": "Articles in corpus", la: int(fa["n"].sum()), lb: int(fb["n"].sum()), "difference_pp": ""},
            {"indicator": f"DOIs also in the other corpus", la: f"{len(both) / max(1, len(doi_a)):.1%}", lb: f"{len(both) / max(1, len(doi_b)):.1%}", "difference_pp": ""}]
    for label, num, den in INDICATORS:
        ra = fa[num].sum() / fa[den].sum() if fa[den].sum() else float("nan")
        rb = fb[num].sum() / fb[den].sum() if fb[den].sum() else float("nan")
        rows.append({"indicator": label, la: f"{ra:.1%}", lb: f"{rb:.1%}", "difference_pp": f"{(rb - ra) * 100:+.1f}"})
    # the wider corpus minus the benchmark: what the title search leaves out
    extra = fb.loc[[d in (doi_b - doi_a) for d in bdd.doi_norm_series(db).loc[fb.index]]] if doi_b else fb.iloc[0:0]
    if len(extra):
        rows.append({"indicator": f"Only in {lb}: articles", la: "", lb: int(extra["n"].sum()), "difference_pp": ""})
        for label, num, den in INDICATORS[:1] + INDICATORS[7:]:
            r = extra[num].sum() / extra[den].sum() if extra[den].sum() else float("nan")
            rows.append({"indicator": f"Only in {lb}: {label.strip()}", la: "", lb: f"{r:.1%}", "difference_pp": ""})
    table = pd.DataFrame(rows)
    with pd.option_context("display.max_rows", 100, "display.width", 160):
        print(table.to_string(index=False))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(args.out, index=False)
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
