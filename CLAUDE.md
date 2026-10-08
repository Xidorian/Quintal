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
- `feedback.py` — the 👎-reason loop. Each 👎 in the app carries a reason code + note
  (stored in the shared preferences log); this reads them back before the next pull,
  splits **filter misses** (should never have been shown → names the module to fix) from
  **taste**, re-runs the current screener over each flagged listing to tell "still slips"
  from "now caught", and mines candidate `SHORT_TERM_PATTERNS` from the misses — each with
  the collateral count. Patterns are **proposed, never auto-applied**.
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
- **A 👎 asks why** (settled 2026-08-25): reason code + free-text note, logged append-only in
  the same store. Un-passing retracts the note, so a reversed 👎 can never harden a filter.
  Screenable reasons name the module at fault; the report proposes patterns, a human adds them.

## Gotchas
- Ubuntu 24 PEP 668: always use `.venv` (see profile).
- **Keep `app.py`'s import path 3.10-compatible.** `datetime.UTC` broke the live app on
  2026-08-25; `preferences.py` uses `timezone.utc` for that reason. `scripts/publish.sh`
  fails the publish on a violation (`vermin -t=3.10-`), so it can't reach Malia again.
  **Streamlit Cloud has since moved to Python 3.14.8** — read off the deploy log 2026-10-08,
  which also shows the runtime at `venv/lib/python3.14`. The gate stays at 3.10 anyway: it
  costs nothing, the platform moved once without telling us and can move back, and nothing
  in this codebase wants a 3.11+ feature. Don't "fix" the gate to match the platform —
  the gate is the reason the platform's version stopped mattering.
- Sample data in `data/sample_listings.jsonl` is **synthetic**, clearly flagged — do not
  treat it as collected market data. Real listings arrive via the same schema.
- With a small pool the hedonic model is low-confidence — the confidence badge is not
  decoration, respect it; peer-median fallback kicks in for thin concelho+bedroom buckets.

## Testing focus
Per the python profile's "cover the pipeline's brain": scoring, valuation (incl. the
peer-median fallback), normalization/keyword derivation. a11y: the 🟢/⚪/🔴 valuation
band is always paired with text — never colour alone.

**`extract.js` is gated too** (`tests/test_extract_js.py`, added 2026-09-26). It is injected
into a live browser, so it used to have no test at all — and both bugs it produced (QT-049,
QT-050) reached the collected pool as corrupted data rather than failing a test.
`tests/extract_harness.mjs` runs the *real* extract.js in jsdom over the saved fixtures in
`tests/fixtures/extract/`, and the tests push those rows through the real Python adapters, so
the JS extraction and the Python parsing are proved to agree on one shared input. Needs
`npm install` (jsdom only); the tests skip loudly without it. **The fixtures are a snapshot —
they catch *our* regressions, not a portal changing its markup.** When a pull looks wrong,
re-capture first: `tests/fixtures/extract/README.md`.

For the portal-moves case there are two runtime guards (QT-052): `quintalExtract` returns
`expected` (a selector-independent count of the page's listing links) plus a `suspect` verdict,
which tells a moved card selector from the genuine end of pagination — watch it on every page of
a pull; and `liveness.cull_absent` refuses to cull a pull that re-surfaced under
`MIN_CULL_COVERAGE` (30%) of the site's live listings, so a collapsed pull can't delist the pool
(`--force-cull` overrides).

## Commands
```
. .venv/bin/activate
python -m quintal.pipeline --input data/sample_listings.jsonl --html out/listings.html   # build the ranked page
python -m quintal.collect.run --print-urls                                                # search URLs to open in Chrome
python -m quintal.collect.run --site idealista --ingest rows.json                         # map extracted cards → listings.jsonl
python -m quintal.feedback report --pool algarve                                          # why we passed → what to harden (run before a pull)
python -m quintal.feedback block --pool algarve                                           # hard-block the flagged misses by id
pytest                                                                                    # run the brain's tests (incl. the extract.js gate)
npm install                                                                               # once: jsdom, for the extract.js harness
node tests/extract_harness.mjs tests/fixtures/extract/imovirtual-search.html imovirtual    # replay a fixture by hand
streamlit run app.py                                                                      # interactive UI (post step-1)
```

## Collection flow (Phase 2)
Browser-session based, no scraping infra. Open the search in logged-in Chrome, extract the
cards, map each `ExtractedRow` via `collect/base.py: row_to_raw`, upsert idempotently by
source URL into `data/listings.jsonl`. Then `screening.py` purges short-term/holiday (AL)
rentals into a persistent blocklist, and the pipeline runs as normal.

**Extraction is versioned** in `collect/extract.js` — inject it into the results tab, then
`quintalReset(site)` (page 1) → `quintalExtract(site)` (each page, accumulates to
`localStorage`) → `quintalDownload(site)` (once, **from a fresh tab**) → `--ingest`. The
per-site card selectors live there as the single source of truth; fix them there when a
portal moves them. Selectors validated live 2026-07-19 (idealista `article.item`;
imovirtual `[data-cy="search.listing.organic"] article`).

### Transport (learned the hard way, 2026-07-01)
Two dead ends: the `javascript_tool` return caps ~1 KB, and Chrome **Private Network Access**
blocks a public page from POSTing to the local `receiver.py` (kept, but unreachable from
idealista.pt). **What works:** in-page JS extracts all cards to a JSON array, replaces
`document.body` with a single `<article><p>…JSON…</p></article>`, then `get_page_text`
returns the whole thing in one call (readability picks the sole article). Bulk, no chunking.

### Caveats
- Idealista's long-term search leaks Spacest.com "Reserve em linha" medium-term listings and
  AL/holiday lets — `screening.py` catches them; extend its patterns as new ones appear.
- **Imovirtual syndicates booking platforms.** Uniplaces stock arrives verbatim, boilerplate
  and all, and was 18% of the ranked Algarve pool before QT-053. Its machine-generated title
  ("Apartamento com 1 quartos - localizado em …") is what `screening.py` matches, because the
  Norte cards carry no description for a text pattern to bite on. Expect other syndicators to
  show up the same way — a platform name and a minimum stay in *days* are the reliable tells.
- **Property type is inferred from the title, matched as whole words** (`normalize.py`), and
  it is not cosmetic: it is worth 12/100 in `score.py` and is a hedonic regression feature.
  The description is a fallback only, and is blind to "casa"/"house" — a PT listing calls any
  home "a casa" in its prose, which is how 145 apartments became houses before QT-054.
- The filter-URL schemes in the adapters are best-effort; the guessed price/bedroom path 404s
  and still needs discovering from the live UI.
- Search cards give ~300-char description previews; full amenities need per-listing detail pages.
- The feedback CLI reads whichever preferences store is configured — **without
  `QUINTAL_GIST_ID`/`QUINTAL_GITHUB_TOKEN` in the env it reads the local file, not the shared
  log**. It prints the store in its header; check it before hardening off the result.

## Licensing
Proprietary / all rights reserved. The repo is **public** only because Streamlit Cloud
hosting requires it — a public repo is not an open-source license.

## Docs
@~/.claude/conventions/four-file.md
