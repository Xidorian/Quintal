# Status — Quintal

**Live and in maintenance.** All five build phases (collect → screen → enrich →
value/score → interactive UI) are in place; the backlog is drained. Malia uses the
hosted app; ongoing work is weekly re-collection to keep the pool fresh, not new
capability.

## What works today
- **End-to-end pipeline** (`pipeline.py`): load → normalize → screen → liveness-drop →
  dedup → enrich → value → score, with per-item error isolation.
- **Collection** — browser-session based (Chrome, no scraping infra) for Idealista +
  Imovirtual. Extraction is versioned in `collect/extract.js` (per-site selectors +
  accumulate/download helpers). Idealista pre-filters via the real URL token `t4-t5`
  for T4+. Current store: **841 listings** (333 idealista / 508 imovirtual) → ~569 ranked.
- **Screening** (`screening.py`) purges short-term/AL/Spacest lets + year-interrupted
  seasonal spans into a persistent blocklist. **Liveness** (`liveness.py`) drops
  delisted 404/410 listings (Imovirtual only — Idealista 403s server-side).
- **Enrichment** — geocode `Nominatim → Photon → skip`; nearest-beach walk-times now
  **real ORS routed** (key in local `.env`, cached in `enrichment_cache.json`, readable
  key-free so hosted app needs no key). Per-listing geo persisted to `data/geo.json` so
  any run carries geo with zero network.
- **Descriptions** (`descriptions.py`) — pulls Imovirtual detail-page owner text from
  `__NEXT_DATA__` into a `data/descriptions.json` sidecar, so yard/bathtub/pets derive
  from real amenities, not titles alone.
- **Valuation** — hedonic ridge on log(price), fit on the robust bulk within
  `VALUATION_FIT_MAD_K` (3.5) MADs, peer-median fallback + confidence badge.
- **Dedup** — attribute-based, plus a guarded photo-hash second pass (`photo_hash.dhash`,
  Hamming ≤6, corroborated by bedrooms + price ±10%).
- **Photos** — captured card thumbnails (incl. Idealista) + og:image fallback to
  `data/photos/`.
- **App** (`app.py`, Streamlit) — filters, 3 sort modes, 👍/👎 per listing & area.
- **Hosting** — live on Streamlit Community Cloud (`deploy` branch), shared prefs via a
  private GitHub Gist (`GistBackend`); `scripts/publish.sh` refreshes → auto-redeploy.
  Malia confirmed it works for her.
- **96 tests green.**

## Where work stopped
Backlog fully drained; last work was QT-033/034/035 (versioned extraction, Idealista
filter URL, ORS routed walk-times) plus the RECOLLECT.md weekly-re-collection runbook.
No open feature work — the standing task is the weekly re-collection (see NEXT.md).

## Known issues / debugging
- **Pool decays fast** — ~13% delisted per 11 days; re-collection must be regular.
- **Idealista detail pages** need the logged-in browser session (DataDome 403s server-side),
  so its descriptions and liveness can't be probed headless.
- **Idealista thumbnails are `/blur/` previews** → idealista↔imovirtual photo-hash matches
  are only partial.
- **Small-pool valuations are low-confidence** — respect the confidence badge; peer-median
  fallback covers thin concelho+bedroom buckets.
- Idealista `com-preco-max_…` filter URL still soft-404s in some paths → price/beds
  filtered post-collection as a fallback.

## Goal
A relative-valuation rental finder for the Algarve that Alexander and Malia use daily to
find an undervalued long-term rental — yard for Luna, beach-walkable — with a fresh,
de-duplicated, honestly-valued pool.
