"""Perceptual image hashing for photo-based dedup (QT-032).

dHash (difference hash): shrink to grayscale, encode whether each pixel is brighter than
its right neighbour → a 64-bit fingerprint. Two encodings of the *same* photo (re-encoded
or lightly resized across sites) stay within a few bits; unrelated photos are far apart.

Used only as a *corroborating* signal in dedup — never alone, because different properties
sometimes share a generic/agency photo (dHash distance 0). See dedup.py for the guards.
"""

from __future__ import annotations

from pathlib import Path


def dhash(path: str | Path, size: int = 8) -> int | None:
    """64-bit difference hash of the image at `path`, or None if it can't be read."""
    from PIL import Image

    try:
        img = Image.open(path).convert("L").resize((size + 1, size))
    except (OSError, ValueError):
        return None
    px = img.tobytes()  # row-major, one byte per pixel (grayscale)
    width = size + 1
    bits = 0
    for row in range(size):
        base = row * width
        for col in range(size):
            bits = (bits << 1) | (1 if px[base + col] > px[base + col + 1] else 0)
    return bits


def hamming(a: int, b: int) -> int:
    """Number of differing bits between two hashes."""
    return (a ^ b).bit_count()
