# Next — Quintal

- [x] Agree stack (Python) + write `python` stack profile
- [x] Scaffold four-file project + package layout
- [x] `Listing` schema (Pydantic v2)
- [x] Normalizer + PT/EN keyword derivation (yard/bathtub/pets) with confidence
- [x] Match score (0–100), weights as config constants
- [x] Hedonic valuation + peer-median fallback + confidence badge
- [x] Attribute-based dedup
- [x] Static Jinja2 HTML render with 3 sort modes
- [x] pytest suite (score / valuation / normalize) green
- [x] **Collection framework**: Idealista + Imovirtual adapters (search-URL builders + row→raw mapping), PT-format parsing (thousands-dot vs decimal-comma), idempotent `listings.jsonl` store, tests
- [x] **Collection — live (Idealista)**: extracted 30 real Faro listings, ingested, ran full pipeline on real data
- [x] **Exclude holiday/AL rentals** — `screening.py` purges short-term + Spacest "reserve em linha" into a persistent blocklist (17/30 purged on first real batch)
- [x] **Full-description transport** — body-swap + `get_page_text` returns all cards in one call (yards/bathtubs now detected)
- [x] **Real Idealista pagination** — fixed: path segment `…/faro-distrito/pagina-N` (NOT `?pagina=N` which overlaps, NOT `/pagina-N.htm` which redirects to landing). Verified live; adapter + comment updated 2026-07-08. Pulled all 6 Faro pages (180 cards).
- [x] **Full Idealista + Imovirtual live pull (2026-07-08)** — Idealista 6 pages (180) + Imovirtual 10 apartamento + 3 moradia pages (443). Store now 656; 578 kept post-screening; 419 ranked after cross-source dedup.
- [x] **Imovirtual live run** — validated: `/pt/resultados/arrendar/{apartamento|moradia}/faro?page=N`, cards `[data-cy="search.listing.organic"] article` with `listing-item-{price,link,title}`, `advert-card-address`, `dl dd` for Tipologia/m², "Oferta privada" flag. Note: **path drops comma-joined types** (`apartamento,moradia` → `apartamento` only) so apt + moradia are pulled as **separate searches**.
- [ ] **Discover Idealista filter-URL format** from the UI (price cap + bedrooms) — my guessed path still 404s; using the plain region URL + post-collection filtering for now
- [ ] **Imovirtual *search cards* carry no description** — the result-grid tiles we scrape give only title+address+specs, so yard/bathtub/pets derivation is title-only for this source. NOT that Imovirtual lacks descriptions: the **detail pages have a full "Descrição"** (jardim/piscina/casas de banho/etc.) — that's where the amenity signal lives (see QT-024). Idealista's cards *do* include a ~300-char preview; Imovirtual's don't.
- [ ] **QT-024 — Imovirtual description enrichment (biggest remaining accuracy win)** — ~443 Imovirtual listings (bulk of the pool) are scored on titles alone for amenities; pull the real detail-page text so yard/bathtub/pets derive from it.
  - **Reuse the working fetch:** `quintal.photos` already GETs each Imovirtual detail page server-side (UA-spoofed `requests`, og:image regex) — Idealista 403s (DataDome), so this covers Imovirtual only, same coverage as photos.
  - **Build `src/quintal/descriptions.py`:** for each stored listing missing a description, fetch its `source_url` HTML, extract the **`Descrição` block** (fuller than `og:description`, which is truncated — the screenshot showed the full text lives in the detail `<div>`), and persist it. Bounded + cached + resumable + per-item error isolation, mirroring `photos.py` (a separate pass because the photo run cached images, not HTML).
  - **Storage decision (pick one):** either write `description_raw` back onto `data/listings.jsonl` records, or a sidecar `data/descriptions.json` keyed by id that `normalize` merges in. Sidecar keeps `listings.jsonl` as raw-collected truth; ties into the still-open "persist enriched fields back to the store" item — decide together.
  - **Wire into `normalize`** so `has_yard`/`has_bathtub`/`pets` re-derive from the enriched text (they already keyword-scan `description_raw` — this just feeds it real content).
  - **Tests:** `Descrição`-block extraction from a saved Imovirtual HTML fixture; normalize deriving yard/pets from enriched text; resumability (skip already-fetched).
  - **DoD:** re-run pipeline → materially more Imovirtual listings flagged yard/bathtub/pets with description-level (not title-only) confidence; then `scripts/publish.sh` so it reaches Malia's app.
  - **Caveat:** fresh ~443-page fetch pass (a few minutes, resumable). Idealista still needs the logged-in browser session for its detail pages.
- [ ] **Ingest ergonomics** — the chunked-rows workaround is manual; wire a cleaner extract→store path. Learned transport: in-page JS accumulates all pages into `localStorage`, then a **Blob download from a *fresh tab*** dumps exact bytes to `~/Downloads` (Chrome blocks a 2nd auto-download in the *same* tab — a new same-origin tab bypasses it). `get_page_text` body-swap still works but caps at ~50 KB so needs chunking.
- [ ] **Price parse gap** — space-separated thousands (`299 000 €`, a sale listing that leaked in) → `None` and the item is skipped (harmless here, but `parse_price` should handle space thousands)
- [x] **Streamlit app** — filters + sort modes + 👍/👎 (listing & area) → `preferences.json` (`app.py`)
- [x] **Enrichment (Phase 3)**: Nominatim geocode → nearest-beach walk-time → ruralness; region features fetched once (295 beaches/106 towns) + cached; `--enrich` flag
- [x] **Geocode concelho-first** (QT-011) — freguesia-first fired a network call per listing on names that often miss (150+), tripping OSM's bulk block; concelho-first is ~50 distinct, all resolve. Also fixed enrichment cache to persist per-lookup (QT-009).
- [x] **Second geocoder fallback (QT-013)** — public Nominatim bulk-rate-limits us (a gentle 44-locality pass resolved only ~5). Added **Photon** (Komoot, OSM-based, no bulk limit) as an ordered fallback `Nominatim → Photon → skip` in `GeoClient.geocode`. Full 499-listing pool now enriches in one ~80s run, **499/499 located**. The spaced auto-retry loop is no longer needed.
- [ ] **OpenRouteService key** → real routed walk-time instead of straight-line estimate (optional upgrade)
- [ ] **Persist enriched fields** back to the store so non-`--enrich` runs keep geo (currently enrichment is per-run + cached)
- [x] **Listing thumbnails (QT-018)** — `quintal.photos` fetches each listing's og:image from its detail page (fallback og:image → twitter:image → placeholder), downloads to `data/photos/<id>.jpg` (gitignored, resumable); app shows it per card. Run: `python -m quintal.photos`.
- [ ] **Idealista thumbnails** — Idealista detail pages 403 to server-side fetches (DataDome), so QT-018 only covers Imovirtual (443/656). Get Idealista's via the logged-in browser session: either capture card `<img>` src during collection (6 page-loads, then test if the img CDN allows plain-HTTP download) or a browser pass over the 213 detail pages for og:image.
- [ ] **Wire `image_url` into the extractors** so future collection captures a thumbnail directly (avoids the per-listing detail fetch for new pulls).
- [ ] Photo-hash dedup (optional enhancement)
- [x] `git init`, first commit (local; no GitHub remote yet)

## Sharing — hosting for Malia (QT-020..022, 2026-07-19)
- [x] **Preferences backend abstraction** — `LocalFileBackend` (dev) + `GistBackend` (shared,
  durable) behind the same `Preferences` API; env/`st.secrets`-selected, falls back to local.
- [x] **Streamlit Cloud readiness** — `app.py` src-path shim + secrets bridge, `.streamlit/config.toml`.
- [x] **`deploy` branch + `scripts/publish.sh`** — worktree-based data snapshot → Cloud redeploy.
- [x] **Gist seeder** (`python -m quintal.seed_prefs`) + **`DEPLOY.md`** runbook. 5 new tests.
- [ ] **Alexander to run the one-time setup** (all in DEPLOY.md): create `Xidorian/Quintal` remote
  (`gh repo create … --push`); create the private Gist + fine-grained (Gists-only) token; seed it;
  `scripts/publish.sh`; create the Streamlit Cloud app on branch `deploy` with the two secrets;
  restrict sharing to Malia's email.
