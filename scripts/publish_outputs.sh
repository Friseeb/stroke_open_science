#!/usr/bin/env bash
# Publish a benchmark run to the outputs repo: the big CSVs go to a GitHub Release, everything that fits in git
# goes to runs/<timestamp>/, the dashboard site goes to docs/ (GitHub Pages). Any file still over GIT_LIMIT_MB
# after the standard excludes is moved to the release too (GitHub rejects files over 100 MB), leaving a pointer.
#
# Env: DATA_DIR (default data/benchmarks), OUTPUTS_DIR (default outputs_repo, a checkout of OUTPUTS_REPO),
#      OUTPUTS_REPO (default Friseeb/stroke_open_science_outputs), TIMESTAMP (default now, UTC), GIT_LIMIT_MB (50: GitHub warns above 50 MB and rejects above 100),
#      ARCHIVE_DIR (default outputs_archive: manifest.csv and metadata.json to copy into the run folder).
# Needs: gh (authenticated for OUTPUTS_REPO), rsync. The caller commits and pushes OUTPUTS_DIR afterwards.
set -euo pipefail
DATA_DIR="${DATA_DIR:-data/benchmarks}"
OUTPUTS_DIR="${OUTPUTS_DIR:-outputs_repo}"
OUTPUTS_REPO="${OUTPUTS_REPO:-Friseeb/stroke_open_science_outputs}"
TIMESTAMP="${TIMESTAMP:-$(date -u +"%Y-%m-%dT%H%M%SZ")}"
GIT_LIMIT_MB="${GIT_LIMIT_MB:-50}"
TAG="run-${TIMESTAMP}"
DISCIPLINES="${DISCIPLINES:-stroke neuroscience neurology cardiology}"

# 1. Release with the full enriched datasets (asset names are discipline-prefixed: unique within a release).
ASSETS=()
for discipline in $DISCIPLINES; do
  csv="$DATA_DIR/$discipline/fully_enriched.csv"
  if [ -f "$csv" ]; then
    dest="/tmp/${discipline}-fully_enriched.csv"
    cp "$csv" "$dest"
    ASSETS+=("$dest")
  fi
done
if gh release view "$TAG" --repo "$OUTPUTS_REPO" >/dev/null 2>&1; then
  echo "Release $TAG exists; uploading only the assets it does not have yet"
  have=$(gh release view "$TAG" --repo "$OUTPUTS_REPO" --json assets --jq '.assets[].name')
  for a in "${ASSETS[@]}"; do
    if echo "$have" | grep -qx "$(basename "$a")"; then echo "  $(basename "$a") already attached"; else gh release upload "$TAG" --repo "$OUTPUTS_REPO" "$a"; fi
  done
else
  if [ ${#ASSETS[@]} -gt 0 ]; then
    gh release create "$TAG" --repo "$OUTPUTS_REPO" --title "Benchmark Run ${TIMESTAMP}" \
      --notes "Full enriched datasets for all disciplines are attached as release assets (e.g. stroke-fully_enriched.csv), as is any other output over ${GIT_LIMIT_MB} MB (discipline-prefixed). The git commit holds the smaller outputs and the dashboard." \
      "${ASSETS[@]}"
    echo "Release created: $TAG"
  fi
fi
rm -f "${ASSETS[@]}"

# 2. Everything that fits in git.
DEST="$OUTPUTS_DIR/runs/${TIMESTAMP}"
mkdir -p "$DEST"
rsync -a \
  --exclude='retrieval_slices/' \
  --exclude='raw_openalex_articles.csv' \
  --exclude='enriched_preview.csv' \
  --exclude='enrich_cache.json' \
  --exclude='llm_cache.json' \
  --exclude='openalex_metadata_cache.jsonl' \
  --exclude='das_cache.jsonl' \
  --exclude='fully_enriched.csv' \
  "$DATA_DIR/." "$DEST/"
ARCHIVE_DIR="${ARCHIVE_DIR:-outputs_archive}"
cp "$ARCHIVE_DIR/manifest.csv" "$DEST/manifest.csv" 2>/dev/null || true
cp "$ARCHIVE_DIR/metadata.json" "$DEST/metadata.json" 2>/dev/null || true
echo "$TIMESTAMP" > "$OUTPUTS_DIR/LATEST_RUN.txt"

# 3. Anything still over the limit goes to the release instead, with a pointer left in its place.
LIMIT_BYTES=$((GIT_LIMIT_MB * 1024 * 1024))
find "$DEST" -type f -size +"${GIT_LIMIT_MB}M" | while read -r big; do
  rel="${big#$DEST/}"
  asset="/tmp/$(echo "$rel" | tr '/' '-')"
  cp "$big" "$asset"
  gh release upload "$TAG" --repo "$OUTPUTS_REPO" --clobber "$asset"
  size=$(stat -f%z "$big" 2>/dev/null || stat -c%s "$big")
  printf 'Too large for git (%s bytes, limit %s). Attached to release %s as %s\n' "$size" "$LIMIT_BYTES" "$TAG" "$(basename "$asset")" > "${big}.release.txt"
  rm -f "$big" "$asset"
  echo "Moved $rel to release $TAG"
done

# 4. GitHub Pages: the interactive site at the root, the single-file report as legacy.html.
if [ -d "$DATA_DIR/dashboard/site" ]; then
  mkdir -p "$OUTPUTS_DIR/docs"
  cp "$DATA_DIR"/dashboard/site/* "$OUTPUTS_DIR/docs/"
  touch "$OUTPUTS_DIR/docs/.nojekyll"
fi
if [ -f "$DATA_DIR/dashboard/discipline_dashboard.html" ]; then
  mkdir -p "$OUTPUTS_DIR/docs"
  cp "$DATA_DIR/dashboard/discipline_dashboard.html" "$OUTPUTS_DIR/docs/legacy.html"
  [ -f "$OUTPUTS_DIR/docs/index.html" ] || cp "$DATA_DIR/dashboard/discipline_dashboard.html" "$OUTPUTS_DIR/docs/index.html"
  cp "$DATA_DIR/dashboard/discipline_overall_summary.csv" "$OUTPUTS_DIR/docs/" 2>/dev/null || true
  cp "$DATA_DIR/dashboard/discipline_year_summary.csv" "$OUTPUTS_DIR/docs/" 2>/dev/null || true
fi
echo "Prepared $DEST and $OUTPUTS_DIR/docs for commit (release $TAG)."
