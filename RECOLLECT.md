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

## 0 · Read the dismissals and write the rules (before pulling anything)
Every 👎 records something, even when the searcher picked nothing — a bare dismiss logs an
`unspecified` receipt with the listing's snapshot. **You** are the inference step. There is a
pattern miner and it is *not* the path: with no quoted text to anchor on it proposes
`a casa e` (47 collateral) and `na rua de` (50). Reading five listings beats it outright.

**First, check the store line.** Every command prints it. `store: shared Gist (both
searchers)` is the real log; `local file` is nobody's notes. Harden off the wrong one and
you have hardened off nothing.

### 0a · Read them
```
python -m quintal.feedback inspect --pool algarve                 # and --pool norte
python -m quintal.feedback inspect --pool algarve --reason unspecified --chars 0
```
Each dismissal comes with its note, its snapshot, **the text the detector actually read**,
whether the screener catches it, and what we derive for pets/yard/short-term. Three kinds:
- **Filter misses** (seasonal, gone, wrong area, not-a-rental, duplicate, bad data) — the
  pool should never have shown it. Each names the module at fault.
- **Unclassified** — dismissed with no reason given. No verdict to act on, so read the text
  and decide what they have in common. This is the biggest bucket and the whole reason the
  receipt exists.
- **Taste** (price, location, condition, no-yard, no-pets) — informs weights and area
  sentiment, never the screener.

`in_pool: false` means the listing is gone and only its snapshot survives — no text, so no
rule can come from it. Those are a liveness signal (step 3), not a screening one.

**Watch for the text simply not being there.** Idealista detail pages are DataDome-blocked,
so many rows are ~400-char card previews and the giveaway sits past the cut. `inspect`
prints the real character count for exactly this reason. No text ⇒ no pattern ⇒ go to 0d.

### 0b · Prove the pattern before you write it
```
python -m quintal.rules test --attribute pets --verdict no --pool norte \
    --pattern 'nao se admite anima'
```
It prints how many listings match, what we say about each today, how many the rule would
**change**, and sample lines with the match bracketed.

That exact command is worth running once, because of what it answers: *matches 1, would
change 0, 1 already agree*. The derivation already handles it, so **the rule would be dead
weight — do not add it.** `would change 0` always means that.

**Read the samples, not just the count.** Two real near-misses from 2026-10-08: `anima` on
the Norte pool would change 29 listings including one reading *"animais de estimação
**bem vindos**"*, and a candidate of mine matched *"renda de caução cada mês"* — a
monthly-paid deposit, not a seasonal let. A large "would change" is not automatically wrong
— it may be a real structural tell — but you have to read enough samples to know which.

### 0c · Write it in the right place
Two sinks, and the choice is about blast radius, not convenience:

| | `src/quintal/rules.py` | `src/quintal/screening.py` |
|---|---|---|
| what it does | **marks** an attribute | **purges** into the blocklist |
| recoverable | yes — untick a filter | no, you notice by absence |
| use for | one listing's own phrasing, species names, a refusal written oddly | a structural tell that generalises: AL number, month span, minimum stay in days |
| needs | `Rule(...)` with provenance | a phrase in `SHORT_TERM_PATTERNS` |

**Default to `rules.py`.** A rule is cheap to add and cheap to be wrong about. Reach for
`screening.py` only when the tell is structural and you have read the collateral.

A rule carries its origin — `source` is required and construction fails without it. The
shape (**illustrative — see the note below, this one is not needed**):
```python
Rule(
    id="pets-example-001",
    attribute="pets",            # pets | yard | bathtub | short_term
    verdict="no",                # short_term may only assert "yes"
    pattern=r"so inquilinos sem bichos",
    source="feedback entry d4bf835622 — Malia, 2026-08-31",
    added="2026-10-08",
    note="colloquial 'bichos'; the built-in lists are all 'animais'/'caes'",
)
```
Then `pytest` (a bad pattern fails at import, not mid-pull) and
`python -m quintal.rules list` to confirm it loaded.

> **`RULES` ships empty, and as of 2026-10-08 nothing in either pool needs one.** Every
> pets phrasing in both stores is covered by the derivation after the QT-058 fix — checked
> with `rules test`. That is the normal state: `rules.py` is for a phrasing that shows up
> *later* and is too idiosyncratic to be worth a built-in pattern. If you find yourself
> wanting several rules at once, that is a built-in gap — fix `normalize.py` instead.

### 0d · Block what no pattern can reach
```
python -m quintal.feedback block --pool algarve --dry-run   # then without --dry-run
```
For the ones with no text to match on, blocking by id is not a fallback — it is the right
tool. The 15 Algarve seasonal misses are in exactly this state.

It is **idempotent**: an already-blocked entry is skipped, so a dry run that says
`would block 0` while `report` shows misses marked `🔒 blocked` is correct, not broken —
the 38 from 2026-10-04 are already in the blocklists. Blocking stamps `blocked_at` but
leaves the note **open** on purpose: blocked is not the same as acted-on, so it keeps
appearing until someone runs `resolve`.

### 0e · Resolve only what you acted on
```
python -m quintal.feedback resolve --all --pool algarve --note "QT-xxx: added <rule id>"
```
Unresolved notes resurface next week on purpose. Resolving something you did not fix is how
a miss becomes invisible.

> **Pending candidate (filed 2026-10-08, not applied).** `_SEASONAL_SPAN` only covers
> *winter* lets (Sep–Dec → Mar–Jul), so a same-month window ("de 1 de setembro a 30 de
> setembro") and any *summer* span ("junho a setembro" — the actual holiday let) slip
> through. An any-month-to-any-month span matches 344 Algarve listings, 323 already caught,
> **21 new**. Read those 21 first, and make sure a full-year span ("janeiro a dezembro")
> cannot match — that is a long let.

## 1 · Collect (per site: idealista, then imovirtual)
Extraction is versioned in [`src/quintal/collect/extract.js`](src/quintal/collect/extract.js) —
the per-site card selectors live there. **Per page**, inject that file's contents then call the
helper (page navigation clears `window`, so re-inject each page). `browser_batch` a
`navigate` + `javascript_tool` pair per page.

**Watch `suspect` on every page.** `quintalExtract` returns
`{page, total, with_image, expected, suspect}`. `expected` is a selector-INDEPENDENT count of
the listings the page shows (unique detail-page links), which is what separates a moved card
selector from the genuine end of pagination — they otherwise look identical, both giving zero
cards:

| | `expected` | `page` | `suspect` | meaning |
|---|---|---|---|---|
| healthy page | >0 | ≈ expected | `none` | carry on |
| past the last page | 0 | 0 | `none` | plateau reached, stop |
| **card selector moved** | **>0** | **0** | **`no-cards`** | **STOP** — fix the selectors in `extract.js` |
| partial markup change | >0 | < expected/2 | `few-cards` | investigate before ingesting |

Anything but `none` means **stop, and never pass `--cull` on that pull** — a zero-card pull
reads as "everything is delisted". A render race also shows as `no-cards` (idealista only); re-fetch
that page with a separate navigate-then-eval before concluding the selector broke.

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
**FIRST: `rm ~/Downloads/quintal_*.json` BEFORE *every* download — not just the first.** If a
file with that name exists, Chrome silently saves the new one as `quintal_<site> (1).json` and
you'll ingest the *old* file — which, with `--cull`, wrongly delists the whole current pull.
(This bit us 2026-08-22: an old Norte download polluted the Algarve store. It bit again
2026-09-26, when a corrected imovirtual re-pull landed as `(1)` because only the *first*
download had been preceded by an `rm`.) Chrome also blocks a 2nd auto-download **per tab** —
so **every download needs its own brand-new tab**: open a new tab → navigate to the site → eval
`<extract.js>` → `quintalDownload('idealista')` (or `'imovirtual'`) → saves
`~/Downloads/quintal_<site>.json`. A download issued from a tab that already downloaded once
**silently never lands** — no error, no file (2026-09-26, Norte idealista). Always `ls` the file
and check its mtime before ingesting. **Then verify the row count matches the browser's reported
total before ingesting:**
```
python -c "import json;print(len(json.load(open('/home/xidorian/Downloads/quintal_idealista.json'))))"  # == the plateau total
python -m quintal.collect.run --site idealista  --ingest ~/Downloads/quintal_idealista.json --cull
python -m quintal.collect.run --site imovirtual --ingest ~/Downloads/quintal_imovirtual.json
```
`--cull` on idealista is its **only** liveness path (idealista IP-rate-limits detail-page probes,
so `quintal.liveness` skips it) — it delists any idealista listing in the store that this pull
didn't re-surface. **Only pass `--cull` when the pull is complete** (step 1 paged to plateau);
it's reversible, so a listing that reappears next week is automatically un-culled.

**The completeness contract is now machine-checked.** A cull requires the pull to re-surface at
least 30% of the site's currently-live store entries (`liveness.MIN_CULL_COVERAGE`); below that
it raises `CullRefused`, writes nothing, prints `CULL REFUSED …` and exits 1 — so a collapsed
pull can't quietly delist the pool. The preceding upsert is idempotent, so the fix is to re-page
and re-run the same command. Real churn is nowhere near the floor (the 22-day 2026-09-26 gap
came in at 62% and 74%). `--force-cull` overrides it, for a genuine mass-delisting only. Imovirtual keeps
its probe-based liveness (step 3), so no `--cull` there.

Sanity: no absurd prices (the Imovirtual `€/m²` concat bug is handled in the adapter; if a new
one appears, check `imovirtual._rent_only`). `rm ~/Downloads/quintal_*.json` when done.

## 3 · Maintenance passes (resumable; each skips already-done work)
```
python -m quintal.descriptions      # enrich new Imovirtual owner-text (yard/pets)
python -m quintal.liveness          # mark newly-delisted (410/404) → data/delisted.json
python -m quintal.photos            # download new thumbnails (captured image_url + fallback)
```
**Norte takes the same passes via `--input`** (its liveness was wrongly assumed impossible until
2026-09-26; the first probe found **1899** dead listings the idealista cull could never see):
```
python -m quintal.liveness --input data/listings-norte.jsonl --path data/delisted-norte.json
python -m quintal.photos   --input data/listings-norte.jsonl
```
(`descriptions` for Norte is still not wired — no `descriptions-norte.json` yet.)
Each is a few minutes — except the Norte liveness probe, which is ~30 min on a 8k store. Run
foreground, or background it and poll; don't let a session reset kill it mid-write.

## 4 · Refresh geo + routes, then publish
```
set -a; source .env; set +a
python -c "from quintal.pipeline import run; L=run('data/listings.jsonl', enrich=True); print(len(L),'ranked')"
scripts/publish.sh                  # data snapshot → deploy branch → Streamlit redeploys
```
The enrich run regenerates `data/geo.json` and caches any new ORS routes; `publish.sh` ships
`listings.jsonl` + all sidecars + photos. The app needs no ORS key (routes read from the cache).

## 5 · Verify + record
- **Re-check what you hardened**, per sink — they are verified differently:
  - a `screening.py` phrase: `python -m quintal.feedback report --pool <region>` — the notes
    you hardened against should flip from `✗ still slips` to `✓ now caught`.
  - a `rules.py` rule: `python -m quintal.feedback inspect --pool <region>` and read the
    `pets:`/`yard:`/`short_term:` line on the listings it was written for. A rule that fired
    shows its verdict there; `report`'s `✓ now caught` only ever reflects the screener, so it
    will *not* move for a rule and that is not a failure.
  - either way, `python -m quintal.rules list` should show what you added, with provenance.
  Record the rule id or pattern in the STATUS.md entry.
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
- **Getting the rows out: use the download, not `get_page_text` (settled 2026-09-26).** The
  2026-09-04 run moved rows as gzip+base64 chunks read back via `get_page_text`; that works in the
  *in-app* browser (which takes a `max_chars`) but **not via the Chrome extension**, whose
  `get_page_text` has no `max_chars`, truncates page text at 50,000 chars, and only spills to a
  file above a token threshold — so a 45k chunk comes back *inline*, where it cannot be
  reassembled byte-exact. `quintalDownload` was byte-exact all four times this run. Keep the
  download; just obey the `rm`-and-fresh-tab rules in step 2.
- **A long auto-pager outruns the 45s CDP timeout.** Paging a big district (Porto: ~30 imovirtual
  pages) exceeds `Runtime.evaluate`'s 45s limit and the tool reports a timeout — but **the page
  keeps running the loop**. Don't re-fire it (you'd double-run): poll
  `JSON.parse(localStorage.getItem('q_imv')).length` until it stops changing, and have the loop
  append per-search results to a `window.__qLog` you can read back afterwards.
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
