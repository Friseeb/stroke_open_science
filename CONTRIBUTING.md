# Contributing

## Scope

This repository tracks source code, configuration, and documentation only.
Large generated outputs under `data/` are not versioned in Git.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest
```

## Before opening a pull request

1. Run tests:

```bash
python -m pytest -q
```

2. Keep changes scoped and avoid committing generated datasets.
3. Update docs when behavior or output schemas change.

## Data and secrets

- Never commit `.env` or API tokens.
- Never commit full benchmark outputs from `data/`.
- Publish benchmark outputs through the external archive process in
  `docs/OUTPUTS_ARCHIVE.md`.
