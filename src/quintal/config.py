"""Tunable constants for scoring and valuation.

Everything a searcher might want to nudge lives here, not scattered through the code.
"""

from __future__ import annotations

# --- Match score weights (sum = 100 → match_score is directly 0–100) ---
# The Algarve default: yard + ocean-beach walkability lead.
WEIGHTS: dict[str, float] = {
    "yard": 25,  # highest — a yard for Luna; partial credit for terrace/balcony
    "beach_walk": 20,  # graded by walking minutes to the nearest beach
    "house": 12,  # house over apartment
    "two_bathrooms": 10,
    "two_bedrooms": 10,  # exactly 2 ideal, more is fine
    "bathtub": 8,
    "rural": 10,  # more rural (further from town centre) scores higher
    "budget_headroom": 5,  # cheaper than the budget cap = small bonus
}
assert sum(WEIGHTS.values()) == 100, "weights must total 100"

# The Norte set (Porto + Douro + Minho): the move is *away from concrete*, so greenery/
# nature walkability, quiet (rural), and water (river beaches, via the shared beach axis)
# lead alongside the yard. `beach_walk` here scores nearest water — river beach or ocean.
WEIGHTS_NORTE: dict[str, float] = {
    "yard": 22,
    "green_walk": 18,  # walk-minutes to nearest green space (park/garden/reserve) — Luna walks
    "beach_walk": 16,  # water: nearest river beach or ocean
    "rural": 12,  # quiet / out of the concrete
    "house": 10,
    "two_bedrooms": 8,
    "two_bathrooms": 6,
    "bathtub": 4,
    "budget_headroom": 4,
}
assert sum(WEIGHTS_NORTE.values()) == 100, "norte weights must total 100"

# Region → weight set. score_listing falls back to WEIGHTS when a region is unmapped.
REGION_WEIGHTS: dict[str, dict[str, float]] = {"algarve": WEIGHTS, "norte": WEIGHTS_NORTE}

# --- Beach walkability (graded, in walking minutes) ---
# Full credit up to FULL, linear decay to FLOOR_SCORE at MID, zero beyond ZERO.
WALK_FULL_MIN = 15.0
WALK_MID_MIN = 30.0
WALK_ZERO_MIN = 45.0
WALK_MID_SCORE = 0.4  # a 30-min place still worth it if the yard carries it
WALK_UNKNOWN_SCORE = 0.4  # neutral-ish when we don't know the walk time

# --- Ruralness ---
RURAL_FULL_DIST_M = 4000.0  # distance to town centre that earns full "rural" credit
RURAL_UNKNOWN_SCORE = 0.5

# --- Budget ---
BUDGET_CAP_EUR = 1500.0  # cheaper than this earns headroom credit

# --- Valuation bands ---
VALUATION_THRESHOLD = 0.10  # ±10% → fair; below → undervalued; above → overpriced
BANDS = {
    "undervalued": {"emoji": "🟢", "label": "Undervalued"},
    "fair": {"emoji": "⚪", "label": "Fair"},
    "overpriced": {"emoji": "🔴", "label": "Overpriced"},
}

# --- Valuation model selection ---
MIN_POOL_FOR_MODEL = 40  # below this the hedonic model overfits → peer-median fallback
PEER_MIN_FOR_MEDIUM = 5  # comparables in the peer bucket for a "medium" confidence
PEER_MIN_FOR_HIGH = 10

# --- Valuation fit robustness ---
# The hedonic model is fit only on rents within this many MADs of the median log(rent), so
# parse-error / sale-leak / luxury outliers don't distort the coefficients. All listings are
# still SCORED from the fitted model — trimming affects the fit set only. MAD-based (not a
# fixed percentile) so a single extreme outlier is caught even in a small pool. 0 disables it.
VALUATION_FIT_MAD_K = 3.5

# --- Dedup tolerances ---
DEDUP_SIZE_TOL = 0.05
DEDUP_PRICE_TOL = 0.05
# Photo-hash dedup (QT-032): a second pass that catches dupes the attribute rule misses
# because the concelho was parsed differently across sites (freguesia vs concelho). Merge
# only when the thumbnails match closely AND bedrooms + price corroborate — a shared generic
# photo alone must not merge two different flats.
DEDUP_PHASH_MAX_DIST = 6  # max dHash Hamming distance to consider two photos "the same"
DEDUP_PHASH_PRICE_TOL = 0.10  # rents must be within this for a photo match to merge
