# Stroke Open Science

This project is a living meta-research pipeline that automatically tracks and analyzes open science practices in stroke neurology publications using Fireducks and DuckDB.

## Goals

- Extract open access, preregistration, data/code sharing, and preprint indicators
- Compare stroke neurology with cognitive neurology, bioinformatics, and meta-research fields
- Update every 6 months via GitHub Actions
- Generate a continuously evolving dataset and dashboard

## Structure

- `scripts/search_stroke_dois.py`: Retrieves DOIs from OpenAlex
- `scripts/extract_open_science_fireduck.py`: Extracts open science metadata with Fireducks
- `output/`: Versioned results
- `data/`: DOI inputs per field

## Usage

```bash
conda env create -f environment.yml
conda activate stroke_open_science
python scripts/extract_open_science_fireduck.py
