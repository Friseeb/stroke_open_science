#!/usr/bin/env python3
"""
Scalable stroke open-science pipeline.

Stages
1) OpenAlex retrieval (parallel term-year cursor pagination)
2) Snapshot joins (Unpaywall + Crossref via DuckDB)
3) Regex extraction (GitHub/Zenodo/OSF signals)
4) API enrichment (Unpaywall/Zenodo/OSF/GitHub, cached + resumable)
5) Embedding ranking (optional)
6) LLM extraction with OpenAI or Ollama (optional, targeted + cached)
7) High-impact subgroup generation
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import glob
import hashlib
import json
import logging
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from tqdm import tqdm

try:
    import duckdb  # type: ignore
except Exception:
    duckdb = None

try:
    import aiohttp  # type: ignore
except Exception:
    aiohttp = None


DEFAULT_TERMS = [
    "stroke",
    "ischemic stroke",
    "hemorrhagic stroke",
    "transient ischemic attack",
    "cerebrovascular accident",
    "cerebral infarction",
]

DOI_PREFIX_RE = re.compile(r"^(?:https?://)?(?:dx\.)?doi\.org/", re.IGNORECASE)
GITHUB_URL_RE = re.compile(r"(https?://(?:www\.)?github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", re.IGNORECASE)
ZENODO_URL_RE = re.compile(r"(https?://(?:www\.)?zenodo\.org/(?:record|records)/\d+)", re.IGNORECASE)
OSF_URL_RE = re.compile(r"(https?://(?:www\.)?osf\.io/[A-Za-z0-9]+/?)", re.IGNORECASE)
ZENODO_DOI_RE = re.compile(r"(10\.5281/zenodo\.\d+)", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# ── Dataset repository URL / DOI patterns ────────────────────────────────────
DRYAD_URL_RE = re.compile(
    r"(https?://(?:www\.)?datadryad\.org/stash/dataset/doi:10\.\d{4,9}/dryad\.[A-Za-z0-9._]+)", re.IGNORECASE)
DRYAD_DOI_RE = re.compile(r"(10\.5061/dryad\.[A-Za-z0-9._]+)", re.IGNORECASE)
FIGSHARE_URL_RE = re.compile(
    r"(https?://(?:[A-Za-z0-9-]+\.)?figshare\.com/(?:articles|collections|projects)/[^\s\"'<>]+)", re.IGNORECASE)
FIGSHARE_DOI_RE = re.compile(r"(10\.6084/m9\.figshare\.\d+)", re.IGNORECASE)
OPENNEURO_URL_RE = re.compile(r"(https?://(?:www\.)?openneuro\.org/datasets/ds\d{6})", re.IGNORECASE)
OPENNEURO_DOI_RE = re.compile(r"(10\.18112/openneuro\.\w+)", re.IGNORECASE)
PHYSIONET_URL_RE = re.compile(r"(https?://(?:www\.)?physionet\.org/content/[A-Za-z0-9_.-]+(?:/[\d.]+)?)", re.IGNORECASE)
PHYSIONET_DOI_RE = re.compile(r"(10\.13026/[A-Za-z0-9._-]+)", re.IGNORECASE)
DATAVERSE_URL_RE = re.compile(
    r"(https?://(?:[A-Za-z0-9-]+\.)*(?:dataverse\.harvard\.edu|borealisdata\.ca|dataverse\.scholarsportal\.info"
    r"|dataverse\.no|data\.gesis\.org|dataverse\.nl|dataverse\.tdl\.org|dataverse\.lib\.virginia\.edu"
    r"|datos\.uchile\.cl|dataverse\.unc\.edu|dataverse\.ada\.edu\.au|researchdata\.ntu\.edu\.sg"
    r")/(?:dataset|dataverse|file)[^\s\"'<>]*)", re.IGNORECASE)
MENDELEY_DATA_URL_RE = re.compile(
    r"(https?://(?:www\.)?data\.mendeley\.com/datasets/[A-Za-z0-9]+)", re.IGNORECASE)
MENDELEY_DOI_RE = re.compile(r"(10\.17632/[A-Za-z0-9]+)", re.IGNORECASE)
GEO_URL_RE = re.compile(r"(https?://(?:www\.)?ncbi\.nlm\.nih\.gov/geo/query/acc\.cgi\?acc=GSE\d+)", re.IGNORECASE)
GEO_ACC_RE = re.compile(r"\b(GSE\d{4,8})\b")
ARRAYEXPRESS_URL_RE = re.compile(
    r"(https?://(?:www\.)?ebi\.ac\.uk/(?:arrayexpress|biostudies)/(?:experiments|studies)/[A-Z]-[A-Z]+-\d+)", re.IGNORECASE)
ARRAYEXPRESS_ACC_RE = re.compile(r"\b(E-[A-Z]+-\d{4,8})\b")
DBGAP_URL_RE = re.compile(r"(https?://(?:www\.)?ncbi\.nlm\.nih\.gov/projects/gap/cgi-bin/study\.cgi\?study_id=phs\d+)", re.IGNORECASE)
DBGAP_ACC_RE = re.compile(r"\b(phs\d{6})\b")
SYNAPSE_URL_RE = re.compile(r"(https?://(?:www\.)?synapse\.org/#!Synapse:syn\d+)", re.IGNORECASE)
SYNAPSE_ACC_RE = re.compile(r"\b(syn\d{6,10})\b")
TCIA_URL_RE = re.compile(r"(https?://(?:www\.)?cancerimagingarchive\.net/[^\s\"'<>]+)", re.IGNORECASE)
NITRC_URL_RE = re.compile(r"(https?://(?:www\.)?nitrc\.org/projects/[A-Za-z0-9_.-]+)", re.IGNORECASE)
NEUROVAULT_URL_RE = re.compile(r"(https?://(?:www\.)?neurovault\.org/collections/\d+)", re.IGNORECASE)
PANGAEA_URL_RE = re.compile(r"(https?://(?:www\.)?pangaea\.de/10\.\d{4,9}/PANGAEA\.\d+)", re.IGNORECASE)
PANGAEA_DOI_RE = re.compile(r"(10\.1594/PANGAEA\.\d+)", re.IGNORECASE)
ICPSR_URL_RE = re.compile(r"(https?://(?:www\.)?icpsr\.umich\.edu/web/[^\s\"'<>]*openicpsr/\d+)", re.IGNORECASE)
VIVLI_URL_RE = re.compile(r"(https?://(?:www\.)?vivli\.org/[^\s\"'<>]+)", re.IGNORECASE)
PROTEOMEXCHANGE_URL_RE = re.compile(r"(https?://(?:www\.)?proteomecentral\.proteomexchange\.org/[^\s\"'<>]+)", re.IGNORECASE)
PROTEOMEXCHANGE_ACC_RE = re.compile(r"\b(PXD\d{6})\b")
METABOLIGHTS_URL_RE = re.compile(r"(https?://(?:www\.)?ebi\.ac\.uk/metabolights/MTBLS\d+)", re.IGNORECASE)
METABOLIGHTS_ACC_RE = re.compile(r"\b(MTBLS\d{4,8})\b")
IEEE_DATAPORT_URL_RE = re.compile(r"(https?://(?:www\.)?ieee-dataport\.org/[^\s\"'<>]+)", re.IGNORECASE)
UKDATA_URL_RE = re.compile(r"(https?://(?:www\.)?(?:ukdataservice|beta\.ukdataservice)\.ac\.uk/[^\s\"'<>]+)", re.IGNORECASE)
ICPSR_DOI_RE = re.compile(r"(10\.3886/(?:ICPSR)?\d+)", re.IGNORECASE)
FLOWREPOSITORY_URL_RE = re.compile(r"(https?://(?:www\.)?flowrepository\.org/id/FR-FCM-[A-Za-z0-9]{4})", re.IGNORECASE)
FLOWREPOSITORY_ACC_RE = re.compile(r"\b(FR-FCM-[A-Z0-9]{4})\b")
IMMPORT_URL_RE = re.compile(r"(https?://(?:www\.)?immport\.org/[^\s\"'<>]+)", re.IGNORECASE)
IMMPORT_ACC_RE = re.compile(r"\b(SDY\d{3,6})\b")
YODA_URL_RE = re.compile(r"(https?://(?:www\.)?yoda\.yale\.edu/[^\s\"'<>]+)", re.IGNORECASE)

# All dataset regex patterns grouped for iteration: (name, url_regex, doi_or_acc_regex_or_None)
DATASET_REPO_PATTERNS = [
    ("dryad",           DRYAD_URL_RE,           DRYAD_DOI_RE),
    ("figshare",        FIGSHARE_URL_RE,        FIGSHARE_DOI_RE),
    ("openneuro",       OPENNEURO_URL_RE,       OPENNEURO_DOI_RE),
    ("physionet",       PHYSIONET_URL_RE,       PHYSIONET_DOI_RE),
    ("dataverse",       DATAVERSE_URL_RE,       None),
    ("mendeley_data",   MENDELEY_DATA_URL_RE,   MENDELEY_DOI_RE),
    ("geo",             GEO_URL_RE,             GEO_ACC_RE),
    ("arrayexpress",    ARRAYEXPRESS_URL_RE,    ARRAYEXPRESS_ACC_RE),
    ("dbgap",           DBGAP_URL_RE,           DBGAP_ACC_RE),
    ("synapse",         SYNAPSE_URL_RE,         SYNAPSE_ACC_RE),
    ("tcia",            TCIA_URL_RE,            None),
    ("nitrc",           NITRC_URL_RE,           None),
    ("neurovault",      NEUROVAULT_URL_RE,      None),
    ("pangaea",         PANGAEA_URL_RE,         PANGAEA_DOI_RE),
    ("icpsr",           ICPSR_URL_RE,           ICPSR_DOI_RE),
    ("vivli",           VIVLI_URL_RE,           None),
    ("proteomexchange", PROTEOMEXCHANGE_URL_RE, PROTEOMEXCHANGE_ACC_RE),
    ("metabolights",    METABOLIGHTS_URL_RE,    METABOLIGHTS_ACC_RE),
    ("ieee_dataport",   IEEE_DATAPORT_URL_RE,   None),
    ("ukdata",          UKDATA_URL_RE,          None),
    ("flowrepository",  FLOWREPOSITORY_URL_RE,  FLOWREPOSITORY_ACC_RE),
    ("immport",         IMMPORT_URL_RE,         IMMPORT_ACC_RE),
    ("yoda",            YODA_URL_RE,            None),
]

KEYWORD_SIGNAL_PATTERNS = [
    ("github", re.compile(r"\bgithub\b", re.IGNORECASE), 5),
    ("gitlab", re.compile(r"\bgitlab\b", re.IGNORECASE), 4),
    ("code", re.compile(r"\b(code available|source code|open[- ]source|software package|software tool|python package|r package)\b", re.IGNORECASE), 4),
    ("data", re.compile(r"\b(data availability|dataset|data set|supplementary data|data repository|data available|repository)\b", re.IGNORECASE), 4),
    ("zenodo", re.compile(r"\bzenodo\b", re.IGNORECASE), 4),
    ("osf", re.compile(r"\b(osf|open science framework)\b", re.IGNORECASE), 4),
    ("dryad", re.compile(r"\b(dryad|datadryad)\b", re.IGNORECASE), 5),
    ("figshare", re.compile(r"\bfigshare\b", re.IGNORECASE), 4),
    ("dataverse", re.compile(r"\b(dataverse|borealis)\b", re.IGNORECASE), 5),
    ("openneuro", re.compile(r"\bopenneuro\b", re.IGNORECASE), 5),
    ("physionet", re.compile(r"\bphysionet\b", re.IGNORECASE), 5),
    ("geo", re.compile(r"\b(gene expression omnibus|GEO accession)\b", re.IGNORECASE), 4),
    ("dbgap", re.compile(r"\bdbgap\b", re.IGNORECASE), 4),
    ("tcia", re.compile(r"\b(cancer imaging archive|TCIA)\b", re.IGNORECASE), 4),
    ("mendeley_data", re.compile(r"\bmendeley data\b", re.IGNORECASE), 4),
    ("synapse", re.compile(r"\bsynapse\.org\b", re.IGNORECASE), 4),
    ("immport", re.compile(r"\bimmport\b", re.IGNORECASE), 4),
    ("vivli", re.compile(r"\bvivli\b", re.IGNORECASE), 4),
    ("yoda", re.compile(r"\byoda project\b", re.IGNORECASE), 4),
    ("icpsr", re.compile(r"\bicpsr\b", re.IGNORECASE), 4),
    ("preregistration", re.compile(r"\b(preregistered|pre[- ]registered|preregistration|trial registration|clinicaltrials\.gov|isrctn)\b", re.IGNORECASE), 3),
    ("preprint", re.compile(r"\b(preprint|medrxiv|biorxiv|arxiv)\b", re.IGNORECASE), 2),
]

# OpenAlex work-level metadata (work type, OA status, locations, authorship countries, funders).
# ``funders`` is a valid ``select`` field on /works; ``grants`` is not.
OPENALEX_WORK_SELECT_FIELDS = (
    "id,doi,title,publication_year,type,open_access,best_oa_location,primary_location,locations,"
    "authorships,ids,abstract_inverted_index,cited_by_count,is_retracted,has_fulltext,funders"
)
OPENALEX_METADATA_SELECT_FIELDS = (
    "id,doi,publication_year,type,open_access,primary_location,locations,authorships,"
    "is_retracted,has_fulltext,funders"
)
PREPRINT_SERVER_PATTERN = re.compile(
    r"medrxiv|biorxiv|research square|ssrn|preprints\.org|preprints \(|arxiv|"
    r"osf preprints|authorea|europe pmc preprints|chinaxiv|scielo preprints|"
    r"jmir preprints|psyarxiv|sportrxiv|preprint",
    re.IGNORECASE,
)
OPENALEX_METADATA_TEXT_COLS = [
    "work_type",
    "oa_status",
    "primary_source_type",
    "preprint_servers",
    "first_author_country",
    "countries",
    "funders",
]
OPENALEX_METADATA_BOOL_COLS = [
    "primary_source_is_in_doaj",
    "has_preprint_version",
    "is_preprint_record",
    "is_retracted",
    "has_fulltext",
]
OPENALEX_METADATA_COLS = OPENALEX_METADATA_TEXT_COLS + OPENALEX_METADATA_BOOL_COLS
LIST_JOIN = "|"

# Registration signals over title + abstract (no LLM). ``preregistered`` stays the LLM field;
# ``registration_signal`` (= ``registered_any``) is the regex-based counterpart available for
# every row.
REGISTRY_PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "trial_registry": re.compile(
        r"\bNCT\s?\d{8}\b|\bISRCTN\s?\d{8}\b|\bChiCTR[-\w]*\d{6,}|\bUMIN\s?\d{9}\b|"
        r"\bACTRN\s?\d{14}\b|\bEudraCT\b|\b\d{4}-\d{6}-\d{2}\b|\bDRKS\s?\d{8}\b|"
        r"\bCTRI/\d{4}/\d{2}/\d{6}\b|\bIRCT\w*\d{6,}|\bNTR\s?\d{4,}\b|\bNL\s?\d{4,}\b(?=.*netherlands trial)|"
        r"\bjRCT\w*\d{6,}|\bKCT\s?\d{7}\b|\bclinicaltrials\.gov\b|\bTCTR\d{11}\b|\bPACTR\d{15}\b",
        re.IGNORECASE,
    ),
    "prospero": re.compile(r"\bCRD\s?42\d{6}\b|\bPROSPERO\b", re.IGNORECASE),
    "preregistration_wording": re.compile(
        r"\bpre-?registered\b|\bpre-?registration\b|\bregistered report\b|\bosf\.io/\w+|"
        r"\bprospectively registered\b|\bregistered protocol\b",
        re.IGNORECASE,
    ),
}
REGISTRATION_FLAG_COLS = [f"reg_{name}" for name in REGISTRY_PATTERNS] + ["registered_any", "registration_signal"]

# Article corpus: OpenAlex journal articles / reviews with a DOI (metadata is joined by DOI, so rows
# without metadata are excluded). The source-name pattern is used only for legacy frames that carry no
# OpenAlex metadata at all (anything that looks like a repository, preprint server or thesis is excluded).
ARTICLE_WORK_TYPES = {"article", "review"}
NON_JOURNAL_SOURCE_PATTERN = re.compile(
    r"figshare|zenodo|research square|^pubmed|doaj|ssrn|medrxiv|biorxiv|arxiv|"
    r"preprints|dryad|osf|mendeley data|europe pmc|hal \(|repository|eprints|"
    r"dissertation|thesis|proquest",
    re.IGNORECASE,
)
CORPUS_FLAG_COLS = ["in_article_corpus"]

# Data-availability-statement (DAS) audit via Europe PMC full text (open-access subset only).
EUROPEPMC_REST_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
EUROPEPMC_DOI_BATCH_SIZE = 25
DAS_TEXT_MAX_CHARS = 1000
DAS_SEC_TYPES = {
    "data-availability",
    "data-availability-statement",
    "data-availability-statements",
    "availability-of-data",
    "data-sharing",
    "code-availability",
    "availability",
}
DAS_SENTENCE_PATTERN = re.compile(
    r"(data|datasets?|materials?)[^.;]{0,100}(support(ing)? the (findings|results|conclusions)|used (and/or |and |or )?analy[sz]ed|"
    r"generated (and|or) analy[sz]ed|of (this|the present|the current) study)[^.;]{0,160}(available|shared|accessible|deposited|provided|obtained)|"
    r"(available|obtained) from the corresponding author|data (sharing|availability) statement|"
    r"(will|can) be (made )?available (up)?on (reasonable )?request|data are not publicly available|no data (were|was) generated",
    re.IGNORECASE,
)
DAS_TITLE_PATTERN = re.compile(
    r"(data|code|material|software)\s+(and\s+\w+\s+)?(availability|sharing|access|statement)|"
    r"availability\s+of\s+(the\s+)?(data|code|supporting)|data\s+statement",
    re.IGNORECASE,
)
DAS_PREFIX_PATTERN = re.compile(r"^(data|code) (availability|sharing)( statement)?[:.]|^availability of data", re.IGNORECASE)
DAS_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
# Multi-label classification; DAS_PRIMARY_PRIORITY resolves to one label per article.
DAS_PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "repository": re.compile(
        r"zenodo|figshare|dryad|osf\.io|open science framework|github\.com|gitlab|bitbucket|dbgap|openneuro|synapse\.org|"
        r"mendeley data|vivli|yoda project|virtual international stroke trials archive|\bvista\b|clinicalstudydatarequest|"
        r"dataverse|\bgeo\b accession|\bgse\d{4,}|arrayexpress|\bsra\b|ega-|european genome-phenome|physionet|"
        r"ukbiobank|uk biobank|\bnda\b|nimh data archive|openicpsr|icpsr|\bzivahub|re3data|doi\.org/10\.5281|doi\.org/10\.6084|"
        r"doi\.org/10\.5061|deposited (in|at|to) (a |the )?(public )?repositor|publicly available (at|in|from|through) (the )?(https?://|www\.)",
        re.IGNORECASE,
    ),
    "on_request": re.compile(
        r"(up)?on (reasonable |justified |formal )?request|by request|available from the corresponding author|"
        r"contact(ing)? the corresponding author|available upon|request to the (corresponding |first )?author|from the authors? (up)?on",
        re.IGNORECASE,
    ),
    "in_article": re.compile(
        r"(included|contained|presented|provided|available) (with)?in (this|the) (published )?(article|manuscript|paper|study)|"
        r"within the (article|manuscript|paper)|supplementa(l|ry) (material|information|file|data|table)|"
        r"all (relevant )?data are (within|in) the (paper|manuscript)",
        re.IGNORECASE,
    ),
    "controlled_or_restricted": re.compile(
        r"restrictions? apply|not publicly available|cannot be (made )?(publicly )?(available|shared)|third[- ]party|"
        r"ethical (restriction|reason|approval)|privacy|confidential|data protection|gdpr|ethics committee|"
        r"institutional (review board|policy)|patient (consent|privacy)|data (use|sharing|access) agreement|"
        r"controlled access|regulatory|governance|licen[cs]e (restriction|agreement)",
        re.IGNORECASE,
    ),
    "not_available_or_na": re.compile(
        r"no (new )?data(sets)? (were|was|are|is) (generated|created|analy[sz]ed)|not applicable|no data (are|is) available|"
        r"data sharing (is )?not applicable|will not be (made )?(available|shared)|not available|data are unavailable",
        re.IGNORECASE,
    ),
    "code_shared": re.compile(
        r"(code|script|software|analysis pipeline)s? (is|are|were|will be|have been) (publicly |freely |openly )?(available|shared|deposited|released)|"
        r"github\.com|gitlab|zenodo",
        re.IGNORECASE,
    ),
}
DAS_PRIMARY_PRIORITY = ["repository", "controlled_or_restricted", "on_request", "in_article", "not_available_or_na"]
DAS_OTHER_LABEL = "other_or_unclear"
DAS_NO_STATEMENT_LABEL = "no_statement"
DAS_CATEGORIES = DAS_PRIMARY_PRIORITY + [DAS_OTHER_LABEL, DAS_NO_STATEMENT_LABEL]
DAS_TEXT_COLS = ["das_pmcid", "das_primary", "das_text"]
DAS_BOOL_COLS = ["das_available", "das_has_statement"]

TEXT_COLS = [
    "id",
    "doi",
    "doi_norm",
    "title",
    "abstract",
    "term",
    "discipline",
    "license",
    "license_unpaywall",
    "journal",
    "journal_norm",
    "source_db",
    "authors",
    "best_oa_location_url",
    "github",
    "zenodo",
    "osf",
    "pubmed_id",
    "repo_links",
    "code_link",
    "data_link",
    "preprint",
    "high_impact_reason",
    "dataset_urls",
    "dataset_repos",
    *OPENALEX_METADATA_TEXT_COLS,
    "corpus_rule",
    *DAS_TEXT_COLS,
]

BOOL_COLS = [
    "is_oa",
    "journal_is_oa",
    "preregistered",
    "high_impact_flag",
    "has_public_dataset",
    *OPENALEX_METADATA_BOOL_COLS,
    *REGISTRATION_FLAG_COLS,
    *CORPUS_FLAG_COLS,
    *DAS_BOOL_COLS,
]
NUM_COLS = ["open_science_score", "cited_by_count", "journal_impact_factor"]

CACHE_FIELDS = [
    "is_oa",
    "best_oa_location_url",
    "license_unpaywall",
    "zenodo",
    "osf",
    "github",
    "pubmed_id",
    "repo_links",
    "dataset_urls",
    "dataset_repos",
]

LLM_FIELDS = ["code_link", "data_link", "preregistered", "preprint"]
DOTENV_CANDIDATES = (".env", ".env.local", "configs/.env", "configs/.env.local")
GLOB_CHARS = set("*?[]")
CROSSREF_RELATION_TYPES = {"issupplementedby", "hasrelatedmaterial", "issourcedby"}


@dataclass
class PipelinePaths:
    output_dir: Path
    raw_csv: Path
    preview_csv: Path
    full_csv: Path
    high_impact_csv: Path
    enrich_cache: Path
    llm_cache: Path
    retrieval_slices_dir: Path
    openalex_metadata_cache: Path = Path("openalex_metadata_cache.jsonl")
    das_cache: Path = Path("das_cache.jsonl")


@dataclass
class PipelineConfig:
    discipline: str
    terms: List[str]
    years: List[int]
    query_window_months: int
    include_pubmed: bool
    pubmed_email: str
    pubmed_api_key: str
    pubmed_tool: str
    pubmed_delay_seconds: float
    pubmed_timeout_seconds: int
    pubmed_max_attempts: int
    pubmed_batch_size: int
    openalex_mailto: str
    openalex_api_key: str
    openalex_workers: int
    openalex_delay_seconds: float
    openalex_timeout_seconds: int
    openalex_max_attempts: int
    openalex_max_failures_per_query: int
    openalex_max_retry_after_seconds: int
    max_per_query: int
    refresh_openalex: bool
    force: bool
    unpaywall_snapshot: str
    crossref_relations: str
    disable_api_enrich: bool
    disable_dataset_search: bool
    api_concurrency: int
    api_delay_seconds: float
    max_api_lookups: int
    cache_flush_every: int
    embedding_top_k: int
    embedding_model: str
    embedding_batch_size: int
    embedding_device: str
    llm_provider: str
    llm_max_items: int
    llm_model: str
    llm_temperature: float
    ollama_base_url: str
    ollama_model: str
    llm_use_fulltext: bool
    fulltext_char_limit: int
    llm_max_fulltext_fetch: int
    preview_rows: int
    journal_metrics_csv: str
    impact_factor_threshold: float
    citation_percentile_threshold: float
    verbose: bool
    openalex_budget_wait_max_hours: float = 30.0
    backfill_openalex_metadata: bool = False
    openalex_metadata_min_budget_remaining: int = 150
    das_audit_sample_per_year: int = 0
    das_audit_workers: int = 5
    das_audit_delay_seconds: float = 0.1
    das_audit_timeout_seconds: int = 90
    das_audit_seed: int = 2026


def parse_dotenv_file(path: Path) -> Dict[str, str]:
    entries: Dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export ") :].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                    continue
                value = value.strip()
                if value and value[0] in {"'", '"'} and value[-1:] == value[0]:
                    value = value[1:-1]
                elif " #" in value:
                    value = value.split(" #", 1)[0].rstrip()
                entries[key] = value
    except Exception:
        return {}
    return entries


def load_project_env(project_root: Path) -> List[Path]:
    merged: Dict[str, str] = {}
    loaded: List[Path] = []
    for relative_path in DOTENV_CANDIDATES:
        candidate = project_root / relative_path
        if not candidate.is_file():
            continue
        parsed = parse_dotenv_file(candidate)
        if not parsed:
            continue
        merged.update(parsed)
        loaded.append(candidate)

    for key, value in merged.items():
        os.environ.setdefault(key, value)
    return loaded


def has_glob_chars(value: str) -> bool:
    return any(ch in value for ch in GLOB_CHARS)


def resolve_project_path(value: str, project_root: Path) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    expanded = os.path.expanduser(raw)
    if os.path.isabs(expanded):
        return os.path.normpath(expanded)
    return str((project_root / expanded).resolve())


def resolve_snapshot_source(value: str, project_root: Path) -> str:
    resolved = resolve_project_path(value, project_root)
    if not resolved or has_glob_chars(resolved):
        return resolved

    path = Path(resolved)
    if path.is_dir():
        parquet_matches = sorted(path.glob("*.parquet"))
        if parquet_matches:
            return str(path / "*.parquet")
        pq_matches = sorted(path.glob("*.pq"))
        if pq_matches:
            return str(path / "*.pq")
        return str(path / "*.parquet")
    return resolved


def list_snapshot_matches(source: str) -> List[str]:
    if not source:
        return []
    if has_glob_chars(source):
        return sorted(glob.glob(source))
    path = Path(source).expanduser()
    if path.is_dir():
        matches = sorted(str(p.resolve()) for p in path.glob("*.parquet"))
        if matches:
            return matches
        return sorted(str(p.resolve()) for p in path.glob("*.pq"))
    if path.exists():
        return [str(path.resolve())]
    return []


def parse_args(script_root: Optional[Path] = None) -> Tuple[PipelineConfig, PipelinePaths]:
    script_root = script_root or Path(__file__).resolve().parents[1]
    default_output = script_root / "data"

    parser = argparse.ArgumentParser(description="Search and enrich stroke open-science works.")
    parser.add_argument("--output-dir", default=str(default_output), help="Output directory")
    parser.add_argument("--raw-csv", default="raw_openalex_articles.csv")
    parser.add_argument("--preview-csv", default="enriched_preview.csv")
    parser.add_argument("--full-csv", default="fully_enriched.csv")
    parser.add_argument("--high-impact-csv", default="high_impact_subset.csv")
    parser.add_argument("--enrich-cache", default="enrich_cache.json")
    parser.add_argument("--llm-cache", default="llm_cache.json")

    parser.add_argument("--terms", nargs="*", default=DEFAULT_TERMS)
    parser.add_argument("--discipline", default="stroke", help="Cohort label to store in output rows")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=dt.datetime.now().year)
    parser.add_argument(
        "--query-window-months",
        type=int,
        default=12,
        help="Split retrieval into smaller month windows per year (for example 6 = Jan-Jun and Jul-Dec)",
    )
    parser.add_argument("--include-pubmed", action="store_true")
    parser.add_argument("--pubmed-email", default=os.getenv("NCBI_EMAIL", os.getenv("PUBMED_EMAIL", "")))
    parser.add_argument("--pubmed-api-key", default=os.getenv("NCBI_API_KEY", ""))
    parser.add_argument("--pubmed-tool", default=os.getenv("NCBI_TOOL", "stroke-open-science"))
    parser.add_argument("--pubmed-delay-seconds", type=float, default=0.34)
    parser.add_argument("--pubmed-timeout-seconds", type=int, default=20)
    parser.add_argument("--pubmed-max-attempts", type=int, default=3)
    parser.add_argument("--pubmed-batch-size", type=int, default=200)
    parser.add_argument("--openalex-mailto", default=os.getenv("OPENALEX_MAILTO", ""))
    parser.add_argument("--openalex-api-key", default=os.getenv("OPENALEX_API_KEY", ""))
    parser.add_argument("--openalex-workers", type=int, default=6)
    parser.add_argument("--openalex-delay-seconds", type=float, default=0.35)
    parser.add_argument("--openalex-timeout-seconds", type=int, default=20)
    parser.add_argument("--openalex-max-attempts", type=int, default=3)
    parser.add_argument("--openalex-max-failures-per-query", type=int, default=3)
    parser.add_argument("--openalex-max-retry-after-seconds", type=int, default=60)
    parser.add_argument(
        "--openalex-budget-wait-max-hours",
        type=float,
        default=30.0,
        help=(
            "When the OpenAlex API key's daily budget is exhausted, sleep until the budget resets "
            "(00:00 UTC) and resume the same cursor, as long as the wait is at most this many hours. "
            "Longer waits stop the slice early and leave a .partial.csv to resume on the next run."
        ),
    )
    parser.add_argument("--max-per-query", type=int, default=0, help="0 means unlimited")
    parser.add_argument("--refresh-openalex", action="store_true")
    parser.add_argument("--force", action="store_true", help="Overwrite existing full output")
    parser.add_argument(
        "--backfill-openalex-metadata",
        action="store_true",
        help=(
            "For an existing retrieval dataset that predates the work-metadata columns (work_type, "
            "oa_status, locations, countries, funders), look the DOIs up on OpenAlex in batches of 50 "
            "(filter=doi:a|b|...). Results are cached in openalex_metadata_cache.jsonl and the run is "
            "resumable. New retrievals capture these fields directly and do not need this flag."
        ),
    )
    parser.add_argument(
        "--openalex-metadata-min-budget-remaining",
        type=int,
        default=150,
        help=(
            "During the metadata backfill, pause for the daily budget reset once X-RateLimit-Remaining "
            "drops below this many requests (keeps headroom for other OpenAlex jobs)."
        ),
    )

    parser.add_argument(
        "--unpaywall-snapshot",
        default=os.getenv("UNPAYWALL_SNAPSHOT", str(default_output / "unpaywall" / "*.parquet")),
    )
    parser.add_argument(
        "--crossref-relations",
        default=os.getenv("CROSSREF_RELATIONS", str(default_output / "crossref" / "*.parquet")),
    )

    parser.add_argument("--disable-api-enrich", action="store_true")
    parser.add_argument("--disable-dataset-search", action="store_true",
                        help="Skip dataset repository API enrichment (DataCite, Dryad, Figshare)")
    parser.add_argument("--api-concurrency", type=int, default=12)
    parser.add_argument("--api-delay-seconds", type=float, default=0.35)
    parser.add_argument("--max-api-lookups", type=int, default=15000)
    parser.add_argument("--cache-flush-every", type=int, default=250)

    parser.add_argument("--embedding-top-k", type=int, default=5000)
    parser.add_argument("--embedding-model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--embedding-batch-size", type=int, default=256)
    parser.add_argument(
        "--embedding-device",
        choices=["auto", "cpu", "cuda", "mps"],
        default=os.getenv("EMBEDDING_DEVICE", "auto"),
        help="Device for SentenceTransformer embeddings",
    )

    parser.add_argument("--llm-provider", choices=["openai", "ollama"], default=os.getenv("LLM_PROVIDER", "openai"))
    parser.add_argument("--llm-max-items", type=int, default=1000)
    parser.add_argument("--llm-model", default=os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini"))
    parser.add_argument("--llm-temperature", type=float, default=0.0)
    parser.add_argument("--ollama-base-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    parser.add_argument("--ollama-model", default=os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
    parser.add_argument("--llm-use-fulltext", action="store_true")
    parser.add_argument("--fulltext-char-limit", type=int, default=12000)
    parser.add_argument("--llm-max-fulltext-fetch", type=int, default=200)

    parser.add_argument(
        "--das-audit-sample-per-year",
        type=int,
        default=0,
        help=(
            "Data-availability-statement audit: per publication year, sample this many in-corpus "
            "articles with full text in Europe PMC, fetch their JATS XML and classify the statement. "
            "0 disables the stage. Results are cached in das_cache.jsonl (resumable)."
        ),
    )
    parser.add_argument("--das-audit-workers", type=int, default=5, help="Parallel Europe PMC full-text fetches")
    parser.add_argument("--das-audit-delay-seconds", type=float, default=0.1, help="Per-worker delay between Europe PMC requests")
    parser.add_argument("--das-audit-timeout-seconds", type=int, default=90)
    parser.add_argument("--das-audit-seed", type=int, default=2026, help="Seed for the per-year DAS audit sample")

    parser.add_argument("--journal-metrics-csv", default=str(script_root / "configs" / "journal_metrics.csv"))
    parser.add_argument("--impact-factor-threshold", type=float, default=10.0)
    parser.add_argument("--citation-percentile-threshold", type=float, default=90.0)

    parser.add_argument("--preview-rows", type=int, default=50000)
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()

    years = list(range(args.start_year, args.end_year + 1))
    if not years:
        raise ValueError("Year range is empty")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = PipelinePaths(
        output_dir=output_dir,
        raw_csv=output_dir / args.raw_csv,
        preview_csv=output_dir / args.preview_csv,
        full_csv=output_dir / args.full_csv,
        high_impact_csv=output_dir / args.high_impact_csv,
        enrich_cache=output_dir / args.enrich_cache,
        llm_cache=output_dir / args.llm_cache,
        retrieval_slices_dir=output_dir / "retrieval_slices",
        openalex_metadata_cache=output_dir / "openalex_metadata_cache.jsonl",
        das_cache=output_dir / "das_cache.jsonl",
    )

    cfg = PipelineConfig(
        discipline=args.discipline.strip().lower(),
        terms=[t.strip() for t in args.terms if t and t.strip()],
        years=years,
        query_window_months=min(12, max(1, args.query_window_months)),
        include_pubmed=args.include_pubmed,
        pubmed_email=args.pubmed_email.strip() or args.openalex_mailto.strip(),
        pubmed_api_key=args.pubmed_api_key.strip(),
        pubmed_tool=args.pubmed_tool.strip() or "stroke-open-science",
        pubmed_delay_seconds=max(0.0, args.pubmed_delay_seconds),
        pubmed_timeout_seconds=max(5, args.pubmed_timeout_seconds),
        pubmed_max_attempts=max(1, args.pubmed_max_attempts),
        pubmed_batch_size=max(1, args.pubmed_batch_size),
        openalex_mailto=args.openalex_mailto.strip(),
        openalex_api_key=args.openalex_api_key.strip(),
        openalex_workers=max(1, args.openalex_workers),
        openalex_delay_seconds=max(0.0, args.openalex_delay_seconds),
        openalex_timeout_seconds=max(5, args.openalex_timeout_seconds),
        openalex_max_attempts=max(1, args.openalex_max_attempts),
        openalex_max_failures_per_query=max(1, args.openalex_max_failures_per_query),
        openalex_max_retry_after_seconds=max(5, args.openalex_max_retry_after_seconds),
        openalex_budget_wait_max_hours=max(0.0, args.openalex_budget_wait_max_hours),
        backfill_openalex_metadata=bool(args.backfill_openalex_metadata),
        openalex_metadata_min_budget_remaining=max(0, args.openalex_metadata_min_budget_remaining),
        das_audit_sample_per_year=max(0, args.das_audit_sample_per_year),
        das_audit_workers=max(1, args.das_audit_workers),
        das_audit_delay_seconds=max(0.0, args.das_audit_delay_seconds),
        das_audit_timeout_seconds=max(10, args.das_audit_timeout_seconds),
        das_audit_seed=int(args.das_audit_seed),
        max_per_query=max(0, args.max_per_query),
        refresh_openalex=args.refresh_openalex,
        force=args.force,
        unpaywall_snapshot=resolve_snapshot_source(args.unpaywall_snapshot, script_root),
        crossref_relations=resolve_snapshot_source(args.crossref_relations, script_root),
        disable_api_enrich=args.disable_api_enrich,
        disable_dataset_search=args.disable_dataset_search,
        api_concurrency=max(1, args.api_concurrency),
        api_delay_seconds=max(0.0, args.api_delay_seconds),
        max_api_lookups=max(0, args.max_api_lookups),
        cache_flush_every=max(1, args.cache_flush_every),
        embedding_top_k=max(0, args.embedding_top_k),
        embedding_model=args.embedding_model,
        embedding_batch_size=max(1, args.embedding_batch_size),
        embedding_device=args.embedding_device.lower().strip(),
        llm_provider=args.llm_provider,
        llm_max_items=max(0, args.llm_max_items),
        llm_model=args.llm_model,
        llm_temperature=args.llm_temperature,
        ollama_base_url=args.ollama_base_url.rstrip("/"),
        ollama_model=args.ollama_model,
        llm_use_fulltext=args.llm_use_fulltext,
        fulltext_char_limit=max(1000, args.fulltext_char_limit),
        llm_max_fulltext_fetch=max(0, args.llm_max_fulltext_fetch),
        preview_rows=max(0, args.preview_rows),
        journal_metrics_csv=resolve_project_path(args.journal_metrics_csv, script_root),
        impact_factor_threshold=max(0.0, args.impact_factor_threshold),
        citation_percentile_threshold=min(99.9, max(0.0, args.citation_percentile_threshold)),
        verbose=args.verbose,
    )

    return cfg, paths


def sanitize_filename_fragment(value: str, fallback: str = "slice") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    text = re.sub(r"_+", "_", text).strip("._")
    return text[:96] or fallback


def month_end(year: int, month: int) -> dt.date:
    if month >= 12:
        return dt.date(year, 12, 31)
    return dt.date(year, month + 1, 1) - dt.timedelta(days=1)


def build_query_date_windows(years: Sequence[int], months_per_window: int) -> List[Tuple[dt.date, dt.date]]:
    windows: List[Tuple[dt.date, dt.date]] = []
    step = min(12, max(1, int(months_per_window or 12)))
    for year in years:
        month = 1
        while month <= 12:
            end_month = min(12, month + step - 1)
            windows.append((dt.date(year, month, 1), month_end(year, end_month)))
            month = end_month + 1
    return windows


def retrieval_slice_path(paths: PipelinePaths, source: str, term: str, start_date: dt.date, end_date: dt.date) -> Path:
    term_slug = sanitize_filename_fragment(term, fallback=source)
    range_slug = f"{start_date.isoformat()}__{end_date.isoformat()}"
    return paths.retrieval_slices_dir / sanitize_filename_fragment(source, fallback="source") / f"{term_slug}__{range_slug}.csv"


def retrieval_slice_partial_path(slice_path: Path) -> Path:
    """Path used for a slice whose retrieval stopped early (never treated as a complete cache)."""
    return slice_path.with_name(f"{slice_path.stem}.partial{slice_path.suffix}")


def assign_source_db(df: pd.DataFrame, source_db: str) -> pd.DataFrame:
    source_value = str(source_db or "").strip().lower()
    if not source_value:
        return df
    if "source_db" not in df.columns:
        df["source_db"] = source_value
        return df
    current = df["source_db"].fillna("").astype(str).str.strip().str.lower()
    missing = current.eq("")
    if missing.any():
        df.loc[missing, "source_db"] = source_value
    return df


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def build_requests_session(cfg: PipelineConfig) -> requests.Session:
    # Keep transport retries off; retries/backoff are handled explicitly in safe_get_json.
    adapter = HTTPAdapter(max_retries=0, pool_connections=128, pool_maxsize=128)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "stroke-open-science/1.1"})
    return session


def normalize_doi(doi: Any) -> str:
    if doi is None:
        return ""
    value = str(doi).strip()
    if not value or value.lower() in {"nan", "none"}:
        return ""
    value = re.sub(r"^doi:\s*", "", value, flags=re.IGNORECASE).strip()
    value = DOI_PREFIX_RE.sub("", value)
    return value.lower().strip()


def normalize_journal_name(name: Any) -> str:
    if name is None:
        return ""
    text = str(name).strip().lower()
    text = WS_RE.sub(" ", text)
    return text


def normalize_crossref_identifier(identifier: Any, id_type: Any = "") -> str:
    raw = str(identifier or "").strip()
    if not raw:
        return ""
    if URL_RE.match(raw):
        return raw

    normalized_doi = normalize_doi(raw)
    id_type_norm = str(id_type or "").strip().lower()
    if normalized_doi.startswith("10.") or id_type_norm == "doi":
        return f"https://doi.org/{normalized_doi}"
    return ""


def extract_crossref_relation_links(message: Dict[str, Any]) -> List[str]:
    relation = message.get("relation") or {}
    if not isinstance(relation, dict):
        return []

    links: List[str] = []
    seen: set[str] = set()
    for relation_type, entries in relation.items():
        relation_key = re.sub(r"[^a-z]", "", str(relation_type or "").lower())
        if relation_key not in CROSSREF_RELATION_TYPES:
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            link = normalize_crossref_identifier(entry.get("id"), entry.get("id-type"))
            if link and link not in seen:
                seen.add(link)
                links.append(link)
    return links


def reconstruct_abstract(inverted_index: Any) -> str:
    if not isinstance(inverted_index, dict) or not inverted_index:
        return ""

    max_pos = -1
    for positions in inverted_index.values():
        if isinstance(positions, list) and positions:
            max_pos = max(max_pos, max(positions))
    if max_pos < 0:
        return ""

    tokens: List[str] = [""] * (max_pos + 1)
    for token, positions in inverted_index.items():
        if not isinstance(positions, list):
            continue
        for pos in positions:
            if isinstance(pos, int) and 0 <= pos <= max_pos:
                tokens[pos] = str(token)

    return " ".join(tok for tok in tokens if tok)


def extract_pubmed_id(work: Dict[str, Any]) -> str:
    ids = work.get("ids") or {}
    pmid = ids.get("pmid") or ""
    if not pmid:
        return ""
    pmid = str(pmid).strip().rstrip("/")
    if pmid.startswith("http"):
        pmid = pmid.split("/")[-1]
    return pmid


def extract_authors(work: Dict[str, Any]) -> str:
    names: List[str] = []
    for authorship in work.get("authorships") or []:
        author = (authorship or {}).get("author") or {}
        display_name = str(author.get("display_name") or "").strip()
        if display_name:
            names.append(display_name)
    return "; ".join(names)


def safe_get_json(
    session: requests.Session,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
    max_attempts: int = 3,
    max_retry_after_seconds: Optional[float] = None,
    request_label: str = "",
    raise_on_budget_exhausted: bool = False,
) -> Optional[Dict[str, Any]]:
    for attempt in range(max_attempts):
        try:
            resp = session.get(url, params=params, timeout=timeout)
            if resp.status_code == 429:
                if raise_on_budget_exhausted:
                    rate_limit = parse_openalex_rate_limit_headers(getattr(resp, "headers", None))
                    remaining = openalex_requests_remaining(rate_limit)
                    if remaining is not None and remaining <= 0:
                        raise OpenAlexBudgetExhausted(rate_limit)
                retry_after = resp.headers.get("Retry-After")
                retry_after_s: Optional[float] = None
                try:
                    retry_after_s = float(retry_after) if retry_after else None
                except Exception:
                    retry_after_s = None

                if (
                    retry_after_s is not None
                    and max_retry_after_seconds is not None
                    and retry_after_s > max_retry_after_seconds
                ):
                    if request_label:
                        logging.warning(
                            "Rate limited on %s with Retry-After %.1fs > cap %.1fs; failing fast.",
                            request_label,
                            retry_after_s,
                            max_retry_after_seconds,
                        )
                    return None

                sleep_s = retry_after_s if retry_after_s is not None else min(30.0, 5.0 + (attempt * 3.0))
                if max_retry_after_seconds is not None:
                    sleep_s = min(sleep_s, max_retry_after_seconds)
                if request_label:
                    logging.warning(
                        "Rate limited on %s (attempt %d/%d). Sleeping %.1fs",
                        request_label,
                        attempt + 1,
                        max_attempts,
                        sleep_s,
                    )
                time.sleep(sleep_s)
                continue
            if resp.status_code >= 500:
                if request_label:
                    logging.warning(
                        "Server error %s on %s (attempt %d/%d)",
                        resp.status_code,
                        request_label,
                        attempt + 1,
                        max_attempts,
                    )
                time.sleep(min(30.0, 2.0 ** attempt))
                continue
            if resp.status_code >= 400:
                if request_label:
                    logging.warning(
                        "HTTP %s on %s (not retrying).",
                        resp.status_code,
                        request_label,
                    )
                return None
            return resp.json()
        except OpenAlexBudgetExhausted:
            raise
        except Exception:
            if request_label:
                logging.warning(
                    "Request exception on %s (attempt %d/%d)",
                    request_label,
                    attempt + 1,
                    max_attempts,
                )
            if attempt == max_attempts - 1:
                break
            time.sleep(min(30.0, 2.0 ** attempt))
    return None


def safe_get_text(
    session: requests.Session,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
    max_attempts: int = 3,
    max_retry_after_seconds: Optional[float] = None,
    request_label: str = "",
) -> Optional[str]:
    for attempt in range(max_attempts):
        try:
            resp = session.get(url, params=params, timeout=timeout)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                retry_after_s: Optional[float] = None
                try:
                    retry_after_s = float(retry_after) if retry_after else None
                except Exception:
                    retry_after_s = None

                if (
                    retry_after_s is not None
                    and max_retry_after_seconds is not None
                    and retry_after_s > max_retry_after_seconds
                ):
                    if request_label:
                        logging.warning(
                            "Rate limited on %s with Retry-After %.1fs > cap %.1fs; failing fast.",
                            request_label,
                            retry_after_s,
                            max_retry_after_seconds,
                        )
                    return None

                sleep_s = retry_after_s if retry_after_s is not None else min(30.0, 5.0 + (attempt * 3.0))
                if max_retry_after_seconds is not None:
                    sleep_s = min(sleep_s, max_retry_after_seconds)
                if request_label:
                    logging.warning(
                        "Rate limited on %s (attempt %d/%d). Sleeping %.1fs",
                        request_label,
                        attempt + 1,
                        max_attempts,
                        sleep_s,
                    )
                time.sleep(sleep_s)
                continue
            if resp.status_code >= 500:
                if request_label:
                    logging.warning(
                        "Server error %s on %s (attempt %d/%d)",
                        resp.status_code,
                        request_label,
                        attempt + 1,
                        max_attempts,
                    )
                time.sleep(min(30.0, 2.0 ** attempt))
                continue
            if resp.status_code >= 400:
                if request_label:
                    logging.warning(
                        "HTTP %s on %s (not retrying).",
                        resp.status_code,
                        request_label,
                    )
                return None
            return resp.text
        except Exception:
            if request_label:
                logging.warning(
                    "Request exception on %s (attempt %d/%d)",
                    request_label,
                    attempt + 1,
                    max_attempts,
                )
            if attempt == max_attempts - 1:
                break
            time.sleep(min(30.0, 2.0 ** attempt))
    return None


def safe_post_json(
    session: requests.Session,
    url: str,
    payload: Dict[str, Any],
    timeout: int = 120,
    max_attempts: int = 4,
) -> Optional[Dict[str, Any]]:
    for attempt in range(max_attempts):
        try:
            resp = session.post(url, json=payload, timeout=timeout)
            if resp.status_code in {429, 500, 502, 503, 504}:
                retry_after = resp.headers.get("Retry-After")
                sleep_s = float(retry_after) if retry_after else min(20.0, 2.0 ** attempt)
                time.sleep(sleep_s)
                continue
            if resp.status_code >= 400:
                return None
            return resp.json()
        except Exception:
            if attempt == max_attempts - 1:
                break
            time.sleep(min(20.0, 2.0 ** attempt))
    return None


OPENALEX_BUDGET_RESET_MARGIN_SECONDS = 60.0
OPENALEX_BUDGET_SLEEP_CHUNK_SECONDS = 300.0

# Header / payload names that carry the same quantity. OpenAlex's metered API returns
# ``x-ratelimit-*`` headers on every response, while the ``/rate-limit`` endpoint has used
# ``credits_remaining`` and ``daily_requests_remaining`` in its JSON body. Read all of them.
OPENALEX_REMAINING_KEYS = (
    "x-ratelimit-remaining",
    "daily_requests_remaining",
    "credits_remaining",
    "requests_remaining",
    "remaining",
)
OPENALEX_RESET_SECONDS_KEYS = (
    "x-ratelimit-reset",
    "resets_in_seconds",
    "reset_in_seconds",
    "reset",
)
OPENALEX_RESET_AT_KEYS = ("resets_at", "reset_at")


class OpenAlexBudgetExhausted(RuntimeError):
    """Raised by safe_get_json when a 429 carries headers showing the daily budget is spent."""

    def __init__(self, rate_limit: Optional[Dict[str, Any]] = None) -> None:
        self.rate_limit: Dict[str, Any] = dict(rate_limit or {})
        super().__init__("OpenAlex API key daily budget exhausted")


def parse_openalex_rate_limit_headers(headers: Any) -> Dict[str, Any]:
    """Extract the OpenAlex ``x-ratelimit-*`` headers (case-insensitively) into a plain dict."""
    out: Dict[str, Any] = {}
    if not headers:
        return out
    try:
        items = list(headers.items())
    except Exception:
        return out
    for name, value in items:
        key = str(name or "").strip().lower()
        if key.startswith("x-ratelimit-") or key == "retry-after":
            out[key] = value
    return out


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            return None
        return int(float(text))
    except Exception:
        return None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            return None
        return float(text)
    except Exception:
        return None


def openalex_requests_remaining(rate_limit: Optional[Dict[str, Any]]) -> Optional[int]:
    """Requests left in the daily budget, whichever header/field name reports it (None if unknown)."""
    if not rate_limit:
        return None
    lowered = {str(k).strip().lower(): v for k, v in rate_limit.items()}
    # Prepaid credit is drawn after the free daily budget, so a near-zero daily counter is not
    # exhaustion while prepaid balance remains: report "unknown" so callers neither stop nor wait.
    for key in ("x-ratelimit-prepaid-remaining-usd", "prepaid_remaining_usd", "prepaid_usd_remaining"):
        prepaid = _coerce_float(lowered.get(key))
        if prepaid is not None and prepaid > 0.05:
            return None
    for key in OPENALEX_REMAINING_KEYS:
        if key in lowered:
            parsed = _coerce_int(lowered[key])
            if parsed is not None:
                return parsed
    usd = _coerce_float(lowered.get("x-ratelimit-remaining-usd"))
    if usd is not None:
        return 0 if usd <= 0 else None
    return None


def seconds_until_next_utc_midnight(now: Optional[dt.datetime] = None) -> float:
    """Seconds from ``now`` (aware or naive UTC) until the next 00:00 UTC budget reset."""
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    else:
        now = now.astimezone(dt.timezone.utc)
    next_midnight = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc)
    return max(0.0, (next_midnight - now).total_seconds())


def openalex_reset_seconds(rate_limit: Optional[Dict[str, Any]], now: Optional[dt.datetime] = None) -> float:
    """Seconds until the budget resets: ``x-ratelimit-reset``/``resets_in_seconds`` if present,
    else an ISO ``resets_at`` timestamp, else the time to the next 00:00 UTC."""
    lowered = {str(k).strip().lower(): v for k, v in (rate_limit or {}).items()}
    for key in OPENALEX_RESET_SECONDS_KEYS:
        if key in lowered:
            parsed = _coerce_float(lowered[key])
            if parsed is not None and parsed >= 0:
                return parsed
    for key in OPENALEX_RESET_AT_KEYS:
        raw = str(lowered.get(key) or "").strip()
        if raw:
            try:
                reset_at = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if reset_at.tzinfo is None:
                    reset_at = reset_at.replace(tzinfo=dt.timezone.utc)
                current = now or dt.datetime.now(dt.timezone.utc)
                if current.tzinfo is None:
                    current = current.replace(tzinfo=dt.timezone.utc)
                return max(0.0, (reset_at - current).total_seconds())
            except Exception:
                pass
    return seconds_until_next_utc_midnight(now)


def compute_openalex_budget_wait_seconds(
    rate_limit: Optional[Dict[str, Any]],
    now: Optional[dt.datetime] = None,
    margin_seconds: float = OPENALEX_BUDGET_RESET_MARGIN_SECONDS,
) -> float:
    """How long to sleep before retrying after budget exhaustion (reset time plus a safety margin)."""
    return openalex_reset_seconds(rate_limit, now) + max(0.0, margin_seconds)


def wait_for_openalex_budget_reset(
    rate_limit: Optional[Dict[str, Any]],
    max_wait_hours: float,
    context: str = "",
    sleep_fn: Optional[Callable[[float], None]] = None,
) -> bool:
    """Sleep until the OpenAlex daily budget resets. Returns False (without sleeping) when the
    required wait exceeds ``max_wait_hours``; the caller should then stop early."""
    sleep = sleep_fn or time.sleep
    wait_seconds = compute_openalex_budget_wait_seconds(rate_limit)
    max_wait_seconds = max(0.0, float(max_wait_hours)) * 3600.0
    label = f" ({context})" if context else ""
    if wait_seconds > max_wait_seconds:
        logging.error(
            "OpenAlex API key budget exhausted%s; reset in ~%.0f min exceeds --openalex-budget-wait-max-hours=%.2f. "
            "Stopping early; re-run after the budget resets to resume.",
            label,
            wait_seconds / 60.0,
            max_wait_hours,
        )
        return False
    resume_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=wait_seconds)
    logging.warning(
        "OpenAlex API key budget exhausted%s. Keeping the key and sleeping %.0f min until ~%s UTC "
        "(reset + %.0fs margin), then resuming the same cursor.",
        label,
        wait_seconds / 60.0,
        resume_at.strftime("%Y-%m-%d %H:%M"),
        OPENALEX_BUDGET_RESET_MARGIN_SECONDS,
    )
    remaining = wait_seconds
    while remaining > 0:
        chunk = min(remaining, OPENALEX_BUDGET_SLEEP_CHUNK_SECONDS)
        sleep(chunk)
        remaining -= chunk
        if remaining > 0:
            logging.info("Waiting for OpenAlex budget reset%s: ~%.0f min left.", label, remaining / 60.0)
    return True


def inspect_openalex_rate_limit(
    session: requests.Session,
    api_key: str,
    timeout_seconds: int,
) -> Optional[Dict[str, Any]]:
    """Query /rate-limit and merge its JSON body with the response's x-ratelimit-* headers so
    callers can use ``openalex_requests_remaining`` / ``openalex_reset_seconds`` uniformly."""
    api_key = str(api_key or "").strip()
    if not api_key:
        return None

    try:
        resp = session.get(
            "https://api.openalex.org/rate-limit",
            params={"api_key": api_key},
            timeout=max(10, timeout_seconds),
        )
    except Exception:
        logging.warning("Request exception on OpenAlex rate-limit check.")
        return None

    merged: Dict[str, Any] = parse_openalex_rate_limit_headers(getattr(resp, "headers", None))
    if resp.status_code < 400:
        try:
            payload = resp.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            body = payload.get("rate_limit") if isinstance(payload.get("rate_limit"), dict) else payload
            for key, value in body.items():
                merged.setdefault(str(key), value)
    elif resp.status_code != 429:
        logging.warning("HTTP %s on OpenAlex rate-limit check.", resp.status_code)
    return merged or None


def ensure_openalex_budget_available(cfg: PipelineConfig, session: requests.Session) -> None:
    """At startup: if the configured API key has no budget left, wait for the reset (bounded by
    ``openalex_budget_wait_max_hours``). The key is never dropped; keyless mode is only used when
    no key is configured at all."""
    if not cfg.openalex_api_key:
        return

    rate_limit = inspect_openalex_rate_limit(session, cfg.openalex_api_key, cfg.openalex_timeout_seconds)
    remaining = openalex_requests_remaining(rate_limit)
    if remaining is None:
        return

    if remaining > 0:
        logging.info("OpenAlex requests remaining in today's budget on current API key: %d", remaining)
        return

    wait_for_openalex_budget_reset(rate_limit, cfg.openalex_budget_wait_max_hours, context="startup check")


# Backwards-compatible alias (the old behaviour dropped the key; it now waits instead).
maybe_disable_exhausted_openalex_key = ensure_openalex_budget_available


def ncbi_common_params(email: str, api_key: str, tool: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key
    if tool:
        params["tool"] = tool
    return params


def pubmed_query_for_term_date_range(term: str, start_date: dt.date, end_date: dt.date) -> str:
    cleaned_term = WS_RE.sub(" ", str(term or "").replace('"', " ")).strip()
    return (
        f'("{cleaned_term}"[Title]) AND '
        f'("{start_date.strftime("%Y/%m/%d")}"[Date - Publication] : '
        f'"{end_date.strftime("%Y/%m/%d")}"[Date - Publication])'
    )


def extract_pubmed_authors(article: ET.Element) -> str:
    names: List[str] = []
    for author in article.findall(".//AuthorList/Author"):
        collective = (author.findtext("CollectiveName") or "").strip()
        if collective:
            names.append(collective)
            continue

        last_name = (author.findtext("LastName") or "").strip()
        fore_name = (author.findtext("ForeName") or "").strip()
        initials = (author.findtext("Initials") or "").strip()
        if last_name and fore_name:
            names.append(f"{fore_name} {last_name}")
        elif last_name and initials:
            names.append(f"{initials} {last_name}")
        elif last_name:
            names.append(last_name)
    return "; ".join(name for name in names if name)


def extract_pubmed_year(article: ET.Element, fallback_year: int, min_year: int, max_year: int) -> int:
    candidates = [
        article.findtext(".//Article/ArticleDate[@DateType='Electronic']/Year"),
        article.findtext(".//Article/ArticleDate/Year"),
        article.findtext(".//JournalIssue/PubDate/Year"),
        article.findtext(".//PubDate/Year"),
        article.findtext(".//JournalIssue/PubDate/MedlineDate"),
        article.findtext(".//PubDate/MedlineDate"),
    ]
    extracted_years: List[int] = []
    for candidate in candidates:
        match = re.search(r"\b(19|20)\d{2}\b", str(candidate or ""))
        if not match:
            continue
        try:
            extracted_years.append(int(match.group(0)))
        except Exception:
            continue

    for year in extracted_years:
        if min_year <= year <= max_year:
            return year
    return int(fallback_year)


def extract_pubmed_abstract(article: ET.Element) -> str:
    abstract_parts: List[str] = []
    for abstract_text in article.findall(".//Abstract/AbstractText"):
        label = (abstract_text.attrib.get("Label") or "").strip()
        text = " ".join(part.strip() for part in abstract_text.itertext() if str(part).strip())
        if not text:
            continue
        if label:
            abstract_parts.append(f"{label}: {text}")
        else:
            abstract_parts.append(text)
    return " ".join(abstract_parts).strip()


def pubmed_article_to_record(
    article: ET.Element,
    term: str,
    discipline: str,
    fallback_year: int,
    min_year: int,
    max_year: int,
) -> Dict[str, Any]:
    pmid = (article.findtext(".//MedlineCitation/PMID") or "").strip()
    article_title_el = article.find(".//ArticleTitle")
    article_title = " ".join(part.strip() for part in article_title_el.itertext() if str(part).strip()) if article_title_el is not None else ""
    abstract = extract_pubmed_abstract(article)
    journal = (article.findtext(".//Journal/Title") or "").strip()

    doi = ""
    for path in [
        ".//PubmedData/ArticleIdList/ArticleId[@IdType='doi']",
        ".//Article/ELocationID[@EIdType='doi']",
    ]:
        doi = normalize_doi(article.findtext(path) or "")
        if doi:
            break

    pmcid = ""
    for path in [
        ".//PubmedData/ArticleIdList/ArticleId[@IdType='pmc']",
        ".//PubmedData/ArticleIdList/ArticleId[@IdType='pmcid']",
    ]:
        raw_pmcid = (article.findtext(path) or "").strip()
        if raw_pmcid:
            pmcid = raw_pmcid.upper()
            if not pmcid.startswith("PMC"):
                pmcid = f"PMC{pmcid}"
            break

    best_oa_location_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else ""
    year = extract_pubmed_year(article, fallback_year, min_year, max_year)

    return {
        "id": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        "doi": doi,
        "title": article_title,
        "abstract": abstract,
        "year": year,
        "term": term,
        "discipline": discipline,
        "is_oa": bool(best_oa_location_url),
        "license": "",
        "license_unpaywall": "",
        "journal": journal,
        "journal_norm": normalize_journal_name(journal),
        "journal_is_oa": pd.NA,
        "source_db": "pubmed",
        "authors": extract_pubmed_authors(article),
        "best_oa_location_url": best_oa_location_url,
        "cited_by_count": pd.NA,
        "github": "",
        "zenodo": "",
        "osf": "",
        "pubmed_id": pmid,
        "repo_links": "",
        "code_link": "",
        "data_link": "",
        "preregistered": pd.NA,
        "preprint": "",
        "journal_impact_factor": pd.NA,
        "high_impact_flag": False,
        "high_impact_reason": "",
    }


def search_pubmed_term_date_range(
    term: str,
    start_date: dt.date,
    end_date: dt.date,
    discipline: str,
    session: requests.Session,
    email: str,
    api_key: str,
    tool: str,
    delay_seconds: float,
    timeout_seconds: int,
    max_attempts: int,
    batch_size: int,
    max_records: Optional[int],
) -> List[Dict[str, Any]]:
    base_params = ncbi_common_params(email, api_key, tool)
    range_label = f"{start_date.isoformat()}..{end_date.isoformat()}"
    search_params: Dict[str, Any] = {
        "db": "pubmed",
        "term": pubmed_query_for_term_date_range(term, start_date, end_date),
        "retmode": "json",
        "retmax": 0,
        "usehistory": "y",
        "sort": "pub date",
    }
    search_params.update(base_params)

    payload = safe_get_json(
        session,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params=search_params,
        timeout=timeout_seconds,
        max_attempts=max_attempts,
        max_retry_after_seconds=60.0,
        request_label=f"PubMed term='{term}' range={range_label} esearch",
    )
    if not payload:
        return []

    esearch = payload.get("esearchresult") or {}
    try:
        count = int(esearch.get("count") or 0)
    except Exception:
        count = 0
    query_key = str(esearch.get("querykey") or "").strip()
    webenv = str(esearch.get("webenv") or "").strip()
    if count <= 0 or not query_key or not webenv:
        logging.info("PubMed done term='%s' range=%s: 0 records across 0 batches", term, range_label)
        return []

    target_count = min(count, max_records) if max_records is not None else count
    span_days = (end_date - start_date).days
    if target_count > 9999 and span_days > 0:
        mid_date = start_date + dt.timedelta(days=span_days // 2)
        logging.info(
            "Splitting PubMed query term='%s' range=%s because count=%d exceeds PubMed fetch window limits.",
            term,
            range_label,
            target_count,
        )
        left_records = search_pubmed_term_date_range(
            term=term,
            start_date=start_date,
            end_date=mid_date,
            discipline=discipline,
            session=session,
            email=email,
            api_key=api_key,
            tool=tool,
            delay_seconds=delay_seconds,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            batch_size=batch_size,
            max_records=target_count if max_records is not None else None,
        )
        remaining = None if max_records is None else max(0, target_count - len(left_records))
        if remaining == 0:
            return left_records[:target_count]
        right_records = search_pubmed_term_date_range(
            term=term,
            start_date=mid_date + dt.timedelta(days=1),
            end_date=end_date,
            discipline=discipline,
            session=session,
            email=email,
            api_key=api_key,
            tool=tool,
            delay_seconds=delay_seconds,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            batch_size=batch_size,
            max_records=remaining,
        )
        merged = left_records + right_records
        return merged[:target_count]
    if target_count > 9999:
        logging.warning(
            "PubMed query term='%s' range=%s still exceeds 9999 records in a single day; truncating to first 9999.",
            term,
            range_label,
        )
        target_count = 9999

    records: List[Dict[str, Any]] = []
    batches = 0

    for retstart in range(0, target_count, batch_size):
        fetch_params: Dict[str, Any] = {
            "db": "pubmed",
            "query_key": query_key,
            "WebEnv": webenv,
            "retmode": "xml",
            "retstart": retstart,
            "retmax": min(batch_size, target_count - retstart),
        }
        fetch_params.update(base_params)

        xml_text = safe_get_text(
            session,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params=fetch_params,
            timeout=timeout_seconds,
            max_attempts=max_attempts,
            max_retry_after_seconds=60.0,
            request_label=f"PubMed term='{term}' range={range_label} efetch start={retstart}",
        )
        if not xml_text:
            logging.warning(
                "Stopping PubMed query early after an efetch failure (term='%s', range=%s, retstart=%s).",
                term,
                range_label,
                retstart,
            )
            break

        try:
            root = ET.fromstring(xml_text)
        except Exception as exc:
            logging.warning(
                "Failed to parse PubMed XML (term='%s', range=%s, retstart=%s): %s",
                term,
                range_label,
                retstart,
                exc,
            )
            break

        articles = root.findall(".//PubmedArticle")
        if not articles:
            break

        batches += 1
        for article in articles:
            records.append(
                pubmed_article_to_record(
                    article,
                    term,
                    discipline,
                    start_date.year,
                    start_date.year,
                    end_date.year,
                )
            )
            if max_records is not None and len(records) >= max_records:
                break

        if max_records is not None and len(records) >= max_records:
            break
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    logging.info("PubMed done term='%s' range=%s: %d records across %d batches", term, range_label, len(records), batches)
    return records


def search_pubmed_term_year(
    term: str,
    year: int,
    discipline: str,
    session: requests.Session,
    email: str,
    api_key: str,
    tool: str,
    delay_seconds: float,
    timeout_seconds: int,
    max_attempts: int,
    batch_size: int,
    max_per_query: int,
) -> List[Dict[str, Any]]:
    start_date = dt.date(year, 1, 1)
    end_date = dt.date(year, 12, 31)
    max_records = max_per_query if max_per_query else None
    records = search_pubmed_term_date_range(
        term=term,
        start_date=start_date,
        end_date=end_date,
        discipline=discipline,
        session=session,
        email=email,
        api_key=api_key,
        tool=tool,
        delay_seconds=delay_seconds,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        batch_size=batch_size,
        max_records=max_records,
    )
    logging.info("PubMed done term='%s' year=%s: %d records", term, year, len(records))
    return records


def fetch_pubmed_records(cfg: PipelineConfig, paths: PipelinePaths, session: requests.Session) -> List[Dict[str, Any]]:
    if not cfg.include_pubmed:
        return []

    if not cfg.pubmed_email:
        logging.warning("PubMed retrieval requested but no pubmed email is configured; proceeding without email.")

    months_per_window = cfg.query_window_months if cfg.max_per_query == 0 else 12
    if cfg.max_per_query and cfg.query_window_months != 12:
        logging.info(
            "Ignoring --query-window-months=%d because --max-per-query=%d is set; using annual retrieval windows.",
            cfg.query_window_months,
            cfg.max_per_query,
        )

    date_windows = build_query_date_windows(cfg.years, months_per_window)
    query_jobs = [(term, start_date, end_date) for term in cfg.terms for start_date, end_date in date_windows]
    all_records: List[Dict[str, Any]] = []

    logging.info(
        "Fetching PubMed sequentially for %d terms x %d windows (%d queries)",
        len(cfg.terms),
        len(date_windows),
        len(query_jobs),
    )

    for term, start_date, end_date in tqdm(query_jobs, desc="PubMed"):
        slice_path = retrieval_slice_path(paths, "pubmed", term, start_date, end_date)
        if slice_path.exists() and not cfg.refresh_openalex:
            cached = load_cached_slice_records(slice_path, cfg.discipline, "pubmed")
            if dataframe_has_data_rows(cached):
                all_records.extend(cached.to_dict(orient="records"))
                continue
            logging.warning("Cached PubMed slice has no data rows; refetching: %s", slice_path)

        max_records = cfg.max_per_query if cfg.max_per_query else None
        records = search_pubmed_term_date_range(
            term=term,
            start_date=start_date,
            end_date=end_date,
            discipline=cfg.discipline,
            session=session,
            email=cfg.pubmed_email,
            api_key=cfg.pubmed_api_key,
            tool=cfg.pubmed_tool,
            delay_seconds=cfg.pubmed_delay_seconds,
            timeout_seconds=cfg.pubmed_timeout_seconds,
            max_attempts=cfg.pubmed_max_attempts,
            batch_size=cfg.pubmed_batch_size,
            max_records=max_records,
        )
        write_slice_records(records, slice_path, cfg.discipline, "pubmed")
        all_records.extend(records)
    return all_records


def flatten_openalex_work_metadata(work: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten the work-level OpenAlex fields into the metadata columns listed in
    ``OPENALEX_METADATA_COLS``: work type, OA status, primary source type / DOAJ flag, preprint
    locations, first-author / all countries, funders, retraction and full-text flags.

    Works whose ``select`` did not include these fields (older retrieval slices) yield blanks /
    None, which ``standardize_dataframe`` turns into "" and <NA>."""
    open_access = work.get("open_access") or {}
    primary_location = work.get("primary_location") or {}
    primary_source = (primary_location.get("source") or {}) if isinstance(primary_location, dict) else {}
    if not isinstance(primary_source, dict):
        primary_source = {}

    preprint_servers: List[str] = []
    for location in work.get("locations") or []:
        if not isinstance(location, dict):
            continue
        location_source = location.get("source") or {}
        if not isinstance(location_source, dict):
            continue
        name = str(location_source.get("display_name") or "").strip()
        if location_source.get("type") == "repository" and name and PREPRINT_SERVER_PATTERN.search(name):
            preprint_servers.append(name)

    work_type = str(work.get("type") or "").strip()
    primary_source_name = str(primary_source.get("display_name") or "")
    is_preprint_record = work_type == "preprint" or (
        primary_source.get("type") == "repository" and bool(PREPRINT_SERVER_PATTERN.search(primary_source_name))
    )

    countries: List[str] = []
    first_author_country = ""
    for i, authorship in enumerate(work.get("authorships") or []):
        if not isinstance(authorship, dict):
            continue
        author_countries = [str(c).strip() for c in (authorship.get("countries") or []) if str(c or "").strip()]
        if i == 0 and author_countries:
            first_author_country = author_countries[0]
        countries.extend(author_countries)

    funders = [
        str(f.get("display_name")).strip()
        for f in (work.get("funders") or [])
        if isinstance(f, dict) and f.get("display_name")
    ]

    return {
        "work_type": work_type,
        "oa_status": str(open_access.get("oa_status") or "").strip(),
        "primary_source_type": str(primary_source.get("type") or "").strip(),
        "primary_source_is_in_doaj": primary_source.get("is_in_doaj"),
        "has_preprint_version": bool(preprint_servers) and not is_preprint_record,
        "is_preprint_record": bool(is_preprint_record),
        "preprint_servers": LIST_JOIN.join(sorted(set(preprint_servers))),
        "first_author_country": first_author_country,
        "countries": LIST_JOIN.join(sorted(set(countries))),
        "funders": LIST_JOIN.join(funders),
        "is_retracted": work.get("is_retracted"),
        "has_fulltext": work.get("has_fulltext"),
    }


def openalex_work_to_record(work: Dict[str, Any], term: str, discipline: str) -> Dict[str, Any]:
    open_access = work.get("open_access") or {}
    primary_location = work.get("primary_location") or {}
    source = (primary_location.get("source") or {}) if isinstance(primary_location, dict) else {}
    best_oa = work.get("best_oa_location") or {}

    best_oa_url = ""
    if isinstance(best_oa, dict):
        best_oa_url = (
            str(best_oa.get("url") or "")
            or str(best_oa.get("landing_page_url") or "")
            or str(best_oa.get("pdf_url") or "")
        ).strip()

    record: Dict[str, Any] = {
        "id": str(work.get("id") or "").strip(),
        "doi": normalize_doi(work.get("doi") or ""),
        "title": str(work.get("title") or "").replace("\n", " ").strip(),
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "year": work.get("publication_year") or "",
        "term": term,
        "discipline": discipline,
        "is_oa": open_access.get("is_oa"),
        "license": str(open_access.get("license") or "").strip(),
        "license_unpaywall": "",
        "journal": str(source.get("display_name") or "").strip(),
        "journal_norm": normalize_journal_name(source.get("display_name") or ""),
        "journal_is_oa": source.get("is_oa"),
        "source_db": "openalex",
        "authors": extract_authors(work),
        "best_oa_location_url": best_oa_url,
        "cited_by_count": work.get("cited_by_count"),
        "github": "",
        "zenodo": "",
        "osf": "",
        "pubmed_id": extract_pubmed_id(work),
        "repo_links": "",
        "code_link": "",
        "data_link": "",
        "preregistered": None,
        "preprint": "",
        "journal_impact_factor": pd.NA,
        "high_impact_flag": False,
        "high_impact_reason": "",
    }
    record.update(flatten_openalex_work_metadata(work))
    return record


@dataclass
class OpenAlexSliceResult:
    """Records fetched for one term x date-window slice plus whether pagination finished."""

    records: List[Dict[str, Any]]
    complete: bool
    pages: int = 0
    stop_reason: str = ""


def search_openalex_term_date_range(
    term: str,
    start_date: dt.date,
    end_date: dt.date,
    discipline: str,
    session: requests.Session,
    mailto: str,
    api_key: str,
    max_per_query: int,
    delay_seconds: float,
    timeout_seconds: int,
    max_attempts: int,
    max_failures_per_query: int,
    max_retry_after_seconds: int,
    budget_wait_max_hours: float = 30.0,
) -> OpenAlexSliceResult:
    url = "https://api.openalex.org/works"
    range_label = f"{start_date.isoformat()}..{end_date.isoformat()}"
    params = {
        "filter": (
            f"title.search:{term},"
            f"from_publication_date:{start_date.isoformat()},"
            f"to_publication_date:{end_date.isoformat()}"
        ),
        "per_page": 200,
        "cursor": "*",
        "select": OPENALEX_WORK_SELECT_FIELDS,
    }
    if mailto:
        params["mailto"] = mailto
    active_api_key = str(api_key or "").strip()
    if active_api_key:
        params["api_key"] = active_api_key

    records: List[Dict[str, Any]] = []
    cursor = "*"
    pages = 0
    consecutive_failures = 0
    budget_waits = 0
    context = f"term='{term}' range={range_label}"

    def _wait_for_budget(rate_limit: Optional[Dict[str, Any]]) -> bool:
        nonlocal budget_waits
        budget_waits += 1
        return wait_for_openalex_budget_reset(rate_limit, budget_wait_max_hours, context=context)

    while cursor:
        params["cursor"] = cursor
        try:
            payload = safe_get_json(
                session,
                url,
                params=params,
                timeout=timeout_seconds,
                max_attempts=max_attempts,
                max_retry_after_seconds=float(max_retry_after_seconds),
                request_label=f"OpenAlex {context}",
                raise_on_budget_exhausted=bool(active_api_key),
            )
        except OpenAlexBudgetExhausted as exc:
            # Keyed mode: never drop the key. Sleep until the daily budget resets and retry
            # the same cursor, unless the wait exceeds the configured cap.
            if _wait_for_budget(exc.rate_limit):
                continue
            return OpenAlexSliceResult(records, complete=False, pages=pages, stop_reason="budget_wait_exceeded")

        if not payload:
            if active_api_key:
                # A 429 without informative headers (or repeated failures) may still be budget
                # exhaustion; confirm via the /rate-limit endpoint and wait rather than fall back.
                rate_limit = inspect_openalex_rate_limit(session, active_api_key, timeout_seconds)
                remaining = openalex_requests_remaining(rate_limit)
                if remaining is not None and remaining <= 0:
                    if _wait_for_budget(rate_limit):
                        continue
                    return OpenAlexSliceResult(
                        records, complete=False, pages=pages, stop_reason="budget_wait_exceeded"
                    )
            consecutive_failures += 1
            if consecutive_failures >= max_failures_per_query:
                logging.warning(
                    "Stopping OpenAlex query early after %d consecutive failures (%s). "
                    "Slice will be saved as partial and re-run on the next invocation.",
                    consecutive_failures,
                    context,
                )
                return OpenAlexSliceResult(records, complete=False, pages=pages, stop_reason="max_failures")
            continue
        consecutive_failures = 0

        works = payload.get("results") or []
        pages += 1
        for work in works:
            records.append(openalex_work_to_record(work, term, discipline))
            if max_per_query and len(records) >= max_per_query:
                return OpenAlexSliceResult(records, complete=True, pages=pages, stop_reason="max_per_query")

        cursor = (payload.get("meta") or {}).get("next_cursor")
        if not cursor:
            break

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    logging.info(
        "OpenAlex done %s: %d records across %d pages%s",
        context,
        len(records),
        pages,
        f" ({budget_waits} budget wait(s))" if budget_waits else "",
    )
    return OpenAlexSliceResult(records, complete=True, pages=pages)


# ---------------------------------------------------------------------------
# OpenAlex work-metadata backfill (batched DOI lookups, resumable JSONL cache)
# ---------------------------------------------------------------------------

OPENALEX_METADATA_BATCH_SIZE = 50
OPENALEX_METADATA_MISSING_KEY = "_missing"
OPENALEX_FILTER_UNSAFE_CHARS = (",", "|")


@dataclass
class OpenAlexDoiBatchResult:
    """Outcome of one batched ``filter=doi:a|b|...`` request."""

    status: str  # "ok" | "bad_request" | "failed" | "stop"
    works: List[Dict[str, Any]] = field(default_factory=list)
    rate_limit: Dict[str, Any] = field(default_factory=dict)


def load_openalex_metadata_cache(path: Path) -> Dict[str, Optional[Dict[str, Any]]]:
    """Read the JSONL cache: DOI -> flattened metadata record, or None when OpenAlex had no work
    for that DOI (recorded as ``{"_missing": [...]}`` lines so they are not re-requested)."""
    cache: Dict[str, Optional[Dict[str, Any]]] = {}
    if not path.exists():
        return cache
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            for missing_doi in rec.get(OPENALEX_METADATA_MISSING_KEY) or []:
                key = normalize_doi(missing_doi)
                if key:
                    cache.setdefault(key, None)
            doi = normalize_doi(rec.get("doi_norm") or rec.get("doi") or "")
            if doi and OPENALEX_METADATA_MISSING_KEY not in rec:
                cache[doi] = rec
    return cache


def append_openalex_metadata_cache(path: Path, records: Sequence[Dict[str, Any]], missing: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(make_json_safe(rec), ensure_ascii=False) + "\n")
        if missing:
            handle.write(json.dumps({OPENALEX_METADATA_MISSING_KEY: list(missing)}) + "\n")
        handle.flush()


def _doi_norm_series(df: pd.DataFrame) -> pd.Series:
    if "doi_norm" in df.columns:
        return df["doi_norm"].fillna("").astype(str).map(normalize_doi)
    return df.get("doi", pd.Series("", index=df.index)).fillna("").astype(str).map(normalize_doi)


def _metadata_missing_mask(df: pd.DataFrame) -> pd.Series:
    if "work_type" not in df.columns:
        return pd.Series(True, index=df.index)
    return df["work_type"].fillna("").astype(str).str.strip().replace({"nan": "", "None": "", "<NA>": ""}).eq("")


def apply_openalex_metadata_cache(df: pd.DataFrame, cache: Dict[str, Optional[Dict[str, Any]]]) -> pd.DataFrame:
    """Fill ``OPENALEX_METADATA_COLS`` for rows whose metadata is blank and whose DOI is cached."""
    if df.empty:
        return df
    for col in OPENALEX_METADATA_TEXT_COLS:
        if col not in df.columns:
            df[col] = ""
    for col in OPENALEX_METADATA_BOOL_COLS:
        if col not in df.columns:
            df[col] = pd.Series([pd.NA] * len(df), index=df.index, dtype="boolean")
    found = {doi: rec for doi, rec in cache.items() if isinstance(rec, dict)}
    if not found:
        return df
    doi_norm = _doi_norm_series(df)
    mask = _metadata_missing_mask(df) & doi_norm.isin(found.keys())
    if not mask.any():
        return df
    meta = pd.DataFrame.from_dict(found, orient="index")
    aligned = meta.reindex(doi_norm[mask].to_numpy())
    for col in OPENALEX_METADATA_TEXT_COLS:
        values = aligned[col] if col in aligned.columns else pd.Series("", index=aligned.index)
        df.loc[mask, col] = values.fillna("").astype(str).replace({"nan": "", "None": ""}).to_numpy()
    for col in OPENALEX_METADATA_BOOL_COLS:
        values = aligned[col] if col in aligned.columns else pd.Series(pd.NA, index=aligned.index)
        df[col] = coerce_nullable_bool(df[col])
        df.loc[mask, col] = coerce_nullable_bool(values.reset_index(drop=True)).to_numpy()
    logging.info("Applied cached OpenAlex work metadata to %d rows.", int(mask.sum()))
    return df


def fetch_openalex_works_by_doi(
    session: requests.Session,
    dois: Sequence[str],
    mailto: str,
    api_key: str,
    timeout_seconds: int,
    max_attempts: int,
    max_retry_after_seconds: int,
    budget_wait_max_hours: float,
    context: str = "metadata backfill",
) -> OpenAlexDoiBatchResult:
    """One ``filter=doi:a|b|...`` lookup (<= 50 DOIs). On a keyed 429 that signals budget
    exhaustion the key is kept and the call sleeps until the reset (bounded by
    ``budget_wait_max_hours``) before retrying the same batch; ``status="stop"`` means the wait
    exceeded the cap and the caller should stop and resume on a later run."""
    url = "https://api.openalex.org/works"
    params: Dict[str, Any] = {
        "filter": "doi:" + "|".join(dois),
        "per_page": max(1, min(OPENALEX_METADATA_BATCH_SIZE, len(dois))),
        "select": OPENALEX_METADATA_SELECT_FIELDS,
    }
    if mailto:
        params["mailto"] = mailto
    active_api_key = str(api_key or "").strip()
    if active_api_key:
        params["api_key"] = active_api_key

    rate_limit: Dict[str, Any] = {}
    attempt = 0
    while attempt < max(1, max_attempts):
        try:
            resp = session.get(url, params=params, timeout=timeout_seconds)
        except Exception:
            attempt += 1
            logging.warning("Request exception on OpenAlex %s (attempt %d/%d)", context, attempt, max_attempts)
            time.sleep(min(30.0, 2.0 ** attempt))
            continue
        rate_limit = parse_openalex_rate_limit_headers(getattr(resp, "headers", None)) or rate_limit
        status = resp.status_code
        if status == 200:
            try:
                payload = resp.json()
            except Exception:
                attempt += 1
                continue
            works = payload.get("results") if isinstance(payload, dict) else None
            return OpenAlexDoiBatchResult("ok", list(works or []), rate_limit)
        if status == 429:
            remaining = openalex_requests_remaining(rate_limit)
            if active_api_key and remaining is None:
                probed = inspect_openalex_rate_limit(session, active_api_key, timeout_seconds)
                if probed:
                    rate_limit = {**rate_limit, **probed}
                    remaining = openalex_requests_remaining(rate_limit)
            if active_api_key and remaining is not None and remaining <= 0:
                if wait_for_openalex_budget_reset(rate_limit, budget_wait_max_hours, context=context):
                    continue  # same batch, same key
                return OpenAlexDoiBatchResult("stop", [], rate_limit)
            attempt += 1
            retry_after = _coerce_float(resp.headers.get("Retry-After")) if getattr(resp, "headers", None) else None
            sleep_s = retry_after if retry_after is not None else min(30.0, 5.0 + 3.0 * attempt)
            sleep_s = min(sleep_s, float(max_retry_after_seconds))
            logging.warning("Rate limited on OpenAlex %s (attempt %d/%d); sleeping %.1fs", context, attempt, max_attempts, sleep_s)
            time.sleep(sleep_s)
            continue
        if status == 400:
            return OpenAlexDoiBatchResult("bad_request", [], rate_limit)
        if status >= 500:
            attempt += 1
            logging.warning("Server error %s on OpenAlex %s (attempt %d/%d)", status, context, attempt, max_attempts)
            time.sleep(min(30.0, 2.0 ** attempt))
            continue
        logging.warning("HTTP %s on OpenAlex %s (not retrying).", status, context)
        return OpenAlexDoiBatchResult("failed", [], rate_limit)
    return OpenAlexDoiBatchResult("failed", [], rate_limit)


def run_openalex_metadata_backfill(
    df: pd.DataFrame,
    cfg: PipelineConfig,
    paths: PipelinePaths,
    session: requests.Session,
) -> Tuple[pd.DataFrame, bool]:
    """Backfill stage: fill the work-metadata columns for rows that lack them.

    The JSONL cache is always applied when present. Network lookups run only with
    ``--backfill-openalex-metadata``; they are batched 50 DOIs per request, cached after every
    batch (resumable), never drop the API key, and sleep through budget resets or stop early when
    the wait exceeds ``--openalex-budget-wait-max-hours``. Returns ``(df, complete)``."""
    cache = load_openalex_metadata_cache(paths.openalex_metadata_cache)
    if cache:
        df = apply_openalex_metadata_cache(df, cache)
    if not cfg.backfill_openalex_metadata:
        return df, True

    doi_norm = _doi_norm_series(df)
    needed = sorted({d for d in doi_norm[_metadata_missing_mask(df) & doi_norm.ne("")].unique() if d})
    unsafe = [d for d in needed if any(ch in d for ch in OPENALEX_FILTER_UNSAFE_CHARS)]
    if unsafe:
        logging.info("Skipping %d DOIs with characters OpenAlex filters cannot encode.", len(unsafe))
    todo = [d for d in needed if d not in cache and d not in set(unsafe)]
    n_batches = (len(todo) + OPENALEX_METADATA_BATCH_SIZE - 1) // OPENALEX_METADATA_BATCH_SIZE
    logging.info(
        "OpenAlex metadata backfill: %d DOIs lack metadata, %d cached, %d to fetch (~%d requests, ~$%.2f).",
        len(needed),
        len(needed) - len(todo) - len(unsafe),
        len(todo),
        n_batches,
        0.0001 * n_batches,
    )
    if not todo:
        return df, True
    if not cfg.openalex_api_key:
        logging.warning("No OPENALEX_API_KEY configured; the metadata backfill will be heavily throttled.")
    else:
        ensure_openalex_budget_available(cfg, session)

    def _fetch(batch: Sequence[str]) -> OpenAlexDoiBatchResult:
        return fetch_openalex_works_by_doi(
            session,
            batch,
            cfg.openalex_mailto,
            cfg.openalex_api_key,
            cfg.openalex_timeout_seconds,
            cfg.openalex_max_attempts,
            cfg.openalex_max_retry_after_seconds,
            cfg.openalex_budget_wait_max_hours,
        )

    stopped = False
    stop_reason = ""
    consecutive_failures = 0
    n_requests = 0
    n_found = 0
    for start in tqdm(range(0, len(todo), OPENALEX_METADATA_BATCH_SIZE), desc="OpenAlex metadata"):
        batch = todo[start : start + OPENALEX_METADATA_BATCH_SIZE]
        result = _fetch(batch)
        n_requests += 1
        if result.status == "stop":
            stopped, stop_reason = True, "budget_wait_exceeded"
            break
        if result.status == "failed":
            consecutive_failures += 1
            if consecutive_failures >= cfg.openalex_max_failures_per_query:
                stopped, stop_reason = True, "max_failures"
                break
            continue
        consecutive_failures = 0
        works = result.works
        if result.status == "bad_request":
            # Usually one malformed DOI in the batch: retry them one at a time.
            works = []
            for doi in batch:
                single = _fetch([doi])
                n_requests += 1
                if single.status == "stop":
                    stopped, stop_reason = True, "budget_wait_exceeded"
                    break
                if single.status == "ok":
                    works.extend(single.works)
                if cfg.openalex_delay_seconds > 0:
                    time.sleep(cfg.openalex_delay_seconds)
            if stopped:
                break
        records: List[Dict[str, Any]] = []
        found: set = set()
        for work in works:
            if not isinstance(work, dict):
                continue
            doi = normalize_doi(work.get("doi") or "")
            if not doi:
                continue
            rec = {"doi_norm": doi, "openalex_id": str(work.get("id") or ""), **flatten_openalex_work_metadata(work)}
            records.append(rec)
            found.add(doi)
            cache[doi] = rec
        missing = [d for d in batch if d not in found]
        for d in missing:
            cache[d] = None
        append_openalex_metadata_cache(paths.openalex_metadata_cache, records, missing)
        n_found += len(found)

        remaining = openalex_requests_remaining(result.rate_limit)
        if cfg.openalex_api_key and remaining is not None and remaining < cfg.openalex_metadata_min_budget_remaining:
            logging.warning(
                "OpenAlex budget headroom reached (remaining=%d < %d); waiting for the daily reset before continuing.",
                remaining,
                cfg.openalex_metadata_min_budget_remaining,
            )
            if not wait_for_openalex_budget_reset(result.rate_limit, cfg.openalex_budget_wait_max_hours, context="metadata backfill headroom"):
                stopped, stop_reason = True, "budget_wait_exceeded"
                break
        if n_requests % 50 == 0:
            logging.info("OpenAlex metadata backfill: %d requests, %d/%d DOIs processed, %d works found, remaining=%s", n_requests, min(start + OPENALEX_METADATA_BATCH_SIZE, len(todo)), len(todo), n_found, remaining)
        if cfg.openalex_delay_seconds > 0:
            time.sleep(cfg.openalex_delay_seconds)

    df = apply_openalex_metadata_cache(df, cache)
    if stopped:
        logging.warning(
            "OpenAlex metadata backfill stopped early (%s) after %d requests; %d works cached so far in %s. "
            "Re-run with --backfill-openalex-metadata to resume; rows without metadata fall back to the "
            "journal-name corpus rule.",
            stop_reason,
            n_requests,
            n_found,
            paths.openalex_metadata_cache,
        )
        return df, False
    logging.info("OpenAlex metadata backfill complete: %d requests, %d works found.", n_requests, n_found)
    return df, True


def read_csv_if_exists(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    return pd.read_csv(path, low_memory=False)


def csv_has_data_rows(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            _ = f.readline()
            second = f.readline()
        return bool(second and second.strip())
    except Exception:
        return False


def dataframe_has_data_rows(df: Optional[pd.DataFrame]) -> bool:
    return isinstance(df, pd.DataFrame) and not df.empty


def write_csv_atomic(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(path)


def load_cached_slice_records(path: Path, discipline: str, source_db: str) -> Optional[pd.DataFrame]:
    cached = read_csv_if_exists(path)
    if cached is None:
        return None
    cached = standardize_dataframe(cached)
    cached = ensure_discipline(cached, discipline)
    cached = assign_source_db(cached, source_db)
    return cached


def write_slice_records(records: Sequence[Dict[str, Any]], path: Path, discipline: str, source_db: str) -> None:
    df = pd.DataFrame(list(records))
    df = standardize_dataframe(df)
    df = ensure_discipline(df, discipline)
    df = assign_source_db(df, source_db)
    write_csv_atomic(df, path)


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): make_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [make_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [make_json_safe(v) for v in value]

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            return make_json_safe(value.item())
        except Exception:
            return str(value)

    return value


def write_json_atomic(obj: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(make_json_safe(obj), f, ensure_ascii=True)
    tmp.replace(path)


def coerce_nullable_bool(series: pd.Series) -> pd.Series:
    def _conv(value: Any) -> Any:
        if pd.isna(value):
            return pd.NA
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in {"", "nan", "none", "null"}:
            return pd.NA
        if s in {"true", "t", "1", "yes", "y"}:
            return True
        if s in {"false", "f", "0", "no", "n"}:
            return False
        return pd.NA

    return series.map(_conv).astype("boolean")


def standardize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if "doi" not in df.columns:
        df["doi"] = ""
    df["doi_norm"] = df["doi"].map(normalize_doi)
    df["doi"] = df["doi_norm"]

    if "journal" not in df.columns:
        df["journal"] = ""
    df["journal_norm"] = df["journal"].map(normalize_journal_name)

    for col in TEXT_COLS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).replace({"nan": "", "None": ""}).str.strip()

    for col in BOOL_COLS:
        if col not in df.columns:
            df[col] = pd.Series([pd.NA] * len(df), dtype="boolean")
        df[col] = coerce_nullable_bool(df[col])

    if "year" not in df.columns:
        df["year"] = pd.NA
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")

    for col in NUM_COLS:
        if col not in df.columns:
            df[col] = pd.NA
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def normalize_open_access_fields(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    is_oa = coerce_nullable_bool(out.get("is_oa", pd.Series([pd.NA] * len(out), index=out.index)))
    journal_is_oa = coerce_nullable_bool(out.get("journal_is_oa", pd.Series([pd.NA] * len(out), index=out.index)))
    best_oa_location_url = out.get("best_oa_location_url", pd.Series([""] * len(out), index=out.index))
    license_unpaywall = out.get("license_unpaywall", pd.Series([""] * len(out), index=out.index))

    has_best_oa_location = (
        best_oa_location_url.fillna("")
        .astype(str)
        .str.strip()
        .replace({"nan": "", "None": "", "<NA>": "", "null": ""})
        .ne("")
    )
    has_oa_license = (
        license_unpaywall.fillna("")
        .astype(str)
        .str.strip()
        .replace({"nan": "", "None": "", "<NA>": "", "null": ""})
        .ne("")
    )

    inferred_oa = has_best_oa_location | has_oa_license | journal_is_oa.fillna(False)
    out["is_oa"] = (is_oa.fillna(False) | inferred_oa).astype("boolean")
    return out


def deduplicate_records(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    before = len(df)

    source_series = df.get("source_db", pd.Series(index=df.index, dtype=object)).fillna("").astype(str).str.strip().str.lower()
    source_priority = source_series.map({"openalex": 0, "pubmed": 1}).fillna(2).astype(int)
    has_doi = df["doi_norm"] != ""
    pubmed_series = df.get("pubmed_id", pd.Series(index=df.index, dtype=object)).fillna("").astype(str).str.strip()
    has_pubmed = pubmed_series != ""
    has_abstract = df.get("abstract", pd.Series(index=df.index, dtype=object)).fillna("").astype(str).str.strip() != ""
    cited_by = pd.to_numeric(df.get("cited_by_count"), errors="coerce").fillna(-1.0)

    df = df.assign(
        _source_priority=source_priority,
        _has_doi=has_doi.astype(int),
        _has_pubmed=has_pubmed.astype(int),
        _has_abstract=has_abstract.astype(int),
        _cited_by_sort=cited_by,
    ).sort_values(
        by=["_has_doi", "_has_pubmed", "_source_priority", "_has_abstract", "_cited_by_sort", "year"],
        ascending=[False, False, True, False, False, False],
        na_position="last",
    )

    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"], keep="first")

    with_doi = df.loc[has_doi].drop_duplicates(subset=["doi_norm"], keep="first")
    without_doi = df.loc[~has_doi]
    df = pd.concat([with_doi, without_doi], ignore_index=True)

    pubmed_norm = df.get("pubmed_id", pd.Series(index=df.index, dtype=object)).fillna("").astype(str).str.strip()
    has_pubmed = pubmed_norm != ""
    with_pubmed = df.loc[has_pubmed].drop_duplicates(subset=["pubmed_id"], keep="first")
    without_pubmed = df.loc[~has_pubmed]
    df = pd.concat([with_pubmed, without_pubmed], ignore_index=True)

    df = df.drop(columns=[c for c in ["_source_priority", "_has_doi", "_has_pubmed", "_has_abstract", "_cited_by_sort"] if c in df.columns])

    after = len(df)
    logging.info("Deduplicated works: %s -> %s", before, after)
    return df


def ensure_discipline(df: pd.DataFrame, discipline: str) -> pd.DataFrame:
    label = (discipline or "").strip().lower() or "unspecified"
    if "discipline" not in df.columns:
        df["discipline"] = label
        return df

    current = df["discipline"].fillna("").astype(str).str.strip().str.lower()
    missing = current.eq("")
    if missing.any():
        df.loc[missing, "discipline"] = label
    return df


def fetch_or_load_openalex(cfg: PipelineConfig, paths: PipelinePaths, session: requests.Session) -> pd.DataFrame:
    cached_openalex_only: Optional[pd.DataFrame] = None

    if paths.raw_csv.exists() and not cfg.refresh_openalex:
        logging.info("Loading cached retrieval dataset: %s", paths.raw_csv)
        cached = read_csv_if_exists(paths.raw_csv)
        if cached is not None:
            cached = standardize_dataframe(cached)
            cached = ensure_discipline(cached, cfg.discipline)
            cached = assign_source_db(cached, "openalex")
            if dataframe_has_data_rows(cached):
                cached_sources = (
                    cached.get("source_db", pd.Series(index=cached.index, dtype=object))
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.lower()
                )
                has_pubmed_rows = cached_sources.eq("pubmed").any()
                if cfg.include_pubmed and "source_db" not in cached.columns:
                    logging.warning(
                        "Cached retrieval dataset predates PubMed support; using it as OpenAlex-only input and fetching PubMed separately: %s",
                        paths.raw_csv,
                    )
                    cached_openalex_only = assign_source_db(cached, "openalex")
                elif cfg.include_pubmed and not has_pubmed_rows:
                    logging.info(
                        "Cached retrieval dataset has OpenAlex rows only; reusing it and fetching PubMed separately: %s",
                        paths.raw_csv,
                    )
                    cached_openalex_only = assign_source_db(cached, "openalex")
                elif not cfg.include_pubmed and has_pubmed_rows:
                    logging.warning(
                        "Cached retrieval dataset includes PubMed rows but --include-pubmed is disabled; refetching: %s",
                        paths.raw_csv,
                    )
                else:
                    return cached
            if cached_openalex_only is None:
                logging.warning(
                    "Cached retrieval file has no data rows; refetching from API: %s",
                    paths.raw_csv,
                )

    all_records: List[Dict[str, Any]] = []
    if cached_openalex_only is not None:
        all_records.extend(cached_openalex_only.to_dict(orient="records"))
    else:
        ensure_openalex_budget_available(cfg, session)

        months_per_window = cfg.query_window_months if cfg.max_per_query == 0 else 12
        if cfg.max_per_query and cfg.query_window_months != 12:
            logging.info(
                "Ignoring --query-window-months=%d because --max-per-query=%d is set; using annual retrieval windows.",
                cfg.query_window_months,
                cfg.max_per_query,
            )
        date_windows = build_query_date_windows(cfg.years, months_per_window)

        logging.info(
            "Fetching OpenAlex in parallel for %d terms x %d windows (%d queries)",
            len(cfg.terms),
            len(date_windows),
            len(cfg.terms) * len(date_windows),
        )

        query_jobs = [(term, start_date, end_date) for term in cfg.terms for start_date, end_date in date_windows]
        pending_jobs: List[Tuple[str, dt.date, dt.date, Path]] = []

        completed_queries = 0
        incomplete_slices: List[str] = []
        for term, start_date, end_date in query_jobs:
            slice_path = retrieval_slice_path(paths, "openalex", term, start_date, end_date)
            partial_path = retrieval_slice_partial_path(slice_path)
            range_label = f"{start_date.isoformat()}..{end_date.isoformat()}"
            if partial_path.exists() and not slice_path.exists():
                logging.warning(
                    "OpenAlex slice term='%s' range=%s stopped early on a previous run; re-running it: %s",
                    term,
                    range_label,
                    partial_path,
                )
            if slice_path.exists() and not cfg.refresh_openalex:
                cached_slice = load_cached_slice_records(slice_path, cfg.discipline, "openalex")
                if dataframe_has_data_rows(cached_slice):
                    cached_records = cached_slice.to_dict(orient="records")
                    all_records.extend(cached_records)
                    completed_queries += 1
                    logging.info(
                        "OpenAlex progress: %d/%d queries complete from cache (latest term='%s' range=%s, %d records, total=%d)",
                        completed_queries,
                        len(query_jobs),
                        term,
                        range_label,
                        len(cached_records),
                        len(all_records),
                    )
                    continue
                logging.warning("Cached OpenAlex slice has no data rows; refetching: %s", slice_path)
            pending_jobs.append((term, start_date, end_date, slice_path))

        with ThreadPoolExecutor(max_workers=cfg.openalex_workers) as executor:
            future_map = {
                executor.submit(
                    search_openalex_term_date_range,
                    term,
                    start_date,
                    end_date,
                    cfg.discipline,
                    session,
                    cfg.openalex_mailto,
                    cfg.openalex_api_key,
                    cfg.max_per_query,
                    cfg.openalex_delay_seconds,
                    cfg.openalex_timeout_seconds,
                    cfg.openalex_max_attempts,
                    cfg.openalex_max_failures_per_query,
                    cfg.openalex_max_retry_after_seconds,
                    cfg.openalex_budget_wait_max_hours,
                ): (term, start_date, end_date, slice_path)
                for term, start_date, end_date, slice_path in pending_jobs
            }

            for future in tqdm(as_completed(future_map), total=len(future_map), desc="OpenAlex"):
                term, start_date, end_date, slice_path = future_map[future]
                partial_path = retrieval_slice_partial_path(slice_path)
                range_label = f"{start_date.isoformat()}..{end_date.isoformat()}"
                try:
                    result = future.result()
                    if isinstance(result, OpenAlexSliceResult):
                        records, slice_complete = result.records, result.complete
                    else:  # legacy: a bare list means a normally completed slice
                        records, slice_complete = list(result), True
                    if not slice_complete:
                        incomplete_slices.append(f"{term} {range_label}")
                        if records:
                            write_slice_records(records, partial_path, cfg.discipline, "openalex")
                        logging.warning(
                            "OpenAlex slice term='%s' range=%s is incomplete (%d records); saved as %s and "
                            "will be re-run on the next invocation.",
                            term,
                            range_label,
                            len(records),
                            partial_path.name,
                        )
                        continue
                    write_slice_records(records, slice_path, cfg.discipline, "openalex")
                    if partial_path.exists():
                        partial_path.unlink()
                    all_records.extend(records)
                    completed_queries += 1
                    logging.info(
                        "OpenAlex progress: %d/%d queries complete (latest term='%s' range=%s, %d records, total=%d)",
                        completed_queries,
                        len(query_jobs),
                        term,
                        range_label,
                        len(records),
                        len(all_records),
                    )
                except Exception as exc:
                    incomplete_slices.append(f"{term} {range_label}")
                    logging.warning("OpenAlex query failed (%s, %s): %s", term, range_label, exc)

        if incomplete_slices:
            raise RuntimeError(
                f"OpenAlex retrieval incomplete: {len(incomplete_slices)}/{len(query_jobs)} slices stopped early "
                f"(e.g. {incomplete_slices[0]}). Completed slices are cached under {paths.retrieval_slices_dir}; "
                "re-run the same command to resume the remaining slices. Not writing the raw retrieval dataset."
            )

    if cfg.include_pubmed:
        pubmed_records = fetch_pubmed_records(cfg, paths, session)
        if pubmed_records:
            logging.info("Merging %d PubMed records into retrieval dataset.", len(pubmed_records))
            all_records.extend(pubmed_records)
        else:
            logging.info("PubMed retrieval returned no records.")

    df = pd.DataFrame(all_records)
    df = standardize_dataframe(df)
    df = ensure_discipline(df, cfg.discipline)
    df = deduplicate_records(df)
    if df.empty:
        raise RuntimeError(
            "Retrieval returned zero records. This usually indicates repeated rate limits "
            "or query failures. Try lowering workers, increasing delay, and using "
            "--openalex-max-retry-after-seconds to cap long OpenAlex backoffs."
        )
    write_csv_atomic(df, paths.raw_csv)
    logging.info("Saved raw retrieval dataset: %s (%d rows)", paths.raw_csv, len(df))
    return df


def _duckdb_quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _duckdb_escape(path_glob: str) -> str:
    return path_glob.replace("'", "''")


def _duckdb_find_column(con: Any, parquet_glob: str, candidates: Sequence[str]) -> Optional[str]:
    try:
        desc = con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{_duckdb_escape(parquet_glob)}', union_by_name=true)"
        ).fetch_df()
    except Exception:
        return None

    mapping: Dict[str, str] = {}
    for col in desc["column_name"].tolist():
        mapping[str(col).lower()] = str(col)

    for cand in candidates:
        if cand.lower() in mapping:
            return mapping[cand.lower()]
    return None


def fill_missing(df: pd.DataFrame, target_col: str, source_col: str) -> None:
    if target_col not in df.columns or source_col not in df.columns:
        return
    target = df[target_col]
    source = df[source_col]
    missing_mask = target.isna() | target.astype(str).str.strip().isin(["", "nan", "None"])
    df.loc[missing_mask, target_col] = source.loc[missing_mask]


def fill_missing_bool(df: pd.DataFrame, target_col: str, source_col: str) -> None:
    if target_col not in df.columns or source_col not in df.columns:
        return
    source = coerce_nullable_bool(df[source_col])
    target = coerce_nullable_bool(df[target_col])
    missing_mask = target.isna()
    target.loc[missing_mask] = source.loc[missing_mask]
    df[target_col] = target


def fill_col_if_blank(df: pd.DataFrame, col: str, values: pd.Series) -> None:
    if col not in df.columns:
        df[col] = ""
    current = df[col].fillna("").astype(str)
    incoming = values.fillna("").astype(str)
    mask = current.str.strip().eq("") & incoming.str.strip().ne("")
    df.loc[mask, col] = incoming.loc[mask]


def apply_unpaywall_snapshot(df: pd.DataFrame, parquet_glob: str) -> pd.DataFrame:
    if not parquet_glob:
        return df
    if duckdb is None:
        logging.warning("duckdb is unavailable; skipping Unpaywall snapshot join.")
        return df

    matches = list_snapshot_matches(parquet_glob)
    if not matches:
        logging.warning("No parquet files matched Unpaywall snapshot source: %s", parquet_glob)
        return df
    logging.info("Using %d Unpaywall snapshot parquet file(s).", len(matches))

    try:
        con = duckdb.connect()
    except Exception as exc:
        logging.warning("Failed to init duckdb; skipping Unpaywall snapshot join: %s", exc)
        return df

    doi_col = _duckdb_find_column(con, parquet_glob, ["doi", "DOI"])
    if not doi_col:
        logging.warning("Could not find DOI column in Unpaywall snapshot: %s", parquet_glob)
        return df

    is_oa_col = _duckdb_find_column(con, parquet_glob, ["is_oa"])
    license_col = _duckdb_find_column(con, parquet_glob, ["license"])
    best_oa_url_col = _duckdb_find_column(con, parquet_glob, ["best_oa_location_url"])
    best_oa_struct_col = _duckdb_find_column(con, parquet_glob, ["best_oa_location"])

    minimal = df[["doi_norm"]].copy()
    minimal = minimal[minimal["doi_norm"] != ""].drop_duplicates()
    if minimal.empty:
        return df

    con.register("works", minimal)

    select_cols = [
        f"lower(regexp_replace(cast({_duckdb_quote_ident(doi_col)} as varchar), '^https?://(dx\\.)?doi\\.org/', '')) AS doi_norm",
        f"cast({_duckdb_quote_ident(is_oa_col)} as boolean) as up_is_oa" if is_oa_col else "NULL::BOOLEAN as up_is_oa",
        f"cast({_duckdb_quote_ident(license_col)} as varchar) as up_license" if license_col else "''::VARCHAR as up_license",
    ]

    if best_oa_url_col:
        select_cols.append(f"cast({_duckdb_quote_ident(best_oa_url_col)} as varchar) as up_best_oa_location_url")
    elif best_oa_struct_col:
        b = _duckdb_quote_ident(best_oa_struct_col)
        select_cols.append(
            f"coalesce(cast({b}.url as varchar), cast({b}.landing_page_url as varchar), cast({b}.pdf_url as varchar), '') as up_best_oa_location_url"
        )
    else:
        select_cols.append("''::VARCHAR as up_best_oa_location_url")

    query = f"""
    WITH up AS (
        SELECT {', '.join(select_cols)}
        FROM read_parquet('{_duckdb_escape(parquet_glob)}', union_by_name=true)
    )
    SELECT w.doi_norm, up.up_is_oa, up.up_license, up.up_best_oa_location_url
    FROM works w
    LEFT JOIN up ON w.doi_norm = up.doi_norm
    """

    try:
        joined = con.execute(query).fetch_df()
    except Exception as exc:
        logging.warning("Unpaywall snapshot join failed: %s", exc)
        return df

    if joined.empty:
        return df

    joined = joined.drop_duplicates(subset=["doi_norm"], keep="first")
    out = df.merge(joined, on="doi_norm", how="left")

    fill_missing(out, "best_oa_location_url", "up_best_oa_location_url")
    fill_missing(out, "license_unpaywall", "up_license")
    fill_missing_bool(out, "is_oa", "up_is_oa")

    out = out.drop(columns=[c for c in ["up_is_oa", "up_license", "up_best_oa_location_url"] if c in out.columns])
    logging.info("Applied Unpaywall snapshot join.")
    return out


def apply_crossref_relations_snapshot(df: pd.DataFrame, parquet_glob: str) -> pd.DataFrame:
    if not parquet_glob:
        return df
    if duckdb is None:
        logging.warning("duckdb is unavailable; skipping Crossref snapshot join.")
        return df

    matches = list_snapshot_matches(parquet_glob)
    if not matches:
        logging.warning("No parquet files matched Crossref relations snapshot source: %s", parquet_glob)
        return df
    logging.info("Using %d Crossref relations snapshot parquet file(s).", len(matches))

    try:
        con = duckdb.connect()
    except Exception as exc:
        logging.warning("Failed to init duckdb; skipping Crossref snapshot join: %s", exc)
        return df

    doi_col = _duckdb_find_column(con, parquet_glob, ["doi", "DOI"])
    if not doi_col:
        logging.warning("Could not find DOI column in Crossref relations snapshot: %s", parquet_glob)
        return df

    relation_col = _duckdb_find_column(con, parquet_glob, ["relation_type", "type"])
    related_col = _duckdb_find_column(con, parquet_glob, ["related_identifier", "related_doi", "related-id"])
    if not related_col:
        logging.warning("Could not find related identifier column in Crossref relations snapshot.")
        return df

    minimal = df[["doi_norm"]].copy()
    minimal = minimal[minimal["doi_norm"] != ""].drop_duplicates()
    if minimal.empty:
        return df

    con.register("works", minimal)

    where_clause = ""
    if relation_col:
        rel = _duckdb_quote_ident(relation_col)
        where_clause = (
            f"WHERE lower(cast({rel} as varchar)) IN ('issupplementedby', 'hasrelatedmaterial', 'issourcedby')"
        )

    query = f"""
    WITH rels AS (
        SELECT
            lower(regexp_replace(cast({_duckdb_quote_ident(doi_col)} as varchar), '^https?://(dx\\.)?doi\\.org/', '')) AS doi_norm,
            cast({_duckdb_quote_ident(related_col)} as varchar) AS related_id
        FROM read_parquet('{_duckdb_escape(parquet_glob)}', union_by_name=true)
        {where_clause}
    )
    SELECT w.doi_norm, string_agg(DISTINCT rels.related_id, '; ') AS crossref_repo_links
    FROM works w
    LEFT JOIN rels ON w.doi_norm = rels.doi_norm
    GROUP BY w.doi_norm
    """

    try:
        joined = con.execute(query).fetch_df()
    except Exception as exc:
        logging.warning("Crossref relations join failed: %s", exc)
        return df

    if joined.empty:
        return df

    joined = joined.drop_duplicates(subset=["doi_norm"], keep="first")
    out = df.merge(joined, on="doi_norm", how="left")
    fill_missing(out, "repo_links", "crossref_repo_links")
    out = out.drop(columns=[c for c in ["crossref_repo_links"] if c in out.columns])
    logging.info("Applied Crossref relations snapshot join.")
    return out


def apply_registration_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Regex registration flags over title + abstract: ``reg_trial_registry``, ``reg_prospero``,
    ``reg_preregistration_wording``, ``registered_any`` and ``registration_signal`` (alias)."""
    if df.empty:
        for col in REGISTRATION_FLAG_COLS:
            if col not in df.columns:
                df[col] = pd.Series(dtype="boolean")
        return df
    title = df.get("title", pd.Series("", index=df.index)).fillna("").astype(str)
    abstract = df.get("abstract", pd.Series("", index=df.index)).fillna("").astype(str)
    text = title + " " + abstract
    any_flag = pd.Series(False, index=df.index)
    for name, pattern in REGISTRY_PATTERNS.items():
        flag = text.str.contains(pattern, na=False)
        df[f"reg_{name}"] = flag
        any_flag = any_flag | flag
    df["registered_any"] = any_flag
    df["registration_signal"] = any_flag
    return df


def apply_metadata_preprint_flag(df: pd.DataFrame) -> pd.DataFrame:
    """When the LLM did not fill ``preprint`` for a row, set it from the OpenAlex preprint
    location (``has_preprint_version``): the preprint server names, or a generic marker."""
    if df.empty or "has_preprint_version" not in df.columns:
        return df
    has_version = coerce_nullable_bool(df["has_preprint_version"]).fillna(False).astype(bool)
    preprint = df.get("preprint", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
    blank = preprint.replace({"nan": "", "None": "", "<NA>": ""}).eq("")
    mask = has_version & blank
    if not mask.any():
        if "preprint" not in df.columns:
            df["preprint"] = preprint
        return df
    servers = df.get("preprint_servers", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
    df["preprint"] = preprint
    df.loc[mask, "preprint"] = servers[mask].where(servers[mask].ne(""), "openalex:preprint_version")
    logging.info("Set preprint from OpenAlex preprint locations for %d rows.", int(mask.sum()))
    return df


def apply_corpus_flag(df: pd.DataFrame) -> pd.DataFrame:
    """``in_article_corpus``: journal articles / reviews per OpenAlex work metadata.

    Rule ``openalex_type_doi_only`` (whenever the frame carries any OpenAlex work metadata, i.e. a
    non-blank ``work_type`` on at least one row): a row is in the corpus only if it has metadata,
    ``work_type`` is article/review, ``primary_source_type`` is ``journal`` and (when a ``doi`` column
    exists) the DOI is non-blank. Rows without metadata are OUT of the corpus: metadata is joined by DOI,
    so a missing DOI or a missing OpenAlex record means we cannot tell an article from, e.g., the
    thousands of DOI-less conference abstracts the journal *Stroke* publishes. There is deliberately no
    journal-name fallback for those rows (it inflated the closed-article count for *Stroke*).

    Rule ``source_name_fallback`` (legacy frames with no metadata on any row): include unless the source
    name looks like a repository / preprint server / thesis (``NON_JOURNAL_SOURCE_PATTERN``).

    Rows are never dropped; ``corpus_rule`` records which rule applied to the frame."""
    if df.empty:
        if "in_article_corpus" not in df.columns:
            df["in_article_corpus"] = pd.Series(dtype="boolean")
        if "corpus_rule" not in df.columns:
            df["corpus_rule"] = pd.Series(dtype=object)
        return df
    blank_tokens = {"nan": "", "none": "", "null": "", "<na>": ""}
    work_type = df.get("work_type", pd.Series("", index=df.index)).fillna("").astype(str).str.strip().str.lower()
    work_type = work_type.replace(blank_tokens)
    source_type = df.get("primary_source_type", pd.Series("", index=df.index)).fillna("").astype(str).str.strip().str.lower()
    journal = df.get("journal", pd.Series("", index=df.index)).fillna("").astype(str)
    has_metadata = work_type.ne("")
    if has_metadata.any():
        is_article = work_type.isin(ARTICLE_WORK_TYPES) & source_type.eq("journal")
        if "doi" in df.columns:
            doi = df["doi"].fillna("").astype(str).str.strip().str.lower().replace(blank_tokens)
            has_doi = doi.ne("")
        else:
            has_doi = pd.Series(True, index=df.index)
        df["in_article_corpus"] = has_metadata & is_article & has_doi
        df["corpus_rule"] = "openalex_type_doi_only"
        logging.info(
            "Article corpus flag (openalex_type_doi_only): %d/%d rows in corpus; %d rows without OpenAlex "
            "metadata and %d without a DOI excluded.",
            int(df["in_article_corpus"].sum()), len(df), int((~has_metadata).sum()), int((~has_doi).sum()),
        )
    else:
        journal_like = ~journal.str.contains(NON_JOURNAL_SOURCE_PATTERN, na=False)
        df["in_article_corpus"] = journal_like
        df["corpus_rule"] = "source_name_fallback"
        logging.info(
            "Article corpus flag (source_name_fallback, no OpenAlex metadata in frame): %d/%d rows in corpus.",
            int(df["in_article_corpus"].sum()), len(df),
        )
    return df


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if pd.isna(value):
        return True
    s = str(value).strip().lower()
    return s in {"", "none", "nan", "null"}


def apply_regex_extraction(df: pd.DataFrame) -> pd.DataFrame:
    text = (
        df["title"].fillna("")
        + " "
        + df["abstract"].fillna("")
        + " "
        + df["best_oa_location_url"].fillna("")
        + " "
        + df["repo_links"].fillna("")
    )

    github_match = text.str.extract(GITHUB_URL_RE, expand=False).fillna("")
    zenodo_match = text.str.extract(ZENODO_URL_RE, expand=False).fillna("")
    osf_match = text.str.extract(OSF_URL_RE, expand=False).fillna("")

    zenodo_doi = text.str.extract(ZENODO_DOI_RE, expand=False).fillna("")
    zenodo_doi_url = zenodo_doi.map(lambda d: f"https://doi.org/{d}" if d else "")

    fill_col_if_blank(df, "github", github_match)
    fill_col_if_blank(df, "zenodo", zenodo_match)
    fill_col_if_blank(df, "zenodo", zenodo_doi_url)
    fill_col_if_blank(df, "osf", osf_match)

    # Only join links that actually matched; otherwise we end up with placeholder separators like ";".
    link_candidates = pd.concat([github_match, zenodo_match, osf_match], axis=1)
    link_candidates = link_candidates.fillna("").astype(str).apply(lambda col: col.str.strip())
    link_candidates = link_candidates.replace({"nan": "", "None": "", "none": "", "null": "", "<NA>": ""})
    regex_links = link_candidates.apply(
        lambda row: "; ".join(value for value in row.tolist() if not is_blank(value)),
        axis=1,
    )
    fill_col_if_blank(df, "repo_links", regex_links)

    fill_col_if_blank(df, "code_link", github_match)
    fill_col_if_blank(df, "data_link", zenodo_match)

    logging.info("Applied regex extraction for GitHub/Zenodo/OSF links.")
    return df


def apply_dataset_regex_extraction(df: pd.DataFrame) -> pd.DataFrame:
    """Extract dataset repository URLs / accession IDs from text fields."""
    text = (
        df["title"].fillna("")
        + " "
        + df["abstract"].fillna("")
        + " "
        + df["best_oa_location_url"].fillna("")
        + " "
        + df["repo_links"].fillna("")
        + " "
        + df.get("data_link", pd.Series("", index=df.index)).fillna("")
    )

    all_urls: List[pd.Series] = []
    all_repos: List[pd.Series] = []

    for repo_name, url_re, acc_re in DATASET_REPO_PATTERNS:
        url_match = text.str.extract(url_re, expand=False).fillna("")
        hits = url_match.str.strip().ne("")

        if acc_re is not None:
            acc_match = text.str.extract(acc_re, expand=False).fillna("")
            acc_hits = acc_match.str.strip().ne("") & ~hits
            # Convert accession/DOI to URL where possible
            _DOI_REPOS = {"dryad", "figshare", "pangaea", "mendeley_data", "openneuro", "physionet", "icpsr"}
            _ACC_URL_MAP = {
                "geo": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={}",
                "dbgap": "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id={}",
                "synapse": "https://www.synapse.org/#!Synapse:{}",
                "proteomexchange": "http://proteomecentral.proteomexchange.org/cgi/GetDataset?ID={}",
                "metabolights": "https://www.ebi.ac.uk/metabolights/{}",
                "arrayexpress": "https://www.ebi.ac.uk/biostudies/studies/{}",
                "flowrepository": "https://flowrepository.org/id/{}",
                "immport": "https://www.immport.org/shared/study/{}",
            }
            if repo_name in _DOI_REPOS:
                acc_as_url = acc_match.map(lambda d: f"https://doi.org/{d}" if d.strip() else "")
            elif repo_name in _ACC_URL_MAP:
                tmpl = _ACC_URL_MAP[repo_name]
                acc_as_url = acc_match.map(lambda a, t=tmpl: t.format(a) if a.strip() else "")
            else:
                acc_as_url = acc_match
            # Merge: prefer URL match, fall back to accession-derived URL
            combined = url_match.copy()
            combined.loc[acc_hits] = acc_as_url.loc[acc_hits]
            hits = hits | acc_hits
        else:
            combined = url_match

        if hits.any():
            all_urls.append(combined.where(hits, ""))
            repo_series = pd.Series("", index=df.index)
            repo_series.loc[hits] = repo_name
            all_repos.append(repo_series)

    if not all_urls:
        for col in ["dataset_urls", "dataset_repos"]:
            if col not in df.columns:
                df[col] = ""
        if "has_public_dataset" not in df.columns:
            df["has_public_dataset"] = False
        logging.info("Dataset regex extraction: no matches found.")
        return df

    # Combine all matches per row
    urls_df = pd.concat(all_urls, axis=1).fillna("")
    repos_df = pd.concat(all_repos, axis=1).fillna("")

    def _join_unique(row: pd.Series) -> str:
        seen: set = set()
        parts: list = []
        for v in row:
            v = str(v).strip()
            if v and v not in seen:
                seen.add(v)
                parts.append(v)
        return "; ".join(parts)

    dataset_urls = urls_df.apply(_join_unique, axis=1)
    dataset_repos = repos_df.apply(_join_unique, axis=1)

    fill_col_if_blank(df, "dataset_urls", dataset_urls)
    fill_col_if_blank(df, "dataset_repos", dataset_repos)

    has_dataset = df["dataset_urls"].fillna("").str.strip().ne("")
    if "has_public_dataset" not in df.columns:
        df["has_public_dataset"] = False
    df.loc[has_dataset, "has_public_dataset"] = True

    # Also feed dataset URLs into data_link and repo_links
    fill_col_if_blank(df, "data_link", dataset_urls)
    fill_col_if_blank(df, "repo_links", dataset_urls)

    n_found = has_dataset.sum()
    repos_found = dataset_repos[has_dataset].str.split("; ").explode().value_counts()
    repo_summary = ", ".join(f"{r}={c}" for r, c in repos_found.head(10).items())
    logging.info("Dataset regex extraction: %d papers with dataset signals (%s).", n_found, repo_summary)
    return df


def normalize_cache(cache: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    norm: Dict[str, Dict[str, Any]] = {}
    for key, value in cache.items():
        doi = normalize_doi(key)
        if not doi or not isinstance(value, dict):
            continue
        existing = norm.get(doi, {})
        norm[doi] = {**existing, **value}
    return norm


def apply_cache_to_dataframe(df: pd.DataFrame, cache: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    if not cache:
        return df

    rows = []
    for doi, payload in cache.items():
        row = {"doi_norm": doi}
        for field in CACHE_FIELDS:
            row[field + "_cache"] = payload.get(field)
        rows.append(row)

    cache_df = pd.DataFrame(rows)
    if cache_df.empty:
        return df

    out = df.merge(cache_df, on="doi_norm", how="left")
    for field in CACHE_FIELDS:
        cache_col = field + "_cache"
        if cache_col not in out.columns:
            continue
        if field in BOOL_COLS:
            fill_missing_bool(out, field, cache_col)
        else:
            fill_missing(out, field, cache_col)

    out = out.drop(columns=[c for c in out.columns if c.endswith("_cache")])
    return out


def keyword_signal_score(*parts: Any) -> int:
    text = " ".join(str(part or "") for part in parts)
    score = 0
    for _, pattern, weight in KEYWORD_SIGNAL_PATTERNS:
        if pattern.search(text):
            score += weight
    return score


def extract_keyword_hints(*parts: Any, max_hints: int = 8) -> List[str]:
    text = " ".join(str(part or "") for part in parts)
    hints: List[str] = []

    for label, pattern, _ in KEYWORD_SIGNAL_PATTERNS:
        if pattern.search(text):
            hints.append(label)

    for regex, label in [
        (GITHUB_URL_RE, "github_url"),
        (ZENODO_URL_RE, "zenodo_url"),
        (OSF_URL_RE, "osf_url"),
    ]:
        if regex.search(text):
            hints.append(label)

    # Preserve order while removing duplicates.
    deduped: List[str] = []
    seen = set()
    for hint in hints:
        if hint in seen:
            continue
        seen.add(hint)
        deduped.append(hint)
        if len(deduped) >= max_hints:
            break

    return deduped


class AsyncRateLimiter:
    def __init__(self, min_interval_seconds: float) -> None:
        self.min_interval_seconds = max(0.0, float(min_interval_seconds))
        self._lock = asyncio.Lock()
        self._next_allowed_at = 0.0

    async def wait(self) -> None:
        if self.min_interval_seconds <= 0:
            return

        loop = asyncio.get_running_loop()
        async with self._lock:
            now = loop.time()
            wait_s = max(0.0, self._next_allowed_at - now)
            if wait_s > 0:
                await asyncio.sleep(wait_s)
                now = loop.time()
            self._next_allowed_at = now + self.min_interval_seconds


async def fetch_json_async(
    session: Any,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    attempts: int = 5,
    rate_limiter: Optional[AsyncRateLimiter] = None,
    request_label: str = "",
) -> Optional[Dict[str, Any]]:
    for attempt in range(attempts):
        try:
            if rate_limiter is not None:
                await rate_limiter.wait()
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status in {429, 500, 502, 503, 504}:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else min(30.0, 2.0 ** attempt)
                    wait = min(60.0, wait)
                    if request_label:
                        logging.warning(
                            "Async request retry on %s (status=%s attempt %d/%d wait=%.1fs)",
                            request_label,
                            resp.status,
                            attempt + 1,
                            attempts,
                            wait,
                        )
                    await asyncio.sleep(wait)
                    continue
                if resp.status >= 400:
                    if request_label:
                        logging.warning("Async request failed on %s with status %s", request_label, resp.status)
                    return None
                return await resp.json(content_type=None)
        except Exception:
            if attempt == attempts - 1:
                return None
            if request_label:
                logging.warning("Async request exception on %s (attempt %d/%d)", request_label, attempt + 1, attempts)
            await asyncio.sleep(min(30.0, 2.0 ** attempt))
    return None


async def enrich_one_via_apis(
    session: Any,
    doi: str,
    title: str,
    abstract: str,
    email: str,
    github_token: str,
    current_row: Dict[str, Any],
    rate_limiters: Dict[str, AsyncRateLimiter],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    signal_text = " ".join(
        [
            str(title or ""),
            str(abstract or ""),
            str(current_row.get("best_oa_location_url", "") or ""),
            str(current_row.get("repo_links", "") or ""),
        ]
    )
    data_signal_score = keyword_signal_score(signal_text)
    data_repo_candidate = doi.startswith("10.5281/zenodo.") or data_signal_score >= 4
    code_candidate = bool(re.search(r"\b(github|gitlab|code available|source code|software package|python package|r package)\b", signal_text, re.IGNORECASE))

    need_oa = is_blank(current_row.get("best_oa_location_url")) or pd.isna(current_row.get("is_oa"))
    need_license = is_blank(current_row.get("license_unpaywall"))

    if (need_oa or need_license) and email:
        up_url = f"https://api.unpaywall.org/v2/{quote(doi, safe='')}"
        up = await fetch_json_async(
            session,
            up_url,
            params={"email": email},
            rate_limiter=rate_limiters.get("unpaywall"),
            request_label=f"Unpaywall doi={doi}",
        )
        if isinstance(up, dict):
            best = up.get("best_oa_location") or {}
            best_url = ""
            if isinstance(best, dict):
                best_url = (
                    str(best.get("url") or "")
                    or str(best.get("landing_page_url") or "")
                    or str(best.get("pdf_url") or "")
                ).strip()
            out["is_oa"] = up.get("is_oa") if up.get("is_oa") is not None else bool(best_url)
            out["best_oa_location_url"] = best_url
            out["license_unpaywall"] = up.get("license") or ""

    if is_blank(current_row.get("zenodo")) and data_repo_candidate:
        if doi.startswith("10.5281/zenodo."):
            out["zenodo"] = f"https://doi.org/{doi}"
        else:
            zen = await fetch_json_async(
                session,
                "https://zenodo.org/api/records",
                params={"q": f'doi:"{doi}"', "size": 1},
                rate_limiter=rate_limiters.get("zenodo"),
                request_label=f"Zenodo doi={doi}",
            )
            if isinstance(zen, dict):
                hits = ((zen.get("hits") or {}).get("hits") or []) if isinstance(zen.get("hits"), dict) else []
                if hits:
                    first = hits[0] if isinstance(hits[0], dict) else {}
                    links = first.get("links") or {}
                    out["zenodo"] = str(links.get("html") or "").strip()

    if email and is_blank(current_row.get("repo_links")) and (data_repo_candidate or code_candidate):
        crossref = await fetch_json_async(
            session,
            f"https://api.crossref.org/works/{quote(doi, safe='')}",
            params={"mailto": email},
            rate_limiter=rate_limiters.get("crossref"),
            request_label=f"Crossref doi={doi}",
        )
        if isinstance(crossref, dict):
            message = crossref.get("message") or {}
            if isinstance(message, dict):
                relation_links = extract_crossref_relation_links(message)
                if relation_links:
                    out["repo_links"] = "; ".join(relation_links)

    if github_token and is_blank(current_row.get("github")) and title.strip() and code_candidate:
        query = f'"{title[:120]}" in:name,description,readme'
        headers = {"Accept": "application/vnd.github+json"}
        headers["Authorization"] = f"Bearer {github_token}"
        gh = await fetch_json_async(
            session,
            "https://api.github.com/search/repositories",
            params={"q": query, "per_page": 1, "sort": "stars", "order": "desc"},
            headers=headers,
            rate_limiter=rate_limiters.get("github"),
            request_label=f"GitHub title={title[:40]}",
        )
        if isinstance(gh, dict):
            items = gh.get("items") or []
            if items and isinstance(items[0], dict):
                out["github"] = str(items[0].get("html_url") or "").strip()

    out = {k: v for k, v in out.items() if not is_blank(v) or k == "is_oa"}
    if out:
        out["_updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return out


async def run_api_enrichment_async(
    pending_rows: List[Tuple[str, str, str, Dict[str, Any]]],
    cache: Dict[str, Dict[str, Any]],
    cache_path: Path,
    email: str,
    github_token: str,
    concurrency: int,
    flush_every: int,
    base_delay_seconds: float,
) -> Dict[str, Dict[str, Any]]:
    if not pending_rows:
        return cache

    timeout = aiohttp.ClientTimeout(total=60)  # type: ignore[attr-defined]
    connector = aiohttp.TCPConnector(limit=concurrency * 2, ttl_dns_cache=300)  # type: ignore[attr-defined]
    sem = asyncio.Semaphore(concurrency)
    rate_limiters = {
        "unpaywall": AsyncRateLimiter(max(base_delay_seconds, 0.35)),
        "crossref": AsyncRateLimiter(max(base_delay_seconds, 0.5)),
        "zenodo": AsyncRateLimiter(max(base_delay_seconds, 0.6)),
    }
    if github_token:
        rate_limiters["github"] = AsyncRateLimiter(max(base_delay_seconds, 1.0))

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:  # type: ignore[attr-defined]

        async def _one(doi: str, title: str, abstract: str, row_data: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
            async with sem:
                result = await enrich_one_via_apis(
                    session,
                    doi,
                    title,
                    abstract,
                    email,
                    github_token,
                    row_data,
                    rate_limiters,
                )
                return doi, result

        tasks = [asyncio.create_task(_one(doi, title, abstract, row_data)) for doi, title, abstract, row_data in pending_rows]

        completed = 0
        for fut in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="API enrichment"):
            doi, payload = await fut
            completed += 1
            if payload:
                existing = cache.get(doi, {})
                cache[doi] = {**existing, **payload}
            if completed % flush_every == 0:
                write_json_atomic(cache, cache_path)

    write_json_atomic(cache, cache_path)
    return cache


def run_api_enrichment(
    df: pd.DataFrame,
    cfg: PipelineConfig,
    cache: Dict[str, Dict[str, Any]],
    cache_path: Path,
) -> Dict[str, Dict[str, Any]]:
    if cfg.disable_api_enrich:
        logging.info("API enrichment disabled by flag.")
        return cache

    if aiohttp is None:
        logging.warning("aiohttp is unavailable; skipping API enrichment.")
        return cache

    email = os.getenv("UNPAYWALL_EMAIL", "").strip() or cfg.openalex_mailto
    if not email:
        logging.warning("No Unpaywall email configured (OPENALEX_MAILTO/UNPAYWALL_EMAIL). Unpaywall API calls will be skipped.")

    github_token = os.getenv("GITHUB_TOKEN", "").strip()

    pending_ranked: List[Tuple[float, int, str, str, str, Dict[str, Any]]] = []
    for row in df.itertuples(index=False):
        doi = getattr(row, "doi_norm", "")
        if not doi:
            continue

        row_data = {
            "is_oa": getattr(row, "is_oa", pd.NA),
            "best_oa_location_url": getattr(row, "best_oa_location_url", ""),
            "license_unpaywall": getattr(row, "license_unpaywall", ""),
            "zenodo": getattr(row, "zenodo", ""),
            "osf": getattr(row, "osf", ""),
            "github": getattr(row, "github", ""),
            "repo_links": getattr(row, "repo_links", ""),
        }

        cached = cache.get(doi, {})
        if cached:
            for field in CACHE_FIELDS:
                if field in cached and is_blank(row_data.get(field)):
                    row_data[field] = cached.get(field)

        needs = (
            pd.isna(row_data.get("is_oa"))
            or is_blank(row_data.get("best_oa_location_url"))
            or is_blank(row_data.get("license_unpaywall"))
            or is_blank(row_data.get("zenodo"))
            or is_blank(row_data.get("osf"))
            or is_blank(row_data.get("github"))
        )
        if needs:
            cited_by_count = pd.to_numeric(getattr(row, "cited_by_count", pd.NA), errors="coerce")
            missing_fields = sum(
                [
                    int(pd.isna(row_data.get("is_oa"))),
                    int(is_blank(row_data.get("best_oa_location_url"))),
                    int(is_blank(row_data.get("license_unpaywall"))),
                    int(is_blank(row_data.get("zenodo"))),
                    int(is_blank(row_data.get("osf"))),
                    int(is_blank(row_data.get("github"))),
                ]
            )
            pending_ranked.append(
                (
                    float(cited_by_count) if not pd.isna(cited_by_count) else -1.0,
                    missing_fields,
                    doi,
                    str(getattr(row, "title", "")),
                    str(getattr(row, "abstract", "")),
                    row_data,
                )
            )

    pending_ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)

    if cfg.max_api_lookups and len(pending_ranked) > cfg.max_api_lookups:
        pending_ranked = pending_ranked[: cfg.max_api_lookups]

    pending = [(doi, title, abstract, row_data) for _, _, doi, title, abstract, row_data in pending_ranked]

    if not pending:
        logging.info("No rows require API enrichment.")
        return cache

    logging.info("Running API enrichment for %d DOI rows.", len(pending))
    if not github_token:
        logging.info(
            "GITHUB_TOKEN not set; skipping GitHub search API enrichment to avoid unauthenticated search throttling."
        )
    else:
        logging.info("GITHUB_TOKEN detected; GitHub search API enrichment enabled.")

    try:
        cache = asyncio.run(
            run_api_enrichment_async(
                pending_rows=pending,
                cache=cache,
                cache_path=cache_path,
                email=email,
                github_token=github_token,
                concurrency=cfg.api_concurrency,
                flush_every=cfg.cache_flush_every,
                base_delay_seconds=cfg.api_delay_seconds,
            )
        )
    except RuntimeError:
        loop = asyncio.get_event_loop()
        cache = loop.run_until_complete(
            run_api_enrichment_async(
                pending_rows=pending,
                cache=cache,
                cache_path=cache_path,
                email=email,
                github_token=github_token,
                concurrency=cfg.api_concurrency,
                flush_every=cfg.cache_flush_every,
                base_delay_seconds=cfg.api_delay_seconds,
            )
        )

    return cache


# ── Dataset repository API enrichment ─────────────────────────────────────────

async def search_datacite_for_doi(
    session: Any,
    doi: str,
    rate_limiter: Optional[AsyncRateLimiter] = None,
) -> List[Dict[str, str]]:
    """Query DataCite for datasets related to a DOI.

    DataCite indexes Dryad, Figshare, Zenodo, Pangaea, and many others.
    Returns list of {"url": ..., "repo": ...} dicts.
    """
    results: List[Dict[str, str]] = []
    data = await fetch_json_async(
        session,
        "https://api.datacite.org/dois",
        params={
            "query": f'relatedIdentifiers.relatedIdentifier:"{doi}"',
            "resource-type-id": "dataset",
            "page[size]": "5",
        },
        rate_limiter=rate_limiter,
        request_label=f"DataCite doi={doi}",
    )
    if not isinstance(data, dict):
        return results
    items = (data.get("data") or []) if isinstance(data.get("data"), list) else []
    for item in items[:5]:
        attrs = item.get("attributes", {}) if isinstance(item, dict) else {}
        item_doi = attrs.get("doi", "")
        url = f"https://doi.org/{item_doi}" if item_doi else ""
        publisher = str(attrs.get("publisher", "") or "").lower()
        # Infer repository name from publisher
        repo = "datacite"
        for name in ("dryad", "figshare", "zenodo", "pangaea", "mendeley", "dataverse"):
            if name in publisher:
                repo = name
                break
        if url:
            results.append({"url": url, "repo": repo})
    return results


async def search_dryad_for_doi(
    session: Any,
    doi: str,
    rate_limiter: Optional[AsyncRateLimiter] = None,
) -> Optional[Dict[str, str]]:
    """Query Dryad API for a dataset linked to a paper DOI."""
    data = await fetch_json_async(
        session,
        "https://datadryad.org/api/v2/search",
        params={"q": doi, "per_page": 1},
        rate_limiter=rate_limiter,
        request_label=f"Dryad doi={doi}",
    )
    if not isinstance(data, dict):
        return None
    items = data.get("_embedded", {}).get("stash:datasets", [])
    if items and isinstance(items[0], dict):
        ds_doi = items[0].get("identifier", "")
        if ds_doi:
            return {"url": f"https://doi.org/{ds_doi}", "repo": "dryad"}
    return None


async def search_figshare_for_doi(
    session: Any,
    doi: str,
    rate_limiter: Optional[AsyncRateLimiter] = None,
) -> Optional[Dict[str, str]]:
    """Query Figshare API for datasets linked to a paper DOI."""
    if rate_limiter:
        await rate_limiter.wait()
    try:
        payload = json.dumps({"search_for": doi, "item_type": 3, "page_size": 1})
        async with session.post(
            "https://api.figshare.com/v2/articles/search",
            data=payload,
            headers={"Content-Type": "application/json"},
        ) as resp:
            if resp.status >= 400:
                return None
            items = await resp.json(content_type=None)
            if isinstance(items, list) and items:
                first = items[0]
                url = str(first.get("url_public_html") or first.get("url") or "").strip()
                if url:
                    return {"url": url, "repo": "figshare"}
    except Exception:
        pass
    return None


async def enrich_one_dataset_repos(
    session: Any,
    doi: str,
    title: str,
    abstract: str,
    current_row: Dict[str, Any],
    rate_limiters: Dict[str, AsyncRateLimiter],
) -> Dict[str, Any]:
    """Orchestrate dataset repository search for a single DOI."""
    out: Dict[str, Any] = {}

    # Skip if already populated
    if not is_blank(current_row.get("dataset_urls")):
        return out

    # Collect discovered datasets
    found: List[Dict[str, str]] = []

    # 1. DataCite (primary — indexes most repos)
    dc_results = await search_datacite_for_doi(session, doi, rate_limiters.get("datacite"))
    found.extend(dc_results)

    # 2. If DataCite found nothing, try direct Dryad + Figshare APIs
    if not found:
        dryad_result = await search_dryad_for_doi(session, doi, rate_limiters.get("dryad"))
        if dryad_result:
            found.append(dryad_result)
        figshare_result = await search_figshare_for_doi(session, doi, rate_limiters.get("figshare"))
        if figshare_result:
            found.append(figshare_result)

    if found:
        # Deduplicate by URL
        seen_urls: set = set()
        unique: List[Dict[str, str]] = []
        for item in found:
            url_norm = item["url"].rstrip("/").lower()
            if url_norm not in seen_urls:
                seen_urls.add(url_norm)
                unique.append(item)
        out["dataset_urls"] = "; ".join(item["url"] for item in unique)
        out["dataset_repos"] = "; ".join(
            dict.fromkeys(item["repo"] for item in unique)  # preserves order, deduplicates
        )

    if out:
        out["_updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return out


async def run_dataset_enrichment_async(
    pending_rows: List[Tuple[str, str, str, Dict[str, Any]]],
    cache: Dict[str, Dict[str, Any]],
    cache_path: Path,
    concurrency: int,
    flush_every: int,
    base_delay_seconds: float,
) -> Dict[str, Dict[str, Any]]:
    if not pending_rows:
        return cache

    timeout = aiohttp.ClientTimeout(total=60)  # type: ignore[attr-defined]
    connector = aiohttp.TCPConnector(limit=concurrency * 2, ttl_dns_cache=300)  # type: ignore[attr-defined]
    sem = asyncio.Semaphore(concurrency)
    rate_limiters = {
        "datacite": AsyncRateLimiter(max(base_delay_seconds, 0.5)),
        "dryad": AsyncRateLimiter(max(base_delay_seconds, 1.0)),
        "figshare": AsyncRateLimiter(max(base_delay_seconds, 0.5)),
    }

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:  # type: ignore[attr-defined]

        async def _one(doi: str, title: str, abstract: str, row_data: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
            async with sem:
                result = await enrich_one_dataset_repos(
                    session, doi, title, abstract, row_data, rate_limiters,
                )
                return doi, result

        tasks = [asyncio.create_task(_one(doi, title, abstract, row_data))
                 for doi, title, abstract, row_data in pending_rows]

        completed = 0
        for fut in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Dataset repo search"):
            doi, payload = await fut
            completed += 1
            if payload:
                existing = cache.get(doi, {})
                cache[doi] = {**existing, **payload}
            if completed % flush_every == 0:
                write_json_atomic(cache, cache_path)

    write_json_atomic(cache, cache_path)
    return cache


def run_dataset_enrichment(
    df: pd.DataFrame,
    cfg: PipelineConfig,
    cache: Dict[str, Dict[str, Any]],
    cache_path: Path,
) -> Dict[str, Dict[str, Any]]:
    """Run dataset repository API enrichment (DataCite, Dryad, Figshare)."""
    if cfg.disable_dataset_search:
        logging.info("Dataset repository search disabled by flag.")
        return cache
    if cfg.disable_api_enrich:
        logging.info("Dataset repository search skipped (API enrichment disabled).")
        return cache
    if aiohttp is None:
        logging.warning("aiohttp is unavailable; skipping dataset repository search.")
        return cache

    pending_ranked: List[Tuple[float, int, str, str, str, Dict[str, Any]]] = []
    for row in df.itertuples(index=False):
        doi = getattr(row, "doi_norm", "")
        if not doi:
            continue

        row_data = {
            "dataset_urls": getattr(row, "dataset_urls", ""),
            "dataset_repos": getattr(row, "dataset_repos", ""),
        }

        cached = cache.get(doi, {})
        if cached:
            for field in ("dataset_urls", "dataset_repos"):
                if field in cached and is_blank(row_data.get(field)):
                    row_data[field] = cached.get(field)

        if not is_blank(row_data.get("dataset_urls")):
            continue

        # Prioritize papers with data-sharing signals
        signal_text = " ".join([
            str(getattr(row, "title", "") or ""),
            str(getattr(row, "abstract", "") or ""),
            str(getattr(row, "best_oa_location_url", "") or ""),
            str(getattr(row, "repo_links", "") or ""),
            str(getattr(row, "data_link", "") or ""),
        ])
        score = keyword_signal_score(signal_text)
        cited = pd.to_numeric(getattr(row, "cited_by_count", pd.NA), errors="coerce")

        pending_ranked.append((
            float(score),
            float(cited) if not pd.isna(cited) else -1.0,
            doi,
            str(getattr(row, "title", "")),
            str(getattr(row, "abstract", "")),
            row_data,
        ))

    # Sort by signal score (high first), then citations
    pending_ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)

    if cfg.max_api_lookups and len(pending_ranked) > cfg.max_api_lookups:
        pending_ranked = pending_ranked[: cfg.max_api_lookups]

    pending = [(doi, title, abstract, row_data)
               for _, _, doi, title, abstract, row_data in pending_ranked]

    if not pending:
        logging.info("No rows require dataset repository search.")
        return cache

    logging.info("Running dataset repository search for %d DOIs (DataCite → Dryad → Figshare).", len(pending))

    try:
        cache = asyncio.run(
            run_dataset_enrichment_async(
                pending_rows=pending,
                cache=cache,
                cache_path=cache_path,
                concurrency=cfg.api_concurrency,
                flush_every=cfg.cache_flush_every,
                base_delay_seconds=cfg.api_delay_seconds,
            )
        )
    except RuntimeError:
        loop = asyncio.get_event_loop()
        cache = loop.run_until_complete(
            run_dataset_enrichment_async(
                pending_rows=pending,
                cache=cache,
                cache_path=cache_path,
                concurrency=cfg.api_concurrency,
                flush_every=cfg.cache_flush_every,
                base_delay_seconds=cfg.api_delay_seconds,
            )
        )

    return cache


def resolve_embedding_device(requested: str) -> str:
    req = (requested or "auto").strip().lower()
    if req not in {"auto", "cpu", "cuda", "mps"}:
        req = "auto"

    try:
        import torch  # type: ignore
    except Exception:
        if req != "cpu":
            logging.warning("PyTorch unavailable for device probing; using CPU embeddings.")
        return "cpu"

    has_cuda = bool(torch.cuda.is_available())
    has_mps = bool(
        hasattr(torch.backends, "mps")
        and torch.backends.mps is not None
        and torch.backends.mps.is_available()
    )

    if req == "cpu":
        return "cpu"
    if req == "cuda":
        if has_cuda:
            return "cuda"
        logging.warning("Requested embedding device 'cuda' is not available; falling back.")
    if req == "mps":
        if has_mps:
            return "mps"
        logging.warning("Requested embedding device 'mps' is not available; falling back.")

    if has_cuda:
        return "cuda"
    if has_mps:
        return "mps"
    return "cpu"


def compute_embedding_scores(df: pd.DataFrame, cfg: PipelineConfig) -> pd.DataFrame:
    if cfg.embedding_top_k <= 0 or df.empty:
        if "open_science_score" not in df.columns:
            df["open_science_score"] = pd.NA
        return df

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        import numpy as np
    except Exception as exc:
        logging.warning("SentenceTransformer unavailable; skipping embedding stage: %s", exc)
        if "open_science_score" not in df.columns:
            df["open_science_score"] = pd.NA
        return df

    device = resolve_embedding_device(cfg.embedding_device)
    logging.info("Computing embedding scores with model '%s' on device '%s'...", cfg.embedding_model, device)
    model = SentenceTransformer(cfg.embedding_model, device=device)

    concept = "open science code available data available github zenodo osf preregistration preprint"
    concept_vec = model.encode([concept], convert_to_numpy=True, normalize_embeddings=True)[0]

    scores = np.empty(len(df), dtype="float32")
    title = df["title"].fillna("").astype(str)
    abstract = df["abstract"].fillna("").astype(str)

    for start in tqdm(range(0, len(df), cfg.embedding_batch_size), desc="Embeddings"):
        end = min(start + cfg.embedding_batch_size, len(df))
        texts = (title.iloc[start:end] + " " + abstract.iloc[start:end]).tolist()
        vecs = model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=cfg.embedding_batch_size,
        )
        scores[start:end] = vecs @ concept_vec

    df["open_science_score"] = scores
    return df


def select_llm_indices(df: pd.DataFrame, max_items: int) -> List[int]:
    if max_items <= 0 or df.empty:
        return []

    tmp = pd.DataFrame({"_idx": df.index})
    tmp["keyword_signal_score"] = [
        keyword_signal_score(
            row.get("title", ""),
            row.get("abstract", ""),
            row.get("best_oa_location_url", ""),
            row.get("repo_links", ""),
            row.get("github", ""),
            row.get("zenodo", ""),
            row.get("osf", ""),
        )
        for _, row in df.iterrows()
    ]
    tmp["has_fulltext_candidate"] = df.get("best_oa_location_url", pd.Series(index=df.index, dtype=object)).map(
        lambda value: 0 if is_blank(value) else 1
    )
    tmp["open_science_score"] = pd.to_numeric(df.get("open_science_score"), errors="coerce").fillna(-1.0)
    tmp["cited_by_count"] = pd.to_numeric(df.get("cited_by_count"), errors="coerce").fillna(-1.0)
    tmp = tmp.sort_values(
        by=["keyword_signal_score", "has_fulltext_candidate", "open_science_score", "cited_by_count"],
        ascending=[False, False, False, False],
    )
    return tmp.head(max_items)["_idx"].tolist()


def llm_row_key(row: pd.Series) -> str:
    doi = normalize_doi(row.get("doi_norm") or row.get("doi") or "")
    if doi:
        return f"doi:{doi}"
    raw = f"{str(row.get('title', ''))}|{str(row.get('abstract', ''))[:1200]}"
    digest = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()
    return f"hash:{digest}"


def normalize_bool_like(value: Any) -> Any:
    if pd.isna(value):
        return pd.NA
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"", "nan", "none", "null", "unknown", "n/a"}:
        return pd.NA
    if s in {"true", "t", "1", "yes", "y"}:
        return True
    if s in {"false", "f", "0", "no", "n"}:
        return False
    return pd.NA


def parse_llm_payload(raw: Any) -> Dict[str, Any]:
    payload: Dict[str, Any]
    if isinstance(raw, dict):
        payload = raw
    else:
        try:
            payload = json.loads(str(raw))
        except Exception:
            payload = {}

    def _normalize_text_field(value: Any) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, str):
            cleaned = value.strip()
            return "" if cleaned.lower() in {"", "none", "nan", "null", "false"} else cleaned
        return ""

    out: Dict[str, Any] = {
        "code_link": _normalize_text_field(payload.get("code_link", "") if isinstance(payload, dict) else ""),
        "data_link": _normalize_text_field(payload.get("data_link", "") if isinstance(payload, dict) else ""),
        "preregistered": payload.get("preregistered", pd.NA) if isinstance(payload, dict) else pd.NA,
        "preprint": _normalize_text_field(payload.get("preprint", "") if isinstance(payload, dict) else ""),
    }
    out["preregistered"] = normalize_bool_like(out.get("preregistered"))
    return out


def clean_text(text: str) -> str:
    cleaned = TAG_RE.sub(" ", text)
    cleaned = WS_RE.sub(" ", cleaned)
    return cleaned.strip()


def fetch_fulltext_snippet(session: requests.Session, url: str, max_chars: int) -> str:
    if not url:
        return ""
    try:
        resp = session.get(url, timeout=25)
        if resp.status_code >= 400:
            return ""
        content_type = str(resp.headers.get("Content-Type", "")).lower()
        if "pdf" in content_type or url.lower().endswith(".pdf"):
            return ""
        body = resp.text or ""
        body = clean_text(body)
        if not body:
            return ""
        return body[:max_chars]
    except Exception:
        return ""


def llm_system_prompt() -> str:
    return (
        "You extract open-science signals from biomedical papers. "
        "Use the title, abstract, keyword hints, and optional full-text snippet. "
        "Return strict JSON with keys: code_link, data_link, preregistered, preprint. "
        "Only report signals supported by the provided evidence. "
        "Use empty string when unknown. preregistered should be true/false/null."
    )


def llm_user_prompt(title: str, abstract: str, fulltext_snippet: str, keyword_hints: Sequence[str]) -> str:
    prompt = f"Title: {title}\\nAbstract: {abstract}"
    if keyword_hints:
        prompt += f"\\nKeywordHints: {', '.join(keyword_hints)}"
    if fulltext_snippet:
        prompt += f"\\nFullTextSnippet: {fulltext_snippet}"
    return prompt


def llm_extract_one_openai(
    client: Any,
    model: str,
    temperature: float,
    title: str,
    abstract: str,
    fulltext_snippet: str,
    keyword_hints: Sequence[str],
) -> Dict[str, Any]:
    user_prompt = llm_user_prompt(title, abstract, fulltext_snippet, keyword_hints)
    system_prompt = llm_system_prompt()

    for attempt in range(4):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
            return parse_llm_payload(content)
        except Exception:
            if attempt == 3:
                return {"code_link": "", "data_link": "", "preregistered": pd.NA, "preprint": ""}
            time.sleep(min(15.0, 2.0 ** attempt))

    return {"code_link": "", "data_link": "", "preregistered": pd.NA, "preprint": ""}


def llm_extract_one_ollama(
    session: requests.Session,
    base_url: str,
    model: str,
    temperature: float,
    title: str,
    abstract: str,
    fulltext_snippet: str,
    keyword_hints: Sequence[str],
) -> Dict[str, Any]:
    payload = {
        "model": model,
        "prompt": llm_system_prompt() + "\\n\\n" + llm_user_prompt(title, abstract, fulltext_snippet, keyword_hints),
        "format": "json",
        "stream": False,
        "options": {"temperature": temperature},
    }

    data = safe_post_json(session, f"{base_url}/api/generate", payload, timeout=180)
    if not isinstance(data, dict):
        return {"code_link": "", "data_link": "", "preregistered": pd.NA, "preprint": ""}

    raw = data.get("response", "")
    return parse_llm_payload(raw)


def run_llm_extraction(
    df: pd.DataFrame,
    cfg: PipelineConfig,
    llm_cache: Dict[str, Dict[str, Any]],
    llm_cache_path: Path,
    session: requests.Session,
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    if cfg.llm_max_items <= 0:
        logging.info("LLM stage disabled (--llm-max-items 0).")
        return df, llm_cache

    provider = cfg.llm_provider.lower().strip()
    model_name = cfg.llm_model if provider == "openai" else cfg.ollama_model

    openai_client: Any = None
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            logging.warning("OPENAI_API_KEY not set; skipping LLM extraction.")
            return df, llm_cache
        try:
            from openai import OpenAI  # type: ignore

            openai_client = OpenAI(api_key=api_key)
        except Exception as exc:
            logging.warning("OpenAI SDK unavailable; skipping LLM extraction: %s", exc)
            return df, llm_cache
    elif provider == "ollama":
        health = safe_get_json(session, f"{cfg.ollama_base_url}/api/tags")
        if health is None:
            logging.warning("Ollama is not reachable at %s; skipping LLM extraction.", cfg.ollama_base_url)
            return df, llm_cache
    else:
        logging.warning("Unknown llm provider '%s'; skipping LLM extraction.", provider)
        return df, llm_cache

    indices = select_llm_indices(df, cfg.llm_max_items)
    if not indices:
        return df, llm_cache

    logging.info("Running %s LLM extraction on %d candidate papers.", provider, len(indices))

    llm_cache = llm_cache if isinstance(llm_cache, dict) else {}
    fulltext_fetches = 0

    for i, idx in enumerate(tqdm(indices, desc="LLM extraction"), start=1):
        row = df.loc[idx]
        key = f"{provider}:{model_name}:{llm_row_key(row)}"

        payload = llm_cache.get(key)
        if not payload:
            fulltext_snippet = ""
            if cfg.llm_use_fulltext and fulltext_fetches < cfg.llm_max_fulltext_fetch:
                fulltext_snippet = fetch_fulltext_snippet(
                    session,
                    str(row.get("best_oa_location_url", "")),
                    cfg.fulltext_char_limit,
                )
                if fulltext_snippet:
                    fulltext_fetches += 1

            title = str(row.get("title", ""))
            abstract = str(row.get("abstract", ""))
            keyword_hints = extract_keyword_hints(
                title,
                abstract,
                row.get("best_oa_location_url", ""),
                row.get("repo_links", ""),
                fulltext_snippet,
            )

            if provider == "openai":
                payload = llm_extract_one_openai(
                    openai_client,
                    cfg.llm_model,
                    cfg.llm_temperature,
                    title,
                    abstract,
                    fulltext_snippet,
                    keyword_hints,
                )
            else:
                payload = llm_extract_one_ollama(
                    session,
                    cfg.ollama_base_url,
                    cfg.ollama_model,
                    cfg.llm_temperature,
                    title,
                    abstract,
                    fulltext_snippet,
                    keyword_hints,
                )

            llm_cache[key] = payload

        payload = parse_llm_payload(payload)
        for field in LLM_FIELDS:
            if field == "preregistered":
                if pd.isna(df.at[idx, field]):
                    df.at[idx, field] = payload.get(field, pd.NA)
            else:
                if is_blank(df.at[idx, field]):
                    df.at[idx, field] = payload.get(field, "")

        if i % cfg.cache_flush_every == 0:
            write_json_atomic(llm_cache, llm_cache_path)

    write_json_atomic(llm_cache, llm_cache_path)
    return df, llm_cache


# ---------------------------------------------------------------------------
# Data-availability-statement audit (Europe PMC full text, open-access subset)
# ---------------------------------------------------------------------------


def _jats_text(element: ET.Element) -> str:
    return WS_RE.sub(" ", " ".join(element.itertext())).strip()


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence of ``text`` that contains the span ``[start, end)``."""
    sentence_start = 0
    sentence_end = len(text)
    for boundary in DAS_SENTENCE_BOUNDARY.finditer(text):
        if boundary.end() <= start:
            sentence_start = boundary.end()
        elif boundary.start() >= end:
            sentence_end = boundary.start()
            break
    return text[sentence_start:sentence_end].strip()


def extract_das_statements(xml_text: Any) -> Dict[str, Any]:
    """Pull data/code-availability statements out of a JATS XML document.

    Looks, in order, at ``<sec sec-type="data-availability">``-style sections, sections whose
    title reads like a DAS, ``notes``/``fn``/``custom-meta``/``supplementary-material`` elements
    flagged as availability statements, and finally (AHA journals put the statement unmarked at
    the start of Methods) paragraphs that start like a DAS or contain a DAS-style sentence.
    Returns ``{"statements": [...], "flags": {...}}`` or ``{"parse_error": True}``."""
    try:
        payload = xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text
        root = ET.fromstring(payload)
    except (ET.ParseError, TypeError, AttributeError):
        return {"parse_error": True}

    statements: List[Dict[str, str]] = []
    seen: set = set()

    def consider(element: ET.Element, how: str, label: str) -> None:
        text = _jats_text(element)
        if not text or text in seen or len(text) > 6000:
            return
        seen.add(text)
        statements.append({"how": how, "label": label[:120], "text": text})

    for sec in root.iter("sec"):
        sec_type = (sec.get("sec-type") or "").lower()
        title_el = sec.find("title")
        title = _jats_text(title_el) if title_el is not None else ""
        if sec_type in DAS_SEC_TYPES or any(token in sec_type for token in ("availab", "data-sharing")):
            consider(sec, "sec-type", sec_type or title)
        elif title and DAS_TITLE_PATTERN.search(title) and len(title) < 90:
            consider(sec, "sec-title", title)
    for tag in ("notes", "fn", "custom-meta", "supplementary-material"):
        for element in root.iter(tag):
            attrs = " ".join(f"{k}={v}" for k, v in element.attrib.items()).lower()
            title_el = element.find("title")
            title = _jats_text(title_el) if title_el is not None else ""
            if "availab" in attrs or "data-sharing" in attrs or (title and DAS_TITLE_PATTERN.search(title)):
                consider(element, tag, attrs or title)
    if not statements:
        for paragraph in root.iter("p"):
            text = _jats_text(paragraph)
            if DAS_PREFIX_PATTERN.match(text):
                consider(paragraph, "p-prefix", text[:40])
                continue
            match = DAS_SENTENCE_PATTERN.search(text)
            if match:
                sentence = _sentence_around(text, match.start(), match.end())
                if 20 < len(sentence) < 700 and sentence not in seen:
                    seen.add(sentence)
                    statements.append({"how": "p-sentence", "label": "unmarked DAS sentence", "text": sentence})

    body_text = _jats_text(root)
    flags = {
        "mentions_trial_registration": bool(
            re.search(r"\bNCT\d{8}\b|ISRCTN\d{8}|ChiCTR|clinicaltrials\.gov|PROSPERO|CRD42\d{6}", body_text)
        ),
        "mentions_github": "github.com" in body_text.lower(),
        "mentions_supplement": bool(re.search(r"supplementa(l|ry)", body_text, re.IGNORECASE)),
        "n_chars": len(body_text),
    }
    return {"statements": statements, "flags": flags}


def classify_das_text(text: str) -> Dict[str, Any]:
    """Multi-label regex classification of a DAS; ``primary`` is the first label in
    ``DAS_PRIMARY_PRIORITY`` that fires, else ``other_or_unclear``."""
    text = str(text or "")
    labels = {name: bool(pattern.search(text)) for name, pattern in DAS_PATTERNS.items()}
    primary = next((name for name in DAS_PRIMARY_PRIORITY if labels[name]), DAS_OTHER_LABEL)
    return {**{f"lab_{name}": flag for name, flag in labels.items()}, "primary": primary}


def load_das_cache(path: Path) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Returns ``(resolved, fetched)``: DOI -> Europe PMC resolution record and PMCID -> full-text
    extraction record."""
    resolved: Dict[str, Dict[str, Any]] = {}
    fetched: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return resolved, fetched
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            kind = rec.get("kind")
            if kind == "resolve" and rec.get("doi"):
                resolved[normalize_doi(rec["doi"])] = rec
            elif kind == "fetch" and rec.get("pmcid"):
                fetched[str(rec["pmcid"])] = rec
    return resolved, fetched


def append_das_cache(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(make_json_safe(rec), ensure_ascii=False) + "\n")
        handle.flush()


def europepmc_doi_query(dois: Sequence[str]) -> str:
    clause = " OR ".join(f'DOI:"{doi}"' for doi in dois)
    return f"({clause}) AND OPEN_ACCESS:y AND HAS_FT:y AND SRC:MED"


def resolve_pmcids_europepmc(
    session: requests.Session,
    dois: Sequence[str],
    timeout_seconds: int,
    max_attempts: int = 3,
) -> Optional[Dict[str, Dict[str, Any]]]:
    """Resolve up to ``EUROPEPMC_DOI_BATCH_SIZE`` DOIs to PMCIDs with open-access full text in
    Europe PMC (``OPEN_ACCESS:y AND HAS_FT:y``: records that only have HAS_FT, e.g. author
    manuscripts, answer a persistent 500 on ``fullTextXML``). Returns a record for every DOI in
    the batch (``has_ft`` False when not found), or None when the request failed (the batch is
    then left unresolved and retried on the next run)."""
    dois = [normalize_doi(d) for d in dois if normalize_doi(d)]
    if not dois:
        return {}
    payload = safe_get_json(
        session,
        f"{EUROPEPMC_REST_BASE}/search",
        params={
            "query": europepmc_doi_query(dois),
            "format": "json",
            "resultType": "lite",
            "pageSize": 100,
        },
        timeout=timeout_seconds,
        max_attempts=max_attempts,
        request_label="Europe PMC DOI->PMCID",
    )
    if payload is None:
        return None
    hits = ((payload.get("resultList") or {}).get("result") or []) if isinstance(payload, dict) else []
    out: Dict[str, Dict[str, Any]] = {doi: {"kind": "resolve", "doi": doi, "pmcid": "", "pmid": "", "has_ft": False} for doi in dois}
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        doi = normalize_doi(hit.get("doi") or "")
        pmcid = str(hit.get("pmcid") or "").strip()
        if doi in out and pmcid and not out[doi]["pmcid"]:
            out[doi].update({"pmcid": pmcid, "pmid": str(hit.get("pmid") or ""), "has_ft": True})
    return out


def fetch_europepmc_fulltext_record(
    session: requests.Session,
    pmcid: str,
    timeout_seconds: int,
    delay_seconds: float = 0.0,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """Fetch ``/{pmcid}/fullTextXML`` and extract DAS statements. ``http`` holds the final status
    (200 = audited; 404 = no XML; "error" = transient failure, not cached)."""
    rec: Dict[str, Any] = {"kind": "fetch", "pmcid": pmcid, "http": "error"}
    url = f"{EUROPEPMC_REST_BASE}/{pmcid}/fullTextXML"
    last_status: Optional[int] = None
    for attempt in range(max(1, max_attempts)):
        try:
            resp = session.get(url, timeout=timeout_seconds)
        except Exception as exc:
            rec["error"] = str(exc)[:200]
            time.sleep(min(30.0, 2.0 ** attempt))
            continue
        status = resp.status_code
        last_status = status
        if status == 200 and (resp.text or "").strip():
            rec.update(extract_das_statements(resp.text))
            rec["http"] = 200
            break
        if status == 429 or status >= 500:
            retry_after = _coerce_float(resp.headers.get("Retry-After")) if getattr(resp, "headers", None) else None
            time.sleep(min(60.0, retry_after if retry_after is not None else 5.0 + 3.0 * attempt))
            continue
        rec["http"] = status if status != 200 else "empty"
        break
    if rec["http"] == "error" and last_status is not None:
        # Europe PMC answers a persistent 500 for some PMCIDs (no XML rendition); record the
        # status so the article counts as not audited instead of being re-fetched every run.
        rec["http"] = last_status
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    return rec


def select_das_audit_sample(
    df: pd.DataFrame,
    sample_per_year: int,
    seed: int,
    resolved: Dict[str, Dict[str, Any]],
    resolve_fn: Callable[[Sequence[str]], Optional[Dict[str, Dict[str, Any]]]],
    on_resolved: Optional[Callable[[Sequence[Dict[str, Any]]], None]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Per year: shuffle the in-corpus DOIs deterministically and walk them in order, resolving
    unresolved DOIs in look-ahead batches, until ``sample_per_year`` articles with full text are
    selected. The selection depends only on the seed and the corpus, not on batching, so a
    resumed run picks the same articles. Returns DOI -> resolution record for selected rows."""
    doi_norm = _doi_norm_series(df)
    in_corpus = coerce_nullable_bool(df.get("in_article_corpus", pd.Series(True, index=df.index))).fillna(True).astype(bool)
    years = pd.to_numeric(df.get("year"), errors="coerce")
    candidates = pd.DataFrame({"doi": doi_norm, "year": years})[in_corpus & doi_norm.ne("") & years.notna()]
    selected: Dict[str, Dict[str, Any]] = {}
    for year, group in candidates.groupby("year"):
        dois = sorted(set(group["doi"].tolist()))
        rng = random.Random(f"{seed}:{int(year)}")
        rng.shuffle(dois)
        picked = 0
        position = 0
        while position < len(dois) and picked < sample_per_year:
            doi = dois[position]
            if doi not in resolved:
                batch = [d for d in dois[position : position + 4 * EUROPEPMC_DOI_BATCH_SIZE] if d not in resolved][:EUROPEPMC_DOI_BATCH_SIZE]
                result = resolve_fn(batch)
                if result is None:
                    logging.warning("Europe PMC resolution failed for a batch in %d; leaving it for the next run.", int(year))
                    break
                resolved.update(result)
                if on_resolved:
                    on_resolved(list(result.values()))
                continue
            rec = resolved[doi]
            if rec.get("has_ft") and rec.get("pmcid"):
                selected[doi] = rec
                picked += 1
            position += 1
        logging.info("DAS audit %d: selected %d/%d full-text articles from %d candidates.", int(year), picked, sample_per_year, len(dois))
    return selected


def apply_das_results(
    df: pd.DataFrame,
    selected: Dict[str, Dict[str, Any]],
    fetched: Dict[str, Dict[str, Any]],
) -> pd.DataFrame:
    """Write das_pmcid / das_available / das_has_statement / das_primary / das_text."""
    for col in DAS_TEXT_COLS:
        if col not in df.columns:
            df[col] = ""
    for col in DAS_BOOL_COLS:
        if col not in df.columns:
            df[col] = pd.Series([pd.NA] * len(df), index=df.index, dtype="boolean")
    df["das_available"] = coerce_nullable_bool(df["das_available"]).fillna(False)
    if not selected:
        return df
    doi_norm = _doi_norm_series(df)
    rows = {}
    for doi, rec in selected.items():
        pmcid = str(rec.get("pmcid") or "")
        fetch_rec = fetched.get(pmcid)
        row: Dict[str, Any] = {"das_pmcid": pmcid, "das_available": False, "das_has_statement": pd.NA, "das_primary": "", "das_text": ""}
        if fetch_rec and fetch_rec.get("http") == 200 and not fetch_rec.get("parse_error"):
            statements = fetch_rec.get("statements") or []
            text = " || ".join(str(s.get("text") or "") for s in statements if isinstance(s, dict))
            row["das_available"] = True
            row["das_has_statement"] = bool(statements)
            row["das_primary"] = classify_das_text(text)["primary"] if statements else DAS_NO_STATEMENT_LABEL
            row["das_text"] = text[:DAS_TEXT_MAX_CHARS]
        rows[doi] = row
    mask = doi_norm.isin(rows.keys())
    results = pd.DataFrame.from_dict(rows, orient="index").reindex(doi_norm[mask].to_numpy())
    for col in DAS_TEXT_COLS:
        df.loc[mask, col] = results[col].fillna("").astype(str).to_numpy()
    for col in DAS_BOOL_COLS:
        df[col] = coerce_nullable_bool(df[col])
        df.loc[mask, col] = coerce_nullable_bool(results[col].reset_index(drop=True)).to_numpy()
    df["das_available"] = coerce_nullable_bool(df["das_available"]).fillna(False)
    return df


def run_das_audit(
    df: pd.DataFrame,
    cfg: PipelineConfig,
    paths: PipelinePaths,
    session: requests.Session,
) -> pd.DataFrame:
    """DAS audit stage (``--das-audit-sample-per-year N``): resolve in-corpus DOIs to PMCIDs via
    Europe PMC search (batched ``DOI:"..." OR ...`` with ``HAS_FT:y``), sample N per year among
    those with full text, fetch the JATS XML with a small thread pool, extract and classify the
    data-availability statement. Everything is appended to ``das_cache.jsonl`` as it completes,
    so an interrupted run resumes. Scope note: only the open-access subset has full text, so
    rates are optimistic relative to the whole corpus."""
    if cfg.das_audit_sample_per_year <= 0:
        return apply_das_results(df, {}, {})
    if df.empty:
        return apply_das_results(df, {}, {})

    resolved, fetched = load_das_cache(paths.das_cache)
    logging.info("DAS audit: %d DOIs resolved and %d full texts cached in %s", len(resolved), len(fetched), paths.das_cache)

    def _resolve(batch: Sequence[str]) -> Optional[Dict[str, Dict[str, Any]]]:
        result = resolve_pmcids_europepmc(session, batch, cfg.das_audit_timeout_seconds)
        if cfg.das_audit_delay_seconds > 0:
            time.sleep(cfg.das_audit_delay_seconds)
        return result

    selected = select_das_audit_sample(
        df,
        cfg.das_audit_sample_per_year,
        cfg.das_audit_seed,
        resolved,
        _resolve,
        on_resolved=lambda recs: append_das_cache(paths.das_cache, recs),
    )
    todo = sorted({str(rec["pmcid"]) for rec in selected.values() if rec.get("pmcid")} - set(fetched))
    logging.info("DAS audit: %d articles selected, %d full texts to fetch (%d workers).", len(selected), len(todo), cfg.das_audit_workers)

    if todo:
        n_ok = n_err = 0
        pending: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=cfg.das_audit_workers) as pool:
            futures = {
                pool.submit(fetch_europepmc_fulltext_record, session, pmcid, cfg.das_audit_timeout_seconds, cfg.das_audit_delay_seconds): pmcid
                for pmcid in todo
            }
            for i, future in enumerate(tqdm(as_completed(futures), total=len(futures), desc="DAS full text"), start=1):
                try:
                    rec = future.result()
                except Exception as exc:
                    rec = {"kind": "fetch", "pmcid": futures[future], "http": "error", "error": str(exc)[:200]}
                if rec.get("http") == "error":
                    n_err += 1  # transient: not cached, retried next run
                else:
                    fetched[str(rec["pmcid"])] = rec
                    pending.append(rec)
                    if rec.get("http") == 200:
                        n_ok += 1
                    else:
                        n_err += 1
                if len(pending) >= 50:
                    append_das_cache(paths.das_cache, pending)
                    pending = []
                if i % 500 == 0:
                    logging.info("DAS audit: %d/%d fetched (ok=%d, failed=%d)", i, len(todo), n_ok, n_err)
        append_das_cache(paths.das_cache, pending)
        logging.info("DAS audit fetch done: ok=%d failed=%d", n_ok, n_err)

    df = apply_das_results(df, selected, fetched)
    audited = int(coerce_nullable_bool(df["das_available"]).fillna(False).sum())
    if audited:
        counts = df.loc[coerce_nullable_bool(df["das_available"]).fillna(False), "das_primary"].value_counts()
        logging.info("DAS audit: %d articles audited; primary categories: %s", audited, counts.to_dict())
    return df


def apply_journal_metrics(df: pd.DataFrame, journal_metrics_csv: str) -> pd.DataFrame:
    path = Path(journal_metrics_csv).expanduser()
    if not path.exists():
        logging.info("Journal metrics file not found (%s); impact-factor rule will be skipped.", path)
        return df

    try:
        jm = pd.read_csv(path, low_memory=False)
    except Exception as exc:
        logging.warning("Failed reading journal metrics CSV (%s): %s", path, exc)
        return df

    if jm.empty:
        return df

    cols_lower = {c.lower(): c for c in jm.columns}
    journal_col = None
    impact_col = None
    for candidate in ["journal", "journal_name", "source", "venue"]:
        if candidate in cols_lower:
            journal_col = cols_lower[candidate]
            break
    for candidate in ["impact_factor", "jif", "if", "impact"]:
        if candidate in cols_lower:
            impact_col = cols_lower[candidate]
            break

    if not journal_col or not impact_col:
        logging.warning("Journal metrics CSV must contain journal + impact factor columns.")
        return df

    jm = jm[[journal_col, impact_col]].copy()
    jm.columns = ["journal", "journal_impact_factor_csv"]
    jm["journal_norm"] = jm["journal"].map(normalize_journal_name)
    jm["journal_impact_factor_csv"] = pd.to_numeric(jm["journal_impact_factor_csv"], errors="coerce")
    jm = jm.dropna(subset=["journal_impact_factor_csv"]).drop_duplicates(subset=["journal_norm"], keep="first")

    if jm.empty:
        return df

    out = df.merge(jm[["journal_norm", "journal_impact_factor_csv"]], on="journal_norm", how="left")
    fill_missing(out, "journal_impact_factor", "journal_impact_factor_csv")
    out = out.drop(columns=[c for c in ["journal_impact_factor_csv"] if c in out.columns])
    logging.info("Applied journal impact-factor mapping from %s", path)
    return out


def build_high_impact_subset(df: pd.DataFrame, cfg: PipelineConfig) -> Tuple[pd.DataFrame, pd.DataFrame]:
    out = df.copy()
    out["high_impact_flag"] = coerce_nullable_bool(out.get("high_impact_flag", pd.Series([False] * len(out))))
    out["high_impact_reason"] = out.get("high_impact_reason", "").fillna("").astype(str)

    if_mask = pd.Series([False] * len(out), index=out.index)
    if "journal_impact_factor" in out.columns:
        jif = pd.to_numeric(out["journal_impact_factor"], errors="coerce")
        if_mask = jif >= cfg.impact_factor_threshold
        out.loc[if_mask, "high_impact_flag"] = True
        out.loc[if_mask, "high_impact_reason"] = out.loc[if_mask, "high_impact_reason"].mask(
            out.loc[if_mask, "high_impact_reason"].eq(""),
            f"impact_factor>={cfg.impact_factor_threshold:g}",
        )

    cited = pd.to_numeric(out.get("cited_by_count"), errors="coerce")
    citation_threshold = None
    if cited.notna().sum() > 0:
        q = cfg.citation_percentile_threshold / 100.0
        citation_threshold = float(cited.quantile(q))
        cit_mask = cited >= citation_threshold
        out.loc[cit_mask, "high_impact_flag"] = True
        reason = f"cited_by_count>={citation_threshold:.0f} (top {100 - cfg.citation_percentile_threshold:.1f}%)"
        out.loc[cit_mask & out["high_impact_reason"].eq(""), "high_impact_reason"] = reason
        out.loc[cit_mask & out["high_impact_reason"].ne(""), "high_impact_reason"] = (
            out.loc[cit_mask & out["high_impact_reason"].ne(""), "high_impact_reason"] + "; " + reason
        )

    subset = out[out["high_impact_flag"].fillna(False)].copy()
    subset = subset.sort_values(by=["journal_impact_factor", "cited_by_count"], ascending=[False, False], na_position="last")

    if citation_threshold is not None:
        logging.info(
            "High-impact definition: IF >= %.2f OR citations >= %.0f (>= %.1fth percentile)",
            cfg.impact_factor_threshold,
            citation_threshold,
            cfg.citation_percentile_threshold,
        )
    else:
        logging.info("High-impact definition: IF >= %.2f", cfg.impact_factor_threshold)

    return out, subset


def apply_snapshots(df: pd.DataFrame, cfg: PipelineConfig) -> pd.DataFrame:
    if cfg.unpaywall_snapshot:
        df = apply_unpaywall_snapshot(df, cfg.unpaywall_snapshot)
    if cfg.crossref_relations:
        df = apply_crossref_relations_snapshot(df, cfg.crossref_relations)
    return df


def main() -> int:
    script_root = Path(__file__).resolve().parents[1]
    loaded_env_files = load_project_env(script_root)
    cfg, paths = parse_args(script_root)
    setup_logging(cfg.verbose)

    if loaded_env_files:
        logging.info(
            "Loaded environment from %s",
            ", ".join(str(path) for path in loaded_env_files),
        )

    if not cfg.openalex_mailto:
        logging.warning("No --openalex-mailto provided. OpenAlex may throttle aggressively.")
    elif cfg.openalex_mailto.lower().endswith(("example.com", "institution.edu")):
        logging.warning(
            "OpenAlex mailto '%s' looks like a placeholder. Use your real email to reduce 429 risk.",
            cfg.openalex_mailto,
        )
    if not cfg.openalex_api_key:
        logging.warning(
            "OPENALEX_API_KEY is not configured. Since February 13, 2026, OpenAlex limits unauthenticated use to testing-scale access."
        )
    else:
        logging.info("OPENALEX_API_KEY detected; authenticated OpenAlex access enabled.")
    if cfg.include_pubmed:
        if not cfg.pubmed_email:
            logging.warning("PubMed retrieval enabled without pubmed email. NCBI recommends supplying one.")
        elif cfg.pubmed_email.lower().endswith(("example.com", "institution.edu")):
            logging.warning(
                "PubMed email '%s' looks like a placeholder. Use your real email to reduce throttling risk.",
                cfg.pubmed_email,
            )
        else:
            logging.info("PubMed retrieval enabled with email '%s'.", cfg.pubmed_email)

    if paths.full_csv.exists() and not cfg.force:
        if csv_has_data_rows(paths.full_csv):
            logging.info("Full output already exists (%s). Use --force to overwrite.", paths.full_csv)
            return 0
        logging.warning(
            "Existing full output has no data rows; recomputing instead of reusing: %s",
            paths.full_csv,
        )

    session = build_requests_session(cfg)

    df = fetch_or_load_openalex(cfg, paths, session)
    df = standardize_dataframe(df)
    df = ensure_discipline(df, cfg.discipline)

    df, backfill_complete = run_openalex_metadata_backfill(df, cfg, paths, session)
    if cfg.backfill_openalex_metadata and backfill_complete:
        # Persist the metadata into the retrieval dataset so later runs need no backfill.
        write_csv_atomic(df, paths.raw_csv)
        logging.info("Rewrote retrieval dataset with OpenAlex work metadata: %s", paths.raw_csv)

    df = apply_snapshots(df, cfg)
    df = standardize_dataframe(df)
    df = ensure_discipline(df, cfg.discipline)

    enrich_cache_raw = load_json(paths.enrich_cache)
    enrich_cache = normalize_cache(enrich_cache_raw)
    if enrich_cache:
        df = apply_cache_to_dataframe(df, enrich_cache)

    df = normalize_open_access_fields(df)
    df = apply_regex_extraction(df)
    df = apply_registration_flags(df)
    df = apply_corpus_flag(df)

    enrich_cache = run_api_enrichment(df, cfg, enrich_cache, paths.enrich_cache)
    if enrich_cache:
        df = apply_cache_to_dataframe(df, enrich_cache)

    # Dataset repository detection: regex pass then API enrichment
    df = apply_dataset_regex_extraction(df)
    enrich_cache = run_dataset_enrichment(df, cfg, enrich_cache, paths.enrich_cache)
    if enrich_cache:
        df = apply_cache_to_dataframe(df, enrich_cache)
    # Finalize has_public_dataset from combined regex + API results
    if "has_public_dataset" not in df.columns:
        df["has_public_dataset"] = False
    df["has_public_dataset"] = (
        df["has_public_dataset"].fillna(False)
        | df.get("dataset_urls", pd.Series("", index=df.index)).fillna("").str.strip().ne("")
    )

    df = standardize_dataframe(df)
    df = ensure_discipline(df, cfg.discipline)
    df = normalize_open_access_fields(df)

    if cfg.preview_rows > 0:
        preview_df = df.head(cfg.preview_rows).copy()
    else:
        preview_df = df.copy()
    write_csv_atomic(preview_df, paths.preview_csv)
    logging.info("Saved preview dataset: %s (%d rows)", paths.preview_csv, len(preview_df))

    df = compute_embedding_scores(df, cfg)

    llm_cache_raw = load_json(paths.llm_cache)
    llm_cache = llm_cache_raw if isinstance(llm_cache_raw, dict) else {}
    df, llm_cache = run_llm_extraction(df, cfg, llm_cache, paths.llm_cache, session)
    df = apply_metadata_preprint_flag(df)

    df = run_das_audit(df, cfg, paths, session)

    df = apply_journal_metrics(df, cfg.journal_metrics_csv)
    df = standardize_dataframe(df)
    df = ensure_discipline(df, cfg.discipline)
    df = normalize_open_access_fields(df)

    df, high_impact_df = build_high_impact_subset(df, cfg)
    write_csv_atomic(high_impact_df, paths.high_impact_csv)
    logging.info("Saved high-impact subset: %s (%d rows)", paths.high_impact_csv, len(high_impact_df))

    write_csv_atomic(df, paths.full_csv)
    logging.info("Pipeline complete. Saved full dataset: %s (%d rows)", paths.full_csv, len(df))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
