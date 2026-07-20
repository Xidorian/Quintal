# Roadmap — Quintal

## Phase 1 — Prove the brain ✓ Shipped
Schema, scoring, valuation, dedup, static HTML on synthetic sample data. No collection.
*Goal: trust the ranking/valuation logic before spending effort on data.*

## Phase 2 — Real data in ✓ Shipped
Idealista + Imovirtual browser-session adapters → `listings.jsonl`. One file per site,
isolated so adding a site = adding a file. Live pool is district-wide. (Casa Sapo / BPI later.)

## Phase 3 — Enrichment ✓ Shipped
Geocode (`Nominatim → Photon → skip`) → beach walk-time (Overpass + real ORS routed) →
ruralness (nearest town centroid). Bounded, cached by lat/lng, observable fallback chain.
Geo persisted per-listing so any run is network-free.

## Phase 4 — The interactive tool ✓ Shipped
Streamlit UI (`app.py`): filters, 3 sort modes (best fit / best deal / fit+deal), 👍/👎
per listing and per area, persisted to `preferences.json`. Hosted for Malia on Streamlit
Cloud with Gist-backed shared prefs. This is the thing we use daily.

## Phase 5 — AI review layer (opt-in) — not started
Local Ollama pass that re-verifies keyword-derived features and drafts a plain-language
"why this valuation" from the description. Layers on top of the deterministic pipeline;
never the primary path.

## Later / maybe
More sites (Casa Sapo / BPI) · saved-search alerts when a 🟢 high-match listing appears.
Photo-hash dedup — ✓ shipped (guarded second pass, QT-032).

## Out of scope
Scraping / CAPTCHA-bypass infra (collection stays browser-session, ToS-respecting) ·
official/appraisal-grade valuation (Quintal is relative-to-current-pool only) · hosted
LLMs as the primary path (AI review is local-first and opt-in).
