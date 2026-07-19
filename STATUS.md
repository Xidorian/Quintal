# Status — Quintal

**2026-07-19 (later) — QT-024: Imovirtual descriptions enriched → real amenity signal.**
The bulk of the pool (443 Imovirtual listings) was being scored on titles alone for
amenities, because the search *cards* carry no description. Built `descriptions.py` to pull
each detail page's real owner text — which lives in the page's `__NEXT_DATA__` JSON, not the
visible description div (empty server-side) nor og:description/JSON-LD (both auto-generated
boilerplate). Extractor takes the longest non-boilerplate `"description"` value, unescapes,
strips tags. Cached to a `data/descriptions.json` sidecar keyed by source_url (survives
re-collection; `pipeline.run` layers it into `description_raw`, so the app benefits too).
Backfill: **386/443 (87%)** enriched (57 empty), Idealista's 213 skipped (DataDome 403s).
Impact on the Imovirtual set: yard **7→75**, bathtub **0→16**, pets-known **0→178** — the
derivation went from nearly blind to working, and it feeds the yard-weighted ranking. 71
tests green (6 new). Next: `scripts/publish.sh` so Malia's app gets the sharper flags.

**2026-07-19 — shareable: Malia can use it hosted, with shared preferences.**
Made Quintal deployable to **Streamlit Community Cloud** (free) so Malia opens a private URL
on her laptop/phone — no install. Two pieces: (1) preferences got a **swappable backend** —
`LocalFileBackend` (dev, unchanged) or a new `GistBackend` that reads/writes a private GitHub
Gist, so the ephemeral-disk host keeps prefs *and* both of us share one live source of truth
(env/`st.secrets`-selected; app falls back to the local file when unset). (2) A **`deploy`
branch** carries the data snapshot (`main` keeps runtime data gitignored, as designed); a
`scripts/publish.sh` worktree-based one-liner refreshes it → Cloud auto-redeploys. Also:
`app.py` src-path shim so the package imports on Cloud (no `pip install -e .` there),
`.streamlit/config.toml` theme, `python -m quintal.seed_prefs` to migrate existing 👍/👎 into
the Gist, and a `DEPLOY.md` runbook. 65 tests green (5 new for the backends). **Not yet done
(needs Alexander):** create the GitHub remote, the Gist + fine-grained token, and the Cloud
app + Malia's viewer email — all scripted in DEPLOY.md.

**2026-07-09 — enrichment complete on the full pool via a geocoder fallback.**
Enrichment surfaced two real bugs (both fixed): Imovirtual concelho was collapsing to the
district 'Faro' for all 443 (QT-010, also un-polluted valuation peer-groups), and geocoding
was freguesia-first, firing a per-listing call on names that often miss (QT-011 → concelho-
first). The true blocker was that **public Nominatim bulk-rate-limits us** — a gentle
44-locality pass resolved only ~5. Fixed by adding **Photon** (Komoot/OSM, no bulk limit) as
an ordered fallback `Nominatim → Photon → skip` (QT-013); the full pool now enriches in one
~80s run, **499/499 located, all with beach walk-times**. Cache also persists per-lookup now
(QT-009), so runs are resumable. Walk-times reshuffled the ranking — top is a Luz moradia
(70/100, undervalued −55%, €1,425); Vale do Lobo luxury villas score high on amenities but
sink on value (+127%). App: run `.venv/bin/streamlit run app.py` (streamlit lives in the
venv). NEXT: freguesia-level geocode precision (now safe with Photon), persist enriched
fields back to the store, ORS routed walk-times.

**2026-07-08 — first FULL live pull; pool is now real and district-wide.**
Drove the logged-in Chrome across the whole Faro district (= the whole Algarve) on both
portals: Idealista 6 pages (180 cards) + Imovirtual 10 apartamento + 3 moradia pages (443).
Store is now **656 listings** (443 imovirtual / 213 idealista). Pipeline runs clean:
normalize → screening purges 76 AL/Spacest short-term → **578 kept** → cross-source dedup →
**419 ranked** (159 duplicates collapsed — the two portals overlap heavily). Top matches are
yard moradias, correctly weighted toward Luna; valuation bands are finally meaningful at this
pool size. Only 2 items skipped (null price — one was a €299k *sale* listing that leaked into
rentals; per-item isolation logged + skipped it, no crash).
Fixed the Idealista **pagination bug** (`?pagina=N` overlapped page 1) — real format is the
path segment `…/faro-distrito/pagina-N`; adapter + tests updated, 51 green. Validated the
**Imovirtual** adapter against the live site for the first time (selectors, `?page=N`, and the
quirk that its path drops comma-joined property types so apt/moradia are separate searches).
Transport learned: accumulate pages in `localStorage`, then Blob-download from a **fresh tab**
(Chrome blocks a 2nd auto-download in the same tab). **Not yet done:** per-listing amenity
enrichment (Imovirtual *search cards* have no description → yard/pets detection is title-only
there; the detail pages DO have a full "Descrição" — that's the fix, see QT-024 in NEXT.md),
and `--enrich` geocoding hasn't been re-run on the big pool. See NEXT.md.

**2026-07-01 — Phase 4 Streamlit app: the MVP is complete.**
`app.py` — the interactive tool. Runs the full brain (screen → enrich → value → score)
over the real pool and gives sidebar filters (price, beds, yard, pets, band, concelho,
max beach-walk), three sort modes (best fit / best deal / fit+deal), and 👍/👎/hide per
listing plus 👍/👎 per **area**, all persisted to `data/preferences.json`. Verified live:
the app renders, filters, and a 👍 click writes through to preferences. `preferences.py`
+ tests. **All five build-order phases' core is now in place** (collect → screen → enrich
→ value/score → interactive UI); remaining work is depth/polish (more listings, Imovirtual,
ORS routing, optional AI review), not new capability.
Live UI surfaced + fixed a real bug: `row_to_raw` picked the first *truthy* of
typology/title/rooms_text and parsed only that, so titles without a "T3" shadowed the real
bedroom count (→ null beds, which also corrupted valuation peer-grouping). Now tries each
source in turn. Run it: `streamlit run app.py`.

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

**2026-07-01 (late) — Phase 3 enrichment built + demonstrated.**
`geo.py` (haversine, walk estimate) + `enrich.py` enrichers: Nominatim geocode →
nearest-beach + walk-time → ruralness. Key insight after getting IP-throttled: fetch **all
Algarve beaches (295) and towns (106) once** for the region and compute nearest locally —
2 Overpass calls total, cached forever, instead of 2×N. Keyless by default (straight-line
walk estimate); ORS key optional for real routing. Demonstrated live: 10/13 geocoded, and
walk-times materially reshaped the ranking — beachfront Portimão flats (1 min) rose, inland
VRSA (103 min / 6.4 km) fell, the Luz yard-moradia (27 min walk) leads at 61. `--enrich`
flag on the pipeline; 44 tests green.
**Caveat:** Nominatim/Overpass rate-limit under this session's heavy repeated testing, so a
fresh run here may locate fewer until the throttle clears — a normal single run of ~13
listings is well within free limits and locates all. Enrichment cache is gitignored.

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
