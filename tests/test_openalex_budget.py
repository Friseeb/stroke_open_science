"""Unit tests for OpenAlex metered-budget handling and partial-slice resume. No network."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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


class FakeResponse:
    def __init__(self, status_code: int, payload: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}

    def json(self) -> Dict[str, Any]:
        return self._payload


class FakeSession:
    """Replays a scripted list of responses and records the params of every request."""

    def __init__(self, responses: List[FakeResponse]):
        self._responses = list(responses)
        self.calls: List[Dict[str, Any]] = []

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, timeout: Any = None) -> FakeResponse:
        self.calls.append({"url": url, "params": dict(params or {})})
        if not self._responses:
            raise AssertionError("FakeSession ran out of scripted responses")
        return self._responses.pop(0)


@pytest.fixture
def no_sleep(monkeypatch):
    slept: List[float] = []
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: slept.append(s))
    return slept


def _work(i: int) -> Dict[str, Any]:
    return {"id": f"https://openalex.org/W{i}", "doi": f"https://doi.org/10.1/{i}", "title": f"Paper {i}", "publication_year": 2020}


# ── header-name helper ─────────────────────────────────────────────────────────

def test_parse_rate_limit_headers_is_case_insensitive_and_filters():
    headers = {"X-RateLimit-Remaining": "0", "x-ratelimit-reset": "3600", "Content-Type": "application/json", "Retry-After": "5"}
    parsed = pipeline.parse_openalex_rate_limit_headers(headers)
    assert parsed == {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "3600", "retry-after": "5"}
    assert pipeline.parse_openalex_rate_limit_headers(None) == {}


@pytest.mark.parametrize(
    "rate_limit, expected",
    [
        ({"x-ratelimit-remaining": "0"}, 0),
        ({"X-RateLimit-Remaining": "123"}, 123),
        ({"daily_requests_remaining": 42}, 42),
        ({"credits_remaining": "7"}, 7),
        ({"x-ratelimit-remaining-usd": "0.0"}, 0),
        ({"x-ratelimit-remaining-usd": "0.5"}, None),
        ({"credits_remaining": "garbage"}, None),
        ({}, None),
        (None, None),
    ],
)
def test_openalex_requests_remaining_reads_all_names(rate_limit, expected):
    assert pipeline.openalex_requests_remaining(rate_limit) == expected


def test_inspect_rate_limit_merges_endpoint_body_and_headers():
    session = FakeSession([
        FakeResponse(200, {"rate_limit": {"credits_remaining": 0, "resets_in_seconds": 1200}}, headers={"x-ratelimit-limit": "10000"})
    ])
    merged = pipeline.inspect_openalex_rate_limit(session, "key", 20)
    assert pipeline.openalex_requests_remaining(merged) == 0
    assert pipeline.openalex_reset_seconds(merged) == 1200
    assert merged["x-ratelimit-limit"] == "10000"
    assert pipeline.inspect_openalex_rate_limit(session, "", 20) is None


# ── reset-wait computation ─────────────────────────────────────────────────────

def test_seconds_until_next_utc_midnight():
    now = dt.datetime(2026, 10, 6, 22, 30, 0, tzinfo=dt.timezone.utc)
    assert pipeline.seconds_until_next_utc_midnight(now) == 5400.0
    naive = dt.datetime(2026, 10, 6, 23, 59, 0)
    assert pipeline.seconds_until_next_utc_midnight(naive) == 60.0
    eastern = dt.datetime(2026, 10, 6, 19, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=-4)))  # 23:00 UTC
    assert pipeline.seconds_until_next_utc_midnight(eastern) == 3600.0


def test_wait_uses_reset_header_plus_margin():
    headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "3600"}
    assert pipeline.compute_openalex_budget_wait_seconds(headers) == 3660.0


def test_wait_falls_back_to_next_utc_midnight_when_header_absent():
    now = dt.datetime(2026, 10, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    assert pipeline.compute_openalex_budget_wait_seconds({"x-ratelimit-remaining": "0"}, now=now) == 4 * 3600 + 60
    assert pipeline.compute_openalex_budget_wait_seconds({}, now=now) == 4 * 3600 + 60


def test_wait_uses_resets_at_timestamp_from_endpoint():
    now = dt.datetime(2026, 10, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    rl = {"credits_remaining": 0, "resets_at": "2026-10-06T21:00:00Z"}
    assert pipeline.compute_openalex_budget_wait_seconds(rl, now=now) == 3660.0


def test_wait_for_budget_reset_sleeps_in_chunks_and_respects_cap():
    slept: List[float] = []
    ok = pipeline.wait_for_openalex_budget_reset({"x-ratelimit-reset": "700"}, max_wait_hours=1.0, sleep_fn=slept.append)
    assert ok is True
    assert sum(slept) == pytest.approx(760.0)
    assert max(slept) <= pipeline.OPENALEX_BUDGET_SLEEP_CHUNK_SECONDS

    slept.clear()
    ok = pipeline.wait_for_openalex_budget_reset({"x-ratelimit-reset": "7200"}, max_wait_hours=1.0, sleep_fn=slept.append)
    assert ok is False
    assert slept == []


# ── search loop: keyed 429 waits and resumes same cursor; never drops the key ─

def _search(session, api_key="secret-key", **overrides):
    kwargs = dict(
        term="stroke",
        start_date=dt.date(2020, 1, 1),
        end_date=dt.date(2020, 12, 31),
        discipline="stroke",
        session=session,
        mailto="me@example.org",
        api_key=api_key,
        max_per_query=0,
        delay_seconds=0.0,
        timeout_seconds=20,
        max_attempts=1,
        max_failures_per_query=3,
        max_retry_after_seconds=60,
        budget_wait_max_hours=30.0,
    )
    kwargs.update(overrides)
    return pipeline.search_openalex_term_date_range(**kwargs)


def test_keyed_429_budget_exhaustion_waits_and_resumes_same_cursor(no_sleep):
    session = FakeSession([
        FakeResponse(200, {"results": [_work(1)], "meta": {"next_cursor": "CUR2"}}),
        FakeResponse(429, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "120", "x-ratelimit-remaining-usd": "0"}),
        FakeResponse(200, {"results": [_work(2)], "meta": {"next_cursor": None}}),
    ])
    result = _search(session)
    assert result.complete is True
    assert [r["title"] for r in result.records] == ["Paper 1", "Paper 2"]
    cursors = [c["params"]["cursor"] for c in session.calls]
    assert cursors == ["*", "CUR2", "CUR2"], "the 429'd cursor must be retried, not skipped"
    assert all(c["params"].get("api_key") == "secret-key" for c in session.calls), "key must never be dropped"
    assert sum(no_sleep) == pytest.approx(180.0)  # 120 s reset + 60 s margin


def test_keyed_429_without_headers_confirms_via_rate_limit_endpoint_then_waits(no_sleep):
    session = FakeSession([
        FakeResponse(429, headers={"Retry-After": "1"}),  # ambiguous 429 (safe_get_json retries once then gives up)
        FakeResponse(200, {"rate_limit": {"daily_requests_remaining": 0, "resets_in_seconds": 30}}),  # /rate-limit
        FakeResponse(200, {"results": [_work(1)], "meta": {"next_cursor": None}}),
    ])
    result = _search(session)
    assert result.complete is True and len(result.records) == 1
    assert session.calls[1]["url"].endswith("/rate-limit")
    assert session.calls[2]["params"].get("api_key") == "secret-key"
    assert 90.0 in no_sleep  # 30 s reset + 60 s margin


def test_keyed_budget_wait_over_cap_stops_early_as_incomplete(no_sleep):
    session = FakeSession([
        FakeResponse(200, {"results": [_work(1)], "meta": {"next_cursor": "CUR2"}}),
        FakeResponse(429, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(10 * 3600)}),
    ])
    result = _search(session, budget_wait_max_hours=1.0)
    assert result.complete is False
    assert result.stop_reason == "budget_wait_exceeded"
    assert len(result.records) == 1
    assert no_sleep == []


def test_keyless_mode_keeps_failure_based_early_stop(no_sleep):
    session = FakeSession([FakeResponse(429, headers={"x-ratelimit-remaining": "0"}) for _ in range(3)])
    result = _search(session, api_key="")
    assert result.complete is False
    assert result.stop_reason == "max_failures"
    assert all("api_key" not in c["params"] for c in session.calls)
    assert not any(c["url"].endswith("/rate-limit") for c in session.calls)


def test_startup_check_waits_instead_of_dropping_key(monkeypatch, no_sleep):
    cfg = _make_cfg(Path("/nonexistent"), api_key="secret-key")
    monkeypatch.setattr(pipeline, "inspect_openalex_rate_limit", lambda *a, **k: {"credits_remaining": 0, "x-ratelimit-reset": "10"})
    pipeline.ensure_openalex_budget_available(cfg, session=object())
    assert cfg.openalex_api_key == "secret-key"
    assert sum(no_sleep) == pytest.approx(70.0)


# ── partial slice is not treated as complete ───────────────────────────────────

def _make_cfg(output_dir: Path, api_key: str = "") -> Any:
    return pipeline.PipelineConfig(
        discipline="stroke", terms=["stroke"], years=[2020], query_window_months=12, include_pubmed=False,
        pubmed_email="", pubmed_api_key="", pubmed_tool="t", pubmed_delay_seconds=0.0, pubmed_timeout_seconds=5,
        pubmed_max_attempts=1, pubmed_batch_size=1, openalex_mailto="me@example.org", openalex_api_key=api_key,
        openalex_workers=1, openalex_delay_seconds=0.0, openalex_timeout_seconds=5, openalex_max_attempts=1,
        openalex_max_failures_per_query=3, openalex_max_retry_after_seconds=5, max_per_query=0,
        refresh_openalex=False, force=False, unpaywall_snapshot="", crossref_relations="", disable_api_enrich=True,
        disable_dataset_search=True, api_concurrency=1, api_delay_seconds=0.0, max_api_lookups=0, cache_flush_every=1,
        embedding_top_k=0, embedding_model="", embedding_batch_size=1, embedding_device="cpu", llm_provider="openai",
        llm_max_items=0, llm_model="", llm_temperature=0.0, ollama_base_url="", ollama_model="", llm_use_fulltext=False,
        fulltext_char_limit=1000, llm_max_fulltext_fetch=0, preview_rows=0, journal_metrics_csv="",
        impact_factor_threshold=10.0, citation_percentile_threshold=90.0, verbose=False,
        openalex_budget_wait_max_hours=1.0,
    )


def _make_paths(output_dir: Path) -> Any:
    return pipeline.PipelinePaths(
        output_dir=output_dir, raw_csv=output_dir / "raw.csv", preview_csv=output_dir / "p.csv",
        full_csv=output_dir / "f.csv", high_impact_csv=output_dir / "h.csv", enrich_cache=output_dir / "e.json",
        llm_cache=output_dir / "l.json", retrieval_slices_dir=output_dir / "retrieval_slices",
    )


def _record(i: int) -> Dict[str, Any]:
    return pipeline.openalex_work_to_record(_work(i), "stroke", "stroke")


def test_partial_slice_written_as_partial_and_rerun_next_time(tmp_path, monkeypatch, no_sleep):
    cfg, paths = _make_cfg(tmp_path), _make_paths(tmp_path)
    monkeypatch.setattr(pipeline, "ensure_openalex_budget_available", lambda cfg, session: None)
    slice_path = pipeline.retrieval_slice_path(paths, "openalex", "stroke", dt.date(2020, 1, 1), dt.date(2020, 12, 31))
    partial_path = pipeline.retrieval_slice_partial_path(slice_path)
    assert partial_path.name.endswith(".partial.csv") and partial_path.parent == slice_path.parent

    calls: List[int] = []

    def fake_search_incomplete(*args, **kwargs):
        calls.append(1)
        return pipeline.OpenAlexSliceResult([_record(1)], complete=False, stop_reason="max_failures")

    monkeypatch.setattr(pipeline, "search_openalex_term_date_range", fake_search_incomplete)
    with pytest.raises(RuntimeError, match="incomplete"):
        pipeline.fetch_or_load_openalex(cfg, paths, session=object())
    assert partial_path.exists(), "early-stopped slice must be saved as .partial.csv"
    assert not slice_path.exists(), "early-stopped slice must not be written as a complete slice"
    assert not paths.raw_csv.exists(), "raw dataset must not be written from incomplete retrieval"
    assert len(calls) == 1

    # Second invocation: the partial slice is re-run (not loaded from cache) and completes normally.
    def fake_search_complete(*args, **kwargs):
        calls.append(2)
        return pipeline.OpenAlexSliceResult([_record(1), _record(2)], complete=True)

    monkeypatch.setattr(pipeline, "search_openalex_term_date_range", fake_search_complete)
    df = pipeline.fetch_or_load_openalex(cfg, paths, session=object())
    assert calls == [1, 2]
    assert slice_path.exists() and not partial_path.exists()
    assert len(df) == 2
    assert paths.raw_csv.exists()

    # Third invocation: completed slice is served from cache, no search call.
    paths.raw_csv.unlink()
    monkeypatch.setattr(pipeline, "search_openalex_term_date_range", lambda *a, **k: pytest.fail("should use cache"))
    df_cached = pipeline.fetch_or_load_openalex(cfg, paths, session=object())
    assert len(df_cached) == 2


def test_slice_exception_counts_as_incomplete(tmp_path, monkeypatch):
    cfg, paths = _make_cfg(tmp_path), _make_paths(tmp_path)
    monkeypatch.setattr(pipeline, "ensure_openalex_budget_available", lambda cfg, session: None)

    def boom(*args, **kwargs):
        raise ValueError("network down")

    monkeypatch.setattr(pipeline, "search_openalex_term_date_range", boom)
    with pytest.raises(RuntimeError, match="incomplete"):
        pipeline.fetch_or_load_openalex(cfg, paths, session=object())
    assert not paths.raw_csv.exists()
