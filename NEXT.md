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
- [x] **Imovirtual *search cards* carry no description** — clarified: the note always meant the result-grid tiles we scrape (title+address+specs only), NOT that Imovirtual lacks descriptions. The detail pages carry the owner's full text — now enriched in via QT-024.
- [x] **QT-024 — Imovirtual description enrichment (built 2026-07-19)** — pulls each Imovirtual detail page's real owner description so yard/bathtub/pets derive from it instead of the title alone.
  - **`src/quintal/descriptions.py`** — the real text is NOT in the visible `data-cy="adPageAdDescription"` div (empty server-side, React fills it) nor `og:description`/JSON-LD (both auto-generated boilerplate: "Descubra esta…", "Encontre a sua casa de sonho…"). It lives in `__NEXT_DATA__` under a `"description"` key. Extractor takes the **longest non-boilerplate** JSON `description` value, JSON-unescapes, strips tags. Verified live: 2420 chars incl. jardim/piscina/logradouro/barbecue where the title had none.
  - **Storage:** sidecar `data/descriptions.json` keyed by `source_url` (chosen over write-back: survives re-collection, keeps `listings.jsonl` raw-collected truth). `pipeline.run` calls `descriptions.apply()` to layer it into `description_raw` before normalize → the app benefits automatically.
  - **Backfill** mirrors `photos.py`: resumable, polite (0.8s), checkpoints every 50, imovirtual-only (Idealista 403s). Run: `python -m quintal.descriptions`.
  - **Tests:** 6 — boilerplate-vs-owner extraction, unescape/tag-strip, apply-merge, yard-derivation flip, imovirtual-only backfill. 71 total green.
  - **Follow-ups:** ship the sidecar via `publish.sh` (added); Idealista still needs the logged-in browser session for its detail pages.
- [x] **QT-026 — liveness screen for delisted listings (built 2026-07-19)** — QT-024's 57 "empty" descriptions were mostly HTTP **410 Gone**. A probe found **56/443 Imovirtual listings (~13%) delisted** 11 days after collection — shown to Malia and polluting the valuation pool.
  - **`src/quintal/liveness.py`** — probes detail pages, records 404/410 urls to persistent `data/delisted.json`; `pipeline.run` drops them right after normalize (before valuation), like `screening.py`. Only deliberate 404/410 count (not transient 5xx/timeouts). Imovirtual-only (Idealista 403s). Resumable (known-gone skipped), polite. Run: `python -m quintal.liveness`.
  - **Impact:** 56 removed from the pool; 35 fewer dead cards in the ranked view (rest were dupes of live listings). 5 tests, 76 total green. Sidecar shipped via `publish.sh`.
  - **Staleness is now a known axis** — re-probe (+ re-collect) periodically; ~13%/11 days is a fast decay. Idealista liveness still needs the browser session.
- [ ] **Ingest ergonomics** — the chunked-rows workaround is manual; wire a cleaner extract→store path. Learned transport: in-page JS accumulates all pages into `localStorage`, then a **Blob download from a *fresh tab*** dumps exact bytes to `~/Downloads` (Chrome blocks a 2nd auto-download in the *same* tab — a new same-origin tab bypasses it). `get_page_text` body-swap still works but caps at ~50 KB so needs chunking.
- [x] **Price parse gap — was a misdiagnosis (checked 2026-07-19).** `parse_price` already handles space-separated thousands, incl. nbsp/narrow-nbsp (`299 000 €` → 299000.0); regression test added. The €299k listing that got skipped wasn't a parse failure — it was a *sale* listing with no monthly-rent value, so skipping it is correct (a sale leaking into rentals is a screening concern, not a parsing one).
- [x] **Streamlit app** — filters + sort modes + 👍/👎 (listing & area) → `preferences.json` (`app.py`)
- [x] **Enrichment (Phase 3)**: Nominatim geocode → nearest-beach walk-time → ruralness; region features fetched once (295 beaches/106 towns) + cached; `--enrich` flag
- [x] **Geocode concelho-first** (QT-011) — freguesia-first fired a network call per listing on names that often miss (150+), tripping OSM's bulk block; concelho-first is ~50 distinct, all resolve. Also fixed enrichment cache to persist per-lookup (QT-009).
- [x] **Second geocoder fallback (QT-013)** — public Nominatim bulk-rate-limits us (a gentle 44-locality pass resolved only ~5). Added **Photon** (Komoot, OSM-based, no bulk limit) as an ordered fallback `Nominatim → Photon → skip` in `GeoClient.geocode`. Full 499-listing pool now enriches in one ~80s run, **499/499 located**. The spaced auto-retry loop is no longer needed.
- [ ] **OpenRouteService key** → real routed walk-time instead of straight-line estimate (optional upgrade)
- [x] **QT-027 — Persist enriched fields** (built 2026-07-19). `enrich.save_geo`/`apply_geo` persist each listing's resolved geo (lat/lng/dist_beach/walk_min/dist_town) by id to `data/geo.json`. `pipeline` applies the sidecar first (zero network), then `--enrich` fills only new localities and re-persists. A plain non-enrich run now carries geo for all 436 (was 0), and the hosted app cold-starts with no network for known listings. Gap-fill only (a fresh enrich wins). Shipped via `publish.sh`. 4 tests.
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
