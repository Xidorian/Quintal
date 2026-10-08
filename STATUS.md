# Status — Quintal

**Live and in maintenance, plus an active Norte expansion (2026-08).** All five build
phases (collect → screen → enrich → value/score → interactive UI) are in place for the
Algarve; the backlog is drained and Malia uses the hosted app. **New direction:** the
search is expanding to **Porto + the Douro + the Minho** (Norte), optimising for
dog-walkable greenery/nature/quiet and river-beach proximity rather than ocean beaches —
kept as a **separate pool** (`data/listings-norte.jsonl`) so Algarve valuations stay clean.

## The dismiss button now records (2026-10-08, QT-058 tier 1)
**Half of every dismissal was being thrown away.** `Preferences.dislike()` logged an entry
only `if reason or note`, so a 👎 with no reason chosen added the id to a set and nothing
else — no date, no author, no snapshot of what the listing was. Measured against the shared
Gist: **88 dismissed listings, 45 with an entry, 43 with nothing**, plus **32 legacy `hidden`
ids**, all reasonless. **0 of the 45 entries carry free text** — all 45 are Malia's, and a
week after QT-055 made the note field reachable in place she still has not typed one. The
report's ★ ("the searcher quoted these words") marks nothing.

So the zero-effort click is the one that has to capture. A bare dismiss now always logs a
receipt: `reason="unspecified"`, with `by` + the listing snapshot (title, url, concelho,
price, pool, timestamp). The reason ask still upgrades it if she answers; un-passing still
retracts it. `unspecified` is a **third bucket** in the taxonomy — `Reason.bucket` is now
`miss | taste | unclassified`, with `screenable` derived from it — because filing a
reasonless 👎 under *taste* would read as "she just didn't like it", a verdict nobody gave.
`feedback report` grew an UNCLASSIFIED section that marks which dismissals are still in the
pool (so still readable) and which survive only as their snapshot.

`test_plain_dislike_still_toggles_and_logs_nothing` **asserted the old behaviour** — the data
loss was tested and documented. It is replaced by `test_plain_dislike_logs_an_unspecified_receipt`.

**All 75 lost dismissals are still recoverable** — every one was still in a pool store on
2026-10-08, so `feedback backfill` can rebuild its receipt from the stored title/text
(68 Algarve + 7 Norte, dry-run verified). It cannot rebuild *when* or *who* — neither was
ever written — so backfilled entries carry `backfilled_at` + `provenance` and leave `by`
empty rather than guessing. **Not yet written to the shared store** (opt-in `--write`);
do it before the next cull drops those listings and the text goes with them.

## One tap per reason, and the 75 recovered (2026-10-08, QT-058 tier 2 + backfill)
**The backfill ran on both pools** — 68 Algarve + 7 Norte written to the shared Gist. The
store went 45 → 120 entries and **`DISLIKED WITH NO ENTRY` is now 0, `HIDDEN WITH NO ENTRY` 0**.
The 75 reconstructed entries are `unspecified` and **unsigned** (`by: ""`): who dismissed
them and when was never recorded, so they carry `backfilled_at` + `provenance` instead of a
guess. A second norte run reported 0 — the idempotence guard, proved on the live store.

**Tier 2: the reason row is now one tap.** It was a `selectbox` plus a separate "Save
reason" button — two clicks and a dropdown to record one fact. The five reasons she has
actually used sit in a pill row, most-used first (seasonal 22 · gone 18 · no_pets 3 ·
wrong_area 1 · not_a_rental 1); the seven she never has wait behind "Something else…",
along with the free-text field. `PILLS_MORE` is **derived** from `PICKABLE`, so a new reason
cannot be silently missing from the UI, and a test asserts the two cover it exactly.

Verified by driving the running app, not just by unit test — QT-055's lesson was that this
data layer can be correct while the UI path is broken:
- **one click, nothing else asked** → a full receipt (reason `unspecified`, author, title,
  url, concelho, price, pool, timestamp). Before, that click appended a string to a set.
- **one more tap** → the receipt is retracted with `retracted_at` and a `seasonal` entry
  replaces it. `open_feedback()` skips retracted, so the report counts one, not two.
- **the typed path** → `reason="other"` with the note intact, Portuguese accents and all.

`record_reason` is a module-level function rather than a closure over the card loop: as a
closure it captured the loop variable, which is only safe because Streamlit happens to call
it inside the same iteration.

## Rules module — searcher-authored overrides (2026-10-08, QT-058)
`src/quintal/rules.py`. A rule is a text pattern plus an attribute verdict, written during
a pull from a listing she actually read and dismissed. Three properties, each with a test:
- **In code, not `data/rules.json`** — `data/*.json` is gitignored, so a rules file there
  would never appear in a diff, never be reviewed, and never reach the `deploy` branch.
- **They mark, never purge.** A rule sets `pets=no`, `has_yard`, `has_bathtub` or the new
  `suspected_short_term` flag, and the app filters on it (`Exclude suspected short-term`,
  default on). A misfired rule mislabels something you can still find by unticking a box;
  one writing to the blocklist would delete it quietly. Nothing here feeds the screener's
  hard purge, which stays on the hand-maintained `SHORT_TERM_PATTERNS`.
- **A rule outranks the derivation** (confidence 1.0, `evidence=["rule:<id>"]`) because
  whoever wrote it opened the listing; the regex did not. A malformed rule — unknown
  attribute, illegal verdict, no provenance, uncompilable pattern — raises at construction
  rather than mid-pull. `RULES` ships **empty**: a rule with no 👎 behind it is a guess.

**`python -m quintal.rules test` is the guard**, and it works. On the Algarve pool a
candidate forward-order pets denial matched 73 listings: 46 already derive `no`, and it
would change **27** (22 currently derived **`yes`** — confidently backwards — and 5
`unknown`). Run carelessly as just `anima` against Norte it matches 41 and would change 29,
including a listing that says *"animais de estimação **bem vindos**"*. The sample lines make
that visible before anything is committed, which is the whole point.

### Two of my earlier measurements were wrong — corrected here
The listing stores have **no `description` key**; the field is **`description_raw`**, and
`descriptions.apply()` merges the detail-page sidecar *into* it before `normalize` folds
`title + description_raw`. Scratch scans I ran earlier this session read `description`, so
they saw title + sidecar only:
- **"Norte's only animal matches are street names" was wrong.** That was titles only (Norte
  has no descriptions sidecar). Norte has 8192 card previews (median 68 chars) and **41**
  listings mention animals, including real denials *and* real welcomes.
- **"23 missed denials, 17 inverted" understated it.** Measured properly through
  `rules test`, the candidate pattern would change **27**, 22 of them from `yes`.

`load_corpus` builds its text as `sidecar or description_raw`, which mirrors the pipeline
exactly — so `rules test` and `normalize` do see the same text. I checked that specifically,
because a guard measuring different text than the pipeline derives from would be worse than
no guard.

## Pets derivation fixed (2026-10-08, QT-058)
The keyword pass only ever handled one word order. `_PETS_DENY_REVERSED` caught
"<noun> … não permitido"; every **verb-first** denial leaked — and because the bare noun
"animais de estimacao" sits in `PETS_POSITIVE` with nothing to negate it, most leaked as a
confident **`yes`**, which even the app's "Exclude explicit no-pets" filter passes. The
fixed-phrase list could never close it: that needs every conjugation
(aceita/aceito/aceites/aceitam/aceitamos/serão aceites) × every verb × both orders.

Four patterns now, plus a conditional bucket:
- **`_PETS_DENY_FORWARD`** — negated verb then the noun. `anima` must follow the verb
  directly (one optional article, or one coordinated noun as in "não são permitidas festas
  e animais). A loose window would read "não é permitido **fumar** … animais são
  permitidos" as a refusal, which is the opposite of what it says.
- **`_PETS_DENY_PROHIBITED`** — "estritamente proibido a animais", including the
  "estritamento" typo that is live in the pool, and the reverse "animais … proibido".
- **`_PETS_DENY_EN`** — the list had "pets not allowed", which "pets **are** not allowed"
  does not contain.
- **Conditional → `unknown`, checked before positive.** "sem a prévia autorização",
  "necessidade a ser confirmado", "mediante autorização prévia", "a confirmar". Order is
  the point: every conditional sentence contains the bare noun, so `PETS_POSITIVE` would
  claim it. Confidence 0.5 — lower than an unmentioned unknown, because this one *was*
  mentioned and we still cannot call it.

**Measured old-vs-new across both pools, 91 verdicts changed:** 58 now read `no` (43 of
them from `yes`), and 33 conditionals moved `yes → unknown`. Only 24 still read `yes`.
**All 91 were read by hand and none was a false positive** — the catches include "não são
aceiteis animais de estimação, só peixes", "a quem não tenha animais" (a refusal written as
a preference) and "não se admite animais" (where the earlier draft's `admitid\w+` missed
"admite"). 59 tests in `test_normalize.py`, each denial and conditional quoted from the
live pool, plus the inverse: five real *allows* asserted to survive the new patterns.

**Effect on Malia's view: 13 listings, not 58.** Corrected 2026-10-08 by measuring the
*ranked* pools rather than the raw stores: Algarve `pets=no` 12 → 19 (+7) of 528 ranked,
Norte 3 → 9 (+6) of 2058. The 91 raw-store flips are mostly listings already removed by
delisting, screening, dedup or the ≥2-bed filter before ranking — so the raw count was never
the number Malia sees. `pets=yes` also fell 7 → 1 and 3 → 1 as the conditionals moved to
`unknown`, which changes nothing visible: `unknown` is kept and flagged, the honest answer
and the legally safer one in a PT long-let.

Two `test_rules.py` tests broke on this and were rewritten: they used real derivation gaps
as fixtures, and this fix closed those gaps. They now stand on gaps the derivation
genuinely has — "proibido ter cães ou gatos" (species, not "animais") and "cães permitidos
apenas no exterior" (a confident `yes` that is useless for a dog).

## `feedback inspect` — the raw material for a rule (2026-10-08, QT-058)
`report` tells you *that* something slipped and hands a miner some prose to guess at.
`inspect` hands you the listing: its note, its snapshot, **the text the detector actually
read**, whether the listing is still in the pool, whether the current screener catches it,
and what we derive for pets/yard/short-term. Grouped by reason, readable ones first,
`--reason` to filter, `--chars 0` for untruncated, `--json` for a session to parse. A
truncated preview always states the real character count, because a preview that hides its
own truncation would have you conclude there is no giveaway when it sits just past the cut.

**It found things the miner could not, on the first run.** The 15 still-slipping seasonal
Algarve dismissals carry `"Disponível de 1 de setembro a 30 de setembro"` and
`"monthly rent varies from month to month, check below … the rent for each month"` — a
same-month availability window and a rent that changes by month. `_SEASONAL_SPAN` only
covers **winter** lets (Sep–Dec → Mar–Jul), so a same-month window and any *summer* span
(junho → setembro — the actual holiday let) slip straight through. Measured: an
any-month-to-any-month span matches 344 Algarve listings, 323 already caught by other
rules, **21 genuinely new**. A candidate for the 10-12 pull, not applied.

The rest of those 15 confirm what NEXT.md already said: their previews cut off at ~400
chars and the tell is past it. `inspect` makes that visible instead of leaving it inferred.

### A bug in `rules test`, found by using it
`current_verdict` returned `"caught (seasonal month-range span)"` for short-term while a
rule asserts `"yes"`. The two could never compare equal, so the guard reported **every**
match as a change with "0 already agree" — turning 21 genuinely-new listings into a
headline of 344, in the one tool meant to be trusted in the minutes before a rule is
committed. It now returns `(verdict, detail)` with the verdict in the same vocabulary a
rule asserts, and only the verdict is compared. `ATTRIBUTES` still constrains what a rule
may *assert* (short_term: only `yes`) — the current state may be any of the three, which is
a different vocabulary sharing the same words, and the test now says so.

## RECOLLECT.md step 0 rewritten around inference (2026-10-08, QT-058 — complete)
The runbook told a fresh session to read the pattern miner's proposals, while NEXT.md told
it to add none of them. Step 0 is now the loop the rest of QT-058 was built for:
**0a read** (`feedback inspect`) → **0b prove** (`rules test`) → **0c write** (`rules.py`
to mark, or `screening.py` to purge) → **0d block** what no pattern can reach → **0e
resolve** only what was acted on. The miner is named and explicitly demoted.

0c carries the sink decision as a table — `rules.py` marks and is recoverable, `screening.py`
purges and you notice by absence — with "default to `rules.py`" stated outright. Step 5's
verification is split per sink, because `report`'s `✓ now caught` only ever reflects the
screener: a `rules.py` rule will **not** move it, and a session that expected otherwise
would think its rule had failed.

**Every command in the rewrite was run before it was written down.** Two were wrong as
first drafted: the `rules test` example used `--pool algarve` for a phrasing that only
exists in Norte (so it printed "Nothing matched"), and 0d implied you would block the 15
seasonal misses when they were already blocked on 10-04. Both corrected — and the first
turned into a better lesson than intended, since on Norte it reports *matches 1, would
change 0*, which is the guard saying **do not add this rule**.

**Verified while writing it: nothing in either pool currently needs a rule.** All 24
remaining `pets = yes` verdicts were re-read after the QT-058 widening and every one is a
genuine allow ("animais de estimação permitido", "bem vindos", "pet friendly", "aceita
animais pequeno porte"). `RULES` staying empty is the expected state — it is for a phrasing
that appears *later* and is too idiosyncratic for a built-in. The runbook now says that,
plus the escalation rule: wanting several rules at once means `normalize.py` has a gap.

## Published 2026-10-08 — QT-058 is live
`scripts/publish.sh` → `deploy` `8c7f1ee` → **`886d590`** (code `a207ad4`). Verified on
`origin/deploy`: the four new pets patterns, `rules.py`, and the app's one-tap pill row +
`hide_short_term` filter are all present. Publish gate passed (min required 3.10).

**No data change, by design.** The app derives at load time, so the pets fix reaches Malia
through the *code* on `deploy`; the snapshot is byte-identical to 10-04's — 2307 Algarve /
8192 Norte rows, `blocklist-norte` still 460.

That last number took a correction mid-run. Verifying the fix, a pipeline run **without**
`--min-beds` screened the T1 listings the app filters out anyway and added **438** entries
to `data/blocklist-norte.json` (460 → 898). Legitimately short-term, but a data change
caused by a verification run's flags, not by the fix — and blocklist side effects are what
QT-047 and QT-056 both were. Restored from backup and confirmed every sidecar byte-identical
before publishing. A real blocklist refresh belongs in the 10-12 pull, run deliberately.

**Not verified: the live app.** The deploy URL is recorded nowhere in this repo, so
confirming Streamlit Cloud actually redeployed and that Malia sees Algarve 528 / Norte 2058
is still open — same gap as the 09-30 entry. Worth writing the URL down somewhere.

## Live app verified (2026-10-08) — and two surprises in the deploy log
Checked in Alexander's signed-in Chrome; the app is **private**, so a browser without his
session gets a Streamlit sign-in wall rather than the app. URL now recorded in DEPLOY.md.

**The publish landed.** Deploy log: `🚀 Starting up repository: 'quintal', branch: 'deploy'`
at 10:54:25, and the sidebar now carries **"Exclude suspected short-term"**, a checkbox that
exists only in the new code. The pipeline numbers on Cloud are **identical** to the local
post-fix run — normalized 2305/2307, delisted 1137, screened 506 purged / 662 kept, geo 517,
valuation trim 35 of 491 — so the deployed code is doing exactly what was tested.

Showing **415 of 528**. That is not comparable to the "453 of 528" from local testing and
the earlier ~446 prediction was wrong-headed: local ran against `data/preferences.json`
(1 dismissal), the live app against the shared Gist (88 disliked + 32 hidden). The gap is
Malia's dismissals, not the pets fix.

**Streamlit Cloud is on Python 3.14.8, not 3.10.** The deploy log says so twice (`uv` env,
and the runtime traceback path `venv/lib/python3.14`). The gotcha in CLAUDE.md said 3.10
since 2026-08-25. The `vermin -t=3.10-` gate stays regardless — see CLAUDE.md for why.

**`use_container_width` is now flooding the log.** Hundreds of deprecation warnings per
render on Streamlit **1.65.0**. Its announced removal date (2025-12-31) passed nine months
ago and it still works, which is luck, not safety. Promoted in NEXT.md: this is the likeliest
way Malia's view breaks without warning.

## Re-collection 2026-10-08 — both pools, published (`deploy` `cd8595b`)
First pull since 09-26 (12 days; covers the skipped 10-05). Both pools, both sites, paged to
the true end of every search.

| | pulled | new | culled | cull coverage |
|---|---|---|---|---|
| Algarve · idealista | 610 / 615 | +96 | 124 | 82.8% |
| Algarve · imovirtual | 437 | +96 | — (never culls) | — |
| Norte · idealista | 1953 | +467 | 493 | 79.6% |
| Norte · imovirtual | 2419 | +587 | — | — |

**+1246 new, 617 culled, 628 found dead by the liveness probes** (110 Algarve, 518 Norte).
Stores: Algarve 2307 → **2498**, Norte 8192 → **9246**. Maintenance: descriptions +83,
photos +190 Algarve / +1044 Norte.

**Ranked after enrich: Algarve 509** (under 135 · fair 198 · over 176), **100% located**;
**Norte 2057** (under 595 · fair 845 · over 610), 2056 located. Both pools came out roughly
flat despite the 1246 new — the churn and the liveness purge cancel it out. `suspect` stayed
`none` on every one of ~140 pages. 276 tests pass; publish gate clear.

### Three collection lessons, all now in RECOLLECT.md
- **Imovirtual silently drops the query filters past the last page** and serves the unfiltered
  search — no error, same-looking cards. The documented "stop after two zero-add pages" cannot
  catch it, because an unfiltered page keeps adding rows; the Faro moradia run took on 23
  out-of-filter rows before it was spotted. Checking `location.search.includes('priceMax')`
  every page catches it on the first bad page, and did so twice more the same day.
- **`totalPages` from `__NEXT_DATA__` is accurate** (43 for Porto apartamento, which was
  exactly the last filtered page) — the older note saying it under-reports is wrong.
- **The recorded page counts drift badly.** Faro idealista was "~456 / 16 pages" and is now
  **615 / 21**; the old `--pages 18` would have missed ~80 and, with `--cull`, delisted them.

Step 0 ran first and added **no rules** — the month-span candidate was tested and rejected on
evidence (see its own entry). `feedback block` had nothing new to block.

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
- **Open follow-ups:** Imovirtual **descriptions** still deferred for Norte; **liveness closed
  2026-09-26** (first probe found 1899 dead listings). Routed (ORS) walk-times still skipped for
  Norte (straight-line — free-tier quota). See NEXT.md.

## Shared prefs wired locally, and a test that could have written to it (2026-10-04, QT-057)
`QUINTAL_GIST_ID` + `QUINTAL_GITHUB_TOKEN` are now in the local `.env`, so the feedback CLI
finally reads the real log — it prints *"store: shared Gist (both searchers)"*, and the local
fallback looks identical otherwise, so check that line.

**Adding them armed a hazard nobody had hit.** `feedback._load_prefs()` calls `load_dotenv()`
*inside* the function, which re-reads `.env` and undoes a test's `monkeypatch.delenv` — so
`pytest` started talking to the live store the moment the keys existed.
`test_cli_report_block_resolve_round_trip` read 45 of Malia's real notes instead of its own
fixture, and its next two lines call `block` and `resolve`, which **save**. It assert-failed on
the report first, so nothing was written — verified against the Gist's revision history (last
write 2026-09-30T10:37:30Z, zero resolved and zero retracted entries). That was luck, not
safety. `tests/conftest.py` now guards every test: the keys are cleared, `load_dotenv` is
neutered, and `GistBackend.save` raises so a test that somehow reaches a real backend fails
loudly instead of writing. The one test that legitimately drives `GistBackend.save` against a
fake `requests` opts out by marker. **alarm-proved per layer** — and they needed separate
proofs, because with layer 1 off the round-trip test still dies on its report assertion and
never reaches the tripwire.

**What the log actually holds: 45 open notes, every one a bare reason code, none with free
text.** This corrects the QT-055 write-up, which said the log "stayed empty" — it was half
empty, and the missing half is the half that matters. Also in the payload: **32 hidden ids**,
every one of which recorded nothing, which is the QT-055 rationale in numbers.
Two consequences, both filed in NEXT.md: **add none of the patterns `feedback report`
currently proposes** (with nothing quoted, the miner is reading 300-char previews of ordinary
prose — "a casa e", "na rua de", each would purge 40–50 real listings), and the 15 still-slipping
seasonal misses are a **text** gap, not a pattern gap — every one still in the store has only a
card preview, none a full description, all idealista (DataDome-blocked). `feedback block` is the
tool for those, not a new regex.

## Pipeline CLI crossed the pools (2026-09-30, QT-056)
Found by making the mistake: refreshing the blocklists before publishing, `python -m
quintal.pipeline --region norte` put **714 Norte listings into `data/blocklist.json`** and
screened them against the *Algarve* delisted set. `main()` passed no sidecar paths at all, so
every `run()` default applied whatever `--region` said — blocklist, delisted, geo, cache and
descriptions alike. With `--enrich` it would have overwritten `data/geo.json` with Norte
coordinates, which is the destructive version of the same bug. The app was never affected
(it resolves sidecars from `config.POOLS`); the CLI now does exactly the same.
Same class as QT-047, other entry point. Blocklists restored from backup and redone
correctly (Algarve 811 unchanged — the UI test session had already refreshed it; Norte
176 → 439). Verified afterwards that neither blocklist holds any of the other pool's ids.
`tests/test_pipeline.py` pins it, **alarm-proved** — reverting the fix turns 3 of its 4 red.

## Three fixes off Malia's 2026-09-30 report (QT-053/054/055)
All three verified against the collected pools, not reasoned about.
- **"Lots and lots of short-term rentals"** was essentially *one platform* (QT-053).
  Imovirtual syndicates Uniplaces stock verbatim — booking boilerplate and a
  "Duração Mínima de Aluguer: 30 dias" — and it was **118 of the 646 ranked Algarve
  listings, 18% of the pool**. Its machine-generated title ("Apartamento com 1 quartos -
  localizado em …", plural after "1") is the tell that works even where descriptions are
  missing: **187/187 precise** where a description existed to check it against, zero false
  positives across 10,499 listings. New patterns purge **365** by that title + **60** more
  by a minimum stay quoted in *days*. Ranked pools: Algarve 646 → **534**, Norte 2188 → **2064**.
  This deliberately **reverses** QT-048's decision to whitelist Uniplaces text — that call
  was aimed at "estudantes" and took the platform name with it. Its guard test now makes the
  "estudantes" point without naming the platform.
- **"Says house but the title says apartamento"** was naive substring matching (QT-054):
  `"villa"` matched *Village* (18), `"house"` matched *penthouse* (15), `"banda"` matched
  *Rua da Banda Musical* (4), and the `"casa "` trailing-space hack matched the description's
  generic "a casa é mobilada" (**145**) — a PT listing calls any home "a casa" in prose.
  **201 of 2307 Algarve listings were mistyped; now 1** (a title typo'd "AApartamento").
  Not cosmetic: `property_type` is worth **12/100** in the match score and is a hedonic
  regression feature, so every one of those was carrying an undeserved house bonus.
  Types now match on whole words, against the **title first**; the description only speaks
  when the title names no dwelling, and stays blind to "casa"/"house".
- **The hide button lost its "why"** (QT-055) — because the reason was unreachable, not
  because it was removed. QT-046 moved it to a follow-up on an *already-passed* card, but a
  pass drops the card out of the default view on the same click, so the "＋ Add a reason"
  button only existed behind the "Show 👎" toggle. **Pass and Hide were also near-duplicates**:
  both just removed the card, and `hidden` is read by nothing but the app's own filter — so
  half the dismissals threw the training signal away. Now **one** dismiss ("🙈 Not for us"),
  and the card **holds its place** with the reason ask attached (reason + note + Done + the
  module the reason points at). Anything hidden under the old button stays hidden behind
  "Show previously hidden". Verified end to end in the live app: pass → reason in place →
  entry in the store → `feedback report` reads it back.
- 212 tests green (`extract.js` jsdom gate included), `vermin -t=3.10-` clean, ruff clean
  bar two pre-existing E501s. **Not yet published — `scripts/publish.sh` still to run.**

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
  for T4+. Current store: **2307 listings** → 646 ranked (Algarve); Norte **8192** → 2188 ranked.
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
- **184 tests green** (incl. 11 that gate `extract.js` in jsdom — see the 2026-09-26 entry).

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
- **2026-09-26** — **both pools re-pulled, both sites, all complete-to-header.** First run in
  22 days (09-07/14/21 missed), so churn was heavy throughout. Driven from the **logged-in Chrome
  extension** (owner logged in mid-session; `list_connected_browsers` had returned `[]` at start
  and the in-app browser was the fallback until then). Idealista reachable, **no CAPTCHA**.
  **Algarve:** idealista 627 cards — **== the header's own "627 casas"** — (+204 new, 423 updated,
  **145 culled**, 10 resurrected); imovirtual 430 (361 apt / 69 moradia) → +153 new, 277 updated;
  store 1950→**2307**. Descriptions +141, liveness **+121 newly delisted** (delisted 881→1137),
  photos +352. **RANKED 646** (174 under / 233 fair / 213 over), **646/646 located**.
  **Norte:** idealista 1955 across the 5 districts — **each district matched its own header
  exactly** (Porto 1154, Braga 455, Viana 169, Vila Real 46, Viseu 131) — (+808 new, 1147 updated,
  **691 culled**, 26 resurrected); imovirtual 2324 across 10 searches (Porto 1591, Braga 450,
  Viana 155, Vila Real 41, Viseu 87) → +853 new, 1471 updated; store 6531→**8192**. Photos +1636.
  **RANKED 2188** (636 under / 881 fair / 642 over), located 2187 (99.95%). Norte walk-times still
  straight-line (ran with the ORS key unset, per the runbook).
  - **Norte liveness run for the first time — the deferred gap is closed.** `quintal.liveness`
    accepts `--input`/`--path`, so the norte store was probed directly:
    **1899 newly-delisted** imovirtual listings (`delisted-norte` 1884→3783) that no prior run
    could ever have detected, since the idealista cull was that pool's only liveness path.
    `delisted.json` stayed at 1137 throughout — **QT-047's sidecar fix confirmed in production
    again**. This is why Norte ranked *fell* 2374→2188: the earlier number was inflated by dead
    listings, 2188 is the honest count.
  - **QT-050 — imovirtual nulled `address.city`, costing every card its freguesia.** The
    `__NEXT_DATA__` blob now emits `address.city = null` and `address.province = null` (verified
    live on the page); only `reverseGeocoding.locations` still carries parish/council/district.
    `imvLocation()` read the freguesia from `addr.city.name`, so **every organic card collapsed to
    a bare concelho** — 430/430 on the first Algarve pull. Not cosmetic: `_geocode_queries` is
    freguesia-first precisely because a concelho centroid wrecks the beach axis (the code's own
    note: Vilamoura geocoded to inland Loulé town read as ~119 min from the sea). Fixed to read
    all three levels from `reverseGeocoding`, keeping `addr.*` as fallback; imovirtual re-pulled
    before ingest. Verified after: 430/430 carry "freguesia, concelho, District", 430/430
    concelhos valid, 307 where the freguesia differs from the concelho. 167 tests green.
  - **Transport: back to the download flow.** The 2026-09-04 gzip+base64-via-`get_page_text`
    trick **does not work on the Chrome extension** — its `get_page_text` has no `max_chars`, caps
    page text at 50,000 chars, and only spills to a file above a token threshold, so a 45k-char
    chunk came back *inline* (unusable for byte-exact reassembly) while a 75k request was silently
    truncated. Reverted to `quintalDownload` → `~/Downloads` → `--ingest`, which was byte-exact all
    four times. **Chrome's one-auto-download-per-tab rule bit twice**: the Norte idealista download
    silently never landed until issued from a *fresh* tab, and the re-pulled imovirtual file landed
    as `quintal_imovirtual (1).json` — the exact 2026-08-22 hazard. `rm ~/Downloads/quintal_*.json`
    before *every* download, not just the first.
  - **`extract.js` now has a real gate (the follow-up to QT-049/QT-050).** It is injected into
    a live browser, so it had no test at all — and both of its bugs reached the pool as corrupted
    data instead of failing a check. `tests/extract_harness.mjs` loads a saved fixture into jsdom,
    evaluates the **real** extract.js in that window, and calls the same `quintalReset`/
    `quintalExtract` entry points a pull uses; `tests/test_extract_js.py` (8 tests) asserts the
    rows and then pushes them through the real Python adapters, so the JS extraction and the
    Python parsing are proved to agree on **one shared input** rather than merely looking aligned.
    Fixtures are **real captured markup** (2026-09-26): 3 imovirtual cards covering both location
    paths (two in `__NEXT_DATA__`, one promoted tile on the `<p>` fallback, one with
    freguesia ≠ concelho) plus 2 idealista cards (one private, one agency-branded). The QT-049
    price-cell CSS is **intermittent** — verified absent from all 40 live cards today — so that
    one fixture is the real card with the incident's `<style>` re-injected, documented as such.
    **Alarm proved:** both regressions were planted into a throwaway copy and each turned the
    matching test red (the QT-049 plant reproduced `.css-6t3bie{…}1000 €` exactly). Worth
    knowing: `_rent_only`'s CSS strip *masks* a JS regression, so the price assertion stayed
    green — the gate has to assert at the JS boundary, and a comment in the test says so.
    Cost: one devDependency (jsdom) + `npm install`; the tests skip loudly without it.
    **Limit: the fixtures are a snapshot — they catch our regressions, not a portal moving its
    markup.** 175 tests green.
  - **Collection-time selector check + a cull guard (QT-052).** The gate above catches *our*
    regressions; these two catch *the portals moving*, which is the failure the fixtures can't
    see. (a) `quintalExtract` now also returns `expected` — a selector-INDEPENDENT count of the
    listings the page shows (unique detail-page links) — and a `suspect` verdict. That is what
    separates a moved card selector from the genuine end of pagination, which were previously
    indistinguishable (both give zero cards): past the last page there are no listing links
    either, so `expected === 0` and it stays quiet, while a broken selector reads
    `expected > 0, page === 0` → `suspect="no-cards"`. Watch it on every page of a pull.
    (b) The `--cull` caller contract ("only a complete pull") was human-remembered, and a
    collapsed pull would delist the pool in one command. `cull_absent` now requires the pull to
    re-surface ≥30% of the site's currently-**live** store entries (already-delisted ones are
    excluded, or a mature store's dead tail would make every healthy pull look collapsed),
    raising `CullRefused` **before any write**; the CLI prints `CULL REFUSED …` and exits 1 so a
    scripted run stops before publish. `--force-cull` overrides. The floor is calibrated against
    real churn — the worst observed was this very run at 62% and 74%. **Both alarms proved:**
    with the guard removed a 2%-coverage pull culled 49 of 50 live listings; with the selector
    check neutered the drift fixture went unflagged. 184 tests green.
  - **Not verified this run:** step 0 read `data/preferences.json`, **not** Malia's shared Gist —
    `QUINTAL_GIST_ID`/`QUINTAL_GITHUB_TOKEN` are still absent from `.env` (3rd run running). Its
    "0 open notes" says nothing about her real 👎 notes, so **no screener was hardened off it**.
- **2026-09-04** — **both pools re-pulled, both sites, all complete-to-header.** Run driven from
  the **in-app browser** (no Chrome extension connected — `list_connected_browsers` returned `[]`).
  Idealista was reachable today with **no CAPTCHA**, unlike 2026-08-31. **Algarve:** imovirtual 395
  cards (+46 new, 349 updated) → store 1847→1893; idealista 558 cards — **== the header's own "558
  casas"** — (+57 new, 501 updated, **48 culled**, 8 resurrected) → store **1950**. Descriptions +33,
  liveness **+38 newly delisted** (delisted 803→881), photos +95. **RANKED 619** (165 under / 211
  fair / 214 over), **619/619 located**. **Norte:** imovirtual 2261 cards (+326 new, 1935 updated)
  → 5956→6282; idealista 1812 across the 5 districts — **each district matched its own header
  exactly** (Porto 1065, Braga 416, Viana 158, Vila Real 45, Viseu 128) — (+249 new, 1563 updated,
  **226 culled**, 19 resurrected) → store **6531**; `delisted-norte` 1012→1219 while `delisted.json`
  stayed 881, i.e. **QT-047's sidecar fix confirmed in production**. Photos +546. **RANKED 2374**
  (679 under / 958 fair / 691 over), located 2363 (99.5%). Norte descriptions + liveness still
  deferred; Norte walk-times still straight-line (ran with the ORS key unset, per the runbook).
  - **QT-049 — a data-corrupting bug caught before it reached the pool.** Imovirtual's SSR'd markup
    emits its styled-components rules *inside* the price cell, so the cell's text read
    `.css-6t3bie{color:#071121FF;font-size:19px;...}1200 €…`. `_rent_only` only strips from the
    first euro sign, so `parse_price` read the digits out of the **colour and font size**: 13 Faro
    listings priced at **€0.63/month**, which would have ranked as the most undervalued properties
    in the Algarve. Fixed at both ends — `extract.js` now reads every card field through a `txt()`
    helper that drops nested `<style>`/`<script>`, and `_rent_only` strips any inline CSS rule as a
    second line of defence. Both tests **verified red against the old code** (reproducing
    `0.630711211970012` exactly). 167 tests green.
  - **Transport changed — no more `~/Downloads` round-trip.** Chrome's multiple-download guard
    started prompting for a Save dialog on the 3rd download, which interrupts the owner. Pages are
    now fetched + document-swapped as before, but the accumulated rows come back **gzipped +
    base64 in ~75k-char chunks via `get_page_text`**, reassembled and verified byte-exact
    (293,272 and 372,060 b64 chars, both matching) before ingest. No file dialogs, and the
    "stale file in ~/Downloads" hazard disappears with it.
  - **Not verified this run:** step 0 read `data/preferences.json`, **not** Malia's shared Gist —
    `QUINTAL_GIST_ID`/`QUINTAL_GITHUB_TOKEN` are still absent from `.env`. Its "0 open notes" says
    nothing about her real 👎 notes, so **no screener was hardened off it**. Still open in NEXT.md.
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
**Carry forward:** `feedback block` ran on both pools 2026-10-04 (38 listings off Malia's
notes; Algarve 811 → 828, Norte 439 → 460) and was **published the same day** (`8c7f1ee`) —
hosted app now at Algarve 528 / Norte 2058, nothing pending. **The 10-05 re-collection is
skipped by Alexander's decision**; the next candidate Monday is 10-12. Skipping costs pool
freshness only (~13% decay per 11 days, last pull 09-26) — correctness is unaffected.

Last work: **QT-057 above** (shared-prefs env wired locally; the test-isolation hazard it
armed, closed and alarm-proved). Before it **QT-056** (the CLI pool-crossing bug, found while
publishing) and **QT-053/054/055** — the three fixes off Malia's 2026-09-30 report
(short-term leak, property-type mislabel, the unreachable "why"). All committed and tested;
**the hosted app has not been republished yet**, so Malia is still on the old build until
`scripts/publish.sh` runs. Before that: QT-051/052 (the extract.js jsdom gate and the
collection-time selector check) and the 2026-09-26 re-collection. The standing task remains
the weekly re-collection (see NEXT.md).

## Known issues / debugging
- **The screener is mostly blind on Norte.** All 4353 Norte imovirtual listings carry *no*
  description and the idealista ones only a ≤400-char card preview, so text patterns have
  almost nothing to read — which is why QT-053's *title*-based rule matters there (210 of its
  351 purges). Fixing this properly is the deferred imovirtual descriptions backfill (NEXT.md).
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
