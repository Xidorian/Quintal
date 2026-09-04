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
- [ ] Imovirtual **descriptions** (yard/pets from detail text) + **liveness** for the norte
      store — deferred (1400+ fetches; liveness moot on a fresh pull).
- [x] Fold Norte into the weekly re-collection runbook (done via the Gotchas Norte block;
      exercised end-to-end on 2026-08-22 and 2026-08-31).

## ▶ Standing routine — weekly re-collection (every Monday through 2026-10-26)
Pool decays ~13% / 11 days. Browser-session based, so a **new interactive session drives
it** — full step-by-step in **[RECOLLECT.md](RECOLLECT.md)**. After each pull, run the
maintenance passes (descriptions, liveness, photos) and `scripts/publish.sh` →
auto-redeploy. Remaining Mondays: 07-27, 08-03, 08-10, 08-17, 08-24, 08-31, 09-07, 09-14,
09-21, 09-28, 10-05, 10-12, 10-19, 10-26. Reassess after October.

## ▶ Feedback loop (QT-044, shipped 2026-08-25) — one thing left
- [x] 👎 asks why (reason + note), logged in the shared prefs store; report / block / resolve CLI.
- [ ] **Add `QUINTAL_GIST_ID` + `QUINTAL_GITHUB_TOKEN` to the local `.env`** — until then the
      feedback CLI reads the local prefs file, not Malia's live notes. (Token already exists in
      Streamlit secrets; needs copying locally. The CLI names the store it read, so this is
      visible, not silent.)

## ▶ From the 2026-09-04 pull
- [x] Both pools pulled complete on both sites (each district verified against its own header).
- [x] QT-049: inline CSS in imovirtual's price cell was parsing as the rent (13 listings at
      €0.63). Fixed in `extract.js` (`txt()` strips nested `<style>`) + `_rent_only`.
- [ ] **Fold the new transport into RECOLLECT.md.** Downloads now trip Chrome's multiple-download
      prompt (a Save dialog the owner has to dismiss). This run moved the rows out as
      **gzip+base64 chunks via `get_page_text`** instead — no dialogs, and it retires the
      "stale file in ~/Downloads" hazard that steps 2 and the 2026-08-22 incident are built around.
      Steps 1–2 of the runbook still describe the download flow.
- [ ] Norte **descriptions + liveness** remain deferred (unchanged gap — see below).

## ▶ From the 2026-08-31 pull
- [x] Idealista pulled for both pools (541 Algarve / 1770 Norte, both to plateau, both culled).
- [x] QT-047: the cull now writes to its store's own delisted sidecar; 1012 undelisted dead
      Norte listings cleared. See STATUS.md.
- [ ] **Norte still has no `descriptions-norte.json` or liveness probe** — the same class of gap
      QT-047 exposed. Norte yard/pets derive from titles alone, and its only liveness path is the
      idealista cull (imovirtual dead listings there are never detected). Worth closing next.

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
