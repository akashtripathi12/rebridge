"""Tests for the Geohash5 location encoding helper (Requirements 17.1, 17.2).

Covers:
- Known reference encodings against well-known coordinates.
- The output-is-always-length-5 invariant (precision bounded to Geohash5).
- Latitude/longitude bounds validation.
"""

import pytest

from rebridge_data.geohash import GEOHASH_PRECISION, encode_geohash5

# Well-known coordinate -> standard geohash. Each expected value is the
# five-character prefix of the canonical full-precision geohash for that point.
KNOWN_ENCODINGS = [
    # Classic Wikipedia example (full geohash "u4pruydqqvj...").
    ((57.64911, 10.40744), "u4pru"),
    # San Francisco (full geohash "9q8yyk8ytpxr...").
    ((37.7749, -122.4194), "9q8yy"),
    # London (full geohash "gcpvj0...").
    ((51.5074, -0.1278), "gcpvj"),
    # Null Island / origin.
    ((0.0, 0.0), "s0000"),
    # Extreme corners of the valid coordinate space.
    ((-90.0, -180.0), "00000"),
    ((90.0, 180.0), "zzzzz"),
]


@pytest.mark.parametrize("coord,expected", KNOWN_ENCODINGS)
def test_known_reference_encodings(coord, expected):
    lat, lon = coord
    assert encode_geohash5(lat, lon) == expected


@pytest.mark.parametrize("coord,expected", KNOWN_ENCODINGS)
def test_output_is_always_length_five(coord, expected):
    lat, lon = coord
    result = encode_geohash5(lat, lon)
    assert len(result) == GEOHASH_PRECISION == 5


def test_output_uses_only_base32_alphabet():
    allowed = set("0123456789bcdefghjkmnpqrstuvwxyz")
    result = encode_geohash5(12.9716, 77.5946)  # Bengaluru
    assert set(result) <= allowed


@pytest.mark.parametrize("lat", [-90.001, 90.001, 100.0, -100.0])
def test_rejects_out_of_range_latitude(lat):
    with pytest.raises(ValueError, match="lat"):
        encode_geohash5(lat, 0.0)


@pytest.mark.parametrize("lon", [-180.001, 180.001, 200.0, -200.0])
def test_rejects_out_of_range_longitude(lon):
    with pytest.raises(ValueError, match="lon"):
        encode_geohash5(0.0, lon)


@pytest.mark.parametrize("lat,lon", [(-90.0, -180.0), (90.0, 180.0), (0.0, 0.0)])
def test_accepts_boundary_coordinates(lat, lon):
    result = encode_geohash5(lat, lon)
    assert len(result) == 5


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_rejects_non_finite_values(bad):
    with pytest.raises(ValueError):
        encode_geohash5(bad, 0.0)
    with pytest.raises(ValueError):
        encode_geohash5(0.0, bad)
