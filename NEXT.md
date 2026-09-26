# Next — Quintal

**Now:** maintenance mode — the weekly re-collection is the standing job, and it now starts by
reading the 👎 notes (step 0 of RECOLLECT.md). Both pools are live; the Norte tail below is
the only unfinished build work.

## ▶ Norte expansion — shipped (2026-08-06), tail to finish
- [x] Regions wired + district-agnostic parsing (QT-038); first pull → 2188 ranked.
- [x] Region-parameterised `enrich.py`; `green_walk` axis + Norte weights (QT-039).
- [x] ≥2-bed filter; geocode junk-locality guard; app pool-switch + publish (QT-040/041).
- [x] Photos backfilled + republished; concelhos fixed by reverse-geocoding (QT-042,
      570+ junk → 18 unlocated tail).
- [ ] Routed (ORS) walk-times for Norte — skipped this pass (free-tier 2000/day < 2188×2);
      straight-line estimates for now. Route the top-N later, or a paid/self-hosted router.
- [x] **Liveness for the norte store — done 2026-09-26.** `quintal.liveness --input
      data/listings-norte.jsonl --path data/delisted-norte.json`; first run found **1899** dead
      listings the idealista cull could never see. Add it to the weekly routine.
- [ ] Imovirtual **descriptions** for the norte store — still deferred (1400+ fetches). Norte
      yard/pets still derive from titles alone.
- [x] Fold Norte into the weekly re-collection runbook (done via the Gotchas Norte block;
      exercised end-to-end on 2026-08-22 and 2026-08-31).

## ▶ Standing routine — weekly re-collection (every Monday through 2026-10-26)
Pool decays ~13% / 11 days. Browser-session based, so a **new interactive session drives
it** — full step-by-step in **[RECOLLECT.md](RECOLLECT.md)**. After each pull, run the
maintenance passes (descriptions, liveness, photos) and `scripts/publish.sh` →
auto-redeploy. **09-07, 09-14 and 09-21 were missed** — the 09-26 run covered 22 days of
churn in one go (145 + 691 culled, 121 + 1899 probed dead). Remaining Mondays: 09-28,
10-05, 10-12, 10-19, 10-26. Reassess after October.

## ▶ Feedback loop (QT-044, shipped 2026-08-25) — one thing left
- [x] 👎 asks why (reason + note), logged in the shared prefs store; report / block / resolve CLI.
- [ ] **Add `QUINTAL_GIST_ID` + `QUINTAL_GITHUB_TOKEN` to the local `.env`** — until then the
      feedback CLI reads the local prefs file, not Malia's live notes. (Token already exists in
      Streamlit secrets; needs copying locally. The CLI names the store it read, so this is
      visible, not silent.)

## ▶ From the 2026-09-26 pull
- [x] Both pools pulled complete on both sites (every district verified against its own header).
- [x] QT-050: imovirtual nulled `address.city`/`address.province`, so every card lost its
      freguesia and geocoded to a concelho centroid (wrecks the beach axis). `extract.js` now
      reads parish/council/district from `reverseGeocoding`. See STATUS.md.
- [x] Norte liveness run for the first time — 1899 dead listings purged.
- [ ] **`extract.js` has no automated gate.** QT-049 and QT-050 were both live-found data
      corruptions in the same file, and every selector in it is validated by eye. A node-based
      harness (export the pure helpers — `txt`, `imvLocation`, `row` — and run them over saved
      fixture HTML/`__NEXT_DATA__` blobs) would have caught QT-050 on the first pull. Worth
      building before the next portal change.
- [x] **RECOLLECT.md corrected in the same session** — transport truth (the gzip+base64
      `get_page_text` trick is in-app-browser-only, not byte-exact on the extension), `rm` before
      *every* download, a fresh tab per download, the Norte liveness/photos commands, and the
      45s-CDP-timeout-vs-auto-pager note.

## ▶ From the 2026-09-04 pull
- [x] Both pools pulled complete on both sites (each district verified against its own header).
- [x] QT-049: inline CSS in imovirtual's price cell was parsing as the rent (13 listings at
      €0.63). Fixed in `extract.js` (`txt()` strips nested `<style>`) + `_rent_only`.
- [x] ~~Fold the gzip+base64 transport into RECOLLECT.md~~ — **superseded 2026-09-26**: that
      transport is in-app-browser-only and is not byte-exact on the Chrome extension. The download
      flow stands; see the 09-26 block above for the corrections it does need.
- [x] Norte **liveness** closed 2026-09-26; **descriptions** still deferred (see below).

## ▶ From the 2026-08-31 pull
- [x] Idealista pulled for both pools (541 Algarve / 1770 Norte, both to plateau, both culled).
- [x] QT-047: the cull now writes to its store's own delisted sidecar; 1012 undelisted dead
      Norte listings cleared. See STATUS.md.
- [x] **Liveness half closed 2026-09-26** (1899 dead listings found on the first probe).
      `descriptions-norte.json` still does not exist — Norte yard/pets derive from titles alone.

## Soon (do when convenient)
- [ ] Discover the working Idealista `com-preco-max_…` filter path for every case (some
      still soft-404 → currently price/beds filtered post-collection as a fallback).
- [ ] Idealista detail-page enrichment (descriptions + liveness) via the logged-in browser
      session — headless 403s (DataDome), so it needs the same Chrome flow as collection.
- [ ] `use_container_width` is deprecated in Streamlit (removal announced for after 2025-12-31,
      still working on 1.58) — swap the app's buttons/images/popovers to `width="stretch"`
      before a Cloud upgrade breaks Malia's view.

## Later / maybe (deferred, not scheduled)
- [ ] **AI review layer (Phase 5)** — opt-in local Ollama pass that re-verifies
      keyword-derived features and drafts a plain-language "why this valuation". Layers on
      top of the deterministic pipeline; never the primary path.
- [ ] More sites (Casa Sapo / BPI) — each is one new adapter file.
- [ ] Saved-search alerts when a 🟢 high-match listing appears.

See **[ROADMAP.md](ROADMAP.md)** for phases and longer-term direction.
