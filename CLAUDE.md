# Quintal

Relative-valuation rental finder for the Algarve. Collects long-term rental listings,
normalizes them, derives features, values each against the *currently-available pool*
(🟢 undervalued / ⚪ fair / 🔴 overpriced), and scores each 0–100 against our
preferences (weighted toward a yard for Luna and beach-walkability). Personal tool for
Alexander's move to the Algarve.

## Stack
This project runs on **python** — see the profile below.
@~/.claude/stacks/python.md
- Platforms: local (venv, run on-demand — no hosting)
- APIs: OpenStreetMap/Nominatim (geocode), Overpass (beaches), OpenRouteService (walk routing) — enrichment phase only

## Story prefix
`QT-###` for story/loop commits (e.g. `QT-001 add hedonic valuation`).

## Architecture
```
collect (browser session)  →  data/listings.jsonl
                                     │
   normalize ─ dedup ─ enrich ─ value ─ score  →  ranked listings
                                     │
                    render_html (step-1 proof)  ·  app.py (Streamlit UI)
```
- `src/quintal/schema.py` — Pydantic `Listing` model (the one contract every stage speaks).
- `normalize.py` — raw site dict → `Listing`; derives `has_yard`/`has_bathtub`/`pets`
  by PT+EN keyword scan of the description, each with a confidence.
- `dedup.py` — attribute-based collapse (same concelho + beds + size ±5% + price ±5%);
  private-landlord listing wins as canonical; photo-hash is a later optional enhancement.
- `enrich.py` — pluggable enricher chain (geocode → beach walk-time → ruralness), each
  step bounded + cached by lat/lng. Designed so an **AI review pass layers on top later**.
- `valuation.py` — hedonic ridge regression on `log(price)` with a **peer-median
  fallback** for thin areas; emits `valuation_pct`, band, and a confidence badge.
- `score.py` — weighted preference match, weights are tunable constants in `config.py`.
- `pipeline.py` — orchestrates load → normalize → dedup → enrich → value → score;
  per-item error isolation so one bad record never aborts the batch.
- `render_html.py` + `templates/listings.html.j2` — static ranked page (step-1 proof).
- `app.py` — Streamlit interactive layer (filters, sort modes, 👍/👎 per listing & area).

## Key design decisions (settled 2026-07-01)
- **Valuation is relative to the current collected pool, not an official appraisal.** UI must say so.
- **Collection is browser-session based** (Claude-in-Chrome, ToS-respecting) — no scraping/CAPTCHA infra.
- **Walk score** graded: full ≤15 min, ~40% at 30 min, 0 beyond ~45 (yard is a separate axis).
- **Pets:** `unknown` kept & flagged (legally protected in PT long-lets); only explicit "não aceita animais" excluded.
- **Furnished:** displayed attribute only — not scored, not filtered.
- **AI:** regex derivation is the system; an LLM review/verification pass is an opt-in layer added later (local Ollama default).
- **Preferences** (👍/👎, per-area sentiment) persist to `data/preferences.json` — source of truth, survives re-collection.

## Gotchas
- Ubuntu 24 PEP 668: always use `.venv` (see profile).
- Sample data in `data/sample_listings.jsonl` is **synthetic**, clearly flagged — do not
  treat it as collected market data. Real listings arrive via the same schema.
- With a small pool the hedonic model is low-confidence — the confidence badge is not
  decoration, respect it; peer-median fallback kicks in for thin concelho+bedroom buckets.

## Commands
```
. .venv/bin/activate
python -m quintal.pipeline --input data/sample_listings.jsonl --html out/listings.html   # build the ranked page
python -m quintal.collect.run --print-urls                                                # search URLs to open in Chrome
python -m quintal.collect.run --site idealista --ingest rows.json                         # map extracted cards → listings.jsonl
pytest                                                                                    # run the brain's tests
streamlit run app.py                                                                      # interactive UI (post step-1)
```

## Collection flow (Phase 2)
Browser-session based, no scraping infra. Open the search in logged-in Chrome, extract the
cards, map each `ExtractedRow` via `collect/base.py: row_to_raw`, upsert idempotently by
source URL into `data/listings.jsonl`. Then `screening.py` purges short-term/holiday (AL)
rentals into a persistent blocklist, and the pipeline runs as normal.

### Transport (learned the hard way, 2026-07-01)
Two dead ends: the `javascript_tool` return caps ~1 KB, and Chrome **Private Network Access**
blocks a public page from POSTing to the local `receiver.py` (kept, but unreachable from
idealista.pt). **What works:** in-page JS extracts all cards to a JSON array, replaces
`document.body` with a single `<article><p>…JSON…</p></article>`, then `get_page_text`
returns the whole thing in one call (readability picks the sole article). Bulk, no chunking.

### Caveats
- Idealista's long-term search leaks Spacest.com "Reserve em linha" medium-term listings and
  AL/holiday lets — `screening.py` catches them; extend its patterns as new ones appear.
- The filter-URL schemes in the adapters are best-effort; the guessed price/bedroom path 404s
  and still needs discovering from the live UI.
- Search cards give ~300-char description previews; full amenities need per-listing detail pages.

## Licensing
Proprietary / all rights reserved (private personal tool).
