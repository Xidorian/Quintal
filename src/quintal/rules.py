"""Searcher-authored rules: a text pattern that overrides a derived attribute.

The built-in keyword sets in `normalize.py` are *our* knowledge of how a Portuguese
listing phrases things. These are **hers** — written during a pull, from a listing she
actually read and dismissed, when the screener got it wrong and no built-in pattern
reaches it.

Three decisions worth knowing before adding one.

**They live in code, not `data/rules.json`.** `data/*.json` is gitignored, so a rules file
there would never show up in a diff, never be reviewed, and never reach the `deploy`
branch the hosted app runs from. Here they are versioned, they ride along with
`scripts/publish.sh`, and the `vermin` 3.10 gate and the test suite both see them.

**They mark, they do not purge.** A rule sets `pets = no` or `suspected_short_term = yes`
and the app's own filter hides the listing. A misfired rule therefore mislabels something
you can still find by unticking a filter — where a rule that wrote to the blocklist would
delete it quietly and you would only notice the absence. The screener's hard purge stays
driven by the hand-maintained `SHORT_TERM_PATTERNS`; nothing here feeds it.

**A rule beats the derivation.** Whoever filed the 👎 opened the listing and read it. The
regex did not. So `evidence` records which rule fired and confidence goes to 1.0.

Adding one, always in this order — see RECOLLECT.md step 0:

    python -m quintal.rules test --attribute pets --pattern 'nao aceit\\w+ anima' --pool algarve

That prints how many listings the pattern hits, what we currently derive for each, and a
sample to eyeball. **Read the collateral count before writing the rule.** The pool's only
"animal" matches in Norte are street names — *Rua Sociedade Protectora dos Animais*, *Rua
de Diogo Cão* — and a pattern like `anima` would mark them all.

Patterns match against `prepare()`d text: folded (lowercase, accents stripped) with every
run of non-alphanumerics collapsed to one space. So write `nao aceita animais`, never
`não aceita animais`, and never rely on punctuation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# attribute → the verdicts a rule may assert for it. A derived boolean takes yes/no; a
# suspicion only ever fires positively, because "this is definitely not short-term" is not
# something a single phrase can establish.
ATTRIBUTES: dict[str, frozenset[str]] = {
    "pets": frozenset({"no", "yes"}),
    "yard": frozenset({"no", "yes"}),
    "bathtub": frozenset({"no", "yes"}),
    "short_term": frozenset({"yes"}),
}

_COLLAPSE = re.compile(r"[^a-z0-9]+")


def prepare(folded_text: str) -> str:
    """The one shape every rule pattern is matched against.

    Takes already-folded text (see `normalize.fold`) and collapses punctuation runs to
    single spaces, so an attribute label like "Animais de estimação: não permitido" reads
    as one continuous run and a rule never has to guess at a separator.
    """
    return _COLLAPSE.sub(" ", folded_text)


@dataclass(frozen=True)
class Rule:
    """One authored pattern. `id` is stable and never reused — evidence strings point at it.

    `source` is the provenance and is not optional: a rule whose origin nobody recorded
    cannot be judged later, and the whole point of these is that a person vouched for one.
    """

    id: str
    attribute: str
    verdict: str
    pattern: str
    source: str
    added: str  # ISO date
    note: str = ""

    def __post_init__(self) -> None:
        allowed = ATTRIBUTES.get(self.attribute)
        if allowed is None:
            raise ValueError(
                f"rule {self.id}: unknown attribute {self.attribute!r} "
                f"(known: {', '.join(sorted(ATTRIBUTES))})"
            )
        if self.verdict not in allowed:
            raise ValueError(
                f"rule {self.id}: {self.attribute} cannot be {self.verdict!r} "
                f"(allowed: {', '.join(sorted(allowed))})"
            )
        if not self.source.strip():
            raise ValueError(f"rule {self.id}: needs a source — where did this come from?")
        re.compile(self.pattern)  # fail at import, not mid-pull

    @property
    def regex(self) -> re.Pattern[str]:
        return re.compile(self.pattern)


# --- The authored rules -------------------------------------------------------
# Empty by design. These are written one at a time during a pull, each one traceable to a
# dismissal that the screener got wrong. A rule added without a 👎 behind it is a guess
# wearing a provenance string.
RULES: list[Rule] = []


def for_attribute(attribute: str) -> list[Rule]:
    return [rule for rule in RULES if rule.attribute == attribute]


def verdict_for(attribute: str, folded_text: str) -> tuple[str, Rule] | None:
    """First rule that fires for this attribute, or None.

    First rather than best: rules are ordered, few, and hand-written. If two disagree the
    answer is to fix one, not to invent a precedence scheme that hides the conflict.
    """
    text = prepare(folded_text)
    for rule in for_attribute(attribute):
        if rule.regex.search(text):
            return rule.verdict, rule
    return None


def matching(folded_text: str) -> list[Rule]:
    """Every rule that fires, across all attributes — for explaining a listing."""
    text = prepare(folded_text)
    return [rule for rule in RULES if rule.regex.search(text)]


# --- CLI ----------------------------------------------------------------------
# `quintal.feedback` imports `normalize`, which imports this module, so the corpus loader
# and the derivation functions are imported inside the commands rather than at module
# scope. The import cycle is real; deferring it is the cheap half of the fix.


_BOOL_WORD = {True: "yes", False: "no", None: "unknown"}


def current_verdict(attribute: str, text: str) -> tuple[str, str]:
    """What the pipeline says about this text today: `(verdict, detail)`.

    The verdict is in **the same vocabulary a rule asserts** — yes / no / unknown — so
    `rules test` can compare the two directly. That was not true at first: the short-term
    branch returned "caught (seasonal month-range span)" while a rule asserts "yes", so
    the two could never be equal, and the guard reported *every* match as a change with
    "0 already agree". On one candidate that turned 21 genuinely-new listings into a
    headline of 344 — in the one tool meant to be trusted right before a rule is written.
    `detail` keeps the human reason, which is worth showing but must not be compared.

    Raises on an unknown attribute rather than falling through to a default, so a new
    attribute with no reader cannot inherit another one's answer.
    """
    from . import screening
    from .normalize import BATHTUB_KEYWORDS, YARD_KEYWORDS, _derive_bool, _derive_pets, fold

    folded = fold(text)
    if attribute == "pets":
        return _derive_pets(folded).value, ""
    if attribute == "yard":
        return _BOOL_WORD[_derive_bool(folded, YARD_KEYWORDS).value], ""
    if attribute == "bathtub":
        return _BOOL_WORD[_derive_bool(folded, BATHTUB_KEYWORDS).value], ""
    if attribute == "short_term":
        reason = screening.short_term_reason(text)
        return ("yes", reason) if reason else ("no", "")
    raise ValueError(f"no current-verdict reader for attribute {attribute!r}")


def _cmd_test(args: object) -> int:
    """Dry-run a candidate pattern over a real pool and report what it would touch.

    This exists because the dangerous rule is not the one that matches nothing — it is the
    one that matches far more than its author pictured. `a casa e` reads like a specific
    phrase and hits 47 listings; `anima` catches three Porto street names. So the count
    comes before the rule, every time.
    """
    from collections import Counter

    from . import config
    from .feedback import load_corpus

    attribute: str = args.attribute  # type: ignore[attr-defined]
    if attribute not in ATTRIBUTES:
        print(f"unknown attribute {attribute!r} — known: {', '.join(sorted(ATTRIBUTES))}")
        return 1
    try:
        regex = re.compile(args.pattern)  # type: ignore[attr-defined]
    except re.error as exc:
        print(f"bad pattern: {exc}")
        return 1

    from .normalize import fold

    pool = config.pool_by_region(args.pool)  # type: ignore[attr-defined]
    corpus = load_corpus(pool)
    hits = []
    for listing_id, row in corpus.items():
        text = prepare(fold(f"{row.get('title', '')} {row.get('text', '')}"))
        match = regex.search(text)
        if match:
            hits.append((listing_id, row, match, text))

    verdict: str = args.verdict  # type: ignore[attr-defined]
    print(f"pattern   {args.pattern!r}")  # type: ignore[attr-defined]
    print(f"attribute {attribute} → {verdict}")
    print(f"pool      {args.pool} · {len(corpus)} rows")  # type: ignore[attr-defined]
    print(f"matches   {len(hits)}")
    if not hits:
        print("\nNothing matched. Either the phrasing differs, or the text is not in the store")
        print("(idealista detail pages are DataDome-blocked, so many rows are card previews).")
        return 0

    now: Counter[tuple[str, str]] = Counter()
    for _, row, _, _ in hits:
        now[current_verdict(attribute, f"{row.get('title', '')} {row.get('text', '')}")] += 1
    print("\nwhat we say about those today:")
    for (value, detail), count in now.most_common():
        shown = f"{value} ({detail})" if detail else value
        change = "" if value == verdict else "  ← the rule would change these"
        print(f"  {shown:<44} {count:>4}{change}")
    already = sum(count for (value, _), count in now.items() if value == verdict)
    print(f"\nwould change {len(hits) - already} listing(s); {already} already agree")

    limit: int = args.limit  # type: ignore[attr-defined]
    print(f"\nsample (first {min(limit, len(hits))}) — read these before adding the rule:")
    for listing_id, row, match, text in hits[:limit]:
        start, end = max(0, match.start() - 40), min(len(text), match.end() + 40)
        print(f"  {listing_id}  {row.get('title', '')[:58]}")
        print(f"      …{text[start:match.start()]}[{match.group(0)}]{text[match.end():end]}…")
    if len(hits) > limit:
        print(f"  … and {len(hits) - limit} more")
    return 0


def _cmd_list(_args: object) -> int:
    if not RULES:
        print("No authored rules yet.")
        print("They are written during a pull, one per dismissal the screener got wrong —")
        print("see RECOLLECT.md step 0. Dry-run first: python -m quintal.rules test --help")
        return 0
    print(f"{len(RULES)} authored rule(s):")
    for rule in RULES:
        print(f"\n  {rule.id}  {rule.attribute} → {rule.verdict}   (added {rule.added})")
        print(f"      pattern  {rule.pattern!r}")
        print(f"      source   {rule.source}")
        if rule.note:
            print(f"      note     {rule.note}")
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Searcher-authored rules that override a derived attribute."
    )
    parser.add_argument("command", choices=["list", "test"])
    parser.add_argument("--attribute", default="pets", help=f"one of: {', '.join(ATTRIBUTES)}")
    parser.add_argument("--verdict", default="no", help="what the rule would assert")
    parser.add_argument("--pattern", default="", help="regex, matched against prepare()d text")
    parser.add_argument("--pool", default="algarve", help="region slug (algarve | norte)")
    parser.add_argument("--limit", type=int, default=10, help="sample size to print")
    args = parser.parse_args(argv)

    if args.command == "list":
        return _cmd_list(args)
    if not args.pattern:
        print("test needs --pattern")
        return 1
    return _cmd_test(args)


if __name__ == "__main__":
    raise SystemExit(main())
