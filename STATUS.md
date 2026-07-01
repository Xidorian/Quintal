# Status — Quintal

**2026-07-01 — Step 1 (the brain) built on synthetic data.**

Fresh project. Stack agreed as **Python** (pandas / scikit-learn / Jinja2 + Streamlit
later); wrote the `python` stack profile before any code, per house rules.

Where it stands: the whole scoring/valuation pipeline runs end-to-end on ~20 **synthetic**
Algarve listings (`data/sample_listings.jsonl`, clearly flagged as not-real) and produces
a ranked static HTML page at `out/listings.html`. That proves the brain before we touch
collection. Included:
- `Listing` schema (Pydantic v2), PT+EN keyword derivation of yard/bathtub/pets w/ confidence.
- Match score 0–100 (yard-for-Luna weighted highest, graded beach-walkability).
- Hedonic ridge valuation on log(price) with peer-median fallback + confidence badge.
- Attribute-based dedup. Static Jinja2 render with 3 client-side sort modes.
- pytest suite over score / valuation / normalization.

**Caveats:** valuation is relative-to-pool only; sample data is synthetic so the numbers
are illustrative, not market truth. Enrichment (geocode / real beach walk-time / ruralness)
is stubbed — walk distances currently come from the sample data, not OSM.

**Left off:** brain proven. Next real work is collection (Idealista + Imovirtual via
browser session) and wiring live enrichment. See NEXT.md.
