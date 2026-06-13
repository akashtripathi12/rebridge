"""Property-based test for missing-required-field rejection on item creation.

# Feature: rebridge-backend, Property 2: Missing required field is rejected with field identified

Property 2 (design.md): *For any* otherwise-valid creation request with exactly
one required field removed, creation SHALL be rejected with a validation error
naming the removed field.

**Validates: Requirements 1.3**

The strategy builds a fully valid creation request in one of the two allowed
context shapes, then removes (or nulls) exactly one of that shape's required
fields. Required fields are:

* ``order_scan``: ``context_source``, ``category``, ``age_months``, ``order_id``
* ``manual``:     ``context_source``, ``category``, ``age_months``

The test asserts that ``create_item`` raises :class:`MissingField` whose
``.field`` equals the omitted field (Requirement 1.3), and that nothing was
persisted as a side effect of the rejected request.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_service.item_service import (
    ItemService,
    MissingField,
    ORDER_SCAN,
    MANUAL,
)

from tests.fakes import FakeItemRepository

# Minimum iterations per the spec's property-testing guideline (>= 100).
_ITERATIONS = 200

# Required-field sets per context shape (mirrors item_service validation).
_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    ORDER_SCAN: ("context_source", "category", "age_months", "order_id"),
    MANUAL: ("context_source", "category", "age_months"),
}

# Generators for each valid field value (constrained to the valid input space).
_category = st.text(min_size=1, max_size=30)
_age_months = st.integers(min_value=0, max_value=600)
_order_id = st.text(min_size=1, max_size=30)


def _valid_request(draw: st.DrawFn, context_source: str) -> dict:
    """Build a fully valid creation request for the given context shape."""
    request = {
        "context_source": context_source,
        "category": draw(_category),
        "age_months": draw(_age_months),
    }
    if context_source == ORDER_SCAN:
        request["order_id"] = draw(_order_id)
    return request


@st.composite
def request_with_one_missing_field(draw: st.DrawFn) -> tuple[dict, str]:
    """Generate an otherwise-valid request with exactly one required field gone.

    Returns the mutated request paired with the name of the omitted field. The
    field is either deleted outright or set to ``None`` (both are treated as
    "missing" by the service), exercising Requirement 1.3 across both context
    shapes.
    """
    context_source = draw(st.sampled_from((ORDER_SCAN, MANUAL)))
    request = _valid_request(draw, context_source)

    omitted = draw(st.sampled_from(_REQUIRED_FIELDS[context_source]))
    if draw(st.booleans()):
        del request[omitted]
    else:
        request[omitted] = None

    return request, omitted


@settings(max_examples=_ITERATIONS)
@given(request_with_one_missing_field())
def test_missing_required_field_is_rejected_naming_the_field(
    case: tuple[dict, str],
) -> None:
    """Omitting exactly one required field is rejected, identifying that field.

    Validates Requirement 1.3: the rejection is a :class:`MissingField` whose
    ``.field`` is the omitted field, and no item is persisted.
    """
    request, omitted = case
    repo = FakeItemRepository()
    svc = ItemService(item_repo=repo)

    try:
        svc.create_item(request)
    except MissingField as exc:
        # The validation error must name exactly the omitted field.
        assert exc.field == omitted
        assert omitted in str(exc)
    else:
        raise AssertionError(
            f"expected MissingField for omitted {omitted!r}, but creation succeeded"
        )

    # The rejected request must not have persisted any item meta.
    assert repo._meta == {}  # type: ignore[attr-defined]
