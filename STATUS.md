# Status — Quintal

**Live and in maintenance, plus an active Norte expansion (2026-08).** All five build
phases (collect → screen → enrich → value/score → interactive UI) are in place for the
Algarve; the backlog is drained and Malia uses the hosted app. **New direction:** the
search is expanding to **Porto + the Douro + the Minho** (Norte), optimising for
dog-walkable greenery/nature/quiet and river-beach proximity rather than ocean beaches —
kept as a **separate pool** (`data/listings-norte.jsonl`) so Algarve valuations stay clean.

## Norte expansion — live (2026-08-06)
A second, separate pool (Porto + Douro + Minho), valued against itself, optimised for
greenery/nature/quiet + river/ocean water. **Published** — selectable in the hosted app
(default stays Algarve, so Malia's view is unchanged). Shipped end to end in one session:
- **Collectors** (QT-038): regions `porto`/`braga`/`viana-do-castelo`/`vila-real`/`viseu`
  wired; Imovirtual district-strip + `extract.js` location regex made district-agnostic.
- **Pull:** 3882 raw (1797 idealista / 2085 imovirtual) → filter ≥2 beds (−974 T1 leaks) →
  screen → dedup → **2188 ranked** (560 under / 978 fair / 626 over), **1884 geocoded (86%)**.
- **Greenery axis** (QT-039): `enrich.py` region-parameterised (bbox + geocode suffix per
  region — was Algarve-hardcoded); new `GreenEnricher` (walk-min to nearest park/garden/
  reserve) + `green_walk` score axis, weighted only in the Norte set. Beach axis already
  covers river beaches (OSM `natural=beach`) → serves the Douro.
- **App + publish** (QT-040/041): region-pool selector, greenery filter, publish ships the
  Norte pool + sidecars; pools load from the shipped geo sidecar (no live geocoding in the
  request path). Geocode robustness: skip title-fragment "localities" (cut enrich ~50→~2 min).
- **Top Norte results** land where hoped: Viana do Castelo, Gaia coast (Gulpilhares/
  Canidelo), Amarante (Tâmega), rural Minho — houses w/ yards, near green *and* water.
- **Concelhos fixed** (QT-042): reverse-geocode the authoritative município for located
  Idealista + junk-concelho cards (title-locality recovery gets the comma-less ones to
  geocode first) — junk/freguesia-level concelhos **570+ → 18** (unlocated tail), 99% located.
  Algarve pool untouched.
- **Open follow-ups:** Imovirtual descriptions + liveness deferred; routed (ORS) walk-times
  skipped for Norte (straight-line for now — free-tier quota). See NEXT.md.

## 👎-with-a-reason loop — shipped (2026-08-25, QT-044)
A 👎 in the app now asks **why**: a reason code (seasonal, not-a-rental, wrong-area, duplicate,
gone, bad-data + taste reasons) plus a free-text note, signed by whoever passed it. Notes append
to the shared preferences store (same Gist), so Malia's reasons reach the next pull.
`python -m quintal.feedback report --pool <region>` reads them back before collecting: it splits
**filter misses** (each naming the module at fault) from **taste**, re-runs the *current* screener
over each flagged listing (`✗ still slips` vs `✓ now caught`), and **mines candidate patterns**
from the still-slipping seasonal ones — ★-marking phrases the searcher quoted, and showing each
phrase's **collateral** (other pool listings it would purge). Patterns are proposed, never
auto-applied. `block` hard-blocks flagged listings by id (works for reasons no pattern could
catch); `resolve` closes notes you acted on; un-passing retracts a note, so a reversed 👎 can't
drive a filter change. Wired into RECOLLECT.md as **step 0**.
- **Caveat (verified 2026-08-25):** locally the CLI reads `data/preferences.json` unless
  `QUINTAL_GIST_ID`/`QUINTAL_GITHUB_TOKEN` are in `.env` — i.e. *not* the shared log. It prints
  which store it read; those two vars still need adding to the local `.env`.

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
- **App** (`app.py`, Streamlit) — filters, 3 sort modes, 👍/👎 per listing & area, and a 👎
  that asks *why* (reason + note, see below).
- **Hosting** — live on Streamlit Community Cloud (`deploy` branch), shared prefs via a
  private GitHub Gist (`GistBackend`); `scripts/publish.sh` refreshes → auto-redeploy.
  Malia confirmed it works for her.
- **141 tests green.**

## Re-collection log
- **2026-08-22** — **both pools re-pulled** (first dual re-collection). **Algarve:** idealista
  477 (+145 new, 332 resurrected), imovirtual 328 (+148 new, 180 updated); descriptions 649,
  120 newly-delisted; **RANKED 593** (166 under / 183 fair / 213 over). **Norte:** idealista
  1750 (+579 new, 1171 updated, 626 culled ~35% churn), imovirtual 2072 (+589 new, 1483
  updated); **RANKED 2441, located 2431 (99.6%)** (676 under / 1009 fair / 721 over). Norte
  concelhos re-cleaned by reverse-geocode (junk 106 → 10). First pull using the imovirtual
  `__NEXT_DATA__` location fix (QT-043) — 35/40 organic cards read structured address live.
  Published both to `deploy`.
  - **Incident (recovered):** the stale Aug-6 `quintal_idealista.json` was still in ~/Downloads,
    so Chrome suffixed the fresh Faro download to `(1)` and the first ingest pulled the *old
    Norte* file into the Algarve store (+1797 rows, culled 456 Faro). Backed up, removed the
    1797 by URL, re-ingested the correct file → store restored, 0 contamination. **Lessons now
    in RECOLLECT.md:** `rm ~/Downloads/quintal_*.json` *before* each download; verify the
    download row-count matches the browser total before `--ingest`.
  - **Idealista render races:** under background-maintenance load the per-page `navigate→eval`
    sometimes ran before cards rendered (`page:0`); re-fetching each miss (or a separate
    navigate-then-eval) recovers it. Imovirtual is SSR → no races. Paused maintenance during
    collection to avoid the contention.
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
Last work: QT-044, the 👎-reason loop above (tested end-to-end in the live app — pass with a
reason, note lands in the store, report reads it, un-pass retracts it). Before that, the
2026-08-22 dual re-collection. Prior
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
