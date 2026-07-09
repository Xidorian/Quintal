"""Quintal — interactive rental finder (Phase 4).

Reads the collected pool, runs the full brain (screen → enrich → value → score), and
lets the searcher filter, sort, and 👍/👎 listings and whole areas. Preferences persist
to data/preferences.json so they survive re-collection.

Run:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from quintal.pipeline import run
from quintal.preferences import Preferences
from quintal.render_html import _view

LISTINGS = "data/listings.jsonl"
PREFS_PATH = "data/preferences.json"

st.set_page_config(page_title="Quintal — Algarve rentals", page_icon="🏡", layout="wide")


@st.cache_data(show_spinner="Screening, enriching, valuing…")
def load_views(input_path: str, enrich: bool) -> list[dict]:
    return [_view(listing) for listing in run(input_path, enrich=enrich)]


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
prefs = Preferences(PREFS_PATH)
st.sidebar.title("🏡 Quintal")
st.sidebar.caption("Algarve rental finder — for Malia & Luna")

enrich = st.sidebar.checkbox("Enrich (beach walk-time, ruralness)", value=True)
try:
    views = load_views(LISTINGS, enrich)
except FileNotFoundError:
    st.error(f"No listings file at `{LISTINGS}`. Collect some first (see NEXT.md).")
    st.stop()

if not views:
    st.warning("No listings in the pool yet.")
    st.stop()

# --- Sidebar filters ----------------------------------------------------------
st.sidebar.header("Filters")
prices = [v["price"] for v in views]
max_price = st.sidebar.slider(
    "Max €/month", 0, int(max(prices)) + 100, min(1500, int(max(prices)) + 100), step=50
)
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
max_walk = st.sidebar.slider("Max beach walk (min, 0 = any)", 0, 120, 0, step=5)

st.sidebar.header("View")
sort_mode = st.sidebar.radio("Sort", ["Best fit", "Best deal", "Fit + deal"])
show_disliked = st.sidebar.checkbox("Show 👎 / disliked areas", value=False)
show_hidden = st.sidebar.checkbox("Show hidden", value=False)

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
st.title("Algarve rentals")
st.caption(
    f"Showing **{len(rows)}** of {len(views)} listings · "
    "Valuation is *relative to the current pool*, not an official appraisal."
)

# --- Cards --------------------------------------------------------------------
for v in rows:
    state = prefs.listing_state(v["id"])
    border = {"liked": "🟩", "disliked": "🟥"}.get(state, "")
    with st.container(border=True):
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
        with actions:
            like_label = "💚 Liked" if state == "liked" else "👍 Like"
            pass_label = "💔 Passed" if state == "disliked" else "👎 Pass"
            if st.button(like_label, key=f"like-{v['id']}", use_container_width=True):
                prefs.like(v["id"])
                prefs.save()
                st.rerun()
            if st.button(pass_label, key=f"pass-{v['id']}", use_container_width=True):
                prefs.dislike(v["id"])
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
