"""Geohash5 location encoding helper (Requirements 17.1, 17.2).

ReBridge stores location for matching only as a *Geohash5* — a five-character
geohash representing an approximate (~5 km) neighborhood rather than an exact
address. This is a data-minimization measure: no representation finer than
Geohash5 is ever produced or persisted.

This module is dependency-free (Python stdlib only) and implements the standard
geohash base-32 algorithm. The single public function, :func:`encode_geohash5`,
encodes a latitude/longitude pair to exactly five characters.
"""

from __future__ import annotations

# Standard geohash base-32 alphabet (note: excludes a, i, l, o).
_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"

# ReBridge persists location at exactly Geohash5 precision — never finer.
GEOHASH_PRECISION = 5


def encode_geohash5(lat: float, lon: float) -> str:
    """Encode a coordinate to a five-character geohash.

    Implements the standard geohash algorithm: longitude and latitude bits are
    interleaved (longitude first) by repeatedly bisecting each interval, and
    every five accumulated bits are mapped to one base-32 character. Encoding
    stops at exactly :data:`GEOHASH_PRECISION` characters, so the result is
    always length 5 and never encodes precision finer than Geohash5
    (Requirements 17.1, 17.2).

    Args:
        lat: Latitude in decimal degrees, within ``[-90, 90]``.
        lon: Longitude in decimal degrees, within ``[-180, 180]``.

    Returns:
        A five-character geohash string drawn from the base-32 alphabet.

    Raises:
        ValueError: If ``lat`` or ``lon`` is outside its valid range, or is not
            a finite number.
    """
    lat_f = _validate_coordinate(lat, "lat", -90.0, 90.0)
    lon_f = _validate_coordinate(lon, "lon", -180.0, 180.0)

    lat_interval = [-90.0, 90.0]
    lon_interval = [-180.0, 180.0]

    geohash_chars: list[str] = []
    bit = 0
    char_index = 0
    even_bit = True  # When True the current bit refines longitude.

    while len(geohash_chars) < GEOHASH_PRECISION:
        if even_bit:
            mid = (lon_interval[0] + lon_interval[1]) / 2
            if lon_f >= mid:
                char_index = (char_index << 1) | 1
                lon_interval[0] = mid
            else:
                char_index = char_index << 1
                lon_interval[1] = mid
        else:
            mid = (lat_interval[0] + lat_interval[1]) / 2
            if lat_f >= mid:
                char_index = (char_index << 1) | 1
                lat_interval[0] = mid
            else:
                char_index = char_index << 1
                lat_interval[1] = mid

        even_bit = not even_bit

        bit += 1
        if bit == 5:
            geohash_chars.append(_BASE32[char_index])
            bit = 0
            char_index = 0

    return "".join(geohash_chars)


def _validate_coordinate(value: float, name: str, low: float, high: float) -> float:
    """Coerce ``value`` to float and ensure it is finite and within bounds."""
    try:
        coerced = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc

    # Reject NaN / infinity, which would silently corrupt the bisection.
    if coerced != coerced or coerced in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be a finite number")

    if coerced < low or coerced > high:
        raise ValueError(f"{name} must be within [{low}, {high}], got {coerced}")

    return coerced
