"""Deterministic idempotency-key derivation for grading submissions.

Requirement 7.2 states: *THE Grading_Pipeline SHALL derive an Idempotency_Key
from the item identifier and the photo-set hash for each grading submission.*
The derived key is used by the pipeline (Requirement 7.3) to deduplicate
processing: a submission whose key has already produced a persisted grade is
skipped rather than reprocessed.

This module is the single source of truth for that derivation. It is pure
(standard-library :mod:`hashlib` only, no I/O, no AWS, no service collaborators)
so it can be exercised directly by property tests against the determinism
invariant.

Design (Property 10): *For any* item identifier and photo set, the derived
Idempotency_Key SHALL be deterministic, and two submissions SHALL share a key
if and only if they have the same item identifier and the same photo-set hash.

To honour that "if and only if":

* The derivation is a pure function of its inputs, so it is **deterministic** -
  the same inputs always yield the same key.
* A photo *set* is order-independent: the photos are hashed individually and
  their digests sorted before combination, so reordering the same photos does
  not change the result. The set is also duplicate-insensitive, matching set
  semantics.
* Every variable-length component is length-prefixed before hashing so that no
  two distinct ``(item_id, photo_set)`` pairs can serialize to the same byte
  stream (avoiding boundary-ambiguity collisions such as ``"ab" + "c"`` vs
  ``"a" + "bc"``). Combined with a collision-resistant hash, distinct inputs
  therefore yield distinct keys.
"""

from __future__ import annotations

import hashlib
from typing import Iterable, Union

__all__ = [
    "PhotoRef",
    "photo_set_hash",
    "derive_idempotency_key",
    "derive_idempotency_key_from_photo_set_hash",
]

# A photo may be referenced either by its storage key (an S3 object key, a
# string) or by its raw bytes. Both are supported so the key can be derived
# before upload (from the planned keys) or after (from the fetched bytes).
PhotoRef = Union[str, bytes, bytearray]

# Domain-separation tags keep the photo-set hash and the final key in distinct
# hash "namespaces" so a photo-set digest can never be mistaken for a finished
# idempotency key.
_PHOTO_DOMAIN = b"rebridge.photo-set.v1"
_KEY_DOMAIN = b"rebridge.idempotency-key.v1"


def _to_bytes(value: PhotoRef) -> bytes:
    """Normalize a single photo reference to bytes for hashing."""

    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    raise TypeError(
        f"photo reference must be str, bytes, or bytearray, got {type(value).__name__}"
    )


def _length_prefixed(chunk: bytes) -> bytes:
    """Length-prefix a byte chunk so concatenations are unambiguous.

    Using a fixed-width big-endian length header guarantees that distinct
    sequences of chunks can never serialize to the same byte stream, which is
    what makes the overall derivation injective up to hash collisions.
    """

    return len(chunk).to_bytes(8, "big") + chunk


def photo_set_hash(photos: Iterable[PhotoRef]) -> str:
    """Compute an order-independent hash of a photo set.

    Each photo is referenced by its storage key (``str``) or raw bytes. The
    per-photo digests are sorted before combination, so the result is
    independent of the order in which photos are supplied and insensitive to
    duplicates - matching the "photo *set*" semantics of Requirement 7.2.

    Returns the hex-encoded SHA-256 digest of the set.
    """

    # Hash each photo reference, then sort the digests. Sorting the digests
    # (rather than the raw refs) gives a stable order regardless of input order
    # and works uniformly for keys and bytes. Deduplicating enforces true set
    # semantics: the same photo supplied twice does not change the hash.
    per_photo_digests = sorted(
        {hashlib.sha256(_to_bytes(photo)).digest() for photo in photos}
    )

    hasher = hashlib.sha256()
    hasher.update(_PHOTO_DOMAIN)
    # Include the count so an empty set differs cleanly from other inputs and so
    # the prefixing remains unambiguous.
    hasher.update(len(per_photo_digests).to_bytes(8, "big"))
    for digest in per_photo_digests:
        hasher.update(_length_prefixed(digest))
    return hasher.hexdigest()


def derive_idempotency_key_from_photo_set_hash(item_id: str, photo_set_hash_hex: str) -> str:
    """Derive the Idempotency_Key from an item id and a precomputed set hash.

    This is the canonical combination step. Both components are length-prefixed
    before hashing so that two distinct ``(item_id, photo_set_hash)`` pairs can
    never collide on the serialized byte stream.

    Returns the hex-encoded SHA-256 digest used as the Idempotency_Key.
    """

    if not isinstance(item_id, str):
        raise TypeError(f"item_id must be a string, got {type(item_id).__name__}")
    if not isinstance(photo_set_hash_hex, str):
        raise TypeError(
            f"photo_set_hash_hex must be a string, got {type(photo_set_hash_hex).__name__}"
        )

    hasher = hashlib.sha256()
    hasher.update(_KEY_DOMAIN)
    hasher.update(_length_prefixed(item_id.encode("utf-8")))
    hasher.update(_length_prefixed(photo_set_hash_hex.encode("utf-8")))
    return hasher.hexdigest()


def derive_idempotency_key(item_id: str, photos: Iterable[PhotoRef]) -> str:
    """Derive the Idempotency_Key for a grading submission (Requirement 7.2).

    Combines the item identifier with the order-independent photo-set hash. The
    result is deterministic and shared by two submissions if and only if they
    have the same item identifier and the same photo set.

    Returns the hex-encoded SHA-256 digest used as the Idempotency_Key.
    """

    return derive_idempotency_key_from_photo_set_hash(item_id, photo_set_hash(photos))
