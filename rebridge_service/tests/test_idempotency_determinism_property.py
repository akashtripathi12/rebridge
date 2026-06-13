"""Property-based test for idempotency-key determinism.

# Feature: rebridge-backend, Property 10: Idempotency-key determinism

Property 10 (design.md): *For any* item identifier and photo set, the derived
Idempotency_Key SHALL be deterministic, and two submissions SHALL share a key
if and only if they have the same item identifier and the same photo-set hash.

**Validates: Requirements 7.2**

The strategies below generate arbitrary item identifiers and photo sets. A
photo set is modeled as a *set* of references (storage keys and/or raw bytes),
matching the order- and duplicate-independent semantics of the derivation. The
test asserts both directions of the "if and only if":

* **Determinism / shared key:** the same item id paired with the same photo set
  (regardless of the order in which photos are supplied, and regardless of
  duplicate occurrences) always yields the same key.
* **Distinctness:** changing the item id, or changing the underlying photo set,
  changes the key.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_service.idempotency import derive_idempotency_key, photo_set_hash

# Minimum iterations per the spec's property-testing guideline.
_ITERATIONS = 200

# An item identifier: an arbitrary non-empty string.
_item_id = st.text(min_size=1, max_size=40)

# A single photo reference: either a storage key (str) or raw bytes. Both are
# supported by the derivation, so the generator exercises both forms.
_photo_ref = st.one_of(
    st.text(min_size=1, max_size=30),
    st.binary(min_size=0, max_size=30),
)


def _canonical(photos):
    """Canonicalize a photo set the way the derivation does: by content hash.

    Two photo sets are "the same set" precisely when their per-photo content
    digests form the same set. Using ``photo_set_hash`` as the canonical form
    lets the test compare sets uniformly across str and bytes references and
    independently of order and duplicates.
    """

    return photo_set_hash(photos)


# A photo set as an *ordered list* of references (so we can also exercise
# ordering), drawn from a deduplicated pool so we can construct genuinely
# distinct sets when needed.
_photo_list = st.lists(_photo_ref, min_size=0, max_size=6)


@settings(max_examples=_ITERATIONS)
@given(_item_id, _photo_list)
def test_derivation_is_deterministic(item_id: str, photos: list) -> None:
    """The same item id and photo set always derive the same key.

    Validates Requirement 7.2: the Idempotency_Key is a deterministic function
    of the item identifier and the photo-set hash.
    """

    assert derive_idempotency_key(item_id, photos) == derive_idempotency_key(
        item_id, photos
    )


@settings(max_examples=_ITERATIONS)
@given(_item_id, _photo_list, st.randoms(use_true_random=False))
def test_key_is_order_and_duplicate_independent(
    item_id: str, photos: list, rng
) -> None:
    """Reordering and duplicating photos does not change the key.

    A photo *set* is order- and duplicate-insensitive, so two submissions with
    the same underlying set share a key regardless of presentation order or
    repeated entries (Requirement 7.2).
    """

    shuffled = list(photos)
    rng.shuffle(shuffled)
    # Append a duplicate of an existing photo (if any) to confirm set semantics.
    if photos:
        shuffled.append(photos[rng.randrange(len(photos))])

    assert derive_idempotency_key(item_id, photos) == derive_idempotency_key(
        item_id, shuffled
    )


@settings(max_examples=_ITERATIONS)
@given(_item_id, _item_id, _photo_list)
def test_different_item_id_yields_different_key(
    item_id_a: str, item_id_b: str, photos: list
) -> None:
    """Different item ids over the same photo set derive different keys.

    Validates the "only if same item identifier" direction of Requirement 7.2.
    """

    if item_id_a == item_id_b:
        return  # Same id: covered by the determinism property instead.

    assert derive_idempotency_key(item_id_a, photos) != derive_idempotency_key(
        item_id_b, photos
    )


@settings(max_examples=_ITERATIONS)
@given(_item_id, _photo_list, _photo_list)
def test_different_photo_set_yields_different_key(
    item_id: str, photos_a: list, photos_b: list
) -> None:
    """Different photo sets under the same item id derive different keys.

    Validates the "only if same photo-set hash" direction of Requirement 7.2.
    Sets are compared by their canonical content hash so that order/duplicate
    variations of the *same* set are excluded from this branch.
    """

    if _canonical(photos_a) == _canonical(photos_b):
        return  # Same underlying set: covered by determinism instead.

    assert derive_idempotency_key(item_id, photos_a) != derive_idempotency_key(
        item_id, photos_b
    )


@settings(max_examples=_ITERATIONS)
@given(_item_id, _item_id, _photo_list, _photo_list)
def test_keys_match_iff_inputs_match(
    item_id_a: str, item_id_b: str, photos_a: list, photos_b: list
) -> None:
    """Two submissions share a key iff same item id and same photo set.

    Directly asserts the biconditional of Property 10 / Requirement 7.2 across
    arbitrary input pairs.
    """

    same_inputs = item_id_a == item_id_b and _canonical(photos_a) == _canonical(
        photos_b
    )
    keys_match = derive_idempotency_key(item_id_a, photos_a) == derive_idempotency_key(
        item_id_b, photos_b
    )

    assert keys_match == same_inputs
