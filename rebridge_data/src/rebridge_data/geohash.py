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

import hashlib
import math

# Standard geohash base-32 alphabet (note: excludes a, i, l, o).
_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
_BASE32_INDEX = {char: index for index, char in enumerate(_BASE32)}

# ReBridge persists location at exactly Geohash5 precision — never finer.
GEOHASH_PRECISION = 5

# Mean Earth radius in kilometers, used by the haversine distance.
_EARTH_RADIUS_KM = 6371.0088

# Seeded-distance band (km) used when no real geo is available: the demo wants a
# stable, plausible "N km away" figure derived deterministically from an id.
_SEED_MIN_KM = 1.0
_SEED_SPAN = 90  # buckets of 0.1 km -> 1.0 .. 9.9 km inclusive.


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


def decode_geohash(geohash: str) -> tuple[float, float]:
    """Decode a geohash to the latitude/longitude centroid of its cell.

    Complements :func:`encode_geohash5`: it reverses the standard base-32
    interleave (longitude bit first) by widening, rather than narrowing, the
    latitude/longitude intervals as each bit is consumed, then returns the
    midpoint of the final cell. Decoding accepts a geohash of any length (not
    only Geohash5) so callers can compare neighborhoods at whatever precision
    they hold.

    Args:
        geohash: A geohash string drawn from the base-32 alphabet (case
            insensitive). Must be non-empty.

    Returns:
        A ``(lat, lon)`` pair of decimal degrees at the cell centroid.

    Raises:
        ValueError: If ``geohash`` is empty or contains a character outside the
            base-32 alphabet.
    """
    if not geohash:
        raise ValueError("geohash must be a non-empty string")

    lat_interval = [-90.0, 90.0]
    lon_interval = [-180.0, 180.0]
    even_bit = True  # When True the current bit refines longitude.

    for char in geohash.lower():
        try:
            char_index = _BASE32_INDEX[char]
        except KeyError as exc:
            raise ValueError(
                f"geohash contains invalid character: {char!r}"
            ) from exc
        # Each base-32 character carries five bits, most-significant first.
        for bit_position in range(4, -1, -1):
            bit = (char_index >> bit_position) & 1
            if even_bit:
                mid = (lon_interval[0] + lon_interval[1]) / 2
                if bit:
                    lon_interval[0] = mid
                else:
                    lon_interval[1] = mid
            else:
                mid = (lat_interval[0] + lat_interval[1]) / 2
                if bit:
                    lat_interval[0] = mid
                else:
                    lat_interval[1] = mid
            even_bit = not even_bit

    lat = (lat_interval[0] + lat_interval[1]) / 2
    lon = (lon_interval[0] + lon_interval[1]) / 2
    return lat, lon


def geohash_distance_km(geo_a: str, geo_b: str) -> float:
    """Return the haversine distance in km between two geohash centroids.

    Decodes each geohash to its cell centroid (see :func:`decode_geohash`) and
    computes the great-circle (haversine) distance between them, rounded to one
    decimal place. Two identical geohashes decode to the same centroid and so
    return ``0.0``.

    Args:
        geo_a: First geohash.
        geo_b: Second geohash.

    Returns:
        The great-circle distance in kilometers, rounded to one decimal.

    Raises:
        ValueError: If either geohash is empty or malformed.
    """
    lat_a, lon_a = decode_geohash(geo_a)
    lat_b, lon_b = decode_geohash(geo_b)

    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    d_phi = math.radians(lat_b - lat_a)
    d_lambda = math.radians(lon_b - lon_a)

    h = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))
    return round(_EARTH_RADIUS_KM * c, 1)


def seeded_distance_km(token: str) -> float:
    """Return a deterministic, stable demo distance in km for ``token``.

    When no real location is available (e.g. an item that is graded but not yet
    listed, so it carries no geohash), the demo still wants a plausible and
    *stable* "N km away" figure. This derives one from a SHA-256 hash of
    ``token`` so the same id always maps to the same distance across calls,
    spread across the ``[1.0, 9.9]`` km band in 0.1 km steps.

    Args:
        token: A stable identifier (e.g. a buyer id or item id).

    Returns:
        A distance in kilometers in ``[1.0, 9.9]``, rounded to one decimal.
    """
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    bucket = int(digest, 16) % _SEED_SPAN
    return round(_SEED_MIN_KM + bucket / 10.0, 1)
