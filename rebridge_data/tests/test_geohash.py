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


# ---------------------------------------------------------------------------
# decode + haversine distance (G-distance helper)
# ---------------------------------------------------------------------------

from rebridge_data.geohash import (  # noqa: E402
    decode_geohash,
    geohash_distance_km,
    seeded_distance_km,
)


@pytest.mark.parametrize("coord", [(37.7749, -122.4194), (51.5074, -0.1278), (0.0, 0.0)])
def test_decode_is_within_cell_of_encode(coord):
    """A decoded geohash centroid lies close to the coordinate it encoded.

    Geohash5 cells are ~5 km, so the centroid is within a few km of the source.
    """
    lat, lon = coord
    gh = encode_geohash5(lat, lon)
    dlat, dlon = decode_geohash(gh)
    # Centroid is within the cell, so within ~0.05 deg lat / lon of the source.
    assert abs(dlat - lat) < 0.05
    assert abs(dlon - lon) < 0.06


def test_identical_geohashes_have_zero_distance():
    assert geohash_distance_km("9q8yy", "9q8yy") == 0.0


def test_nearby_geohashes_are_closer_than_far_ones():
    """Two adjacent SF neighborhoods are far closer than SF vs NYC."""
    # 9q8yy / 9q8yz are adjacent San Francisco cells.
    near = geohash_distance_km("9q8yy", "9q8yz")
    # dr5ru is on the US east coast (New York area).
    far = geohash_distance_km("9q8yy", "dr5ru")
    assert near < far
    assert near < 20.0
    assert far > 3000.0


def test_distance_is_symmetric_and_rounded():
    a_to_b = geohash_distance_km("9q5ct", "dr72j")
    b_to_a = geohash_distance_km("dr72j", "9q5ct")
    assert a_to_b == b_to_a
    # Rounded to one decimal place.
    assert round(a_to_b, 1) == a_to_b


@pytest.mark.parametrize("bad", ["", "!", "ailo"])
def test_decode_rejects_empty_or_invalid(bad):
    with pytest.raises(ValueError):
        decode_geohash(bad)


def test_seeded_distance_is_deterministic_and_in_band():
    first = seeded_distance_km("buy_001")
    second = seeded_distance_km("buy_001")
    assert first == second
    assert 1.0 <= first <= 9.9


def test_seeded_distance_varies_by_token():
    values = {seeded_distance_km(f"buy_{i:03d}") for i in range(20)}
    # Not all identical — the hash spreads tokens across the band.
    assert len(values) > 1
