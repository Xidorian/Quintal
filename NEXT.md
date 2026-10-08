# Next — Quintal

**Now:** maintenance mode — the weekly re-collection is the standing job, and it now starts by
reading the 👎 notes (step 0 of RECOLLECT.md). Both pools are live; the Norte tail below is
the only unfinished build work.

> 🛑 **Skip the 2026-10-05 re-collection — Alexander's call, 2026-10-04.** Everything that
> run would have delivered is already live: the 38-listing block was published the same day
> (snapshot `8c7f1ee`), so the hosted app is current at Algarve **528** / Norte **2058**.
> Nothing is waiting on a publish.
>
> The cost of skipping is pool freshness, not correctness — listings decay ~13% per 11 days,
> and the last pull was 09-26, so by 10-12 the pool is ~2.5 weeks stale. That is the thing to
> weigh when deciding whether 10-12 also slips. *(If the intent was only "don't publish
> again tomorrow" rather than "skip the run", the collect + maintenance passes are still
> worth doing — just stop before `scripts/publish.sh`.)*

## ▶ QT-058 — the dismiss button becomes the instrument (started 2026-10-08)
Malia does the bulk of the searching, so the 👎 *is* the data collection. Three tiers, by
how much effort she feels like spending. See STATUS.md for the numbers behind this.
- [x] **Tier 1 — one click, zero decisions.** A bare dismiss always logs an `unspecified`
      receipt with the listing snapshot. Was silently discarding 43 of 88 dismissals.
- [x] **Backfill run on both pools, 2026-10-08** — 68 Algarve + 7 Norte written to the
      shared Gist; store 45 → 120 entries, zero dismissals left without one. The 75 are
      `unspecified` and unsigned by design (date and author were never recorded).
- [x] **Tier 2 — one-tap reason pills.** Five primary (her measured usage), seven behind
      "Something else…", `PILLS_MORE` derived from `PICKABLE` so none can go missing.
- [x] **Tier 3 — free text behind "Something else…".** Verified saving `reason="other"`
      with the note intact. Still expect her to use it rarely; the pills carry the load.
- [ ] **Check in a week whether the pills actually moved the numbers.** The thing to watch
      is the `unspecified` share of *new* entries (anything after 2026-10-08) — if it stays
      high, the pill row is still too much friction and the next lever is inference, not UI.
- [x] **Rules module + `rules test`** — `src/quintal/rules.py`, 15 tests. Marks
      `pets`/`yard`/`bathtub`/`suspected_short_term`; provenance required; `RULES` ships
      empty. `python -m quintal.rules test --attribute … --pattern …` prints the collateral
      count and sample lines before anything is committed.
- [ ] **`feedback inspect`** — the remaining half: one view of each dismissal with its note
      *and* the text the detector saw, so a rule can be inferred without hand-digging.
- [ ] **Rewrite RECOLLECT.md step 0** as the inference workflow: read the dismissals and
      their text, infer the rule, prove it, commit it — instead of reading a miner's output.
- [x] **Pets regex fix — done 2026-10-08.** Forward-order + "proibido" + English denial
      patterns, and conditionals ("sem prévia autorização") now read `unknown` instead of
      `yes`. **91 verdicts changed across both pools** — 58 to `no` (43 from `yes`), 33 to
      `unknown`; all 91 hand-read, no false positives. See STATUS.md.
- [ ] **Re-run the pipeline and republish so Malia gets it.** The fix only reaches her
      through a publish; until then the hosted app still shows the 43 wrongly-permissive
      listings. Fold into the 10-12 pull rather than publishing twice.
- [ ] **Short-term has no text to match on.** The 15 still-slipping seasonal listings are
      idealista cards with no description. No rule can reach them; the only lever is
      capturing more from the search card (platform name / minimum stay in days). Unverified
      whether those fields are on the card — check the fixtures before assuming.

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
- [ ] Imovirtual **descriptions** for the norte store — still deferred (1400+ fetches).
      Norte derives from titles + short card previews (median 68 chars), not from titles
      alone as this said before 2026-10-08 — but not from full descriptions either.
- [x] Fold Norte into the weekly re-collection runbook (done via the Gotchas Norte block;
      exercised end-to-end on 2026-08-22 and 2026-08-31).

## ▶ Standing routine — weekly re-collection (every Monday through 2026-10-26)
Pool decays ~13% / 11 days. Browser-session based, so a **new interactive session drives
it** — full step-by-step in **[RECOLLECT.md](RECOLLECT.md)**. After each pull, run the
maintenance passes (descriptions, liveness, photos) and `scripts/publish.sh` →
auto-redeploy. **09-07, 09-14 and 09-21 were missed** — the 09-26 run covered 22 days of
churn in one go (145 + 691 culled, 121 + 1899 probed dead). **10-05 is deliberately skipped**
(see the banner at the top). Remaining Mondays: ~~10-05~~, 10-12, 10-19, 10-26.
Reassess after October.

## ▶ Feedback loop (QT-044, shipped 2026-08-25) — wired up
- [x] 👎 asks why (reason + note), logged in the shared prefs store; report / block / resolve CLI.
- [x] **QT-055 (2026-09-30): the reason ask was unreachable.** A pass dropped the card from the
      default view on the same click, so the follow-up "＋ Add a reason" button only existed
      behind the "Show 👎" toggle. One dismiss button now,
      and the card holds its place with the reason ask attached. Pass and Hide were also
      duplicates (`hidden` is read by nothing but the app's own filter), so half the dismissals
      recorded nothing; Hide is gone, old hidden ids kept behind "Show previously hidden".
- [x] **`QUINTAL_GIST_ID` + `QUINTAL_GITHUB_TOKEN` are in the local `.env` (2026-10-04).**
      `feedback report` now prints *"store: shared Gist (both searchers)"* — check that line
      before acting on a report; the local-file fallback looks identical otherwise. Both keys
      are documented in `.env.example`.
- [x] **What the shared log turned out to hold: 45 open notes, all from Malia, and not one
      with free text.** Reason codes only. That corrects the QT-055 write-up, which said the
      log "stayed empty" — it wasn't empty, it was *half* empty, and the missing half is the
      half that matters. The dropdown survived because picking it was the click that passed
      the card; the note needed a second visit the vanishing card denied. Post-QT-055 the
      note is in the same panel, so this should start filling — worth re-checking in a week.
- [ ] **Don't add any pattern `feedback report` currently proposes.** With no quoted text to
      anchor on, the miner is reading 300-char card previews of ordinary prose: its top
      candidates are "a casa e", "na rua de", "lavar loica", each of which would purge 40–50
      real listings. The candidates become useful only once notes carry quotes.
- [x] **`feedback block` run on both pools, 2026-10-04 — 38 listings.** Algarve 17 (15
      seasonal, 1 wrong-area, 1 not-a-rental; blocklist 811 → 828), Norte 21 (14 dead links,
      7 seasonal; 439 → 460). Each blocklist entry carries its provenance
      (`feedback:gone — … (Malia, <date>)`). The notes are stamped `blocked_at` but stay
      **open** by design — blocked is not the same as acted-on, so they keep showing in the
      report until someone runs `feedback resolve`. **Published 2026-10-04** (`8c7f1ee`).
- [ ] **Norte's misses are mostly a liveness problem, not a screening one** — 14 of its 21
      were "already rented / dead link". Blocking by id only catches the ones Malia happened
      to click; a liveness run is the general fix and its first pass (2026-09-26) found 1899
      dead listings. Run it as part of the weekly routine rather than blocking by hand again.
- [ ] **The 15 still-slipping seasonal misses are not a pattern gap — they are a text gap.**
      Every one still in the store has only a ≤400-char card preview and *zero* have a full
      description (all idealista, whose detail pages are DataDome-blocked). The screener never
      saw the line that gives them away. Two ways out, neither a new regex: Malia quoting the
      line in her note, or `python -m quintal.feedback block --pool algarve` to hard-block
      them by id — which is exactly what `block` exists for when no pattern can reach them.

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
      `descriptions-norte.json` still does not exist. **Not "titles alone", though** — the
      Norte store carries 8192 card previews in `description_raw` (median 68 chars), which
      `normalize` does fold; what is missing is the fuller detail-page text (2026-10-08).

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
