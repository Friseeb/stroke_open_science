#!/usr/bin/env python3
"""
Run the pipeline across multiple discipline presets and optionally build a dashboard.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_DISCIPLINES = ["stroke", "neuroscience", "neurology", "cardiology"]
DOTENV_CANDIDATES = (".env", ".env.local", "configs/.env", "configs/.env.local")


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


def parse_args(script_root: Optional[Path] = None) -> argparse.Namespace:
    script_root = script_root or Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(description="Run cross-discipline benchmark.")
    parser.add_argument("--disciplines", nargs="+", default=DEFAULT_DISCIPLINES)
    parser.add_argument("--presets-json", default=str(script_root / "configs" / "discipline_presets.json"))
    parser.add_argument("--base-output-dir", default=str(script_root / "data" / "benchmarks"))
    parser.add_argument("--include-pubmed", action="store_true", help="Also retrieve matching PubMed records")
    parser.add_argument("--pubmed-email", default=os.getenv("NCBI_EMAIL", os.getenv("PUBMED_EMAIL", "")))
    parser.add_argument("--pubmed-api-key", default=os.getenv("NCBI_API_KEY", ""))
    parser.add_argument("--pubmed-tool", default=os.getenv("NCBI_TOOL", "stroke-open-science"))
    parser.add_argument("--pubmed-delay-seconds", type=float, default=0.34)
    parser.add_argument("--pubmed-timeout-seconds", type=int, default=20)
    parser.add_argument("--pubmed-max-attempts", type=int, default=3)
    parser.add_argument("--pubmed-batch-size", type=int, default=200)
    parser.add_argument(
        "--openalex-mailto",
        default=os.getenv("OPENALEX_MAILTO", ""),
        help="Email passed to OpenAlex requests",
    )
    parser.add_argument(
        "--openalex-api-key",
        default=os.getenv("OPENALEX_API_KEY", ""),
        help="API key passed to OpenAlex requests",
    )
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=dt.datetime.now().year)
    parser.add_argument(
        "--query-window-months",
        type=int,
        default=12,
        help="Split retrieval into month windows within each year (for example 6 = Jan-Jun and Jul-Dec)",
    )
    parser.add_argument("--embedding-device", choices=["auto", "cpu", "cuda", "mps"], default="auto")
    parser.add_argument("--openalex-workers", type=int, default=3)
    parser.add_argument("--openalex-delay-seconds", type=float, default=0.5)
    parser.add_argument("--openalex-timeout-seconds", type=int, default=20)
    parser.add_argument("--openalex-max-attempts", type=int, default=3)
    parser.add_argument("--openalex-max-failures-per-query", type=int, default=3)
    parser.add_argument("--openalex-max-retry-after-seconds", type=int, default=60)
    parser.add_argument("--max-per-query", type=int, default=0, help="0 means unlimited")
    parser.add_argument("--refresh-openalex", action="store_true")
    parser.add_argument("--api-concurrency", type=int, default=12)
    parser.add_argument("--api-delay-seconds", type=float, default=0.35)
    parser.add_argument("--max-api-lookups", type=int, default=15000)
    parser.add_argument("--embedding-top-k", type=int, default=5000)
    parser.add_argument("--llm-provider", choices=["openai", "ollama"], default=os.getenv("LLM_PROVIDER", "openai"))
    parser.add_argument("--llm-max-items", type=int, default=1000)
    parser.add_argument("--llm-model", default=os.getenv("OPENAI_LLM_MODEL", ""))
    parser.add_argument("--llm-temperature", type=float, default=0.0)
    parser.add_argument("--ollama-base-url", default=os.getenv("OLLAMA_BASE_URL", ""))
    parser.add_argument("--ollama-model", default=os.getenv("OLLAMA_MODEL", ""))
    parser.add_argument("--llm-use-fulltext", action="store_true")
    parser.add_argument("--fulltext-char-limit", type=int, default=12000)
    parser.add_argument("--llm-max-fulltext-fetch", type=int, default=200)
    parser.add_argument("--disable-api-enrich", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Skip discipline runs with existing fully_enriched.csv")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-dashboard", action="store_true")
    parser.add_argument("--python-executable", default="", help="Python interpreter for child pipeline runs")
    parser.add_argument("--bootstrap", action="store_true", help="Install requirements in selected interpreter before run")
    parser.add_argument("--verbose", action="store_true")

    return parser.parse_args()


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")


def load_presets(path: Path) -> Dict[str, List[str]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    out: Dict[str, List[str]] = {}
    for key, terms in data.items():
        if isinstance(terms, list):
            out[str(key).strip().lower()] = [str(t).strip() for t in terms if str(t).strip()]
    return out


def run_cmd(cmd: List[str]) -> None:
    logging.info("$ %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def resolve_python_executable(script_root: Path, user_value: str) -> str:
    if user_value.strip():
        return str(Path(user_value).expanduser().resolve())

    local_venv = script_root / ".venv" / "bin" / "python"
    if local_venv.exists():
        return str(local_venv)

    return sys.executable


def has_required_modules(py_exe: str) -> bool:
    probe = [
        py_exe,
        "-c",
        "import requests, pandas, tqdm, aiohttp, duckdb; print('ok')",
    ]
    result = subprocess.run(probe, capture_output=True, text=True)
    return result.returncode == 0


def csv_has_data_rows(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            _ = f.readline()  # header
            second = f.readline()
        return bool(second and second.strip())
    except Exception:
        return False


def bootstrap_requirements(py_exe: str, requirements_path: Path) -> None:
    run_cmd([py_exe, "-m", "pip", "install", "-r", str(requirements_path)])


def main() -> int:
    script_root = Path(__file__).resolve().parents[1]
    loaded_env_files = load_project_env(script_root)
    args = parse_args(script_root)
    setup_logging(args.verbose)

    if loaded_env_files:
        logging.info(
            "Loaded environment from %s",
            ", ".join(str(path) for path in loaded_env_files),
        )

    pipeline_script = script_root / "scripts" / "search_stroke_dois.py"
    dashboard_script = script_root / "scripts" / "build_discipline_dashboard.py"
    requirements_path = script_root / "requirements.txt"
    python_exe = resolve_python_executable(script_root, args.python_executable)

    logging.info("Using python executable: %s", python_exe)

    if args.bootstrap:
        bootstrap_requirements(python_exe, requirements_path)

    if not has_required_modules(python_exe):
        raise RuntimeError(
            "Selected interpreter is missing required packages. "
            f"Install with: {python_exe} -m pip install -r {requirements_path}"
        )

    presets_path = Path(args.presets_json).expanduser().resolve()
    if not presets_path.exists():
        raise FileNotFoundError(f"Preset file not found: {presets_path}")

    presets = load_presets(presets_path)
    base_output = Path(args.base_output_dir).expanduser().resolve()
    base_output.mkdir(parents=True, exist_ok=True)

    dash_inputs: List[str] = []

    for discipline_raw in args.disciplines:
        discipline = discipline_raw.strip().lower()
        if discipline not in presets:
            raise ValueError(f"No preset terms found for discipline '{discipline}'")

        terms = presets[discipline]
        out_dir = base_output / discipline
        out_dir.mkdir(parents=True, exist_ok=True)
        full_csv = out_dir / "fully_enriched.csv"

        if args.resume and full_csv.exists() and not args.force:
            if csv_has_data_rows(full_csv):
                logging.info("Skipping %s (resume enabled, existing output found): %s", discipline, full_csv)
                dash_inputs.append(f"{discipline}={full_csv}")
                continue
            logging.warning(
                "Existing output for %s has no data rows; rerunning discipline: %s",
                discipline,
                full_csv,
            )

        cmd: List[str] = [
            python_exe,
            str(pipeline_script),
            "--discipline",
            discipline,
            "--output-dir",
            str(out_dir),
            "--terms",
            *terms,
            "--start-year",
            str(args.start_year),
            "--end-year",
            str(args.end_year),
            "--query-window-months",
            str(max(1, min(12, args.query_window_months))),
            "--embedding-device",
            args.embedding_device,
            "--openalex-workers",
            str(max(1, args.openalex_workers)),
            "--openalex-delay-seconds",
            str(max(0.0, args.openalex_delay_seconds)),
            "--openalex-timeout-seconds",
            str(max(5, args.openalex_timeout_seconds)),
            "--openalex-max-attempts",
            str(max(1, args.openalex_max_attempts)),
            "--openalex-max-failures-per-query",
            str(max(1, args.openalex_max_failures_per_query)),
            "--openalex-max-retry-after-seconds",
            str(max(5, args.openalex_max_retry_after_seconds)),
            "--max-per-query",
            str(max(0, args.max_per_query)),
            "--api-concurrency",
            str(max(1, args.api_concurrency)),
            "--api-delay-seconds",
            str(max(0.0, args.api_delay_seconds)),
            "--max-api-lookups",
            str(max(0, args.max_api_lookups)),
            "--embedding-top-k",
            str(max(0, args.embedding_top_k)),
            "--llm-provider",
            args.llm_provider,
            "--llm-max-items",
            str(args.llm_max_items),
            "--llm-temperature",
            str(args.llm_temperature),
            "--fulltext-char-limit",
            str(max(1000, args.fulltext_char_limit)),
            "--llm-max-fulltext-fetch",
            str(max(0, args.llm_max_fulltext_fetch)),
        ]

        if args.include_pubmed:
            cmd.append("--include-pubmed")
        if args.pubmed_email.strip():
            cmd.extend(["--pubmed-email", args.pubmed_email.strip()])
        if args.pubmed_api_key.strip():
            cmd.extend(["--pubmed-api-key", args.pubmed_api_key.strip()])
        if args.pubmed_tool.strip():
            cmd.extend(["--pubmed-tool", args.pubmed_tool.strip()])
        if args.pubmed_delay_seconds > 0:
            cmd.extend(["--pubmed-delay-seconds", str(max(0.0, args.pubmed_delay_seconds))])
        if args.pubmed_timeout_seconds:
            cmd.extend(["--pubmed-timeout-seconds", str(max(5, args.pubmed_timeout_seconds))])
        if args.pubmed_max_attempts:
            cmd.extend(["--pubmed-max-attempts", str(max(1, args.pubmed_max_attempts))])
        if args.pubmed_batch_size:
            cmd.extend(["--pubmed-batch-size", str(max(1, args.pubmed_batch_size))])
        if args.openalex_mailto.strip():
            cmd.extend(["--openalex-mailto", args.openalex_mailto.strip()])
        if args.openalex_api_key.strip():
            cmd.extend(["--openalex-api-key", args.openalex_api_key.strip()])
        if args.llm_model.strip():
            cmd.extend(["--llm-model", args.llm_model.strip()])
        if args.ollama_base_url.strip():
            cmd.extend(["--ollama-base-url", args.ollama_base_url.strip()])
        if args.ollama_model.strip():
            cmd.extend(["--ollama-model", args.ollama_model.strip()])

        if args.disable_api_enrich:
            cmd.append("--disable-api-enrich")
        if args.refresh_openalex:
            cmd.append("--refresh-openalex")
        if args.force:
            cmd.append("--force")
        if args.llm_use_fulltext:
            cmd.append("--llm-use-fulltext")
        if args.verbose:
            cmd.append("--verbose")

        run_cmd(cmd)

        if csv_has_data_rows(full_csv):
            dash_inputs.append(f"{discipline}={full_csv}")
        else:
            logging.warning("Discipline output has no data rows and will be excluded from dashboard: %s", full_csv)

    if not args.skip_dashboard:
        if not dash_inputs:
            logging.warning("No discipline outputs with data rows available; skipping dashboard build.")
            return 0
        dashboard_out = base_output / "dashboard"
        cmd = [
            python_exe,
            str(dashboard_script),
            "--inputs",
            *dash_inputs,
            "--out-dir",
            str(dashboard_out),
            "--title",
            "Open-Science Uptake Across Stroke and Adjacent Fields",
        ]
        run_cmd(cmd)

    logging.info("Benchmark run complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
