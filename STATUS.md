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

## Pass UX corrected (2026-08-31, QT-046)
Malia was being asked *why* on every 👎, including the many that just mean "don't show me this
again". **A pass is one click again**; the reason is an optional follow-up on the already-passed
card (＋ Add a reason / ✏️ Edit reason), and free-text is first-class — 🤷 Something else now
*requires* the note, so a reason the taxonomy misses is recorded as itself instead of mis-filed.
Editing retracts the prior entry rather than stacking, so one listing can't be double-counted by
`feedback report`. 141 tests green, `vermin -t=3.10-` clean.

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
- **Incident + fix (2026-08-25, QT-045):** the first deploy took the live app down —
  `ImportError` on `from datetime import UTC` in `preferences.py`. **Streamlit Cloud runs Python
  3.10**; this repo develops on 3.12, so a 3.11-only alias passed every local check and only
  failed once hosted. Fixed with `timezone.utc`; `vermin` confirmed that was the *only* 3.11+
  construct in the app path. `scripts/publish.sh` now gates every publish with
  `vermin -t=3.10-` (verified to fail on a planted `datetime.UTC`), so the skew can't reach
  Malia again.
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

## Short-term screening hardened (2026-08-31, QT-048)
Malia was still hitting short-term lets. Root cause was `_SEASONAL_SPAN`: it only knew
`setembro|outubro` → `maio|junho|julho` joined by "a"/"até", so it missed **every** November/
December start, every March/April end, the "e" connector, dash spans, and abbreviated months
("de out/26 a mai/27", "nov 26- abril 27"). Widened, plus explicit duration phrases
(curta/média duração, curto/médio prazo, winter let, arrendamento de inverno, ano lectivo,
erasmus, "não é um arrendamento anual"). **101 listings newly caught** — Algarve screening
226 → 299 purged, Norte 63 → 84. Pools: Algarve **657 → 597**, Norte **2333 → 2316**.
- **Method — collateral measured before adding, per the runbook.** Phrase counts alone are
  misleading: `estudantes` matched 19% of the Algarve pool but is Uniplaces boilerplate
  ("liga indivíduos, sejam estudantes, profissionais ou famílias"); `meses`/`mínimo de` match
  *"contrato de 12 meses"* (explicitly long-term); `mês de` is a deposit; `hóspedes` is a guest
  bedroom; `a partir de setembro` is an annual let that starts in September. **All five were
  rejected**, and `test_long_term_listings_are_not_purged` now pins that decision so a future
  session can't "helpfully" add them.
- Every "e"-connector match was hand-audited before widening (14/14 real seasonal lets, one
  reading *"não é um arrendamento anual"*), and a sample of the 101 was read directly — several
  say *"não aceitamos contrato anual"* / *"não arrendo ao ano"*. New tests verified to fail
  against the old regex before committing.

## Re-collection log
- **2026-08-31 (part 2, same day)** — **Idealista pulled for both pools** once Chrome reconnected,
  completing the Monday run. Filtered search URL was transiently 503-ing ("Ups! De momento não
  estamos disponíveis") but recovered after loading the homepage first. **Algarve:** 541 cards
  (19 pages, plateau == the header's 541) → +123 new, 418 updated, **65 culled**, 6 resurrected;
  store 1724 → **1847**. Photos +120, liveness +3. **RANKED 628** (173 under / 233 fair /
  222 over). **Norte:** 1770 cards across the 5 districts (Porto 1041 of a stated 1.045, Braga
  409, Viana 151, Vila Real 47, Viseu ~122) → +406 new, 1364 updated, **1012 culled**, 16
  resurrected; store 5550 → **5956**. Photos +402. **RANKED 2333** (695 under / 940 fair /
  658 over), located 2322 (99.5%).
  - **QT-047 — a real bug found mid-run, and it predates today.** `liveness.cull_absent()`
    defaults to `data/delisted.json`, and `collect/run.py: ingest()` never overrode it per
    store. So **every Norte cull ever run wrote into the Algarve delisted file**, and
    `data/delisted-norte.json` had never existed — meaning the Norte pipeline (which reads its
    own sidecar) **applied zero delistings** and kept showing dead listings: 1012 of them
    (402 from today + ~610 surviving from the 2026-08-22 cull). Fixed by deriving the sidecar
    from the store path; repaired the data by removing exactly those 1012 foreign `absent`
    entries from `delisted.json` (1815 → 803) and re-running the Norte cull, which wrote the
    same 1012 into `delisted-norte.json`. Re-ingest was idempotent (+0 new), so the repair is
    self-consistent. Two regression tests added, **verified to fail against the old code**.
  - **This corrects a number reported earlier the same day:** the "Norte ranked 2658" from the
    Imovirtual-only pass was inflated by those undelisted dead listings. 2333 is the honest count.
- **2026-08-31** — **Imovirtual-only re-pull, both pools. Idealista NOT pulled** (see below), so
  no `--cull` anywhere and no idealista listing was delisted by absence. **Algarve:** 367 cards
  (298 apartamento / 69 moradia) → +91 new, 279 updated; store 1633 → **1724**; descriptions +78
  (727); liveness **+61 newly delisted** (1306 → 1367); photos +74. **RANKED 622** (178 under /
  194 fair / 220 over), **622/622 located**. **Norte:** 2227 cards across all 5 districts →
  +500 new, 1727 updated; store 5050 → **5550**; photos +419. **RANKED 2658** (772 under /
  1077 fair / 767 over), located 2648 (99.6%). Norte descriptions + liveness still deferred.
  - **Idealista blocked (verified, not inferred):** the Claude-in-Chrome extension returned
    `[]` on every retry for the whole session, and the in-app browser hits a DataDome CAPTCHA
    (`captcha-delivery` iframe, 0 cards) — never solved, per the runbook. The idealista half of
    both pools is therefore a pull stale; re-run step 1–2 for idealista once Chrome connects.
  - **Runbook bug found + fixed:** Imovirtual's `__NEXT_DATA__` `pagination.totalPages`
    **under-reports the real last page**. Paging to it and stopping — what RECOLLECT.md said to
    do — silently lost listings: one page past the reported end still returned new cards in every
    district (+13 Porto, +16 Braga, +15 Viana, +9 Vila Real, +4 Viseu, plus a whole extra Faro
    apartamento page). A short page isn't the end either (Faro moradia: 12 on p3, 37 on p4). The
    counts above use the new rule — **page until two consecutive pages add zero new rows** — now
    written into RECOLLECT.md.
  - **Transport note:** collection ran in the in-app browser, not the extension. Same
    `extract.js` + `quintalDownload` → `~/Downloads` → `--ingest` flow; page fetch + document
    swap replaced navigate-per-page. The local `receiver.py` is still unreachable from a portal
    page (fetch to `127.0.0.1:8231` blocked), so the download remains the transport.
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
