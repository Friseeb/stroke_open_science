"""Unit tests for OpenAlex work metadata, registration / corpus flags and the DAS audit helpers.

No network: fixtures are plain dicts and small JATS snippets.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List

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


# ── OpenAlex metadata backfill (batched DOI lookups, resumable cache) ──────────

class FakeResponse:
    def __init__(self, status_code: int, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        if not self._responses:
            raise AssertionError("FakeSession ran out of scripted responses")
        return self._responses.pop(0)


@pytest.fixture
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: slept.append(s))
    return slept


def _meta_work(doi: str, work_type: str = "article", oa_status: str = "gold", preprint: bool = False) -> Dict[str, Any]:
    locations = [{"source": _journal_source("J")}]
    if preprint:
        locations.append({"source": _repository_source("medRxiv (Cold Spring Harbor Laboratory)")})
    return {
        "id": f"https://openalex.org/W-{doi}",
        "doi": f"https://doi.org/{doi}",
        "type": work_type,
        "open_access": {"oa_status": oa_status},
        "primary_location": {"source": _journal_source("J")},
        "locations": locations,
        "authorships": [{"countries": ["GB"]}],
        "funders": [],
    }


def _cfg(tmp_path: Path, **overrides) -> Any:
    import dataclasses

    fields = {f.name: None for f in dataclasses.fields(pipeline.PipelineConfig)}
    fields.update(
        discipline="stroke", terms=["stroke"], years=[2020], query_window_months=12, include_pubmed=False,
        pubmed_email="", pubmed_api_key="", pubmed_tool="t", pubmed_delay_seconds=0, pubmed_timeout_seconds=5,
        pubmed_max_attempts=1, pubmed_batch_size=1, openalex_mailto="me@example.org", openalex_api_key="secret-key",
        openalex_workers=1, openalex_delay_seconds=0.0, openalex_timeout_seconds=5, openalex_max_attempts=2,
        openalex_max_failures_per_query=2, openalex_max_retry_after_seconds=5, max_per_query=0,
        refresh_openalex=False, force=False, unpaywall_snapshot="", crossref_relations="", disable_api_enrich=True,
        disable_dataset_search=True, api_concurrency=1, api_delay_seconds=0, max_api_lookups=0, cache_flush_every=1,
        embedding_top_k=0, embedding_model="", embedding_batch_size=1, embedding_device="cpu", llm_provider="openai",
        llm_max_items=0, llm_model="", llm_temperature=0.0, ollama_base_url="", ollama_model="", llm_use_fulltext=False,
        fulltext_char_limit=1000, llm_max_fulltext_fetch=0, preview_rows=0, journal_metrics_csv="",
        impact_factor_threshold=10.0, citation_percentile_threshold=90.0, verbose=False,
        openalex_budget_wait_max_hours=30.0, backfill_openalex_metadata=True, openalex_metadata_min_budget_remaining=0,
    )
    fields.update(overrides)
    return pipeline.PipelineConfig(**fields)


def _paths(tmp_path: Path) -> Any:
    return pipeline.PipelinePaths(
        output_dir=tmp_path, raw_csv=tmp_path / "raw.csv", preview_csv=tmp_path / "p.csv", full_csv=tmp_path / "f.csv",
        high_impact_csv=tmp_path / "h.csv", enrich_cache=tmp_path / "e.json", llm_cache=tmp_path / "l.json",
        retrieval_slices_dir=tmp_path / "slices", openalex_metadata_cache=tmp_path / "openalex_metadata_cache.jsonl",
    )


def _legacy_df(dois):
    return pipeline.standardize_dataframe(pd.DataFrame([{"doi": d, "title": f"paper {d}", "journal": "J", "year": 2020} for d in dois]))


def test_backfill_waits_on_budget_429_keeps_key_and_caches(tmp_path, no_sleep, monkeypatch):
    monkeypatch.setattr(pipeline, "ensure_openalex_budget_available", lambda cfg, session: None)
    dois = [f"10.1/{i}" for i in range(60)]  # two batches of 50 + 10
    batch1 = sorted(dois)[:50]
    batch2 = sorted(dois)[50:]
    session = FakeSession([
        FakeResponse(200, {"results": [_meta_work(d, preprint=(d == batch1[0])) for d in batch1[:-1]]},
                     headers={"X-RateLimit-Remaining": "5000"}),
        FakeResponse(429, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "120"}),
        FakeResponse(200, {"results": [_meta_work(d, work_type="review", oa_status="closed") for d in batch2]},
                     headers={"X-RateLimit-Remaining": "4998"}),
    ])
    df = _legacy_df(dois)
    out, complete = pipeline.run_openalex_metadata_backfill(df, _cfg(tmp_path), _paths(tmp_path), session)
    assert complete is True
    assert len(session.calls) == 3
    assert all(c["params"].get("api_key") == "secret-key" for c in session.calls), "key must never be dropped"
    assert session.calls[1]["params"]["filter"] == session.calls[2]["params"]["filter"], "429'd batch is retried"
    assert all("select" in c["params"] and "funders" in c["params"]["select"] for c in session.calls)
    assert sum(no_sleep) == pytest.approx(180.0)  # 120 s reset + 60 s margin

    by_doi = out.set_index("doi")
    assert by_doi.loc[batch1[0], "has_preprint_version"] is True or bool(by_doi.loc[batch1[0], "has_preprint_version"])
    assert by_doi.loc[batch1[0], "preprint_servers"] == "medRxiv (Cold Spring Harbor Laboratory)"
    assert by_doi.loc[batch2[0], "work_type"] == "review"
    assert by_doi.loc[batch2[0], "oa_status"] == "closed"
    assert by_doi.loc[batch1[-1], "work_type"] == ""  # not returned by OpenAlex -> stays blank
    assert (out["first_author_country"] == "GB").sum() == 59

    cache = pipeline.load_openalex_metadata_cache(tmp_path / "openalex_metadata_cache.jsonl")
    assert cache[batch1[-1]] is None, "missing DOIs are recorded so they are not re-requested"
    assert cache[batch2[0]]["work_type"] == "review"
    assert len(cache) == 60


def test_backfill_resumes_from_cache_without_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "ensure_openalex_budget_available", lambda cfg, session: None)
    path = tmp_path / "openalex_metadata_cache.jsonl"
    pipeline.append_openalex_metadata_cache(
        path,
        [{"doi_norm": "10.1/a", **pipeline.flatten_openalex_work_metadata(_meta_work("10.1/a"))}],
        ["10.1/b"],
    )
    session = FakeSession([])
    out, complete = pipeline.run_openalex_metadata_backfill(_legacy_df(["10.1/a", "10.1/b"]), _cfg(tmp_path), _paths(tmp_path), session)
    assert complete is True
    assert session.calls == []
    assert out.loc[out["doi"] == "10.1/a", "work_type"].iloc[0] == "article"
    assert out.loc[out["doi"] == "10.1/b", "work_type"].iloc[0] == ""


def test_backfill_cache_is_applied_even_without_the_flag(tmp_path):
    path = tmp_path / "openalex_metadata_cache.jsonl"
    pipeline.append_openalex_metadata_cache(path, [{"doi_norm": "10.1/a", **pipeline.flatten_openalex_work_metadata(_meta_work("10.1/a", oa_status="hybrid"))}], [])
    out, complete = pipeline.run_openalex_metadata_backfill(
        _legacy_df(["10.1/a"]), _cfg(tmp_path, backfill_openalex_metadata=False), _paths(tmp_path), FakeSession([])
    )
    assert complete is True and out.loc[0, "oa_status"] == "hybrid"


def test_backfill_400_falls_back_to_single_doi_lookups(tmp_path, no_sleep, monkeypatch):
    monkeypatch.setattr(pipeline, "ensure_openalex_budget_available", lambda cfg, session: None)
    session = FakeSession([
        FakeResponse(400, {"error": "bad filter"}),
        FakeResponse(200, {"results": [_meta_work("10.1/a")]}),
        FakeResponse(200, {"results": []}),
    ])
    out, complete = pipeline.run_openalex_metadata_backfill(_legacy_df(["10.1/a", "10.1/b"]), _cfg(tmp_path), _paths(tmp_path), session)
    assert complete is True
    assert [c["params"]["filter"] for c in session.calls] == ["doi:10.1/a|10.1/b", "doi:10.1/a", "doi:10.1/b"]
    assert out.loc[out["doi"] == "10.1/a", "work_type"].iloc[0] == "article"


def test_backfill_stops_early_when_budget_wait_exceeds_cap(tmp_path, no_sleep, monkeypatch):
    monkeypatch.setattr(pipeline, "ensure_openalex_budget_available", lambda cfg, session: None)
    session = FakeSession([
        FakeResponse(429, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(10 * 3600)}),
    ])
    out, complete = pipeline.run_openalex_metadata_backfill(
        _legacy_df(["10.1/a"]), _cfg(tmp_path, openalex_budget_wait_max_hours=1.0), _paths(tmp_path), session
    )
    assert complete is False
    assert no_sleep == []
    assert not (tmp_path / "openalex_metadata_cache.jsonl").exists()


# ── registration regex flags ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text, expected",
    [
        ("Registered at ClinicalTrials.gov (NCT01234567).", "reg_trial_registry"),
        ("Trial registration ISRCTN12345678", "reg_trial_registry"),
        ("ChiCTR2000031234 registry", "reg_trial_registry"),
        ("EudraCT 2016-001234-56", "reg_trial_registry"),
        ("Protocol registered in PROSPERO (CRD42020123456)", "reg_prospero"),
        ("The analysis plan was pre-registered on osf.io/abc12", "reg_preregistration_wording"),
        ("This prospectively registered cohort", "reg_preregistration_wording"),
    ],
)
def test_registry_patterns_match(text, expected):
    df = pipeline.apply_registration_flags(pd.DataFrame([{"title": "t", "abstract": text}]))
    assert bool(df.loc[0, expected]) is True
    assert bool(df.loc[0, "registered_any"]) is True
    assert bool(df.loc[0, "registration_signal"]) is True


def test_registry_patterns_do_not_fire_on_plain_text():
    df = pipeline.apply_registration_flags(pd.DataFrame([
        {"title": "Registered nurses and stroke care", "abstract": "A survey of 1234 nurses registered with the college."},
    ]))
    assert not df.loc[0, "registered_any"]
    for col in pipeline.REGISTRATION_FLAG_COLS:
        assert col in df.columns


# ── metadata-based preprint flag ───────────────────────────────────────────────

def test_metadata_preprint_flag_fills_only_blank_preprint():
    df = pd.DataFrame([
        {"preprint": "", "has_preprint_version": True, "preprint_servers": "medRxiv (Cold Spring Harbor Laboratory)"},
        {"preprint": "https://www.medrxiv.org/x", "has_preprint_version": True, "preprint_servers": "medRxiv"},
        {"preprint": "", "has_preprint_version": False, "preprint_servers": ""},
        {"preprint": "", "has_preprint_version": True, "preprint_servers": ""},
        {"preprint": "", "has_preprint_version": pd.NA, "preprint_servers": ""},
    ])
    out = pipeline.apply_metadata_preprint_flag(df)
    assert out["preprint"].tolist() == [
        "medRxiv (Cold Spring Harbor Laboratory)", "https://www.medrxiv.org/x", "", "openalex:preprint_version", "",
    ]


# ── in_article_corpus ──────────────────────────────────────────────────────────

def test_in_article_corpus_rules():
    df = pd.DataFrame([
        {"journal": "Stroke", "work_type": "article", "primary_source_type": "journal"},
        {"journal": "Lancet Neurology", "work_type": "review", "primary_source_type": "journal"},
        {"journal": "medRxiv", "work_type": "preprint", "primary_source_type": "repository"},
        {"journal": "Figshare", "work_type": "dataset", "primary_source_type": "repository"},
        {"journal": "Stroke", "work_type": "erratum", "primary_source_type": "journal"},
        {"journal": "Research Square", "work_type": "article", "primary_source_type": "repository"},
        # no metadata: fall back to the source name
        {"journal": "Journal of Stroke and Cerebrovascular Diseases", "work_type": "", "primary_source_type": ""},
        {"journal": "Research Square (Research Square)", "work_type": "", "primary_source_type": ""},
        {"journal": "ProQuest Dissertations", "work_type": None, "primary_source_type": None},
        {"journal": "", "work_type": "", "primary_source_type": ""},
    ])
    out = pipeline.apply_corpus_flag(df)
    assert out["in_article_corpus"].tolist() == [True, True, False, False, False, False, True, False, False, True]
    assert out["corpus_rule"].tolist()[:6] == ["openalex_type"] * 6
    assert out["corpus_rule"].tolist()[6:] == ["source_name_fallback"] * 4
    assert len(out) == len(df), "rows are flagged, never dropped"


def test_corpus_flag_survives_standardize_dataframe():
    df = pipeline.apply_corpus_flag(pd.DataFrame([{"doi": "10.1/x", "journal": "Stroke", "work_type": "article", "primary_source_type": "journal"}]))
    out = pipeline.standardize_dataframe(df)
    assert str(out["in_article_corpus"].dtype) == "boolean"
    assert bool(out.loc[0, "in_article_corpus"]) is True


# ── DAS audit: JATS extraction ─────────────────────────────────────────────────

JATS_MARKED = """<?xml version="1.0"?>
<article><front><article-meta><title-group><article-title>Trial</article-title></title-group></article-meta></front>
<body>
  <sec sec-type="methods"><title>Methods</title><p>We enrolled 120 patients with acute ischemic stroke (NCT01234567).</p></sec>
  <sec sec-type="results"><title>Results</title><p>Outcomes improved.</p></sec>
</body>
<back>
  <sec sec-type="data-availability"><title>Data Availability Statement</title>
    <p>De-identified individual participant data and analysis code are deposited in Zenodo
    (<ext-link>https://doi.org/10.5281/zenodo.1234567</ext-link>) and on GitHub (github.com/lab/stroke-trial).</p>
  </sec>
</back></article>"""

JATS_UNMARKED_AHA = """<?xml version="1.0"?>
<article><body>
  <sec><title>Methods</title>
    <p>The data that support the findings of this study are available from the corresponding author upon reasonable request. Patients were recruited at 12 comprehensive stroke centers between 2016 and 2019.</p>
    <p>Statistical analyses were performed in R.</p>
  </sec>
</body></article>"""


def test_extract_das_statements_marked_section():
    out = pipeline.extract_das_statements(JATS_MARKED)
    assert "parse_error" not in out
    assert len(out["statements"]) == 1
    stmt = out["statements"][0]
    assert stmt["how"] == "sec-type"
    assert stmt["label"] == "data-availability"
    assert "zenodo" in stmt["text"].lower()
    assert "Methods" not in stmt["text"]
    assert out["flags"]["mentions_trial_registration"] is True
    assert out["flags"]["mentions_github"] is True


def test_extract_das_statements_unmarked_aha_paragraph():
    out = pipeline.extract_das_statements(JATS_UNMARKED_AHA)
    assert len(out["statements"]) == 1
    stmt = out["statements"][0]
    assert stmt["how"] == "p-sentence"
    assert stmt["text"] == (
        "The data that support the findings of this study are available from the corresponding author upon reasonable request."
    ), "only the DAS sentence is kept, with its first word intact"
    assert out["flags"]["mentions_trial_registration"] is False


def test_extract_das_statements_handles_bad_xml_and_absence():
    assert pipeline.extract_das_statements("<article><body><p>unclosed") == {"parse_error": True}
    out = pipeline.extract_das_statements("<article><body><p>Nothing about sharing here.</p></body></article>")
    assert out["statements"] == []


# ── DAS audit: classification ──────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text, primary",
    [
        ("Data are deposited in Dryad (https://doi.org/10.5061/dryad.abc).", "repository"),
        ("Analysis code is available at github.com/lab/repo.", "repository"),
        ("Restrictions apply to the availability of these data, which were used under license.", "controlled_or_restricted"),
        ("Data are not publicly available due to patient privacy; they are available on reasonable request.", "controlled_or_restricted"),
        ("The datasets analysed during the current study are available from the corresponding author on reasonable request.", "on_request"),
        ("All relevant data are within the paper and its Supplementary Information files.", "in_article"),
        ("Data sharing is not applicable to this article as no datasets were generated or analysed.", "not_available_or_na"),
        ("The authors declare that they have nothing to add.", "other_or_unclear"),
    ],
)
def test_classify_das_text_primary_label(text, primary):
    out = pipeline.classify_das_text(text)
    assert out["primary"] == primary


def test_classify_das_text_is_multilabel():
    out = pipeline.classify_das_text("Code is available on GitHub (github.com/x/y); data are available upon reasonable request.")
    assert out["lab_repository"] and out["lab_on_request"] and out["lab_code_shared"]
    assert out["primary"] == "repository"
    assert set(pipeline.DAS_CATEGORIES) >= {"repository", "on_request", "no_statement", "other_or_unclear"}


# ── DAS audit: end-to-end with a scripted Europe PMC session ───────────────────

class RoutingFakeSession:
    """Routes Europe PMC search / fullTextXML URLs to canned responses and records calls."""

    def __init__(self, articles: Dict[str, Dict[str, Any]], xml_by_pmcid: Dict[str, str]):
        self.articles = articles  # doi -> {"pmcid": ..., "pmid": ...}
        self.xml_by_pmcid = xml_by_pmcid
        self.calls: List[str] = []
        self.search_queries: List[str] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(url)
        if url.endswith("/search"):
            query = params["query"]
            self.search_queries.append(query)
            assert "HAS_FT:y" in query and "SRC:MED" in query and "OPEN_ACCESS:y" in query
            dois = [m.lower() for m in __import__("re").findall(r'DOI:"([^"]+)"', query)]
            assert len(dois) <= pipeline.EUROPEPMC_DOI_BATCH_SIZE
            hits = [{"doi": d, "pmcid": self.articles[d]["pmcid"], "pmid": self.articles[d]["pmid"], "source": "MED"} for d in dois if d in self.articles]
            return FakeResponse(200, {"hitCount": len(hits), "resultList": {"result": hits}})
        if url.endswith("/fullTextXML"):
            pmcid = url.rsplit("/", 2)[-2]
            xml = self.xml_by_pmcid.get(pmcid)
            resp = FakeResponse(200 if xml else 404)
            resp.text = xml or ""
            return resp
        raise AssertionError(f"unexpected url {url}")




def _corpus_df(n_per_year: int, years=(2020, 2021)) -> pd.DataFrame:
    rows = []
    for year in years:
        for i in range(n_per_year):
            rows.append({"doi": f"10.1/{year}-{i}", "title": "t", "journal": "Stroke", "year": year,
                         "work_type": "article", "primary_source_type": "journal"})
    rows.append({"doi": "10.1/dataset", "title": "d", "journal": "Figshare", "year": 2020, "work_type": "dataset", "primary_source_type": "repository"})
    df = pipeline.apply_corpus_flag(pd.DataFrame(rows))
    return pipeline.standardize_dataframe(df)


def test_run_das_audit_samples_per_year_fetches_and_caches(tmp_path, no_sleep):
    df = _corpus_df(40)
    # every third in-corpus article has full text; the dataset row must never be considered
    articles = {}
    xml = {}
    k = 0
    for doi in df.loc[df["in_article_corpus"].fillna(False), "doi"]:
        k += 1
        if k % 3 == 0:
            pmcid = f"PMC{k:05d}"
            articles[doi] = {"pmcid": pmcid, "pmid": str(k)}
            xml[pmcid] = JATS_MARKED if k % 2 == 0 else JATS_UNMARKED_AHA
    articles["10.1/dataset"] = {"pmcid": "PMC99999", "pmid": "9"}
    xml["PMC99999"] = JATS_MARKED
    session = RoutingFakeSession(articles, xml)
    cfg = _cfg(tmp_path, das_audit_sample_per_year=5, das_audit_workers=2, das_audit_delay_seconds=0.0, das_audit_timeout_seconds=10)
    paths = _paths(tmp_path)
    paths.das_cache = tmp_path / "das_cache.jsonl"

    out = pipeline.run_das_audit(df, cfg, paths, session)

    audited = out[out["das_available"].fillna(False).astype(bool)]
    assert audited.groupby("year").size().to_dict() == {2020: 5, 2021: 5}
    assert "10.1/dataset" not in set(audited["doi"])
    assert set(audited["das_primary"]) <= {"repository", "on_request"}
    assert audited["das_has_statement"].all()
    assert audited["das_text"].str.len().max() <= pipeline.DAS_TEXT_MAX_CHARS
    assert audited["das_pmcid"].str.startswith("PMC").all()
    assert (~out["das_available"].astype(bool)).sum() == len(out) - 10
    assert out.loc[~out["das_available"].astype(bool), "das_primary"].eq("").all()
    assert all(q.count('DOI:"') <= 25 for q in session.search_queries)
    n_fulltext = sum(1 for u in session.calls if u.endswith("/fullTextXML"))
    assert n_fulltext == 10

    resolved, fetched = pipeline.load_das_cache(paths.das_cache)
    assert len(fetched) == 10
    assert all(r["kind"] == "resolve" for r in resolved.values())

    # Resume: same corpus, same seed -> same sample, no new requests
    session2 = RoutingFakeSession(articles, xml)
    out2 = pipeline.run_das_audit(df, cfg, paths, session2)
    assert session2.calls == []
    assert set(out2.loc[out2["das_available"].astype(bool), "doi"]) == set(audited["doi"])


def test_run_das_audit_disabled_adds_empty_columns(tmp_path):
    df = _corpus_df(2)
    out = pipeline.run_das_audit(df, _cfg(tmp_path, das_audit_sample_per_year=0), _paths(tmp_path), RoutingFakeSession({}, {}))
    assert out["das_available"].astype(bool).sum() == 0
    for col in pipeline.DAS_TEXT_COLS + pipeline.DAS_BOOL_COLS:
        assert col in out.columns


def test_das_no_statement_label_when_fulltext_has_no_das(tmp_path, no_sleep):
    df = _corpus_df(1, years=(2022,))
    doi = df.loc[df["in_article_corpus"].fillna(False), "doi"].iloc[0]
    session = RoutingFakeSession({doi: {"pmcid": "PMC1", "pmid": "1"}}, {"PMC1": "<article><body><p>No sharing text.</p></body></article>"})
    paths = _paths(tmp_path)
    out = pipeline.run_das_audit(df, _cfg(tmp_path, das_audit_sample_per_year=3, das_audit_delay_seconds=0.0), paths, session)
    row = out[out["doi"] == doi].iloc[0]
    assert bool(row["das_available"]) is True
    assert bool(row["das_has_statement"]) is False
    assert row["das_primary"] == "no_statement"
