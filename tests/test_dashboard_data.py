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
            "das_mentions_github": (i % 8 == 0 and i % 3 == 0) or (i % 7 == 0),  # the i%7 case is never audited
            "das_mentions_trial_registration": i % 8 == 0 and i % 2 == 0,
            "das_mentions_supplement": pd.NA if i % 8 else True,
            "first_author_income_group": ["high", "upper_middle", "", "lower_middle", "low"][i % 5] if i % 19 else "",
            "institutions": ["Western University|Charité", "Western University", "", "MIT|Western University"][i % 4],
        })
    return pd.DataFrame(rows)


LEGACY_DROP = ["oa_status", "first_author_country", "funders", "registration_signal", "in_article_corpus",
               "das_available", "das_has_statement", "das_primary", "has_preprint_version", "abstract", "title",
               "das_mentions_github", "das_mentions_trial_registration", "das_mentions_supplement",
               "first_author_income_group", "institutions"]


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
    assert totals["oa"] == int(dash.derive_open_access(ref).sum())
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
    ref["oa_bool"] = dash.derive_open_access(ref)
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
    # default filter ends at the last complete year (run year - 1); the run year stays selectable
    assert payload["default_year_range"] == [2019, 2021]
    assert payload["years"] == [2019, 2020, 2021, 2022]
    later = bdd.assemble_payload([agg], run_date="2026-06-01")
    assert later["partial_years"] == [] and later["default_year_range"] == [2019, 2022]


# ---------------------------------------------------------------------------
# One OA definition
# ---------------------------------------------------------------------------

def test_derive_open_access_prefers_oa_status_and_falls_back():
    df = pd.DataFrame({
        "oa_status": ["gold", "closed", "Hybrid", "", None, "closed", "green", "nan"],
        "is_oa": [False, True, False, True, False, True, False, False],
        "license_unpaywall": ["", "cc-by", "", "", "", "", "", "cc-by"],
    })
    out = dash.derive_open_access(df)
    assert out.dtype == bool
    # known oa_status wins (even when the legacy signals disagree); unknown -> legacy inference
    assert out.tolist() == [True, False, True, True, False, False, True, True]
    # no oa_status column at all -> pure legacy inference
    legacy = df.drop(columns=["oa_status"])
    assert dash.derive_open_access(legacy).tolist() == dash.infer_oa_series(legacy).tolist()


def test_dashboard_json_oa_counts_match_helper():
    df = make_frame(150)
    agg = bdd.aggregate_discipline(df, "stroke")
    payload = json.loads(json.dumps(bdd.assemble_payload([agg], run_date="2023-01-01")))
    off = len(bdd.CELL_KEYS)
    K = {k: i for i, k in enumerate(bdd.COUNT_KEYS)}
    cells = payload["disciplines"][0]["cells"]
    ref = corpus(df)
    oa_expected = dash.derive_open_access(ref)
    assert sum(r[off + K["oa"]] for r in cells) == int(oa_expected.sum())
    # per year as well, and the OA count equals n - closed wherever oa_status is known
    for year in sorted(ref["year"].unique()):
        rows = [r for r in cells if r[0] == year]
        sub = ref[ref["year"] == year]
        assert sum(r[off + K["oa"]] for r in rows) == int(oa_expected[sub.index].sum())
    known = ref["oa_status"].fillna("").ne("")
    n_known = int(known.sum())
    closed_known = int((ref.loc[known, "oa_status"] == "closed").sum())
    assert int(oa_expected[known].sum()) == n_known - closed_known
    assert "oa_status" in payload["metrics"][0]["definition"]


def test_no_doi_conference_abstract_excluded_from_site_corpus(tmp_path):
    """Release rows without a DOI never match the DOI-keyed enrichment CSV; they must be out of corpus and
    not counted as closed journal articles."""
    df = make_frame(30).drop(columns=["oa_status", "first_author_country", "funders", "has_preprint_version",
                                      "in_article_corpus"])
    abstracts = pd.DataFrame([{"doi": "", "title": f"Abstract WP{i}: ISC poster", "journal": "Stroke",
                               "journal_norm": "stroke", "year": 2020, "is_oa": False, "abstract": ""}
                              for i in range(12)])
    df = pd.concat([df, abstracts], ignore_index=True)
    meta = pd.DataFrame({
        "doi_norm": [f"10.1000/{i}" for i in range(30)], "openalex_id": [f"W{i}" for i in range(30)],
        "work_type": ["article"] * 30, "primary_source_type": ["journal"] * 30,
        "oa_status": ["gold" if i % 2 else "closed" for i in range(30)],
    })
    meta.to_csv(tmp_path / "stroke_work_metadata.csv", index=False)
    out = bdd.prepare_frame(df, "stroke", enrichment_dir=tmp_path)
    assert int(out["in_article_corpus"].sum()) == 30
    assert not out.loc[out["doi"].fillna("").eq(""), "in_article_corpus"].any()
    agg = bdd.aggregate_discipline(out, "stroke")
    assert agg["totals"]["in_corpus"] == 30 and agg["totals"]["dropped"] == 12
    assert agg["corpus_rule"] == "in_article_corpus (openalex_type_doi_only)"
    off = len(bdd.CELL_KEYS)
    K = {k: i for i, k in enumerate(bdd.COUNT_KEYS)}
    assert sum(r[off + K["oa"]] for r in agg["cells"]) == 15
    assert sum(r[off + K["oa_closed"]] for r in agg["cells"]) == 15


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


# ---------------------------------------------------------------------------
# Schema v2: full-text flags, income groups, institutions
# ---------------------------------------------------------------------------

def test_fulltext_flags_count_only_audited_rows():
    df = make_frame()
    agg = bdd.aggregate_discipline(df, "stroke")
    c = counts_dict(agg["cells"], len(bdd.CELL_KEYS))
    ref = corpus(df)
    audited = dash.to_bool_series(ref["das_available"]) & ref["das_primary"].isin(bdd.DAS_ORDER)
    assert c["ft_github"] == int((audited & dash.to_bool_series(ref["das_mentions_github"])).sum())
    assert c["ft_reg"] == int((audited & dash.to_bool_series(ref["das_mentions_trial_registration"])).sum())
    assert c["ft_supp"] == int((audited & dash.to_bool_series(ref["das_mentions_supplement"])).sum())
    assert c["ft_github"] <= c["das_audited"] and c["ft_github"] > 0
    assert bdd.COUNT_KEYS[-3:] == bdd.FULLTEXT_KEYS


def test_income_cells_partition_the_corpus():
    df = make_frame()
    agg = bdd.aggregate_discipline(df, "stroke")
    assert agg["available"]["income"]
    assert agg["income_groups"] == bdd.INCOME_ORDER + [bdd.INCOME_UNKNOWN]
    width = len(bdd.INCOME_KEYS) + len(bdd.COUNT_KEYS)
    assert all(len(r) == width for r in agg["income_cells"])
    total_n = counts_dict(agg["cells"], len(bdd.CELL_KEYS))["n"]
    income_n = counts_dict(agg["income_cells"], len(bdd.INCOME_KEYS))["n"]
    assert income_n == total_n
    ref = corpus(df)
    hi_n = sum(r[len(bdd.INCOME_KEYS)] for r in agg["income_cells"] if r[2] == 0)
    assert hi_n == int(ref["first_author_income_group"].fillna("").eq("high").sum())


def test_institution_cells_are_multivalued_with_other_and_none():
    df = make_frame()
    agg = bdd.aggregate_discipline(df, "stroke", top_institutions=2)
    assert agg["available"]["institutions"]
    assert agg["institutions"][-2:] == [bdd.OTHER_LABEL, bdd.NO_INSTITUTION_LABEL]
    assert "Western University" in agg["institutions"]
    width = len(bdd.INSTITUTION_KEYS) + len(bdd.COUNT_KEYS)
    assert all(len(r) == width for r in agg["institution_cells"])
    ref = corpus(df)
    west_idx = agg["institutions"].index("Western University")
    west_n = sum(r[len(bdd.INSTITUTION_KEYS)] for r in agg["institution_cells"] if r[2] == west_idx)
    assert west_n == int(ref["institutions"].fillna("").str.contains("Western University").sum())
    none_idx = agg["institutions"].index(bdd.NO_INSTITUTION_LABEL)
    none_n = sum(r[len(bdd.INSTITUTION_KEYS)] for r in agg["institution_cells"] if r[2] == none_idx)
    assert none_n == int(ref["institutions"].fillna("").eq("").sum())


def test_legacy_frame_has_no_income_or_institutions():
    df = make_frame().drop(columns=LEGACY_DROP)
    agg = bdd.aggregate_discipline(df, "stroke")
    assert not agg["available"]["income"] and not agg["available"]["institutions"] and not agg["available"]["fulltext"]
    assert agg["income_cells"] == [] and agg["institution_cells"] == []
    c = counts_dict(agg["cells"], len(bdd.CELL_KEYS))
    assert c["ft_github"] == 0 and c["ft_reg"] == 0


def test_payload_v2_carries_new_keys():
    payload = bdd.assemble_payload([bdd.aggregate_discipline(make_frame(), "stroke")], run_date="2026-10-12")
    assert payload["schema_version"] == 2
    assert payload["income_order"] == bdd.INCOME_ORDER and payload["fulltext_keys"] == bdd.FULLTEXT_KEYS
    assert [s["key"] for s in payload["commitment_signals"]] == ["das_deposit", "ft_github", "ft_reg"]
    d = payload["disciplines"][0]
    assert d["income_cells"] and d["institution_cells"] and d["institutions"][-1] == bdd.NO_INSTITUTION_LABEL
    assert all(m.get("denominator", "n") in ("n", "n_abs", "das_audited") for m in payload["metrics"])
