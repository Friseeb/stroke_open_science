#!/usr/bin/env python3
"""Build a manifest of publishable output artifacts for an external archive repo."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

INCLUDE_SUFFIXES = {".csv", ".html", ".json", ".parquet"}
EXCLUDE_NAMES = {
    "enrich_cache.json",
    "llm_cache.json",
}
EXCLUDE_PATH_PARTS = {
    "retrieval_slices",
}


def should_include(path: Path) -> bool:
    if path.name in EXCLUDE_NAMES:
        return False
    if path.suffix.lower() not in INCLUDE_SUFFIXES:
        return False
    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts & EXCLUDE_PATH_PARTS:
        return False
    return True


def collect_files(data_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in data_dir.rglob("*"):
        if not path.is_file():
            continue
        if should_include(path):
            files.append(path)
    return sorted(files)


def write_manifest(paths: list[Path], repo_root: Path, out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["relative_path", "size_bytes"])
        for path in paths:
            rel = path.relative_to(repo_root)
            writer.writerow([str(rel), path.stat().st_size])


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare output archive manifest")
    parser.add_argument("--data-dir", default="data", help="Data directory to scan")
    parser.add_argument(
        "--output",
        default="outputs_archive/manifest.csv",
        help="Output manifest CSV path",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    data_dir = (repo_root / args.data_dir).resolve()
    out_csv = (repo_root / args.output).resolve()

    if not data_dir.exists() or not data_dir.is_dir():
        raise SystemExit(f"Data directory not found: {data_dir}")

    files = collect_files(data_dir)
    write_manifest(files, repo_root, out_csv)

    print(f"Wrote manifest with {len(files)} files: {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
