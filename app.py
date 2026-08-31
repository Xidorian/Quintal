"""Quintal — interactive rental finder (Phase 4).

Reads the collected pool, runs the full brain (screen → enrich → value → score), and
lets the searcher filter, sort, and 👍/👎 listings and whole areas. A 👎 asks *why* —
the reason + note land in the shared preferences log, which `python -m quintal.feedback
report` reads before the next pull to harden collection. Preferences persist to
data/preferences.json (or the shared Gist) so they survive re-collection.

Run:  streamlit run app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Streamlit Cloud pip-installs requirements.txt but does not `pip install -e .`, so make
# the src-layout package importable both there and in a local venv.
sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from quintal import config
from quintal.feedback import REASONS, context_from_view, label_of
from quintal.photos import photo_path
from quintal.pipeline import run
from quintal.preferences import GistBackend, Preferences
from quintal.render_html import _view

PREFS_PATH = "data/preferences.json"
SEARCHERS = ["Malia", "Alexander"]

# Pools live in config.POOLS so the app and the CLIs read one definition.
POOLS = config.POOLS

st.set_page_config(page_title="Quintal — rental finder", page_icon="🏡", layout="wide")


def _secret(name: str) -> str | None:
    """Read a secret from st.secrets (hosted) first, then the environment (local)."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # no secrets.toml at all → fall through to env
        pass
    return os.getenv(name)


def _load_prefs() -> Preferences:
    """Shared Gist store when configured, else the local JSON file."""
    gist_id, token = _secret("QUINTAL_GIST_ID"), _secret("QUINTAL_GITHUB_TOKEN")
    if gist_id and token:
        return Preferences(backend=GistBackend(gist_id, token))
    return Preferences(PREFS_PATH)


@st.cache_data(show_spinner="Screening, enriching, valuing…")
def load_views(pool_name: str, enrich: bool) -> list[dict]:
    pool = POOLS[pool_name]
    kwargs = {k: v for k, v in pool.items() if k.endswith("_path")}
    listings = run(
        pool["listings"],
        enrich=enrich,
        region=pool["region"],
        min_beds=pool.get("min_beds") or None,
        **kwargs,
    )
    return [_view(listing) for listing in listings]


def deal_norm(v: dict, lo: float, hi: float) -> float:
    """0–100, higher = better deal (more undervalued)."""
    pct = v.get("valuation_pct")
    if pct is None:
        return 0.0
    return 50.0 if hi == lo else 100.0 * (hi - pct) / (hi - lo)


def base_sort_value(v: dict, mode: str, lo: float, hi: float) -> float:
    if mode == "Best deal":
        return deal_norm(v, lo, hi)
    if mode == "Fit + deal":
        return 0.5 * (v.get("match_score") or 0) + 0.5 * deal_norm(v, lo, hi)
    return v.get("match_score") or 0  # Best fit


def pets_badge(v: dict) -> str:
    return {"yes": "🐾 pets ok", "no": "🚫 no pets"}.get(v["pets"], "🐾 pets unknown")


# --- Load ---------------------------------------------------------------------
try:
    prefs = _load_prefs()
except RuntimeError as exc:  # shared store unreachable — don't proceed and risk clobbering it
    st.error(f"Couldn't reach the shared preferences store: {exc}")
    st.stop()
st.sidebar.title("🏡 Quintal")
st.sidebar.caption("Rental finder — for Malia & Luna")

pool_name = st.sidebar.selectbox("Region pool", list(POOLS), index=0)
pool = POOLS[pool_name]
default_searcher = _secret("QUINTAL_USER") or SEARCHERS[0]
searcher = st.sidebar.selectbox(
    "You are",
    SEARCHERS,
    index=SEARCHERS.index(default_searcher) if default_searcher in SEARCHERS else 0,
    help="Signs your 👎 notes so we know whose call it was.",
)
is_norte = pool["region"] == "norte"
# Norte optimises for greenery/nature/river; Algarve for ocean-beach walkability.
water_label = "river/ocean" if is_norte else "beach"

# Geo comes from the shipped sidecar (data/geo*.json); live enrich is an offline/local
# backfill only — never in the hosted request path (it would geocode gaps on every load).
enrich = st.sidebar.checkbox(
    "Live-enrich gaps (slow — local backfill only)", value=False
)
try:
    views = load_views(pool_name, enrich)
except FileNotFoundError:
    st.error(f"No listings file at `{pool['listings']}`. Collect some first (see NEXT.md).")
    st.stop()

if not views:
    st.warning("No listings in the pool yet.")
    st.stop()

# --- Sidebar filters ----------------------------------------------------------
st.sidebar.header("Filters")
prices = [v["price"] for v in views]
# Long-term budget tops out at €3000 — anything above ~€2000 is out of scope, so a slider
# that stretched to a stray €30k listing was useless. Over-cap listings still get filtered out.
budget_max = min(int(max(prices)) + 100, 3000)
max_price = st.sidebar.slider("Max €/month", 0, budget_max, min(1500, budget_max), step=50)
min_beds = st.sidebar.number_input("Min bedrooms", 0, 6, 0)
sizes = [v["size"] for v in views if v["size"]]
size_cap = int(max(sizes)) if sizes else 300
size_range = st.sidebar.slider("Size (m²)", 0, size_cap, (0, size_cap), step=5)
size_active = size_range != (0, size_cap)  # a listing with unknown size is only dropped once this is narrowed
yard_only = st.sidebar.checkbox("Yard only")
hide_no_pets = st.sidebar.checkbox("Exclude explicit no-pets", value=True)
bands = st.sidebar.multiselect("Valuation band", ["undervalued", "fair", "overpriced"])
concelhos = sorted({v["concelho"] for v in views})
picked_concelhos = st.sidebar.multiselect("Concelho", concelhos)
max_walk = st.sidebar.slider(f"Max water walk — {water_label} (min, 0 = any)", 0, 120, 0, step=5)
max_green = (
    st.sidebar.slider("Max greenery walk (min, 0 = any)", 0, 120, 0, step=5) if is_norte else 0
)

st.sidebar.header("View")
sort_mode = st.sidebar.radio("Sort", ["Best fit", "Best deal", "Fit + deal"])
show_disliked = st.sidebar.checkbox("Show 👎 / disliked areas", value=False)
show_hidden = st.sidebar.checkbox("Show hidden", value=False)

open_notes = [e for e in prefs.open_feedback() if not e.get("pool") or e.get("pool") == pool_name]
if open_notes:
    with st.sidebar.expander(f"🗒️ Pass notes ({len(open_notes)})"):
        st.caption("Feeds the next pull — `python -m quintal.feedback report`.")
        for entry in reversed(open_notes[-12:]):
            who = f" · {entry['by']}" if entry.get("by") else ""
            st.markdown(
                f"**{label_of(entry.get('reason', 'other'))}**{who}  \n"
                f"{(entry.get('title') or '')[:60]}"
                + (f"  \n*“{entry['note']}”*" if entry.get("note") else "")
            )

if prefs.areas:
    st.sidebar.header("Area sentiment")
    for concelho, sentiment in sorted(prefs.areas.items()):
        emoji = "👍" if sentiment == "like" else "👎"
        if st.sidebar.button(f"{emoji} {concelho}  ✕", key=f"clear-{concelho}"):
            prefs.set_area(concelho, None)
            prefs.save()
            st.rerun()

# --- Filter -------------------------------------------------------------------
pcts = [v["valuation_pct"] for v in views if v["valuation_pct"] is not None]
lo, hi = (min(pcts + [0]), max(pcts + [0]))


def keep(v: dict) -> bool:
    if v["id"] in prefs.hidden and not show_hidden:
        return False
    if not show_disliked and (
        v["id"] in prefs.disliked or prefs.area_of(v["concelho"]) == "dislike"
    ):
        return False
    if v["price"] > max_price:
        return False
    if (v["beds"] or 0) < min_beds:
        return False
    if v["size"] is not None:
        if not (size_range[0] <= v["size"] <= size_range[1]):
            return False
    elif size_active:  # unknown size can't be confirmed in range once the filter is set
        return False
    if yard_only and not v["yard"]:
        return False
    if hide_no_pets and v["pets"] == "no":
        return False
    if bands and v["band"] not in bands:
        return False
    if picked_concelhos and v["concelho"] not in picked_concelhos:
        return False
    if max_walk and (v["walk_min"] is None or v["walk_min"] > max_walk):
        return False
    if max_green and (v.get("walk_min_green") is None or v["walk_min_green"] > max_green):
        return False
    return True


rows = [v for v in views if keep(v)]
rows.sort(
    key=lambda v: (
        prefs.preference_rank(v["id"], v["concelho"]),
        base_sort_value(v, sort_mode, lo, hi),
    ),
    reverse=True,
)

# --- Header -------------------------------------------------------------------
st.title(f"{pool_name} rentals")
st.caption(
    f"Showing **{len(rows)}** of {len(views)} listings · "
    "Valuation is *relative to the current pool*, not an official appraisal."
)

# --- Cards --------------------------------------------------------------------
for v in rows:
    state = prefs.listing_state(v["id"])
    border = {"liked": "🟩", "disliked": "🟥"}.get(state, "")
    with st.container(border=True):
        photo = photo_path(v["id"])
        if photo.exists():
            photo_col, top, actions = st.columns([1, 2.4, 1])
            photo_col.image(str(photo), use_container_width=True)
        else:
            top, actions = st.columns([3, 1])
        with top:
            walk = (
                f"🏖️ {v['walk_min']:.0f} min to beach"
                if v["walk_min"] is not None
                else "🏖️ walk unknown"
            )
            band_pct = (
                f" {v['valuation_pct'] * 100:+.0f}%" if v["valuation_pct"] is not None else ""
            )
            conf = f" · {v['confidence']} confidence" if v["confidence"] else ""
            size = v["size"] or "?"
            beds = v["beds"] if v["beds"] is not None else "?"
            baths = v["baths"] if v["baths"] is not None else "?"
            spec = f"{v['type']} · {beds}bd · {baths}ba · {size} m² · {v['concelho']}"
            st.markdown(
                f"### {border} €{v['price']:.0f}/mo · fit {v['match_score']}/100\n"
                f"**{v['title']}**  \n"
                f"{spec}  \n"
                f"{v['band_emoji']} **{v['band_label']}**{band_pct}{conf} · {walk}"
            )
            tags = []
            if v["yard"]:
                tags.append("🌳 yard")
            elif v["terrace"]:
                tags.append("🪴 terrace")
            if v["bathtub"]:
                tags.append("🛁 bathtub")
            tags.append(pets_badge(v))
            if v["furnished"] is True:
                tags.append("furnished")
            st.caption(" · ".join(tags))
            if v["why"]:
                st.caption("💶 " + " · ".join(v["why"]))
            if v["url"]:
                st.markdown(f"[Open listing ↗]({v['url']})")
            passed_note = prefs.latest_feedback(v["id"]) if state == "disliked" else None
            if passed_note:
                who = f" · {passed_note['by']}" if passed_note.get("by") else ""
                quote = f" — “{passed_note['note']}”" if passed_note.get("note") else ""
                st.caption(f"👎 {label_of(passed_note.get('reason', 'other'))}{quote}{who}")
        with actions:
            like_label = "💚 Liked" if state == "liked" else "👍 Like"
            pass_label = "💔 Passed" if state == "disliked" else "👎 Pass"
            if st.button(like_label, key=f"like-{v['id']}", use_container_width=True):
                prefs.like(v["id"])
                prefs.save()
                st.rerun()
            # A pass is one click and asks nothing — most passes are just "not for us".
            # The reason is a separate, optional follow-up (it's what hardens the next
            # pull, so it's offered, never demanded).
            if st.button(pass_label, key=f"pass-{v['id']}", use_container_width=True):
                prefs.dislike(v["id"])  # toggles; un-passing retracts the note behind it
                prefs.save()
                st.rerun()
            if state == "disliked":
                why_label = "✏️ Edit reason" if passed_note else "＋ Add a reason"
                with st.popover(why_label, use_container_width=True):
                    st.caption("Optional — but it's what hardens the next pull.")
                    code = st.selectbox(
                        "Reason",
                        list(REASONS),
                        format_func=label_of,
                        key=f"why-{v['id']}",
                    )
                    st.caption(REASONS[code].hint or "")
                    note = st.text_input(
                        "In your own words"
                        + (" (required for this reason)" if code == "other" else " (optional)"),
                        key=f"note-{v['id']}",
                        placeholder=(
                            "what was wrong with it?"
                            if code == "other"
                            else "quote the giveaway line if there is one"
                        ),
                    )
                    if st.button("Save reason", key=f"savepass-{v['id']}", type="primary"):
                        if code == "other" and not note.strip():
                            st.warning("Tell us what it was — otherwise the note says nothing.")
                        else:
                            # Editing replaces rather than stacks — otherwise one listing's
                            # change of mind would count twice in the report.
                            prefs.retract_feedback(v["id"])
                            prefs.add_feedback(
                                v["id"],
                                reason=code,
                                note=note,
                                by=searcher,
                                context=context_from_view(v, pool_name),
                            )
                            prefs.save()
                            st.rerun()
            if st.button("🙈 Hide", key=f"hide-{v['id']}", use_container_width=True):
                prefs.hide(v["id"])
                prefs.save()
                st.rerun()
            area = prefs.area_of(v["concelho"])
            area_col1, area_col2 = st.columns(2)
            if area_col1.button(
                "👍 area" if area != "like" else "✅",
                key=f"al-{v['id']}",
                help=f"Like {v['concelho']}",
            ):
                prefs.set_area(v["concelho"], None if area == "like" else "like")
                prefs.save()
                st.rerun()
            if area_col2.button(
                "👎 area" if area != "dislike" else "🚫",
                key=f"ad-{v['id']}",
                help=f"Dislike {v['concelho']}",
            ):
                prefs.set_area(v["concelho"], None if area == "dislike" else "dislike")
                prefs.save()
                st.rerun()
