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
- No CAPTCHA wall on the portals (if one appears, **stop** and tell the owner — never solve it).

## 1 · Collect (per site: idealista, then imovirtual)
Extraction is versioned in [`src/quintal/collect/extract.js`](src/quintal/collect/extract.js) —
the per-site card selectors live there. **Per page**, inject that file's contents then call the
helper (page navigation clears `window`, so re-inject each page). `browser_batch` a
`navigate` + `javascript_tool` pair per page.

- **Idealista** — get URLs with `python -m quintal.collect.run --site idealista --print-urls --pages 6`
  (already the correct filtered format `…/com-preco-max_1500,t2,t3,t4-t5/…pagina-N`). 6 pages ≈ 180 cards.
  - Page 1: eval `<extract.js>` then `quintalReset('idealista'); quintalExtract('idealista')`.
  - Pages 2–6: eval `<extract.js>` then `quintalExtract('idealista')`. Watch the `total` climb.
- **Imovirtual** — the CLI URL is wrong (it drops comma-joined types), so use these two searches
  **separately** (`&page=N`), paging until `total` stops growing (apt ≈ 9 pages/~237, moradia ≈ 5/~46):
  - apt:     `https://www.imovirtual.com/pt/resultados/arrendar/apartamento/faro?priceMax=1500&roomsNumber=%5BTWO%2CTHREE%2CFOUR%5D&page=N`
  - moradia: `https://www.imovirtual.com/pt/resultados/arrendar/moradia/faro?priceMax=1500&roomsNumber=%5BTWO%2CTHREE%2CFOUR%5D&page=N`
  - Page 1 of the apt run: `quintalReset('imovirtual')` first; moradia pages just `quintalExtract('imovirtual')` (same `q_imv` key → apt+moradia accumulate together).

## 2 · Download + ingest (per site)
Chrome blocks a 2nd auto-download in the **same** tab — download from a **fresh same-origin tab**:
open a new tab → navigate to the site → eval `<extract.js>` → `quintalDownload('idealista')`
(or `'imovirtual'`) → it saves `~/Downloads/quintal_<site>.json`. Then:
```
python -m quintal.collect.run --site idealista  --ingest ~/Downloads/quintal_idealista.json
python -m quintal.collect.run --site imovirtual --ingest ~/Downloads/quintal_imovirtual.json
```
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
- Check the ranked count and band spread look sane (roughly balanced under/fair/over, not all-one).
- Spot-check `git show origin/deploy:data/listings.jsonl | wc -l` grew and the top listings look right.
- **Append a short dated entry to `STATUS.md`** with the run's numbers (store total, new/updated,
  delisted, ranked). Commit docs. Data is gitignored on `main` — only the `deploy` branch carries it.

## Gotchas (all learned the hard way)
- Idealista detail pages 403 server-side (DataDome) — thumbnails come from the captured card
  `image_url`, not a detail fetch. Older records without a captured image stay thumbnail-less.
- Imovirtual pagination clamps past the last page (repeats) — stop when `total` plateaus.
- The JS `javascript_tool` return caps ~1 KB and the browser tool blocks returning query-string
  URLs — that's why extraction accumulates to `localStorage` and returns only counts.
