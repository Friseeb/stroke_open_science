"""Unit tests for OpenAlex work metadata, registration / corpus flags and the DAS audit helpers.

No network: fixtures are plain dicts and small JATS snippets.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import pytest


def _load_pipeline_module():
    existing = sys.modules.get("search_stroke_dois")
    if existing is not None:
        return existing
    root = Path(__file__).resolve().parents[1]
    target = root / "scripts" / "search_stroke_dois.py"
    spec = importlib.util.spec_from_file_location("search_stroke_dois", target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pipeline = _load_pipeline_module()


# ── fixtures ───────────────────────────────────────────────────────────────────

def _journal_source(name: str = "Stroke", in_doaj: bool = False) -> Dict[str, Any]:
    return {"id": "https://openalex.org/S1", "display_name": name, "type": "journal", "is_in_doaj": in_doaj, "is_oa": False}


def _repository_source(name: str) -> Dict[str, Any]:
    return {"id": "https://openalex.org/S2", "display_name": name, "type": "repository", "is_in_doaj": False}


@pytest.fixture
def article_work() -> Dict[str, Any]:
    return {
        "id": "https://openalex.org/W123",
        "doi": "https://doi.org/10.1161/STROKEAHA.120.030335",
        "title": "Thrombectomy outcomes",
        "publication_year": 2020,
        "type": "article",
        "open_access": {"is_oa": True, "oa_status": "green", "oa_url": "https://europepmc.org/x"},
        "primary_location": {"source": _journal_source("Stroke"), "version": "publishedVersion", "license": None},
        "locations": [
            {"source": _journal_source("Stroke"), "version": "publishedVersion"},
            {"source": _repository_source("medRxiv (Cold Spring Harbor Laboratory)"), "version": "submittedVersion"},
            {"source": _repository_source("Europe PMC (PubMed Central)"), "version": "acceptedVersion"},
        ],
        "authorships": [
            {"author": {"display_name": "A One"}, "countries": ["CA", "US"], "institutions": []},
            {"author": {"display_name": "B Two"}, "countries": ["DE"], "institutions": []},
            {"author": {"display_name": "C Three"}, "countries": [], "institutions": []},
        ],
        "is_retracted": False,
        "has_fulltext": True,
        "funders": [{"id": "F1", "display_name": "Heart and Stroke Foundation of Canada"}, {"id": "F2", "display_name": "CIHR"}],
        "cited_by_count": 12,
        "abstract_inverted_index": {"Background": [0], "matters": [1]},
    }


# ── openalex_work_to_record: new metadata columns ──────────────────────────────

def test_openalex_work_to_record_emits_metadata_columns(article_work):
    rec = pipeline.openalex_work_to_record(article_work, term="stroke", discipline="stroke")
    # existing columns unchanged
    assert rec["doi"] == "10.1161/strokeaha.120.030335"
    assert rec["journal"] == "Stroke"
    assert rec["is_oa"] is True
    assert rec["abstract"] == "Background matters"
    # new flat columns
    assert rec["work_type"] == "article"
    assert rec["oa_status"] == "green"
    assert rec["primary_source_type"] == "journal"
    assert rec["primary_source_is_in_doaj"] is False
    assert rec["has_preprint_version"] is True
    assert rec["is_preprint_record"] is False
    assert rec["preprint_servers"] == "medRxiv (Cold Spring Harbor Laboratory)"
    assert rec["first_author_country"] == "CA"
    assert rec["countries"] == "CA|DE|US"
    assert rec["funders"] == "Heart and Stroke Foundation of Canada|CIHR"
    assert rec["is_retracted"] is False
    assert rec["has_fulltext"] is True
    for col in pipeline.OPENALEX_METADATA_COLS:
        assert col in rec


def test_openalex_work_to_record_preprint_record_is_not_a_preprint_version(article_work):
    work = dict(article_work)
    work["type"] = "preprint"
    work["primary_location"] = {"source": _repository_source("medRxiv (Cold Spring Harbor Laboratory)")}
    rec = pipeline.openalex_work_to_record(work, term="stroke", discipline="stroke")
    assert rec["is_preprint_record"] is True
    assert rec["has_preprint_version"] is False
    assert rec["primary_source_type"] == "repository"


def test_openalex_work_to_record_repository_primary_source_counts_as_preprint_record(article_work):
    work = dict(article_work)
    work["type"] = "article"  # OpenAlex sometimes types preprints as articles
    work["primary_location"] = {"source": _repository_source("Research Square (Research Square)")}
    rec = pipeline.openalex_work_to_record(work, term="stroke", discipline="stroke")
    assert rec["is_preprint_record"] is True


def test_openalex_work_to_record_handles_minimal_work():
    rec = pipeline.openalex_work_to_record({"id": "W1", "doi": "10.1/x", "title": "t"}, term="stroke", discipline="stroke")
    assert rec["work_type"] == ""
    assert rec["oa_status"] == ""
    assert rec["has_preprint_version"] is False
    assert rec["is_preprint_record"] is False
    assert rec["preprint_servers"] == ""
    assert rec["countries"] == ""
    assert rec["funders"] == ""
    assert rec["primary_source_is_in_doaj"] is None


def test_metadata_select_fields_include_required_names():
    for name in ("type", "locations", "is_retracted", "has_fulltext", "funders", "open_access", "authorships"):
        assert name in pipeline.OPENALEX_WORK_SELECT_FIELDS.split(",")
        assert name in pipeline.OPENALEX_METADATA_SELECT_FIELDS.split(",")
    assert "grants" not in pipeline.OPENALEX_WORK_SELECT_FIELDS.split(",")


def test_standardize_dataframe_adds_metadata_columns_for_legacy_rows():
    df = pd.DataFrame([{"doi": "10.1/x", "title": "legacy row", "journal": "Stroke"}])
    out = pipeline.standardize_dataframe(df)
    assert out.loc[0, "work_type"] == ""
    assert pd.isna(out.loc[0, "has_preprint_version"])
    assert str(out["has_preprint_version"].dtype) == "boolean"
