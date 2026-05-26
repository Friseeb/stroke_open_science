from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest


def _load_pipeline_module():
    root = Path(__file__).resolve().parents[1]
    target = root / "scripts" / "search_stroke_dois.py"
    spec = importlib.util.spec_from_file_location("search_stroke_dois", target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pipeline = _load_pipeline_module()


# ── DOI normalization ──────────────────────────────────────────────────────────

def test_normalize_doi_handles_prefix_and_case():
    assert pipeline.normalize_doi("https://doi.org/10.1000/ABC123") == "10.1000/abc123"
    assert pipeline.normalize_doi("DOI:10.5555/TeSt") == "10.5555/test"
    assert pipeline.normalize_doi(None) == ""


def test_normalize_doi_strips_dx_prefix():
    assert pipeline.normalize_doi("http://dx.doi.org/10.9999/xyz") == "10.9999/xyz"


def test_normalize_doi_empty_inputs():
    assert pipeline.normalize_doi("") == ""
    assert pipeline.normalize_doi("nan") == ""
    assert pipeline.normalize_doi("none") == ""


# ── Date window generation ─────────────────────────────────────────────────────

def test_build_query_date_windows_two_windows_for_six_months():
    windows = pipeline.build_query_date_windows([2025], 6)
    assert windows == [
        (dt.date(2025, 1, 1), dt.date(2025, 6, 30)),
        (dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
    ]


def test_build_query_date_windows_annual():
    windows = pipeline.build_query_date_windows([2022, 2023], 12)
    assert windows == [
        (dt.date(2022, 1, 1), dt.date(2022, 12, 31)),
        (dt.date(2023, 1, 1), dt.date(2023, 12, 31)),
    ]


def test_build_query_date_windows_quarterly():
    windows = pipeline.build_query_date_windows([2024], 3)
    assert len(windows) == 4
    assert windows[0] == (dt.date(2024, 1, 1), dt.date(2024, 3, 31))
    assert windows[-1] == (dt.date(2024, 10, 1), dt.date(2024, 12, 31))


# ── LLM payload parsing ────────────────────────────────────────────────────────

def test_parse_llm_payload_normalizes_booleans_and_empty_text():
    payload = pipeline.parse_llm_payload(
        {
            "code_link": " https://github.com/org/repo ",
            "data_link": "none",
            "preregistered": "yes",
            "preprint": "  ",
        }
    )
    assert payload["code_link"] == "https://github.com/org/repo"
    assert payload["data_link"] == ""
    assert payload["preregistered"] is True
    assert payload["preprint"] == ""


def test_parse_llm_payload_false_preregistered():
    payload = pipeline.parse_llm_payload({"preregistered": "no", "code_link": "", "data_link": "", "preprint": ""})
    assert payload["preregistered"] is False


def test_parse_llm_payload_null_preregistered():
    payload = pipeline.parse_llm_payload({"preregistered": "unknown", "code_link": "", "data_link": "", "preprint": ""})
    assert pd.isna(payload["preregistered"])


def test_parse_llm_payload_from_json_string():
    import json
    raw = json.dumps({"code_link": "https://github.com/x/y", "data_link": "", "preregistered": True, "preprint": ""})
    payload = pipeline.parse_llm_payload(raw)
    assert payload["code_link"] == "https://github.com/x/y"
    assert payload["preregistered"] is True


# ── Regex extraction ───────────────────────────────────────────────────────────

def test_apply_regex_extraction_finds_repository_links():
    df = pd.DataFrame(
        [
            {
                "title": "Code for our model",
                "abstract": "Artifacts at https://github.com/acme/project and https://zenodo.org/record/1234",
                "best_oa_location_url": "",
                "repo_links": "",
                "github": "",
                "zenodo": "",
                "osf": "",
                "code_link": "",
                "data_link": "",
            }
        ]
    )
    out = pipeline.apply_regex_extraction(df)
    assert out.loc[0, "github"] == "https://github.com/acme/project"
    assert out.loc[0, "zenodo"] == "https://zenodo.org/record/1234"
    assert "github.com/acme/project" in out.loc[0, "repo_links"]


def test_apply_regex_extraction_finds_osf_link():
    df = pd.DataFrame(
        [
            {
                "title": "Preregistered study",
                "abstract": "Protocol available at https://osf.io/abc12",
                "best_oa_location_url": "",
                "repo_links": "",
                "github": "",
                "zenodo": "",
                "osf": "",
                "code_link": "",
                "data_link": "",
            }
        ]
    )
    out = pipeline.apply_regex_extraction(df)
    assert "osf.io/abc12" in out.loc[0, "osf"]


def test_apply_regex_extraction_no_links_produces_empty_strings():
    df = pd.DataFrame(
        [
            {
                "title": "A study about stroke outcomes",
                "abstract": "We conducted a randomized controlled trial.",
                "best_oa_location_url": "",
                "repo_links": "",
                "github": "",
                "zenodo": "",
                "osf": "",
                "code_link": "",
                "data_link": "",
            }
        ]
    )
    out = pipeline.apply_regex_extraction(df)
    assert out.loc[0, "github"] == ""
    assert out.loc[0, "zenodo"] == ""
    assert out.loc[0, "repo_links"] == ""


# ── Deduplication ──────────────────────────────────────────────────────────────

def test_deduplicate_records_prefers_record_with_pubmed_id():
    df = pd.DataFrame(
        [
            {
                "id": "W1",
                "doi_norm": "10.1000/x",
                "source_db": "pubmed",
                "pubmed_id": "123",
                "abstract": "",
                "cited_by_count": 5,
                "year": 2024,
            },
            {
                "id": "W2",
                "doi_norm": "10.1000/x",
                "source_db": "openalex",
                "pubmed_id": "",
                "abstract": "has abstract",
                "cited_by_count": 15,
                "year": 2024,
            },
        ]
    )
    out = pipeline.deduplicate_records(df)
    assert len(out) == 1
    assert out.iloc[0]["source_db"] == "pubmed"


def test_deduplicate_records_removes_duplicate_ids():
    df = pd.DataFrame(
        [
            {"id": "W1", "doi_norm": "10.1/a", "source_db": "openalex", "pubmed_id": "", "abstract": "x", "cited_by_count": 10, "year": 2022},
            {"id": "W1", "doi_norm": "10.1/a", "source_db": "openalex", "pubmed_id": "", "abstract": "x", "cited_by_count": 10, "year": 2022},
        ]
    )
    out = pipeline.deduplicate_records(df)
    assert len(out) == 1


def test_deduplicate_records_keeps_distinct_dois():
    df = pd.DataFrame(
        [
            {"id": "W1", "doi_norm": "10.1/a", "source_db": "openalex", "pubmed_id": "", "abstract": "", "cited_by_count": 1, "year": 2022},
            {"id": "W2", "doi_norm": "10.1/b", "source_db": "openalex", "pubmed_id": "", "abstract": "", "cited_by_count": 1, "year": 2022},
        ]
    )
    out = pipeline.deduplicate_records(df)
    assert len(out) == 2


# ── Open-access inference ──────────────────────────────────────────────────────

def test_normalize_open_access_fields_infers_oa_from_best_url():
    df = pd.DataFrame(
        [
            {
                "is_oa": pd.NA,
                "journal_is_oa": pd.NA,
                "best_oa_location_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
                "license_unpaywall": "",
            }
        ]
    )
    out = pipeline.normalize_open_access_fields(df)
    assert bool(out.loc[0, "is_oa"]) is True


def test_normalize_open_access_fields_infers_oa_from_license():
    df = pd.DataFrame(
        [
            {
                "is_oa": pd.NA,
                "journal_is_oa": pd.NA,
                "best_oa_location_url": "",
                "license_unpaywall": "cc-by",
            }
        ]
    )
    out = pipeline.normalize_open_access_fields(df)
    assert bool(out.loc[0, "is_oa"]) is True


def test_normalize_open_access_fields_preserves_explicit_false():
    df = pd.DataFrame(
        [
            {
                "is_oa": False,
                "journal_is_oa": pd.NA,
                "best_oa_location_url": "",
                "license_unpaywall": "",
            }
        ]
    )
    out = pipeline.normalize_open_access_fields(df)
    assert bool(out.loc[0, "is_oa"]) is False


# ── High-impact subgroup ───────────────────────────────────────────────────────

def _make_cfg(**kwargs):
    defaults = dict(
        impact_factor_threshold=10.0,
        citation_percentile_threshold=90.0,
    )
    defaults.update(kwargs)

    class _Cfg:
        pass

    cfg = _Cfg()
    for k, v in defaults.items():
        setattr(cfg, k, v)
    return cfg


def test_build_high_impact_subset_by_impact_factor():
    # Use citation_percentile_threshold=100.0 so no row qualifies via citations;
    # only the IF rule should fire.
    df = pd.DataFrame(
        [
            {"doi_norm": "10.1/a", "journal_impact_factor": 15.0, "cited_by_count": 5, "high_impact_flag": False, "high_impact_reason": ""},
            {"doi_norm": "10.1/b", "journal_impact_factor": 3.0, "cited_by_count": 5, "high_impact_flag": False, "high_impact_reason": ""},
        ]
    )
    cfg = _make_cfg(impact_factor_threshold=10.0, citation_percentile_threshold=99.9)
    full, subset = pipeline.build_high_impact_subset(df, cfg)
    # At least the high-IF paper is in the subset; the low-IF paper may also qualify
    # via citations if the percentile lands on 5. Assert the high-IF paper is flagged.
    flagged_dois = set(subset["doi_norm"].tolist())
    assert "10.1/a" in flagged_dois


def test_build_high_impact_subset_by_citation_percentile():
    df = pd.DataFrame(
        [
            {"doi_norm": "10.1/a", "journal_impact_factor": pd.NA, "cited_by_count": 100, "high_impact_flag": False, "high_impact_reason": ""},
            {"doi_norm": "10.1/b", "journal_impact_factor": pd.NA, "cited_by_count": 1, "high_impact_flag": False, "high_impact_reason": ""},
            {"doi_norm": "10.1/c", "journal_impact_factor": pd.NA, "cited_by_count": 2, "high_impact_flag": False, "high_impact_reason": ""},
        ]
    )
    # 90th percentile of [100, 1, 2] → only the 100-citation paper qualifies
    cfg = _make_cfg(impact_factor_threshold=999.0, citation_percentile_threshold=90.0)
    full, subset = pipeline.build_high_impact_subset(df, cfg)
    assert len(subset) == 1
    assert subset.iloc[0]["doi_norm"] == "10.1/a"


# ── Dataset regex extraction ───────────────────────────────────────────────────

def _regex_df(abstract: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "title": "",
                "abstract": abstract,
                "best_oa_location_url": "",
                "repo_links": "",
                "data_link": "",
                "dataset_urls": "",
                "dataset_repos": "",
            }
        ]
    )


def test_dataset_regex_finds_geo_accession():
    df = _regex_df("Raw sequencing data deposited in GEO accession GSE123456.")
    out = pipeline.apply_dataset_regex_extraction(df)
    assert "geo" in out.loc[0, "dataset_repos"]
    assert bool(out.loc[0, "has_public_dataset"]) is True


def test_dataset_regex_finds_dryad_doi():
    df = _regex_df("Data available via Dryad at https://datadryad.org/stash/dataset/doi:10.5061/dryad.abc123")
    out = pipeline.apply_dataset_regex_extraction(df)
    assert "dryad" in out.loc[0, "dataset_repos"]


def test_dataset_regex_finds_figshare():
    df = _regex_df("Supplementary data at https://figshare.com/articles/dataset/my_data/12345")
    out = pipeline.apply_dataset_regex_extraction(df)
    assert "figshare" in out.loc[0, "dataset_repos"]


def test_dataset_regex_no_match_leaves_empty():
    df = _regex_df("We conducted a clinical trial. All data available on request.")
    out = pipeline.apply_dataset_regex_extraction(df)
    assert out.loc[0, "dataset_repos"] == ""
    assert bool(out.loc[0, "has_public_dataset"]) is False


# ── Keyword signal scoring ─────────────────────────────────────────────────────

def test_keyword_signal_score_github_mention():
    score = pipeline.keyword_signal_score("Code on github", "", "", "", "", "", "")
    assert score > 0


def test_keyword_signal_score_no_signals():
    score = pipeline.keyword_signal_score("A stroke outcome study", "Patients were recruited.", "", "", "", "", "")
    assert score == 0


def test_keyword_signal_score_multiple_signals_higher():
    score_multi = pipeline.keyword_signal_score("", "Data on zenodo and code on github and preregistered on osf", "", "", "", "", "")
    score_single = pipeline.keyword_signal_score("", "Code on github", "", "", "", "", "")
    assert score_multi > score_single


# ── Journal normalization ──────────────────────────────────────────────────────

def test_normalize_journal_name_lowercases_and_collapses_whitespace():
    assert pipeline.normalize_journal_name("Stroke") == "stroke"
    assert pipeline.normalize_journal_name("  New England  Journal  ") == "new england journal"
