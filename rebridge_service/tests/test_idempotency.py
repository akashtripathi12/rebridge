"""Unit tests for deterministic idempotency-key derivation (Requirement 7.2).

These example-based tests complement the Property 10 property test (task 8.2).
They pin down the concrete guarantees of the derivation: determinism,
order/duplicate-independence of the photo set, sensitivity to item id and photo
content, parity between str-key and bytes references, and the stable hex shape
of the output.
"""

from __future__ import annotations

from rebridge_service.idempotency import (
    derive_idempotency_key,
    derive_idempotency_key_from_photo_set_hash,
    photo_set_hash,
)


# --- Determinism ------------------------------------------------------------

def test_derivation_is_deterministic():
    photos = ["item-1/a.jpg", "item-1/b.jpg"]
    first = derive_idempotency_key("item-1", photos)
    second = derive_idempotency_key("item-1", photos)
    assert first == second


def test_photo_set_hash_is_deterministic():
    photos = ["a.jpg", "b.jpg", "c.jpg"]
    assert photo_set_hash(photos) == photo_set_hash(photos)


# --- Same inputs share a key; different inputs do not -----------------------

def test_same_item_and_photo_set_share_key():
    a = derive_idempotency_key("item-1", ["x.jpg", "y.jpg"])
    b = derive_idempotency_key("item-1", ["x.jpg", "y.jpg"])
    assert a == b


def test_different_item_id_yields_different_key():
    photos = ["x.jpg", "y.jpg"]
    assert derive_idempotency_key("item-1", photos) != derive_idempotency_key(
        "item-2", photos
    )


def test_different_photo_set_yields_different_key():
    a = derive_idempotency_key("item-1", ["x.jpg", "y.jpg"])
    b = derive_idempotency_key("item-1", ["x.jpg", "z.jpg"])
    assert a != b


# --- Photo set semantics: order- and duplicate-independent ------------------

def test_photo_order_does_not_change_key():
    ordered = derive_idempotency_key("item-1", ["a.jpg", "b.jpg", "c.jpg"])
    shuffled = derive_idempotency_key("item-1", ["c.jpg", "a.jpg", "b.jpg"])
    assert ordered == shuffled


def test_duplicate_photos_do_not_change_key():
    deduped = derive_idempotency_key("item-1", ["a.jpg", "b.jpg"])
    with_dupe = derive_idempotency_key("item-1", ["a.jpg", "b.jpg", "a.jpg"])
    assert deduped == with_dupe


# --- Bytes references ------------------------------------------------------

def test_bytes_photos_are_supported_and_deterministic():
    photos = [b"\x89PNG-bytes-1", b"\x89PNG-bytes-2"]
    assert derive_idempotency_key("item-1", photos) == derive_idempotency_key(
        "item-1", photos
    )


def test_bytes_order_independent():
    a = derive_idempotency_key("item-1", [b"one", b"two"])
    b = derive_idempotency_key("item-1", [b"two", b"one"])
    assert a == b


def test_different_bytes_content_yields_different_key():
    a = derive_idempotency_key("item-1", [b"one", b"two"])
    b = derive_idempotency_key("item-1", [b"one", b"three"])
    assert a != b


# --- Boundary-ambiguity: length-prefixing prevents collisions ---------------

def test_item_id_photo_boundary_is_unambiguous():
    # Without length-prefixing, ("ab", "c.jpg") and ("a", "bc.jpg") style
    # boundary shifts could collide. They must not here.
    from_hash_1 = derive_idempotency_key_from_photo_set_hash("ab", "c")
    from_hash_2 = derive_idempotency_key_from_photo_set_hash("a", "bc")
    assert from_hash_1 != from_hash_2


# --- Output shape -----------------------------------------------------------

def test_key_is_hex_sha256():
    key = derive_idempotency_key("item-1", ["a.jpg", "b.jpg"])
    assert len(key) == 64
    int(key, 16)  # raises ValueError if not valid hex


def test_photo_set_hash_is_hex_sha256():
    digest = photo_set_hash(["a.jpg"])
    assert len(digest) == 64
    int(digest, 16)


def test_empty_photo_set_is_handled():
    # An empty set is still deterministic and distinct from a non-empty one.
    assert derive_idempotency_key("item-1", []) == derive_idempotency_key("item-1", [])
    assert derive_idempotency_key("item-1", []) != derive_idempotency_key(
        "item-1", ["a.jpg"]
    )
