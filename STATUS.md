# Status — Quintal

**2026-07-01 — Step 1 (the brain) built on synthetic data.**

Fresh project. Stack agreed as **Python** (pandas / scikit-learn / Jinja2 + Streamlit
later); wrote the `python` stack profile before any code, per house rules.

Where it stands: the whole scoring/valuation pipeline runs end-to-end on ~20 **synthetic**
Algarve listings (`data/sample_listings.jsonl`, clearly flagged as not-real) and produces
a ranked static HTML page at `out/listings.html`. That proves the brain before we touch
collection. Included:
- `Listing` schema (Pydantic v2), PT+EN keyword derivation of yard/bathtub/pets w/ confidence.
- Match score 0–100 (yard-for-Luna weighted highest, graded beach-walkability).
- Hedonic ridge valuation on log(price) with peer-median fallback + confidence badge.
- Attribute-based dedup. Static Jinja2 render with 3 client-side sort modes.
- pytest suite over score / valuation / normalization.

**Caveats:** valuation is relative-to-pool only; sample data is synthetic so the numbers
are illustrative, not market truth. Enrichment (geocode / real beach walk-time / ruralness)
is stubbed — walk distances currently come from the sample data, not OSM.

**Left off:** brain proven. Next real work is collection (Idealista + Imovirtual via
browser session) and wiring live enrichment. See NEXT.md.

**2026-07-01 (night) — screening + full-description transport solved.**
Added `screening.py`: detects short-term/holiday/AL rentals (incl. Spacest.com "Reserve em
linha" medium-term platform listings) and purges them into a persistent `data/blocklist.json`
shitlist; wired into the pipeline right after normalize. Solved the transport wall — in-page
JS dumps all cards into a single `<article>` and `get_page_text` returns the lot in one call
(full descriptions, no chunking). Re-ran on the real Idealista batch: **17/30 purged, 13
genuine long-term kept**, and full descriptions mean amenities now register (3 yards, 1
bathtub detected — top matches are all yard properties). Pool is finally meaningful, though
small (n=13 → low-confidence valuations until we collect more pages/sites). 36 tests green.

**2026-07-01 (evening) — first LIVE collection run (Idealista).**
Drove the searcher's logged-in Chrome, extracted 30 real Faro-district listings, ingested
to `data/listings.jsonl`, ran the full pipeline on real data end-to-end (30 → 29 after
dedup, ranked HTML produced). The pipeline *works* on real data. Findings that need action:
- **URL filters:** my guessed Idealista filter path (`com-preco-max_…,t2,…`) 404s. The plain
  regional URL works; the real filter-segment format still needs discovering from the UI.
- **Holiday/AL rentals contaminate the pool:** unfiltered results include €3–8k short-term
  "para Férias" listings that wreck the peer-median valuation (bands came out ~50/50 noise).
  Need a long-term-only filter (price cap in URL + AL exclusion) before valuation is meaningful.
- **Transport cap:** the JS→assistant channel caps ~1 KB, and Chrome **Private Network Access**
  blocks the page from POSTing to the local `receiver.py` (built + tested, but unreachable from
  a public origin). Worked around by paging compact rows out in chunks; descriptions truncated
  to 120 chars as a result, which under-detects yards (only 1 found). Proper fix: per-listing
  enrichment or a receiver reachable without PNA.
- **Keyword gaps:** real data said "não permitimos animais" (not in my list) — now added.

**2026-07-01 (afternoon) — Phase 2 collection framework built.**
`src/quintal/collect/`: Idealista + Imovirtual adapters (search-URL builders with per-site
region slugs, shared `row_to_raw` mapper), robust PT-format parsing (the thousands-dot vs
decimal-comma trap), and an idempotent `listings.jsonl` store keyed by source URL. 12 new
tests (29 total, all green). The durable core is done and tested **offline** — what remains
needs a browser: connect logged-in Chrome, validate the live URL schemes (flagged best-effort
in the adapters), extract rendered cards, `--ingest`. No Chrome was connected this session.
