"""Why we passed: read the 👎 reason log and harden the next pull off it.

The app records a reason code + free-text note with every 👎 (`preferences.py`). This is
the other end of that loop — the thing a re-collection session runs *before* pulling:

    python -m quintal.feedback report          # what slipped through, and what to add
    python -m quintal.feedback block           # hard-block the offenders by id, now
    python -m quintal.feedback resolve --all   # mark the notes acted on

Two kinds of reason, and they go to different places:

- **Screenable** — the listing should never have been in the pool (seasonal let, not a
  rental, wrong area, duplicate, already gone, bad data). That's a *filter bug*: each maps
  to the module that should have caught it.
- **Taste** — a perfectly valid listing we just don't want. That feeds scoring/filters and
  area sentiment, never the screener.

For the screenable ones the report re-runs the *current* screener over each flagged
listing's text, so it separates "we now catch this" from "still slips through", and mines
the still-slipping text for candidate phrases — each shown with how many other pool
listings it would also purge. Candidates are **proposed, never auto-applied**: a careless
pattern ("casa") would purge the pool. A human adds the good ones to
`screening.SHORT_TERM_PATTERNS`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import textwrap
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from . import config, descriptions, rules
from .normalize import fold
from .preferences import (
    UNSPECIFIED_REASON,
    GistBackend,
    Preferences,
    default_backend,
    utc_now_iso,
)
from .screening import SHORT_TERM_PATTERNS, Blocklist, short_term_reason

PREFS_PATH = "data/preferences.json"


# --- The taxonomy -------------------------------------------------------------
Bucket = Literal["miss", "taste", "unclassified"]


@dataclass(frozen=True)
class Reason:
    code: str
    label: str  # what the app shows in the dropdown
    bucket: Bucket  # miss = a filter bug · taste = a preference · unclassified = no reason given
    target: str  # where the fix belongs
    hint: str = ""  # what a good note looks like for this reason
    pill: str = ""  # short label for the app's one-tap reason row (falls back to `label`)

    @property
    def screenable(self) -> bool:
        """A filter bug — the pool should never have shown it."""
        return self.bucket == "miss"


REASONS: dict[str, Reason] = {
    r.code: r
    for r in (
        Reason(
            "seasonal",
            "🗓️ Seasonal / short-term let",
            "miss",
            "screening.py — SHORT_TERM_PATTERNS",
            "quote the words that give it away (e.g. 'só até junho', 'época escolar')",
            pill="🗓️ Seasonal",
        ),
        Reason(
            "not_a_rental",
            "🚫 Not a long-term rental (sale, room, commercial)",
            "miss",
            "screening.py / collect adapters",
            "say what it actually is",
            pill="🚫 Not a rental",
        ),
        Reason(
            "wrong_area",
            "🗺️ Outside the area we're searching",
            "miss",
            "enrich.py regions / concelho filter",
            "name where it really is",
            pill="🗺️ Wrong area",
        ),
        Reason(
            "duplicate",
            "👯 Duplicate of another listing",
            "miss",
            "dedup.py",
            "paste the other listing's URL if you have it",
            pill="👯 Duplicate",
        ),
        Reason(
            "gone",
            "💨 Already rented / dead link / scam",
            "miss",
            "liveness.py",
            "what happened when you opened it",
            pill="💨 Already gone",
        ),
        Reason(
            "bad_data",
            "🧮 Wrong details (price, size, beds, photos)",
            "miss",
            "collect/extract.js, normalize.py",
            "what the listing actually says vs what we showed",
            pill="🧮 Wrong details",
        ),
        Reason(
            "location",
            "📍 Area doesn't work for us",
            "taste",
            "area sentiment / scoring",
            pill="📍 Area's wrong",
        ),
        Reason(
            "price",
            "💶 Not worth the price",
            "taste",
            "valuation / budget filter",
            pill="💶 Too pricey",
        ),
        Reason(
            "no_yard",
            "🌳 No real outdoor space",
            "taste",
            "normalize.py yard keywords",
            pill="🌳 No outdoor space",
        ),
        Reason(
            "no_pets",
            "🐾 No pets allowed",
            "taste",
            "normalize.py pets keywords",
            pill="🐾 No pets",
        ),
        Reason(
            "condition",
            "🔨 Condition / layout",
            "taste",
            "taste only",
            pill="🔨 Condition",
        ),
        Reason(
            "other",
            "🤷 Something else",
            "taste",
            "taste only",
            pill="🤷 Something else",
        ),
        # Written by the dismiss button itself when nothing else was offered. Not a verdict —
        # a receipt, so a reasonless 👎 still leaves something to infer from at pull time.
        # Before this existed a bare dismiss recorded only set membership: 43 of Malia's 88
        # (2026-10-08, measured against the shared Gist) had no reason, no timestamp and no
        # snapshot of what the listing even was.
        Reason(
            "unspecified",
            "🙈 Not for us — no reason given",
            "unclassified",
            "inferred at pull time — RECOLLECT.md step 0",
        ),
    )
}
UNSPECIFIED = UNSPECIFIED_REASON
SCREENABLE = [code for code, r in REASONS.items() if r.screenable]
# What the app offers: everything a human would actually pick.
PICKABLE = [code for code in REASONS if code != UNSPECIFIED]
# The one-tap pill row, most-used first — measured against the shared Gist on 2026-10-08:
# seasonal 22 · gone 18 · no_pets 3 · wrong_area 1 · not_a_rental 1. Every other reason has
# never been picked once, so it waits behind "Something else" instead of competing for the
# first tap. Derived, not listed, so a new reason can never be silently dropped from the UI.
PILLS_PRIMARY = ["seasonal", "gone", "no_pets", "wrong_area", "not_a_rental"]
PILLS_MORE = [code for code in PICKABLE if code not in PILLS_PRIMARY]


def pill_of(code: str) -> str:
    """Short label for the reason row; falls back to the full label."""
    reason = REASONS.get(code)
    if reason is None:
        return code
    return reason.pill or reason.label


def label_of(code: str) -> str:
    reason = REASONS.get(code)
    return reason.label if reason else code


def context_from_view(view: dict, pool_name: str) -> dict:
    """Snapshot the card a 👎 was cast on, so the log reads even after the listing is gone."""
    return {
        "pool": pool_name,
        "title": view.get("title"),
        "url": view.get("url"),
        "concelho": view.get("concelho"),
        "price": view.get("price"),
    }


# --- Joining the log back to the listing text ---------------------------------
def _id_for_url(url: str) -> str:
    """Mirror `Listing.ensure_id` for a URL-keyed row (tested against it in test_feedback)."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def load_corpus(pool: dict) -> dict[str, dict]:
    """Every row in the pool's store, keyed by listing id → {title, text, url}.

    Reads the raw store (not the ranked pipeline output) on purpose: a listing that was
    later blocked, delisted or deduped still has its text here, which is exactly the text
    a 👎 was about.
    """
    path = Path(pool["listings"])
    if not path.exists():
        return {}
    sidecar = descriptions.load(pool.get("descriptions_path", descriptions.DEFAULT_PATH))
    corpus: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        url = row.get("source_url")
        if not url:
            continue
        title = row.get("title") or ""
        body = sidecar.get(url) or row.get("description_raw") or ""
        corpus[_id_for_url(url)] = {"title": title, "text": f"{title} {body}".strip(), "url": url}
    return corpus


def store_label(prefs: Preferences) -> str:
    """Name the store the notes were read from — local dev and the shared Gist differ, and
    reporting on the wrong one silently reads nobody's notes."""
    if isinstance(prefs.backend, GistBackend):
        return "shared Gist (both searchers)"
    path = getattr(prefs.backend, "path", "?")
    return f"local file {path} — set QUINTAL_GIST_ID + QUINTAL_GITHUB_TOKEN to read the shared log"


# --- Findings -----------------------------------------------------------------
@dataclass
class Finding:
    """One open screenable note, checked against the *current* screener."""

    entry: dict
    text: str  # listing text we could recover ("" when the row is gone)
    caught_by: str | None  # screener verdict today, None = still slips through

    @property
    def reason(self) -> str:
        return self.entry.get("reason", "other")

    @property
    def listing_id(self) -> str:
        return self.entry.get("listing_id", "")


@dataclass
class Candidate:
    """A phrase mined from still-slipping listings, with its blast radius."""

    phrase: str
    flagged_hits: int  # flagged listings it would catch
    collateral: int  # *other* pool listings it would also purge
    examples: list[str] = field(default_factory=list)  # titles of that collateral
    quoted: bool = False  # the searcher quoted these words in their note — strongest signal


@dataclass
class Report:
    pool_name: str
    store: str
    findings: list[Finding]
    taste: list[dict]
    unclassified: list[dict]
    candidates: list[Candidate]
    corpus_size: int
    open_total: int
    # Which listing ids the pool still holds — lets the unclassified section say which
    # dismissals are still readable and which survive only as their snapshot.
    corpus_ids: frozenset[str] = frozenset()


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _ngrams(text: str, n_min: int = 2, n_max: int = 4) -> set[str]:
    tokens = _TOKEN_RE.findall(fold(text))
    grams: set[str] = set()
    for n in range(n_min, n_max + 1):
        for i in range(len(tokens) - n + 1):
            grams.add(" ".join(tokens[i : i + n]))
    return grams


def _has_digit(phrase: str) -> bool:
    return any(ch.isdigit() for ch in phrase)


def _already_covered(phrase: str, existing: list[str]) -> bool:
    """True when a current pattern already implies this phrase (either direction)."""
    return any(pat in phrase or phrase in pat for pat in existing)


def mine_patterns(
    missed: list[str],
    corpus: dict[str, dict],
    *,
    notes: list[str] | None = None,
    exclude_ids: set[str] | None = None,
    existing: list[str] | None = None,
    min_flagged: int | None = None,
    limit: int = 12,
    max_collateral_ratio: float = 0.05,
) -> list[Candidate]:
    """Phrases common to the missed listings and rare in everything else.

    `missed` is the text of listings a 👎 said were short-term but the screener let through.
    Each candidate carries its **collateral** — how many other pool listings adding it would
    purge — because that number, not the phrase, is what makes it safe or reckless.

    A phrase the searcher also quoted in their `notes` sorts first: they read the listing and
    told us which words gave it away, which beats any frequency count.
    """
    existing = existing if existing is not None else list(SHORT_TERM_PATTERNS)
    exclude_ids = exclude_ids or set()
    texts = [t for t in missed if t.strip()]
    if not texts:
        return []
    # Two flagged listings is the bar for a *frequency* claim — one listing's n-grams are
    # mostly its own street name. A phrase the searcher quoted bypasses the bar.
    floor = min_flagged if min_flagged is not None else 2

    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(_ngrams(text))
    quoted = set()
    for note in notes or []:
        quoted |= _ngrams(note)

    others = [
        entry for lid, entry in corpus.items() if lid not in exclude_ids and entry["text"].strip()
    ]
    folded_others = [(entry["title"], fold(entry["text"])) for entry in others]
    collateral_cap = max(1, int(len(folded_others) * max_collateral_ratio))

    candidates: list[Candidate] = []
    for phrase, flagged_hits in counts.items():
        was_quoted = phrase in quoted
        if not was_quoted and (flagged_hits < floor or _has_digit(phrase)):
            continue  # digits are street numbers and T2/T3 — never a seasonality signal
        if _already_covered(phrase, existing):
            continue
        hits = [title for title, text in folded_others if phrase in text]
        if len(hits) > collateral_cap:  # too generic to be a screening pattern
            continue
        candidates.append(Candidate(phrase, flagged_hits, len(hits), hits[:2], was_quoted))

    candidates.sort(key=lambda c: (not c.quoted, -c.flagged_hits, c.collateral, len(c.phrase)))
    # Drop longer phrases a shorter, equally-effective one already contains ("o ano letivo"
    # once "ano letivo" is in) — same catch, needless noise in the list.
    kept: list[Candidate] = []
    for cand in candidates:
        if any(k.phrase in cand.phrase and k.flagged_hits >= cand.flagged_hits for k in kept):
            continue
        kept.append(cand)
    return kept[:limit]


def entries_for_pool(
    prefs: Preferences, pool_name: str, *, include_resolved: bool = False
) -> list[dict]:
    """Open notes tagged to this pool. Untagged entries (pre-dating pools) count everywhere."""
    entries = prefs.feedback if include_resolved else prefs.open_feedback()
    return [e for e in entries if not e.get("pool") or e.get("pool") == pool_name]


def build_report(
    prefs: Preferences, pool_name: str, pool: dict, *, include_resolved: bool = False
) -> Report:
    entries = entries_for_pool(prefs, pool_name, include_resolved=include_resolved)
    corpus = load_corpus(pool)

    findings: list[Finding] = []
    taste_entries: list[dict] = []
    unclassified: list[dict] = []
    for entry in entries:
        bucket = REASONS.get(entry.get("reason", ""), REASONS["other"]).bucket
        if bucket == "miss":
            row = corpus.get(entry.get("listing_id", ""), {})
            text = row.get("text", "")
            findings.append(Finding(entry, text, short_term_reason(text) if text else None))
        elif bucket == "unclassified":
            # No verdict to act on — these are raw material for the pull-time inference
            # pass, not something a pattern can be mined from. Kept out of `taste` on
            # purpose: filing them there would read as "she just didn't like it".
            unclassified.append(entry)
        else:
            taste_entries.append(entry)

    slipping = [f for f in findings if f.reason == "seasonal" and f.caught_by is None and f.text]
    candidates = mine_patterns(
        [f.text for f in slipping],
        corpus,
        notes=[f.entry.get("note", "") for f in slipping],
        exclude_ids={f.listing_id for f in findings},
    )

    taste: list[dict] = []
    for code, count in Counter(e.get("reason", "other") for e in taste_entries).most_common():
        places = Counter(e.get("concelho") for e in taste_entries if e.get("reason") == code)
        taste.append(
            {
                "reason": code,
                "count": count,
                "places": [f"{name} ×{n}" for name, n in places.most_common(4) if name],
                "notes": [
                    e["note"]
                    for e in taste_entries
                    if e.get("reason") == code and e.get("note")
                ],
            }
        )

    return Report(
        pool_name=pool_name,
        unclassified=unclassified,
        corpus_ids=frozenset(corpus),
        store=store_label(prefs),
        findings=findings,
        taste=taste,
        candidates=candidates,
        corpus_size=len(corpus),
        open_total=len(entries),
    )


# --- Acting on the log --------------------------------------------------------
def block_open_findings(
    prefs: Preferences, pool_name: str, pool: dict, *, dry_run: bool = False
) -> list[dict]:
    """Blocklist every open screenable listing by id — the hard stop, independent of patterns.

    A pattern is the general fix; this is the specific one. It works even for reasons no
    text pattern could ever catch (duplicate, already-gone, wrong area). Returns the
    entries blocked. The caller saves prefs.
    """
    blocklist = Blocklist(pool["blocklist_path"])
    blocked: list[dict] = []
    for finding in build_report(prefs, pool_name, pool).findings:
        entry = finding.entry
        lid = finding.listing_id
        if not lid or blocklist.contains(lid):
            continue
        who = entry.get("by") or "searcher"
        note = entry.get("note") or REASONS.get(finding.reason, REASONS["other"]).label
        blocklist.add(lid, f"feedback:{finding.reason} — {note} ({who}, {entry.get('at', '')})")
        if not dry_run:
            entry["blocked_at"] = entry.get("blocked_at") or utc_now_iso()
        blocked.append(entry)
    if blocked and not dry_run:
        blocklist.save()
    return blocked


# --- Rendering ----------------------------------------------------------------
def _fmt_entry(entry: dict) -> str:
    bits = [f"€{entry['price']:.0f}" if entry.get("price") else None, entry.get("concelho")]
    head = " · ".join(b for b in bits if b)
    title = (entry.get("title") or "(listing gone from the store)")[:64]
    return f"{head} · {title}" if head else title


def backfill_receipts(
    prefs: Preferences, pool_name: str, pool: dict, *, dry_run: bool = True
) -> list[dict]:
    """Reconstruct `unspecified` receipts for dismissals that recorded nothing.

    Before the dismiss button logged unconditionally, a 👎 with no reason chosen added the
    id to a set and nothing else — 75 of them (43 `disliked`, 32 legacy `hidden`) as of
    2026-10-08. Every one was still in a pool store on that date, so the title and text
    survive and a receipt can be rebuilt from them.

    What cannot be rebuilt is **when** she dismissed it or **who** did: neither was ever
    written down. So the entry carries `backfilled_at`, `by` stays empty rather than
    guessing, and `at` is the backfill time, not the dismissal time. A future session
    reading the log can tell a reconstructed receipt from a captured one — which matters,
    because the reconstructed ones can only ever say "this was rejected", never why.

    Idempotent: a listing that already has any entry is skipped, so re-running adds nothing.
    """
    corpus = load_corpus(pool)
    already = {e.get("listing_id") for e in prefs.feedback}
    at = utc_now_iso()
    added: list[dict] = []
    for listing_id in sorted((prefs.disliked | prefs.hidden) - already):
        row = corpus.get(listing_id)
        if row is None:
            continue  # belongs to the other pool, or its text is already gone
        entry = {
            "entry_id": f"backfill-{listing_id[:12]}",
            "listing_id": listing_id,
            "reason": UNSPECIFIED,
            "note": "",
            "by": "",  # never recorded — do not attribute
            "at": at,
            "backfilled_at": at,
            "provenance": (
                "backfill QT-058: dismissed before the receipt existed; "
                "original date and author unknown"
            ),
            "title": row.get("title", ""),
            "url": row.get("url", ""),
            "pool": pool_name,
            "was_hidden": listing_id in prefs.hidden,
        }
        added.append(entry)
        if not dry_run:
            prefs.feedback.append(entry)
    return added


# --- inspect: the raw material for a rule ------------------------------------
# `report` tells you *that* something slipped and lets a miner guess at phrases. This
# shows you the listing — its note, its snapshot, the text the detector actually read, and
# what we say about it today — so a person (or a session) can read it and write the rule.
# The miner was never going to get there: with no quoted text to anchor on it proposes
# "a casa e" (47 collateral) and "na rua de" (50). Reading five listings beats it outright.

INSPECT_ATTRIBUTES = ("pets", "yard", "short_term")


def inspect_entries(
    prefs: Preferences,
    pool_name: str,
    pool: dict,
    *,
    reason: str | None = None,
    include_resolved: bool = False,
) -> list[dict]:
    """Open dismissals for this pool, each joined to its listing text and our verdicts.

    Readable ones (listing still in the store) sort first, because those are the ones a
    rule can be written from — a dismissal whose listing is gone has only its snapshot.
    """
    corpus = load_corpus(pool)
    rows = []
    for entry in entries_for_pool(prefs, pool_name, include_resolved=include_resolved):
        if reason and entry.get("reason") != reason:
            continue
        listing_id = entry.get("listing_id", "")
        row = corpus.get(listing_id)
        text = (row or {}).get("text", "")
        rows.append(
            {
                "entry": entry,
                "in_pool": row is not None,
                "text": text,
                "screener": short_term_reason(text) if text else None,
                "verdicts": (
                    {
                        a: " ".join(filter(None, rules.current_verdict(a, text)))
                        for a in INSPECT_ATTRIBUTES
                    }
                    if text
                    else {}
                ),
            }
        )
    rows.sort(key=lambda r: (not r["in_pool"], r["entry"].get("reason", "")))
    return rows


def render_inspect(rows: list[dict], *, pool_name: str, store: str, chars: int = 360) -> str:
    out = [f"\nInspect — {pool_name}", f"store: {store}", f"{len(rows)} dismissal(s)"]
    if not rows:
        out.append("\nNothing open for this pool.")
        return "\n".join(out)

    readable = sum(1 for r in rows if r["text"])
    out.append(f"{readable} with text to read · {len(rows) - readable} snapshot-only")
    out.append(
        "\nRead these, find what they share, then prove the pattern before writing it:"
        "\n  python -m quintal.rules test --attribute <a> --pattern '<p>' --pool <region>"
    )

    by_reason: dict[str, list[dict]] = {}
    for row in rows:
        by_reason.setdefault(row["entry"].get("reason", "other"), []).append(row)

    for code, group in by_reason.items():
        meta = REASONS.get(code, REASONS["other"])
        target = f" → {meta.target}" if meta.screenable else ""
        out.append(f"\n{'=' * 78}\n{meta.label}  ({len(group)}){target}")
        for row in group:
            entry = row["entry"]
            out.append(f"\n  ─ entry {entry.get('entry_id', '?')}  {_fmt_entry(entry)}")
            who = entry.get("by") or "(unsigned)"
            stamp = entry.get("at", "")[:10]
            extra = "  [reconstructed]" if entry.get("backfilled_at") else ""
            out.append(f"    by {who} · {stamp}{extra}")
            if entry.get("url"):
                out.append(f"    {entry['url']}")
            if entry.get("note"):
                out.append(f'    note: "{entry["note"]}"')
            if not row["in_pool"]:
                out.append("    ✗ gone from the pool — snapshot only, no text to read")
                continue
            screener = row["screener"]
            out.append(
                "    screener: "
                + (f"✓ caught ({screener})" if screener else "✗ does not catch it")
                + "".join(f" · {a}: {v}" for a, v in row["verdicts"].items())
            )
            text = row["text"]
            if not text:
                out.append("    (no text in the store — card preview missing)")
                continue
            shown = text if chars <= 0 or len(text) <= chars else text[:chars] + " …"
            out.append(f"    text ({len(text)} chars):")
            for line in textwrap.wrap(shown, width=92):
                out.append(f"      {line}")
    return "\n".join(out)


def render_report(report: Report) -> str:
    out: list[str] = []
    misses = report.findings
    out.append(f"\nFeedback report — {report.pool_name}")
    out.append(f"store: {report.store}")
    out.append(
        f"{report.open_total} open note(s): {len(misses)} filter miss(es), "
        f"{sum(t['count'] for t in report.taste)} taste, "
        f"{len(report.unclassified)} unclassified · pool store {report.corpus_size} rows"
    )

    if misses:
        out.append("\nFILTER MISSES — these should never have reached the app")
        by_reason: dict[str, list[Finding]] = {}
        for finding in misses:
            by_reason.setdefault(finding.reason, []).append(finding)
        for code, group in by_reason.items():
            reason = REASONS.get(code, REASONS["other"])
            out.append(f"\n  {reason.label}  ({len(group)}) → fix in {reason.target}")
            for finding in group:
                if finding.caught_by:
                    mark = f"✓ now caught ({finding.caught_by})"
                elif not finding.text:
                    mark = "· no text in the store"
                else:
                    mark = "✗ still slips"
                entry = finding.entry
                flags = " 🔒 blocked" if entry.get("blocked_at") else ""
                out.append(f"    {mark}{flags}  {_fmt_entry(entry)}")
                if entry.get("note"):
                    who = f" — {entry['by']}" if entry.get("by") else ""
                    out.append(f'        note: "{entry["note"]}"{who}')
                if entry.get("url"):
                    out.append(f"        {entry['url']}")
                out.append(f"        entry {entry.get('entry_id', '?')}")
    else:
        out.append("\nNo open filter misses. 🎉")

    if report.candidates:
        out.append("\nCANDIDATE PATTERNS — mined from the still-slipping seasonal notes")
        out.append(f"  {'':2}{'phrase':<38}{'flags':>6}{'also purges':>13}   example collateral")
        for cand in report.candidates:
            example = cand.examples[0][:38] if cand.examples else "—"
            mark = "★ " if cand.quoted else "  "
            out.append(
                f"  {mark}{cand.phrase:<38}{cand.flagged_hits:>6}{cand.collateral:>13}   {example}"
            )
        out.append("  ★ = the searcher quoted these words in their note.")
        out.append(
            "  Review, then add the safe ones to SHORT_TERM_PATTERNS in"
            " src/quintal/screening.py.\n  'also purges' = other pool listings the phrase"
            " would drop — check a couple before adding."
        )

    if report.unclassified:
        out.append(
            f"\nUNCLASSIFIED — {len(report.unclassified)} dismissed with no reason given"
        )
        out.append(
            "  Nothing to act on mechanically. Read the listings, find what they share,"
            "\n  then write the rule yourself — RECOLLECT.md step 0."
        )
        in_pool = 0
        for entry in report.unclassified:
            here = entry.get("listing_id", "") in report.corpus_ids
            in_pool += here
            out.append(f"    {'·' if here else '✗ gone from pool'}  {_fmt_entry(entry)}")
            if entry.get("url"):
                out.append(f"        {entry['url']}")
            out.append(f"        entry {entry.get('entry_id', '?')}")
        out.append(
            f"  {in_pool}/{len(report.unclassified)} still in the pool — those have full text"
            " to read; the rest have only the snapshot above."
        )

    if report.taste:
        out.append("\nTASTE — feeds scoring/filters and area sentiment, never the screener")
        for item in report.taste:
            places = f"  ({', '.join(item['places'])})" if item["places"] else ""
            out.append(f"  {label_of(item['reason'])} ×{item['count']}{places}")
            for note in item["notes"][:3]:
                out.append(f'      "{note}"')

    out.append("\nNext:")
    out.append("  python -m quintal.feedback block --pool <region>      # hard-block the misses")
    out.append(
        "  python -m quintal.feedback resolve --all --pool <region>"
        ' --note "QT-xxx patterns added"'
    )
    return "\n".join(out) + "\n"


def _report_json(report: Report) -> str:
    return json.dumps(
        {
            "pool": report.pool_name,
            "store": report.store,
            "open_total": report.open_total,
            "corpus_size": report.corpus_size,
            "unclassified": [
                {**entry, "in_pool": entry.get("listing_id", "") in report.corpus_ids}
                for entry in report.unclassified
            ],
            "findings": [
                {
                    **finding.entry,
                    "caught_by": finding.caught_by,
                    "has_text": bool(finding.text),
                    "target": REASONS.get(finding.reason, REASONS["other"]).target,
                }
                for finding in report.findings
            ],
            "candidates": [
                {
                    "phrase": c.phrase,
                    "flagged_hits": c.flagged_hits,
                    "collateral": c.collateral,
                    "quoted": c.quoted,
                    "examples": c.examples,
                }
                for c in report.candidates
            ],
            "taste": report.taste,
        },
        ensure_ascii=False,
        indent=2,
    )


# --- CLI ----------------------------------------------------------------------
def _load_prefs(path: str) -> Preferences:
    """Same store the app uses: the shared Gist when configured, else the local file."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    return Preferences(backend=default_backend(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read the 👎 reason log and harden the pull.")
    parser.add_argument(
        "command", choices=["report", "inspect", "block", "resolve", "backfill"]
    )
    parser.add_argument("--pool", default="algarve", help="region slug (algarve | norte)")
    parser.add_argument("--prefs", default=PREFS_PATH, help="local preferences file (Gist wins)")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--reason", default="", help="inspect: only this reason code")
    parser.add_argument(
        "--chars", type=int, default=360, help="inspect: text to show per listing (0 = all)"
    )
    parser.add_argument("--all", action="store_true", help="resolve: every open entry")
    parser.add_argument("--entry", action="append", default=[], help="resolve: one entry id")
    parser.add_argument("--note", default="", help="resolve: what was done about it")
    parser.add_argument(
        "--dry-run", action="store_true", help="block: show, don't write (backfill: default)"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="backfill: actually write the reconstructed receipts to the store",
    )
    parser.add_argument(
        "--include-resolved", action="store_true", help="report: show acted-on entries too"
    )
    args = parser.parse_args(argv)

    pool = config.pool_by_region(args.pool)
    pool_name = next(name for name, p in config.POOLS.items() if p is pool)
    prefs = _load_prefs(args.prefs)

    if args.command == "report":
        report = build_report(prefs, pool_name, pool, include_resolved=args.include_resolved)
        print(
            _report_json(report) if args.json else render_report(report)
        )
        return 0

    if args.command == "inspect":
        rows = inspect_entries(
            prefs,
            pool_name,
            pool,
            reason=args.reason or None,
            include_resolved=args.include_resolved,
        )
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            print(
                render_inspect(
                    rows, pool_name=pool_name, store=store_label(prefs), chars=args.chars
                )
            )
        return 0

    if args.command == "block":
        print(f"store: {store_label(prefs)}")
        blocked = block_open_findings(prefs, pool_name, pool, dry_run=args.dry_run)
        for entry in blocked:
            print(f"  blocked {entry.get('listing_id')}  {_fmt_entry(entry)}")
        if blocked and not args.dry_run:
            prefs.save()
        verb = "would block" if args.dry_run else "blocked"
        print(f"{verb} {len(blocked)} listing(s) → {pool['blocklist_path']}")
        return 0

    if args.command == "backfill":
        # Writing to a store two people share, so it opts IN rather than out.
        dry = not args.write
        print(f"store: {store_label(prefs)}" + ("  (dry run)" if dry else "  (WRITING)"))
        added = backfill_receipts(prefs, pool_name, pool, dry_run=dry)
        for entry in added:
            tag = " [was hidden]" if entry["was_hidden"] else ""
            print(f"  {entry['listing_id']}{tag}  {entry['title'][:66]}")
        verb = "would reconstruct" if dry else "reconstructed"
        print(f"{verb} {len(added)} receipt(s) for {pool_name}")
        if dry:
            print("Nothing written. Re-run with --write to commit.")
        else:
            prefs.save()
        return 0

    # resolve
    ids = list(args.entry)
    if args.all:
        ids += [e["entry_id"] for e in entries_for_pool(prefs, pool_name) if e.get("entry_id")]
    if not ids:
        print("Nothing to resolve — pass --all or --entry <id>.")
        return 1
    n = prefs.resolve_feedback(ids, note=args.note)
    prefs.save()
    print(f"resolved {n} entry(ies)" + (f' — "{args.note}"' if args.note else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
