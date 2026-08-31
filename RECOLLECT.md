# Weekly re-collection runbook

**Purpose:** keep Malia's pool fresh. Listings decay fast (~13% of Imovirtual went 410-Gone
in 11 days), so re-collect + republish weekly. This is browser-session based (needs the
owner's logged-in Chrome), so it can't run headless — a **new interactive session drives it**.

**Cadence:** every **Monday** through end of October 2026, then reassess. Remaining Mondays:
`2026-07-20, 07-27, 08-03, 08-10, 08-17, 08-24, 08-31, 09-07, 09-14, 09-21, 09-28, 10-05,
10-12, 10-19, 10-26`. (After 10-26, decide whether to continue — likely moved to the Algarve by then.)

**A fresh session should:** read `STATUS.md`/`NEXT.md`/`CLAUDE.md` first, confirm the prereqs,
then work top to bottom here. Everything is resumable — a mid-run interruption re-runs safely.

---

## Prereqs
- **Logged-in Chrome connected** (`mcp__Claude_in_Chrome__list_connected_browsers` returns a browser).
- `.env` present with `OPENROUTESERVICE_API_KEY` (routed walk-times). `. .venv/bin/activate` first.
- **`QUINTAL_GIST_ID` + `QUINTAL_GITHUB_TOKEN` in `.env`** so step 0 reads the *shared* 👎 notes.
  Without them the feedback CLI reads the local `data/preferences.json` — nobody's live log — and
  says so in its header. Check that header; don't harden off the wrong store.
- No CAPTCHA wall on the portals (if one appears, **stop** and tell the owner — never solve it).

## 0 · Read the 👎 notes and harden (before pulling anything)
Every 👎 in the app can carry a reason + note. This is where they get spent.
```
python -m quintal.feedback report --pool algarve     # and --pool norte
```
- **Filter misses** are listings the pool should never have shown. Each names the module that
  should have caught it. Entries marked `✗ still slips` are live bugs; `✓ now caught` means an
  earlier hardening already covers it (nothing to do).
- **Candidate patterns** are mined from the still-slipping *seasonal* ones, ★-marked when the
  searcher quoted the words themselves. Each shows **`also purges`** — how many other pool
  listings it would drop. **Read that number before adding anything**: a careless phrase
  ("moradia") would purge the pool. Add the safe ones to `SHORT_TERM_PATTERNS` in
  [`src/quintal/screening.py`](src/quintal/screening.py), then re-run the report to confirm they
  flip to `✓ now caught`.
- **Taste** notes never touch the screener — they inform scoring weights / area sentiment.
```
python -m quintal.feedback block --pool algarve      # hard-block the misses by id (--dry-run first)
python -m quintal.feedback resolve --all --pool algarve --note "QT-xxx: added <pattern>"
```
`block` is the specific fix (this listing, never again), a pattern is the general one — do both.
Only `resolve` what you actually acted on; unresolved notes resurface next week on purpose.

## 1 · Collect (per site: idealista, then imovirtual)
Extraction is versioned in [`src/quintal/collect/extract.js`](src/quintal/collect/extract.js) —
the per-site card selectors live there. **Per page**, inject that file's contents then call the
helper (page navigation clears `window`, so re-inject each page). `browser_batch` a
`navigate` + `javascript_tool` pair per page.

- **Idealista** — get URLs with `python -m quintal.collect.run --site idealista --print-urls --pages 18`
  (already the correct filtered format `…/com-preco-max_1500,t2,t3,t4-t5/…pagina-N`; ~30 cards/page).
  The full Faro search is **~16 pages / ~456 listings** — the old 6-page cap silently missed ~60%.
  - Page 1: eval `<extract.js>` then `quintalReset('idealista'); quintalExtract('idealista')`.
  - Later pages: eval `<extract.js>` then `quintalExtract('idealista')`. **Page until `total`
    plateaus** — the results page prints its own count in the `<h1>` (e.g. "456 casas"); pull
    until `total` matches it (the last page returns <30). Completeness is load-bearing: the
    `--cull` in step 2 delists any idealista listing absent from this pull, so a short pull would
    wrongly cull live listings on the pages you skipped.
- **Imovirtual** — the CLI URL is wrong (it drops comma-joined types), so use these two searches
  **separately** (`&page=N`), paging until **two consecutive pages add zero new rows** — not until
  the reported `totalPages`, which under-reports (see Gotchas). 2026-08-31: apt 10 pages, moradia 3:
  - apt:     `https://www.imovirtual.com/pt/resultados/arrendar/apartamento/faro?priceMax=1500&roomsNumber=%5BTWO%2CTHREE%2CFOUR%5D&page=N`
  - moradia: `https://www.imovirtual.com/pt/resultados/arrendar/moradia/faro?priceMax=1500&roomsNumber=%5BTWO%2CTHREE%2CFOUR%5D&page=N`
  - Page 1 of the apt run: `quintalReset('imovirtual')` first; moradia pages just `quintalExtract('imovirtual')` (same `q_imv` key → apt+moradia accumulate together).

## 2 · Download + ingest (per site)
**FIRST: `rm ~/Downloads/quintal_*.json` BEFORE downloading.** If a stale file with that name
exists, Chrome silently saves the new one as `quintal_<site> (1).json` and you'll ingest the
*old* file — which, with `--cull`, wrongly delists the whole current pull. (This bit us
2026-08-22: an old Norte download polluted the Algarve store; recovered by removing the bad
rows by URL and re-ingesting.) Chrome also blocks a 2nd auto-download in the **same** tab —
download from a **fresh same-origin tab**: open a new tab → navigate to the site → eval
`<extract.js>` → `quintalDownload('idealista')` (or `'imovirtual'`) → saves
`~/Downloads/quintal_<site>.json`. **Then verify the row count matches the browser's reported
total before ingesting:**
```
python -c "import json;print(len(json.load(open('/home/xidorian/Downloads/quintal_idealista.json'))))"  # == the plateau total
python -m quintal.collect.run --site idealista  --ingest ~/Downloads/quintal_idealista.json --cull
python -m quintal.collect.run --site imovirtual --ingest ~/Downloads/quintal_imovirtual.json
```
`--cull` on idealista is its **only** liveness path (idealista IP-rate-limits detail-page probes,
so `quintal.liveness` skips it) — it delists any idealista listing in the store that this pull
didn't re-surface. **Only pass `--cull` when the pull is complete** (step 1 paged to plateau);
it's reversible, so a listing that reappears next week is automatically un-culled. Imovirtual keeps
its probe-based liveness (step 3), so no `--cull` there.

Sanity: no absurd prices (the Imovirtual `€/m²` concat bug is handled in the adapter; if a new
one appears, check `imovirtual._rent_only`). `rm ~/Downloads/quintal_*.json` when done.

## 3 · Maintenance passes (resumable; each skips already-done work)
```
python -m quintal.descriptions      # enrich new Imovirtual owner-text (yard/pets)
python -m quintal.liveness          # mark newly-delisted (410/404) → data/delisted.json
python -m quintal.photos            # download new thumbnails (captured image_url + fallback)
```
Each is a few minutes; run foreground (background tasks get killed by session resets).

## 4 · Refresh geo + routes, then publish
```
set -a; source .env; set +a
python -c "from quintal.pipeline import run; L=run('data/listings.jsonl', enrich=True); print(len(L),'ranked')"
scripts/publish.sh                  # data snapshot → deploy branch → Streamlit redeploys
```
The enrich run regenerates `data/geo.json` and caches any new ORS routes; `publish.sh` ships
`listings.jsonl` + all sidecars + photos. The app needs no ORS key (routes read from the cache).

## 5 · Verify + record
- **Re-run `python -m quintal.feedback report`** for each pool — the notes you hardened against
  should now read `✓ now caught`. Record any pattern you added in the STATUS.md entry.
- Check the ranked count and band spread look sane (roughly balanced under/fair/over, not all-one).
- Spot-check `git show origin/deploy:data/listings.jsonl | wc -l` grew and the top listings look right.
- **Append a short dated entry to `STATUS.md`** with the run's numbers (store total, new/updated,
  delisted, ranked). Commit docs. Data is gitignored on `main` — only the `deploy` branch carries it.

## Gotchas (all learned the hard way)
- Idealista detail pages 403 server-side (DataDome) — thumbnails come from the captured card
  `image_url`, not a detail fetch. Older records without a captured image stay thumbnail-less.
- **Imovirtual under-reports its own page count (2026-08-31).** `__NEXT_DATA__`'s
  `searchAds.pagination.totalPages` is *not* the end: paging one past it still returned a full
  page of new cards on every district we checked (+13 Porto, +16 Braga, +15 Viana, +9 Vila Real,
  +4 Viseu, and a whole extra Faro apartamento page past its reported 9). A short page isn't the
  end either — Faro moradia gave 12 on p3 then 37 on p4. **Stop on evidence, not on the reported
  count: keep paging until two consecutive pages add zero new rows** (`gain === 0` twice). It
  clamps and repeats past the real end, so over-paging is free — under-paging silently loses
  listings.
- The JS `javascript_tool` return caps ~1 KB and the browser tool blocks returning query-string
  URLs — that's why extraction accumulates to `localStorage` and returns only counts.
- **Idealista render races (2026-08-22):** a `browser_batch` `navigate→eval` pair can run the
  eval before the page's cards render → `page:0` (a *missed* page, not end-of-list). Watch every
  page's count; re-fetch any `page:0` with a **separate** navigate then eval (gives render time).
  Worse under load — **don't run the maintenance passes while collecting** (pause them first).
  Imovirtual is server-rendered → no races.
- **Norte pool** is a separate store + sidecars (`--region {porto,braga,viana-do-castelo,vila-real,
  viseu}`, `--store data/listings-norte.jsonl`, and its `-norte` sidecars). Idealista: page each of
  the 5 districts to plateau, one accumulated `q_ide`, one `--cull` ingest. Imovirtual: apt+moradia
  × 5 districts. Enrich with `region='norte', min_beds=2` and **no ORS key** (straight-line —
  2431×2 routes blow the free 2000/day quota). Its concelhos come clean from imovirtual
  `__NEXT_DATA__` + a reverse-geocode pass; Algarve's ORS routes stay cached.
