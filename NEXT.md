# Next — Quintal

**Now:** Norte expansion in progress (Porto + Douro + Minho, separate pool). Pull is done
(2828 ranked); the geography/greenery layer is the active build. Weekly Algarve
re-collection continues alongside.

## ▶ Norte expansion — active build
- [x] Wire Norte regions into both collectors + fix district-agnostic parsing (QT-038).
- [x] First Norte pull → `data/listings-norte.jsonl` (3882 raw → 2828 ranked).
- [ ] **Region-parameterise `enrich.py`** — bbox + geocode suffix per region (it's
      Algarve-hardcoded). Blocks all Norte geo.
- [ ] **`green_walk` enricher + score axis** — walk-minutes to nearest green space
      (park/forest/nature-reserve/trail); generalise the beach axis to river beaches (water).
- [ ] Reverse-geocode concelho during enrich (fixes Idealista Norte freguesia-level concelhos).
- [ ] Filter the Norte pool to ≥2 beds (632 T1s leaked past portal filters).
- [ ] Norte maintenance passes (descriptions/photos/liveness on the norte store + sidecars).
- [ ] App pool-switching (Algarve ↔ Norte) + publish the Norte pool.

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
