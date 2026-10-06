"""Tests for scripts/build_dashboard_data.py: pre-aggregated counts for the interactive dashboard."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest


def _load(name: str):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    root = Path(__file__).resolve().parents[1]
    target = root / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bdd = _load("build_dashboard_data")
dash = _load("build_discipline_dashboard")

JOURNALS = ["Stroke", "Lancet Neurology", "J Misc", "Tiny Journal"]
COUNTRIES = ["US", "GB", "CN", "DE", "FR"]
OA_STATUS = ["gold", "closed", "green", "hybrid", "diamond", "bronze"]


def make_frame(n: int = 120) -> pd.DataFrame:
    rows = []
    for i in range(n):
        journal = JOURNALS[i % 4] if i % 11 else "Tiny Journal"
        funders = ["NIH|NINDS", "NIH", "", "Wellcome Trust"][i % 4]
        rows.append({
            "doi": f"10.1000/{i}", "title": f"Paper {i}",
            "abstract": "" if i % 9 == 0 else ("Registered NCT01234567" if i % 6 == 0 else "Plain abstract text"),
            "year": 2019 + (i % 4),
            "journal": journal, "journal_norm": journal.lower(),
            "is_oa": i % 2 == 0, "license_unpaywall": "cc-by" if i % 10 == 0 else "",
            "github": "https://github.com/x/y" if i % 5 == 0 else "", "code_link": "", "zenodo": "", "osf": "", "repo_links": "",
            "data_link": "https://osf.io/abc" if i % 13 == 0 else "", "dataset_urls": "", "has_public_dataset": i % 7 == 0,
            "preprint": "", "has_preprint_version": i % 4 == 0,
            "high_impact_flag": i % 3 == 0, "high_impact_reason": "impact_factor>=10" if i % 3 == 0 else "",
            "oa_status": OA_STATUS[i % 6] if i % 17 else "",
            "first_author_country": COUNTRIES[i % 5] if i % 19 else "",
            "funders": funders,
            "registration_signal": i % 6 == 0 and i % 9 != 0,
            "in_article_corpus": i % 23 != 0,
            "das_available": i % 8 == 0, "das_has_statement": i % 16 == 0,
            "das_primary": "repository" if i % 16 == 0 else ("no_statement" if i % 8 == 0 else ""),
        })
    return pd.DataFrame(rows)


LEGACY_DROP = ["oa_status", "first_author_country", "funders", "registration_signal", "in_article_corpus",
               "das_available", "das_has_statement", "das_primary", "has_preprint_version", "abstract", "title"]


def counts_dict(rows, offset):
    total = [0] * len(bdd.COUNT_KEYS)
    for row in rows:
        for i, v in enumerate(row[offset:]):
            total[i] += v
    return dict(zip(bdd.COUNT_KEYS, total))


def corpus(df: pd.DataFrame) -> pd.DataFrame:
    out = df[dash.to_bool_series(df["in_article_corpus"])].copy() if "in_article_corpus" in df else df.copy()
    out["year"] = pd.to_numeric(out["year"], errors="coerce")
    return out[out["year"].notna()]


# ---------------------------------------------------------------------------

def test_cell_totals_match_pandas():
    df = make_frame()
    agg = bdd.aggregate_discipline(df, "stroke")
    ref = corpus(df)
    totals = counts_dict(agg["cells"], len(bdd.CELL_KEYS))
    assert totals["n"] == len(ref)
    assert totals["oa"] == int(dash.infer_oa_series(ref).sum())
    assert totals["code"] == int(dash.nonblank(ref["github"]).sum())
    expected_data = int((dash.to_bool_series(ref["has_public_dataset"]) | dash.nonblank(ref["data_link"])).sum())
    assert totals["data"] == expected_data
    assert totals["preprint"] == int(dash.to_bool_series(ref["has_preprint_version"]).sum())
    assert totals["reg"] == int(dash.to_bool_series(ref["registration_signal"]).sum())
    assert totals["n_abs"] == int(dash.nonblank(ref["abstract"]).sum())
    status = ref["oa_status"].fillna("").str.lower()
    for s in bdd.OA_STATUS_ORDER:
        assert totals[f"oa_{s}"] == int(status.eq(s).sum())
    audited = dash.to_bool_series(ref["das_available"]) & ref["das_primary"].isin(bdd.DAS_ORDER)
    assert totals["das_audited"] == int(audited.sum())
    assert totals["das_repository"] == int((audited & ref["das_primary"].eq("repository")).sum())
    assert totals["das_stmt"] == int((audited & dash.to_bool_series(ref["das_has_statement"])).sum())
    assert agg["totals"]["dropped"] == int((~dash.to_bool_series(df["in_article_corpus"])).sum())
    assert all(agg["available"][k] for k in ("oa_status", "das", "registration", "country", "funders", "high_impact"))


def test_row_layout_and_key_order():
    agg = bdd.aggregate_discipline(make_frame(), "stroke")
    width = len(bdd.CELL_KEYS) + len(bdd.COUNT_KEYS)
    assert all(len(row) == width for row in agg["cells"])
    assert all(len(row) == len(bdd.FUNDER_KEYS) + len(bdd.COUNT_KEYS) for row in agg["funder_cells"])
    assert bdd.COUNT_KEYS[:2] == ["n", "oa"]
    years = {row[0] for row in agg["cells"]}
    assert years == {2019, 2020, 2021, 2022}
    assert {row[1] for row in agg["cells"]} == {0, 1}


def test_top_n_folding_journals_and_countries():
    df = make_frame()
    agg = bdd.aggregate_discipline(df, "stroke", top_journals=2, top_countries=3)
    keys = [j["key"] for j in agg["journals"]]
    assert len(keys) == 3 and keys[-1] == "Other"
    ref = corpus(df)
    top2 = ref["journal_norm"].value_counts().index[:2].tolist()
    assert keys[:2] == top2
    # display label is the original spelling
    labels = {j["key"]: j["label"] for j in agg["journals"]}
    assert labels[top2[0]] == top2[0].title() or labels[top2[0]].lower() == top2[0]
    other_idx = keys.index("Other")
    other_n = sum(row[len(bdd.CELL_KEYS)] for row in agg["cells"] if row[2] == other_idx)
    assert other_n == int((~ref["journal_norm"].isin(top2)).sum())

    ckeys = [c["key"] for c in agg["countries"]]
    assert len(ckeys) == 4 and ckeys[-1] == "Other"
    country = ref["first_author_country"].fillna("").str.upper()
    top3 = country[country.ne("")].value_counts().index[:3].tolist()
    assert ckeys[:3] == top3
    other_c = sum(row[len(bdd.CELL_KEYS)] for row in agg["cells"] if row[3] == len(ckeys) - 1)
    # blank country is folded into Other too
    assert other_c == int((~country.isin(top3)).sum())
    assert agg["countries"][0]["label"] == bdd.ISO2_NAMES[top3[0]]


def test_funders_multivalued_and_no_funder_bucket():
    df = make_frame()
    agg = bdd.aggregate_discipline(df, "stroke", top_funders=2)
    assert agg["funders"][-2:] == ["Other", "(no funder listed)"]
    ref = corpus(df)
    exploded = ref["funders"].fillna("").str.split("|").explode().str.strip()
    nih_idx = agg["funders"].index("NIH")
    nih_n = sum(row[len(bdd.FUNDER_KEYS)] for row in agg["funder_cells"] if row[2] == nih_idx)
    assert nih_n == int(exploded.eq("NIH").sum())
    none_idx = agg["funders"].index("(no funder listed)")
    none_n = sum(row[len(bdd.FUNDER_KEYS)] for row in agg["funder_cells"] if row[2] == none_idx)
    assert none_n == int(exploded.eq("").sum())
    # a paper with two funders is counted under both, so funder n exceeds the paper total
    total_funder_n = sum(row[len(bdd.FUNDER_KEYS)] for row in agg["funder_cells"])
    assert total_funder_n == len(exploded) > len(ref)


@pytest.mark.parametrize("hi_only", [False, True])
def test_rates_recomputed_from_counts_match_pandas(hi_only):
    df = make_frame()
    agg = bdd.aggregate_discipline(df, "stroke", top_journals=2, top_countries=3)
    ref = corpus(df)
    ref["hi"] = dash.to_bool_series(ref["high_impact_flag"])
    ref["oa_bool"] = dash.infer_oa_series(ref)
    ref["reg_bool"] = dash.to_bool_series(ref["registration_signal"])
    ref["abs_ok"] = dash.nonblank(ref["abstract"])
    journal_key = agg["journals"][0]["key"]
    j_idx = 0
    off = len(bdd.CELL_KEYS)
    K = {k: i for i, k in enumerate(bdd.COUNT_KEYS)}
    for year in (2019, 2021):
        rows = [r for r in agg["cells"] if r[0] == year and r[2] == j_idx and (r[1] == 1 or not hi_only)]
        n = sum(r[off + K["n"]] for r in rows)
        oa = sum(r[off + K["oa"]] for r in rows)
        reg = sum(r[off + K["reg"]] for r in rows)
        n_abs = sum(r[off + K["n_abs"]] for r in rows)
        sub = ref[(ref["year"] == year) & (ref["journal_norm"] == journal_key)]
        if hi_only:
            sub = sub[sub["hi"]]
        assert n == len(sub)
        if n:
            assert oa / n == pytest.approx(sub["oa_bool"].mean())
            # registration denominator is papers with an abstract
            assert n_abs == int(sub["abs_ok"].sum())
            if n_abs:
                assert reg / n_abs == pytest.approx(sub.loc[sub["abs_ok"], "reg_bool"].mean())


def test_legacy_frame_without_new_columns():
    df = make_frame().drop(columns=LEGACY_DROP)
    agg = bdd.aggregate_discipline(df, "neurology")
    avail = agg["available"]
    assert not avail["oa_status"] and not avail["das"] and not avail["registration"]
    assert not avail["country"] and not avail["funders"] and not avail["preprint_metadata"]
    assert agg["funder_cells"] == [] and agg["funders"] == []
    totals = counts_dict(agg["cells"], len(bdd.CELL_KEYS))
    assert totals["n"] == len(df)                     # no corpus column -> every row kept
    assert totals["reg"] == 0 and totals["n_abs"] == 0 and totals["das_audited"] == 0
    assert sum(totals[f"oa_{s}"] for s in bdd.OA_STATUS_ORDER) == 0
    assert totals["oa"] == int(dash.infer_oa_series(df).sum())
    assert totals["preprint"] == 0                    # falls back to the blank `preprint` text column
    assert [c["key"] for c in agg["countries"]] == ["Other"]
    assert "no in_article_corpus" in agg["corpus_rule"]


def test_registration_derived_from_text_when_flags_missing():
    df = make_frame().drop(columns=["registration_signal"])
    out = bdd.prepare_frame(df, "stroke")
    assert "registration_signal" in out.columns
    ref = corpus(out)
    agg = bdd.aggregate_discipline(out, "stroke")
    totals = counts_dict(agg["cells"], len(bdd.CELL_KEYS))
    assert totals["reg"] == int(ref["registration_signal"].sum()) > 0


def test_payload_json_shape_and_size():
    frames = {"stroke": make_frame(), "neurology": make_frame(80).drop(columns=LEGACY_DROP)}
    aggs = [bdd.aggregate_discipline(df, d) for d, df in frames.items()]
    payload = bdd.assemble_payload(aggs, run_date="2026-10-06")
    text = json.dumps(payload, separators=(",", ":"))
    assert len(text) < 200_000
    assert payload["count_keys"] == bdd.COUNT_KEYS
    assert [d["key"] for d in payload["disciplines"]] == ["stroke", "neurology"]
    assert payload["disciplines"][0]["color"] == "#2a78d6" and payload["disciplines"][1]["color"] == "#eb6834"
    assert payload["years"] == [2019, 2020, 2021, 2022]
    assert payload["partial_years"] == []
    assert payload["high_impact"]["settings"]["impact_factor_threshold"] == 10.0
    assert {m["key"] for m in payload["metrics"]} >= {"oa", "data", "code", "preprint", "reg"}
    assert len(payload["methods_notes"]) >= 5
    assert payload["citation"].get("repository-code", "").startswith("https://github.com/")
    # every discipline carries the per-dataset availability flags the page uses to hide charts
    assert set(payload["disciplines"][1]["available"]) == set(payload["disciplines"][0]["available"])
    # size budget for the real build: per-cell row is a short int list
    row_bytes = len(json.dumps(payload["disciplines"][0]["cells"][0], separators=(",", ":")))
    assert row_bytes < 120


def test_partial_years_follow_run_date():
    agg = bdd.aggregate_discipline(make_frame(), "stroke")
    payload = bdd.assemble_payload([agg], run_date="2022-03-01")
    assert payload["partial_years"] == [2021, 2022]
    assert "2021, 2022 are incomplete" in payload["methods_notes"][3]


def test_enrichment_join_fills_missing_columns_and_corpus_flag(tmp_path):
    df = make_frame(40).drop(columns=["oa_status", "first_author_country", "funders", "has_preprint_version",
                                      "in_article_corpus"])
    meta = pd.DataFrame({
        "doi_norm": [f"10.1000/{i}" for i in range(40)],
        "openalex_id": [f"W{i}" for i in range(40)],
        "work_type": ["article" if i % 10 else "dataset" for i in range(40)],
        "oa_status": ["gold" if i % 2 else "closed" for i in range(40)],
        "primary_source_type": ["journal" if i % 10 else "repository" for i in range(40)],
        "has_preprint_version": [i % 3 == 0 for i in range(40)],
        "first_author_country": ["US"] * 40,
        "funders": ["NIH"] * 40,
    })
    path = tmp_path / "stroke_work_metadata.csv"
    meta.to_csv(path, index=False)
    out = bdd.prepare_frame(df, "stroke", enrichment_dir=tmp_path)
    assert out["oa_status"].eq("gold").sum() == 20
    assert out["first_author_country"].eq("US").all()
    assert "in_article_corpus" in out.columns
    assert int(out["in_article_corpus"].sum()) == 36       # 4 datasets excluded
    agg = bdd.aggregate_discipline(out, "stroke")
    assert agg["available"]["oa_status"] and agg["available"]["country"] and agg["available"]["funders"]
    assert agg["totals"]["in_corpus"] == 36


def test_enrichment_join_does_not_overwrite_existing_values(tmp_path):
    df = make_frame(10)
    df["oa_status"] = ["" if i % 2 else "green" for i in range(10)]
    df = df.drop(columns=["in_article_corpus"])
    meta = pd.DataFrame({"doi_norm": [f"10.1000/{i}" for i in range(10)], "oa_status": ["gold"] * 10,
                         "work_type": ["article"] * 10, "primary_source_type": ["journal"] * 10})
    meta.to_csv(tmp_path / "stroke_work_metadata.csv", index=False)
    out = bdd.apply_enrichment_metadata(df, tmp_path / "stroke_work_metadata.csv")
    assert out["oa_status"].tolist() == ["green" if i % 2 == 0 else "gold" for i in range(10)]


def test_copy_site_bundles_static_assets(tmp_path):
    payload = bdd.assemble_payload([bdd.aggregate_discipline(make_frame(), "stroke")], run_date="2026-10-06")
    json_path = tmp_path / "dashboard_data.json"
    bdd.write_payload(payload, json_path)
    site = tmp_path / "site"
    copied = bdd.copy_site(json_path, site)
    names = sorted(p.name for p in copied)
    assert names == ["app.js", "dashboard_data.json", "index.html", "styles.css"]
    html = (site / "index.html").read_text(encoding="utf-8")
    assert 'src="app.js"' in html and 'href="styles.css"' in html
    assert "dashboard_data.json" in (site / "app.js").read_text(encoding="utf-8")
