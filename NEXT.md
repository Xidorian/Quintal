# Next — Quintal

**Now:** maintenance mode — the weekly re-collection is the standing job, and it now starts by
reading the 👎 notes (step 0 of RECOLLECT.md). Both pools are live; the Norte tail below is
the only unfinished build work.

## ▶ Shipped 2026-09-30 — one thing left to eyeball
- [x] **Published.** QT-053/054/055/056 are on `deploy` (snapshot `d325b65` on `0b9f1c0`),
      so Malia has the short-term fix, the house/apartamento fix and the working "why".
- [ ] **Open the hosted app and confirm the pool sizes:** Algarve **534**, Norte **2064**
      (down from 646 / 2188 — that drop is the short-term purge, not data loss). The deploy
      URL is not recorded in this repo; it is the Streamlit Cloud app on branch `deploy`.
- [ ] **Tell Malia the 👎 button changed** — Pass and Hide are now one "🙈 Not for us", and it
      asks why *in place* instead of hiding the card. Her older notes are unaffected.

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
- [x] **QT-055 (2026-09-30): the reason ask was unreachable.** A pass dropped the card from the
      default view on the same click, so the follow-up "＋ Add a reason" button only existed
      behind the "Show 👎" toggle — which is why the log stayed empty. One dismiss button now,
      and the card holds its place with the reason ask attached. Pass and Hide were also
      duplicates (`hidden` is read by nothing but the app's own filter), so half the dismissals
      recorded nothing; Hide is gone, old hidden ids kept behind "Show previously hidden".
- [ ] **Add `QUINTAL_GIST_ID` + `QUINTAL_GITHUB_TOKEN` to the local `.env`** — until then the
      feedback CLI reads the local prefs file, not Malia's live notes. (Token already exists in
      Streamlit secrets; needs copying locally. The CLI names the store it read, so this is
      visible, not silent.)

## ▶ From Malia's 2026-09-30 report
- [x] QT-053 short-term leak (one platform, 18% of the Algarve pool), QT-054 property-type
      mislabel (201 → 1), QT-055 the unreachable "why". See STATUS.md.
- [ ] **Watch whether the short-term purge is now over-eager.** The syndication-title rule was
      187/187 precise on the pool it was built from, which is exactly the sample that can't
      show its own blind spot. If Malia reports a *good* listing vanishing, `data/blocklist.json`
      names the rule that took it.
- [ ] **Raise the priority of the deferred imovirtual descriptions backfill for Norte.** With
      4353 Norte cards carrying no description, every text-based screen and every yard/pets
      derivation there is running on titles alone. QT-053 worked around it with a title rule;
      the next leak may not have one.

## ▶ From the 2026-09-26 pull
- [x] Both pools pulled complete on both sites (every district verified against its own header).
- [x] QT-050: imovirtual nulled `address.city`/`address.province`, so every card lost its
      freguesia and geocoded to a concelho centroid (wrecks the beach axis). `extract.js` now
      reads parish/council/district from `reverseGeocoding`. See STATUS.md.
- [x] Norte liveness run for the first time — 1899 dead listings purged.
- [x] **`extract.js` gate built (2026-09-26).** `tests/extract_harness.mjs` runs the real
      extract.js in jsdom over real captured fixtures; `tests/test_extract_js.py` asserts the
      rows and pushes them through the Python adapters (cross-surface check on one shared
      input). 8 tests, **both regressions planted and proved red**. 175 tests green.
- [x] **Collection-time selector check + cull guard built (QT-052).** `quintalExtract` reports
      `expected` (selector-independent link count) and `suspect`, which distinguishes a moved
      card selector from the end of pagination; `cull_absent` refuses to cull a pull that
      re-surfaced <30% of live listings (`--force-cull` overrides). Both alarms proved.
- [ ] **Fixtures are still a snapshot.** The `suspect` flag catches a portal moving its card
      selector *during a pull*, but the fixtures themselves only catch our own regressions —
      a changed *field* selector (price, area, location) that still matches cards stays silent
      in both. Re-capture when a pull looks wrong (`tests/fixtures/extract/README.md`). A
      field-level ingest sanity check (warn when >X% of a pull is missing price or location)
      would close that last gap cheaply.
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
