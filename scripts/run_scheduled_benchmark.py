#!/usr/bin/env python3
"""
Run dated benchmark snapshots suitable for cron/launchd jobs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import duckdb  # type: ignore
except Exception:
    duckdb = None

import run_discipline_benchmark as benchmark


RESERVED_BENCHMARK_FLAGS = {"--base-output-dir", "--python-executable"}


def parse_args(script_root: Optional[Path] = None) -> argparse.Namespace:
    script_root = script_root or Path(__file__).resolve().parents[1]
    default_output_root = script_root / "data" / "scheduled_runs"

    parser = argparse.ArgumentParser(description="Run a dated benchmark snapshot and export parquet copies.")
    parser.add_argument("--run-name", default="daily_benchmark")
    parser.add_argument("--run-date", default=dt.date.today().isoformat(), help="Folder label, e.g. 2026-03-14")
    parser.add_argument("--base-output-root", default=str(default_output_root))
    parser.add_argument("--python-executable", default="", help="Python interpreter used for benchmark runs")
    parser.add_argument("--manifest-name", default="run_manifest.json")
    parser.add_argument(
        "--parquet-compression",
        choices=["zstd", "snappy", "uncompressed"],
        default="zstd",
        help="Compression used for exported parquet copies",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--refresh-openalex", dest="refresh_openalex", action="store_true")
    parser.add_argument("--no-refresh-openalex", dest="refresh_openalex", action="store_false")
    parser.add_argument("--export-parquet", dest="export_parquet", action="store_true")
    parser.add_argument("--no-export-parquet", dest="export_parquet", action="store_false")
    parser.add_argument("--update-latest", dest="update_latest", action="store_true")
    parser.add_argument("--no-update-latest", dest="update_latest", action="store_false")
    parser.set_defaults(refresh_openalex=False, export_parquet=True, update_latest=True)
    parser.add_argument(
        "benchmark_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to run_discipline_benchmark.py after '--'",
    )
    return parser.parse_args()


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")


def sanitize_path_part(value: str, fallback: str) -> str:
    text = (value or "").strip()
    if not text:
        return fallback
    cleaned = []
    for ch in text:
        if ch.isalnum() or ch in {"-", "_", "."}:
            cleaned.append(ch)
        else:
            cleaned.append("_")
    collapsed = "".join(cleaned).strip("._")
    return collapsed or fallback


def normalize_passthrough_args(values: List[str]) -> List[str]:
    args = list(values)
    if args and args[0] == "--":
        args = args[1:]
    return args


def validate_passthrough_args(args: List[str]) -> None:
    for idx, token in enumerate(args):
        if token in RESERVED_BENCHMARK_FLAGS:
            raise ValueError(f"{token} is managed by run_scheduled_benchmark.py and should not be passed through.")
        if token.startswith("--base-output-dir=") or token.startswith("--python-executable="):
            raise ValueError(f"{token} is managed by run_scheduled_benchmark.py and should not be passed through.")
        if token == "--":
            raise ValueError("Unexpected nested '--' in benchmark args.")
        if idx == 0 and token.startswith("-"):
            continue


def sql_escape(value: str) -> str:
    return value.replace("'", "''")


def build_benchmark_cmd(args: argparse.Namespace, script_root: Path, python_exe: str, run_dir: Path) -> List[str]:
    runner_script = script_root / "scripts" / "run_discipline_benchmark.py"
    passthrough = normalize_passthrough_args(args.benchmark_args)
    validate_passthrough_args(passthrough)

    cmd = [
        python_exe,
        str(runner_script),
        "--base-output-dir",
        str(run_dir),
        "--python-executable",
        python_exe,
    ]
    cmd.extend(passthrough)

    if args.refresh_openalex and "--refresh-openalex" not in passthrough:
        cmd.append("--refresh-openalex")
    if args.verbose and "--verbose" not in passthrough:
        cmd.append("--verbose")

    return cmd


def export_csv_tree_to_parquet(root: Path, compression: str) -> List[str]:
    if duckdb is None:
        logging.warning("duckdb is unavailable; skipping parquet export.")
        return []

    csv_paths = sorted(root.rglob("*.csv"))
    if not csv_paths:
        logging.info("No CSV outputs found to export as parquet under %s", root)
        return []

    con = duckdb.connect()
    exported: List[str] = []
    try:
        for csv_path in csv_paths:
            parquet_path = csv_path.with_suffix(".parquet")
            logging.info("Exporting parquet: %s", parquet_path)
            con.execute(
                (
                    "COPY (SELECT * FROM read_csv_auto('{csv}', HEADER=TRUE, SAMPLE_SIZE=-1)) "
                    "TO '{parquet}' (FORMAT PARQUET, COMPRESSION {compression})"
                ).format(
                    csv=sql_escape(str(csv_path)),
                    parquet=sql_escape(str(parquet_path)),
                    compression=compression.upper(),
                )
            )
            exported.append(str(parquet_path))
    finally:
        con.close()
    return exported


def update_latest_symlink(run_parent: Path, run_dir: Path) -> Optional[Path]:
    latest_path = run_parent / "latest"
    target_name = run_dir.name

    if latest_path.exists() or latest_path.is_symlink():
        if latest_path.is_symlink() or latest_path.is_file():
            latest_path.unlink()
        else:
            logging.warning("Latest path exists as a directory; leaving it unchanged: %s", latest_path)
            return None

    latest_path.symlink_to(Path(target_name))
    logging.info("Updated latest symlink: %s -> %s", latest_path, target_name)
    return latest_path


def write_manifest(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def main() -> int:
    script_root = Path(__file__).resolve().parents[1]
    loaded_env_files = benchmark.load_project_env(script_root)
    args = parse_args(script_root)
    setup_logging(args.verbose)

    if loaded_env_files:
        logging.info("Loaded environment from %s", ", ".join(str(path) for path in loaded_env_files))

    run_name = sanitize_path_part(args.run_name, "daily_benchmark")
    run_date = sanitize_path_part(args.run_date, dt.date.today().isoformat())
    base_output_root = Path(args.base_output_root).expanduser().resolve()
    run_parent = base_output_root / run_name
    run_dir = run_parent / run_date
    manifest_path = run_dir / args.manifest_name

    python_exe = benchmark.resolve_python_executable(script_root, args.python_executable)
    cmd = build_benchmark_cmd(args, script_root, python_exe, run_dir)

    manifest: Dict[str, Any] = {
        "run_name": run_name,
        "run_date": run_date,
        "run_dir": str(run_dir),
        "python_executable": python_exe,
        "command": cmd,
        "loaded_env_files": [str(path) for path in loaded_env_files],
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "status": "planned" if args.dry_run else "running",
    }

    if args.dry_run:
        logging.info("Dry run only. Command:")
        logging.info("$ %s", " ".join(cmd))
        return 0

    run_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(manifest_path, manifest)

    exit_code = 0
    parquet_exports: List[str] = []
    latest_link: Optional[Path] = None

    try:
        logging.info("$ %s", " ".join(cmd))
        subprocess.run(cmd, check=True)

        if args.export_parquet:
            parquet_exports = export_csv_tree_to_parquet(run_dir, args.parquet_compression)

        if args.update_latest:
            latest_link = update_latest_symlink(run_parent, run_dir)

        manifest["status"] = "completed"
    except subprocess.CalledProcessError as exc:
        exit_code = exc.returncode
        manifest["status"] = "failed"
        manifest["error"] = f"Benchmark command failed with exit code {exc.returncode}"
        logging.error("Scheduled benchmark failed with exit code %s", exc.returncode)
    except Exception as exc:
        exit_code = 1
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        logging.exception("Scheduled benchmark failed")
    finally:
        manifest["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        manifest["parquet_exports"] = parquet_exports
        if latest_link is not None:
            manifest["latest_symlink"] = str(latest_link)
        dashboard_html = run_dir / "dashboard" / "discipline_dashboard.html"
        if dashboard_html.exists():
            manifest["dashboard_html"] = str(dashboard_html)
        write_manifest(manifest_path, manifest)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
