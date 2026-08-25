#!/usr/bin/env bash
# Publish the current data snapshot to the `deploy` branch → Streamlit Cloud redeploys.
#
# `main` keeps runtime data gitignored (the project's design decision). The hosted app
# needs that data, so we carry a snapshot on a dedicated `deploy` branch = current `main`
# code + a force-added data snapshot. Done in a throwaway git worktree so your working
# tree and branch are never disturbed.
#
# Prereqs: an `origin` remote exists, and the Streamlit Cloud app tracks branch `deploy`.
# Usage:   scripts/publish.sh
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
WT="$ROOT/.deploy-worktree"

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "No 'origin' remote. Create the GitHub repo and add it first." >&2
  exit 1
fi

# Data that must reach the deploy (photos are large but re-fetchable, shipped for thumbnails).
FILES=(data/listings.jsonl data/enrichment_cache.json data/blocklist.json)
for f in "${FILES[@]}"; do
  [[ -f "$f" ]] || { echo "Missing $f — collect/enrich before publishing." >&2; exit 1; }
done
# Optional enrichment sidecars — shipped if present (absent before their first backfill run).
# Includes the per-region Norte pool + its sidecars (photos share one id-keyed dir, below).
for f in data/descriptions.json data/delisted.json data/geo.json \
         data/listings-norte.jsonl data/geo-norte.json data/enrichment_cache-norte.json \
         data/blocklist-norte.json data/delisted-norte.json data/descriptions-norte.json; do
  [[ -f "$f" ]] && FILES+=("$f")
done

# The hosted app runs an older Python than this repo develops on: Streamlit Cloud is on
# 3.10, `pyproject.toml` says 3.12. A 3.11+ feature in the app's import path passes every
# local check and only explodes once it's live (it did, 2026-08-25: `datetime.UTC`). Gate it
# here — the last point before it reaches Malia. Skipped when vermin isn't installed
# (`pip install -r requirements-dev.txt`).
if command -v vermin >/dev/null 2>&1; then
  if ! vermin --no-tips -t=3.10- --violations app.py src/quintal; then
    echo "Above needs newer than Python 3.10 — Streamlit Cloud would fail to import it." >&2
    exit 1
  fi
else
  echo "note: vermin not installed — skipping the Python-3.10 compatibility check." >&2
fi

cleanup() { git worktree remove --force "$WT" 2>/dev/null || true; }
trap cleanup EXIT
cleanup  # clear any stale worktree from an interrupted run

# `deploy` = current HEAD (main code). Checked out clean, so gitignored data is absent here.
git worktree add -B deploy "$WT" HEAD >/dev/null

mkdir -p "$WT/data/photos"
cp "${FILES[@]}" "$WT/data/"
[[ -d data/photos ]] && cp -a data/photos/. "$WT/data/photos/"

git -C "$WT" add -f "${FILES[@]}" data/photos
if git -C "$WT" diff --cached --quiet; then
  echo "No data changes to publish."
  exit 0
fi

STAMP="$(git log -1 --format=%h) $(TZ=UTC git log -1 --format=%cd --date=format-local:%Y-%m-%dT%H:%MZ)"
git -C "$WT" commit -q -m "publish: data snapshot on ${STAMP}"
git -C "$WT" push -f origin deploy
echo "Published to 'deploy'. Streamlit Cloud will redeploy shortly."
