"""Pure-logic tests for build_discipline_dashboard.py (no Plotly rendering, no network)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest


def _load_dashboard_module():
    existing = sys.modules.get("build_discipline_dashboard")
    if existing is not None:
        return existing
    root = Path(__file__).resolve().parents[1]
    target = root / "scripts" / "build_discipline_dashboard.py"
    spec = importlib.util.spec_from_file_location("build_discipline_dashboard", target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dash = _load_dashboard_module()


def _rows(n: int, year: int, in_corpus: bool = True, **extra):
    base = {
        "doi": "10.1/x", "year": year, "discipline": "stroke", "is_oa": True, "journal": "Stroke",
        "work_type": "article" if in_corpus else "dataset", "primary_source_type": "journal" if in_corpus else "repository",
        "in_article_corpus": in_corpus, "registration_signal": False, "preregistered": pd.NA,
        "has_preprint_version": False, "preprint": "", "github": "", "zenodo": "", "osf": "", "repo_links": "",
        "code_link": "", "data_link": "", "dataset_urls": "", "has_public_dataset": False, "cited_by_count": 1,
        "high_impact_flag": False, "high_impact_reason": "", "oa_status": "gold", "das_available": False, "das_primary": "",
    }
    base.update(extra)
    return [dict(base) for _ in range(n)]


def test_composite_weights_do_not_double_count_github_or_dataset():
    assert "github_rate" not in dash.COMPOSITE_WEIGHTS
    assert "dataset_rate" not in dash.COMPOSITE_WEIGHTS
    assert "open_material_rate" in dash.COMPOSITE_WEIGHTS
    assert sum(dash.COMPOSITE_WEIGHTS.values()) == pytest.approx(1.0)


def test_composite_index_renormalises_over_available_metrics():
    full = dash.composite_index_from_rates({"oa_rate": 0.5, "open_material_rate": 0.1, "registration_rate": 0.2, "preprint_rate": 0.0})
    w = dash.COMPOSITE_WEIGHTS
    expected = (0.5 * w["oa_rate"] + 0.1 * w["open_material_rate"] + 0.2 * w["registration_rate"]) / sum(w.values()) * 100
    assert full == pytest.approx(expected, abs=0.01)
    # missing registration -> falls back to the LLM preregistered rate
    fb = dash.composite_index_from_rates({"oa_rate": 0.5, "open_material_rate": 0.1, "registration_rate": pd.NA, "preregistered_rate": 0.2, "preprint_rate": 0.0})
    assert fb == pytest.approx(full, abs=0.01)
    # nothing but OA -> the index is the OA rate itself (weights renormalised to 1)
    assert dash.composite_index_from_rates({"oa_rate": 0.42}) == pytest.approx(42.0)
    assert pd.isna(dash.composite_index_from_rates({}))


def test_composite_description_is_generated_from_weights():
    text = dash.composite_description()
    for col, weight in dash.COMPOSITE_WEIGHTS.items():
        assert f"({weight:.0%})" in text
    assert "renormalised" in text


def test_high_impact_description_from_inferred_settings():
    df = pd.DataFrame({"high_impact_reason": ["", "impact_factor>=10", "cited_by_count>=57 (top 10.0%)", "impact_factor>=10; cited_by_count>=57 (top 10.0%)"]})
    settings = dash.infer_high_impact_settings(df)
    assert settings == {"impact_factor_threshold": 10.0, "citation_percentile_threshold": 90.0}
    text = dash.high_impact_description(settings)
    assert "IF ≥ 10" in text
    assert "90th percentile" in text
    assert "pooled across all years" in text
    assert "discipline-year" not in text


def test_prepare_panel_filters_to_article_corpus_and_adds_new_rates():
    rows = _rows(6, 2020) + _rows(4, 2020, in_corpus=False, oa_status="closed") + _rows(10, 2021, registration_signal=True, has_preprint_version=True, oa_status="hybrid")
    rows[0]["das_available"], rows[0]["das_primary"] = True, "repository"
    rows[1]["das_available"], rows[1]["das_primary"] = True, "on_request"
    dash.CORPUS_FILTER_STATS.clear()
    panel = dash.prepare_discipline_panel(pd.DataFrame(rows), "stroke")
    by_year = panel.set_index("year")
    assert by_year.loc[2020, "papers"] == 6, "dataset rows are excluded from the corpus"
    assert dash.CORPUS_FILTER_STATS["stroke"] == {"kept": 16, "dropped": 4}
    assert by_year.loc[2021, "registration_rate"] == pytest.approx(1.0)
    assert by_year.loc[2020, "registration_rate"] == pytest.approx(0.0)
    assert by_year.loc[2021, "preprint_rate"] == pytest.approx(1.0), "preprint_rate comes from the metadata flag"
    assert by_year.loc[2020, "oa_status_gold_count"] == 6 and by_year.loc[2020, "oa_status_closed_count"] == 0
    assert by_year.loc[2021, "oa_status_hybrid_count"] == 10
    assert by_year.loc[2020, "das_audited"] == 2
    assert by_year.loc[2020, "das_repository_count"] == 1 and by_year.loc[2020, "das_on_request_count"] == 1
    assert 0 <= by_year.loc[2021, "composite_index"] <= 100

    overall = dash.build_overall_summary(panel)
    row = overall.iloc[0]
    assert row["papers"] == 16
    assert row["oa_status_known"] == 16
    assert row["oa_status_hybrid_share"] == pytest.approx(10 / 16)
    assert row["das_audited"] == 2
    assert row["das_repository_share"] == pytest.approx(0.5)
    assert row["registration_rate"] == pytest.approx(10 / 16)


def test_prepare_panel_legacy_csv_without_new_columns():
    rows = [
        {"doi": "10.1/x", "year": 2020, "is_oa": True, "journal": "Stroke", "preprint": "https://medrxiv.org/a",
         "github": "", "zenodo": "", "osf": "", "repo_links": "", "code_link": "", "data_link": "", "dataset_urls": "",
         "has_public_dataset": False, "preregistered": True, "cited_by_count": 3, "high_impact_flag": False},
        {"doi": "10.1/y", "year": 2020, "is_oa": False, "journal": "Stroke", "preprint": "",
         "github": "", "zenodo": "", "osf": "", "repo_links": "", "code_link": "", "data_link": "", "dataset_urls": "",
         "has_public_dataset": False, "preregistered": pd.NA, "cited_by_count": 0, "high_impact_flag": False},
    ]
    dash.CORPUS_FILTER_STATS.clear()
    panel = dash.prepare_discipline_panel(pd.DataFrame(rows), "stroke")
    assert panel["papers"].iloc[0] == 2, "no in_article_corpus column -> no filtering"
    assert "stroke" not in dash.CORPUS_FILTER_STATS
    assert pd.isna(panel["registration_rate"].iloc[0])
    assert panel["preprint_rate"].iloc[0] == pytest.approx(0.5), "falls back to the preprint text field"
    assert panel["oa_status_known"].iloc[0] == 0 and panel["das_audited"].iloc[0] == 0
    # composite falls back to the LLM preregistered rate and renormalises
    expected = dash.composite_index_from_rates({"oa_rate": 0.5, "open_material_rate": 0.0, "preregistered_rate": 0.5, "preprint_rate": 0.5})
    assert panel["composite_index"].iloc[0] == pytest.approx(expected)


def test_overall_summary_keeps_unavailable_rate_na_for_legacy_input():
    rows = [
        {"doi": "10.1/x", "year": 2020, "is_oa": True, "journal": "Stroke", "preprint": "", "github": "", "zenodo": "",
         "osf": "", "repo_links": "", "code_link": "", "data_link": "", "dataset_urls": "", "has_public_dataset": False,
         "preregistered": True, "cited_by_count": 3, "high_impact_flag": False},
        {"doi": "10.1/y", "year": 2021, "is_oa": False, "journal": "Stroke", "preprint": "", "github": "", "zenodo": "",
         "osf": "", "repo_links": "", "code_link": "", "data_link": "", "dataset_urls": "", "has_public_dataset": False,
         "preregistered": False, "cited_by_count": 0, "high_impact_flag": False},
    ]
    panel = dash.prepare_discipline_panel(pd.DataFrame(rows), "stroke")
    overall = dash.build_overall_summary(panel)
    assert pd.isna(overall["registration_rate"].iloc[0])
    assert overall["oa_rate"].iloc[0] == pytest.approx(0.5)
    assert overall["preregistered_rate"].iloc[0] == pytest.approx(0.5)
    expected = dash.composite_index_from_rates({"oa_rate": 0.5, "open_material_rate": 0.0, "preregistered_rate": 0.5, "preprint_rate": 0.0})
    assert overall["composite_index"].iloc[0] == pytest.approx(expected)
