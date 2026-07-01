"""Pure geographic helpers — no network, so they're cheap to test."""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000.0

# Walking-time estimate from straight-line distance (used when no routing key is set).
WALK_SPEED_M_PER_MIN = 80.0  # ~4.8 km/h
WALK_DETOUR = 1.3  # streets aren't straight lines


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two lat/lng points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def estimate_walk_minutes(dist_m: float) -> float:
    """Rough walking minutes from a straight-line distance, with a detour factor.

    A first approximation until real routing (OpenRouteService) is wired in.
    """
    return dist_m * WALK_DETOUR / WALK_SPEED_M_PER_MIN
