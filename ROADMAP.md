# Roadmap — Quintal

## Phase 1 — Prove the brain ✅
Schema, scoring, valuation, dedup, static HTML on synthetic sample data. No collection.
*Goal: trust the ranking/valuation logic before spending effort on data.*

## Phase 2 — Real data in
Idealista + Imovirtual browser-session adapters → `listings.jsonl`. One file per site,
isolated so adding a site = adding a file. (Casa Sapo / BPI later.)

## Phase 3 — Enrichment
Geocode (Nominatim) → beach walk-time (Overpass + OpenRouteService) → ruralness
(nearest town centroid). Bounded, cached by lat/lng, observable fallback chain.

## Phase 4 — The interactive tool
Streamlit UI: filters, 3 sort modes (best fit / best deal / blend), 👍/👎 per listing
and per area, persisted to `preferences.json`. This is the thing we actually use daily.

## Phase 5 — AI review layer (opt-in)
Local Ollama pass that re-verifies keyword-derived features and drafts a plain-language
"why this valuation" from the description. Layers on top of the deterministic pipeline;
never the primary path.

## Later / maybe
Photo-hash dedup · more sites · saved-search alerts when a 🟢 high-match listing appears.
