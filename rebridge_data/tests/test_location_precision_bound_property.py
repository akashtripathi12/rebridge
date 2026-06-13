"""Property-based test for location precision bounded to Geohash5.

# Feature: rebridge-backend, Property 29: Location precision is bounded to Geohash5

Property 29 (design.md): *For any* location input, the persisted location value
SHALL be a five-character geohash and no representation finer than Geohash5
SHALL be stored.

**Validates: Requirements 17.1, 17.2**

The strategies below generate arbitrary valid coordinates: latitudes in
``[-90, 90]`` and longitudes in ``[-180, 180]``. For every such input the test
asserts the precision bound holds:

* the encoder returns a string of *exactly* five characters (never finer than
  Geohash5 — Requirement 17.2), and
* every character is drawn from the standard geohash base-32 alphabet
  (Requirement 17.1), and
* encoding is deterministic — the same coordinate always encodes to the same
  value (a precondition for persisting a single coarse representation).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.geohash import GEOHASH_PRECISION, encode_geohash5

# Minimum iterations per the spec's property-testing guideline.
_ITERATIONS = 200

# The standard geohash base-32 alphabet (excludes a, i, l, o).
_BASE32_ALPHABET = set("0123456789bcdefghjkmnpqrstuvwxyz")

# Valid coordinate ranges. ``allow_nan``/``allow_infinity`` are disabled so the
# generator stays within the well-defined input space the encoder accepts.
_latitude = st.floats(
    min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False
)
_longitude = st.floats(
    min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False
)


@settings(max_examples=_ITERATIONS)
@given(_latitude, _longitude)
def test_encoding_is_exactly_geohash5_from_alphabet(lat: float, lon: float) -> None:
    """Any valid coordinate encodes to exactly five base-32 characters.

    Validates Requirements 17.1 and 17.2: the persisted location is a
    five-character geohash and no representation finer than Geohash5 is
    produced.
    """

    result = encode_geohash5(lat, lon)

    assert isinstance(result, str)
    assert len(result) == GEOHASH_PRECISION == 5
    assert set(result) <= _BASE32_ALPHABET


@settings(max_examples=_ITERATIONS)
@given(_latitude, _longitude)
def test_encoding_is_deterministic(lat: float, lon: float) -> None:
    """The same coordinate always encodes to the same Geohash5 value.

    Determinism guarantees a single coarse representation is persisted for a
    given location, reinforcing the precision bound of Requirements 17.1, 17.2.
    """

    assert encode_geohash5(lat, lon) == encode_geohash5(lat, lon)
