from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pandas as pd


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


def test_normalize_doi_handles_prefix_and_case():
    assert pipeline.normalize_doi("https://doi.org/10.1000/ABC123") == "10.1000/abc123"
    assert pipeline.normalize_doi("DOI:10.5555/TeSt") == "10.5555/test"
    assert pipeline.normalize_doi(None) == ""


def test_build_query_date_windows_two_windows_for_six_months():
    windows = pipeline.build_query_date_windows([2025], 6)
    assert windows == [
        (dt.date(2025, 1, 1), dt.date(2025, 6, 30)),
        (dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
    ]


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
