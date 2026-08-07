# Next — Quintal

**Now:** Norte expansion in progress (Porto + Douro + Minho, separate pool). Pull is done
(2828 ranked); the geography/greenery layer is the active build. Weekly Algarve
re-collection continues alongside.

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
- [ ] Fold Norte into the weekly re-collection runbook (RECOLLECT.md is Algarve-only).

## ▶ Standing routine — weekly re-collection (every Monday through 2026-10-26)
Pool decays ~13% / 11 days. Browser-session based, so a **new interactive session drives
it** — full step-by-step in **[RECOLLECT.md](RECOLLECT.md)**. After each pull, run the
maintenance passes (descriptions, liveness, photos) and `scripts/publish.sh` →
auto-redeploy. Remaining Mondays: 07-27, 08-03, 08-10, 08-17, 08-24, 08-31, 09-07, 09-14,
09-21, 09-28, 10-05, 10-12, 10-19, 10-26. Reassess after October.

## Soon (do when convenient)
- [ ] Discover the working Idealista `com-preco-max_…` filter path for every case (some
      still soft-404 → currently price/beds filtered post-collection as a fallback).
- [ ] Idealista detail-page enrichment (descriptions + liveness) via the logged-in browser
      session — headless 403s (DataDome), so it needs the same Chrome flow as collection.

## Later / maybe (deferred, not scheduled)
- [ ] **AI review layer (Phase 5)** — opt-in local Ollama pass that re-verifies
      keyword-derived features and drafts a plain-language "why this valuation". Layers on
      top of the deterministic pipeline; never the primary path.
- [ ] More sites (Casa Sapo / BPI) — each is one new adapter file.
- [ ] Saved-search alerts when a 🟢 high-match listing appears.

See **[ROADMAP.md](ROADMAP.md)** for phases and longer-term direction.
