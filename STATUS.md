# Status — Quintal

**Live and in maintenance, plus an active Norte expansion (2026-08).** All five build
phases (collect → screen → enrich → value/score → interactive UI) are in place for the
Algarve; the backlog is drained and Malia uses the hosted app. **New direction:** the
search is expanding to **Porto + the Douro + the Minho** (Norte), optimising for
dog-walkable greenery/nature/quiet and river-beach proximity rather than ocean beaches —
kept as a **separate pool** (`data/listings-norte.jsonl`) so Algarve valuations stay clean.

## Norte expansion — in progress (2026-08-06)
- **Regions wired** into both collectors (`porto`, `braga`, `viana-do-castelo`,
  `vila-real`, `viseu` → portal slugs); fixed Imovirtual's Faro-hardcoded district-strip
  and `extract.js`'s Faro-only location regex to be district-agnostic (QT-038).
- **First Norte pull done:** 3882 raw (1797 idealista / 2085 imovirtual) →
  screen/dedup → **2828 ranked** (746 under / 1219 fair / 811 over) into the Norte pool.
- **Known gaps (open work):** ~632 T1s leaked past both portals' bed filters (filter to
  ≥2); Idealista Norte concelhos parse freguesia-level (fix via reverse-geocoded concelho
  during enrich); `enrich.py` is Algarve-hardcoded (bbox + ", Algarve" suffix) → must be
  region-parameterised before the Norte pool can be geocoded; `green_walk` axis + river-beach
  water axis still to build. See NEXT.md.

## What works today
- **End-to-end pipeline** (`pipeline.py`): load → normalize → screen → liveness-drop →
  dedup → enrich → value → score, with per-item error isolation.
- **Collection** — browser-session based (Chrome, no scraping infra) for Idealista +
  Imovirtual. Extraction is versioned in `collect/extract.js` (per-site selectors +
  accumulate/download helpers). Idealista pre-filters via the real URL token `t4-t5`
  for T4+. Current store: **1340 listings** (755 idealista / 585 imovirtual) → 594 ranked.
- **Screening** (`screening.py`) purges short-term/AL/Spacest lets + year-interrupted
  seasonal spans into a persistent blocklist. **Liveness** (`liveness.py`) drops delisted
  listings two ways: Imovirtual by **detail-page 404/410 probe** (sticky); Idealista by
  **cull-by-absence** — `--ingest --cull` delists any idealista listing a *complete* pull
  didn't re-surface (idealista IP-rate-limits detail probes, so absence is the signal).
  Cull is reversible: a listing that reappears next pull is un-culled.
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

## Re-collection log
- **2026-07-27** — store 841 → **1081** (+240 new: idealista 163, imovirtual 77;
  235 updated). Collected 180 idealista (6 pages) + 295 imovirtual (251 apt / 44 moradia).
  Maintenance: 67 new descriptions, **72 newly-delisted** (410/404 → delisted 65→137),
  238 new photos. Ranked **614** (221 undervalued / 161 fair / 209 overpriced), 27 price
  outliers trimmed from the hedonic fit. Published to `deploy`.
  - Added **idealista cull-by-absence liveness** (`--ingest --cull`) after finding idealista
    IP-rate-limits detail probes (429). **Applied same day** after the rate-limit cooled: pulled
    the *complete* idealista search (456/456 per its own header — the old 6-page cap only saw
    ~180), which **added 259 long-missed listings (pages 7–16)** and **culled 299 stale ones**.
    Re-ranked **594** (idealista 283 / imovirtual 311), delisted set 137 → 436, re-published.

## Where work stopped
Backlog fully drained; last work was the 2026-07-27 weekly re-collection (above). Prior
feature work was QT-033/034/035 (versioned extraction, Idealista filter URL, ORS routed
walk-times) plus the RECOLLECT.md runbook. No open feature work — the standing task is
the weekly re-collection (see NEXT.md).

## Known issues / debugging
- **Pool decays fast** — ~13% delisted per 11 days; re-collection must be regular.
- **Idealista detail pages** can't be fetched programmatically (DataDome 403 server-side; even
  in-browser XHR trips a 429 IP rate-limit fast — learned 2026-07-27). So idealista descriptions
  stay title-only, and idealista liveness uses cull-by-absence (`--cull`) instead of probing.
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
