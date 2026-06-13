"""Property-based test for the Demand_Matching_Engine top-N push and placement.

# Feature: rebridge-backend, Property 23: Top-N push and placement

Property 23 (design.md): *For any* ranking and configured N, the
Demand_Matching_Engine SHALL notify exactly the top min(N, count) buyers,
upsert the Item onto the Second-Chance PDP shelf, and emit a MATCHED event
identifying the Item.

**Validates: Requirements 13.5, 15.4**

This test drives :meth:`DemandMatchingEngine.match` over arbitrary seeded
persona pools and an arbitrary configured ``N``, exercised against the
in-memory fakes (:class:`FakeBuyerPersonaRepository`,
:class:`FakeBuyerNotifier`, :class:`FakeSecondChanceShelf`,
:class:`FakeEventPublisher`) wired through the real
:class:`EventingService` -- no AWS, no mocks. Every generated persona shares
the listed Item's category and geohash so it survives filtering; this makes
``count`` (the number of ranked candidates) equal to the size of the pool and
lets the property reason directly about min(N, count).

It asserts the universal properties:

* exactly ``min(N, count)`` buyers are notified -- never more than ``N`` and
  never more than the number of ranked candidates;
* the notified buyers are, in order, exactly the top-N prefix of the engine's
  own ``rank()`` output (notification happens in ranking order);
* the Item is upserted onto the Second-Chance shelf exactly once and appears
  there once regardless of the ranking (idempotent placement);
* exactly one MATCHED event is emitted and it identifies the listed Item.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.models import BuyerPersona

from rebridge_service.demand_matching_engine import DemandMatchingEngine
from rebridge_service.eventing_service import EventingService
from rebridge_service.models import EventType

from .fakes import (
    FakeBuyerNotifier,
    FakeBuyerPersonaRepository,
    FakeEventPublisher,
    FakeSecondChanceShelf,
)

ITEM_ID = "item-prop23"
GEO = "9q8yy"
CATEGORY = "electronics"

# Persona types span both favored (deal_seeker / price_balker) and non-favored
# kinds so the generated rankings exercise the anti-cannibalization bias too.
_PERSONA_TYPES = ["browser", "researcher", "deal_seeker", "price_balker"]

_signal = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


def _persona(values: dict) -> BuyerPersona:
    """Build a filter-surviving persona (same category + geohash as the Item)."""
    return BuyerPersona(
        buyer_id=values["buyer_id"],
        geohash5=GEO,
        persona_type=values["persona_type"],
        category_interests=[CATEGORY],
        intent=values["intent"],
        lifecycle=values["lifecycle"],
        price_sensitivity=values["price_sensitivity"],
    )


# A pool of personas with unique buyer ids so notified ordering is unambiguous.
_pool = st.lists(
    st.fixed_dictionaries(
        {
            "buyer_id": st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
                min_size=1,
                max_size=10,
            ),
            "persona_type": st.sampled_from(_PERSONA_TYPES),
            "intent": _signal,
            "lifecycle": _signal,
            "price_sensitivity": _signal,
        }
    ),
    max_size=12,
    unique_by=lambda v: v["buyer_id"],
)


@settings(max_examples=200)
@given(pool=_pool, n=st.integers(min_value=1, max_value=20))
def test_top_n_push_and_placement(pool, n):
    personas = [_persona(v) for v in pool]
    repo = FakeBuyerPersonaRepository(personas=personas)
    notifier = FakeBuyerNotifier()
    shelf = FakeSecondChanceShelf()
    publisher = FakeEventPublisher()
    eventing = EventingService(publisher)
    engine = DemandMatchingEngine(
        repo,
        notifier=notifier,
        shelf=shelf,
        eventing=eventing,
        top_n=n,
    )

    # The expected ranking, computed independently via the engine's rank().
    expected_ranking = engine.rank(GEO, CATEGORY)
    count = len(expected_ranking)
    cutoff = min(n, count)
    expected_top = expected_ranking[:cutoff]
    expected_buyer_ids = [c.persona.buyer_id for c in expected_top]

    result = engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY)

    # 1) Exactly min(N, count) buyers notified -- never more than N, never more
    #    than the number of ranked candidates.
    assert len(result.notified) == cutoff
    assert len(notifier.notifications) == cutoff

    # 2) Notified buyers are exactly the top-N prefix of rank(), in rank order.
    assert [c.persona.buyer_id for c in result.notified] == expected_buyer_ids
    assert notifier.buyers_for(ITEM_ID) == expected_buyer_ids
    assert result.notified == result.ranking[:cutoff]
    # Every notification targets the listed Item.
    assert all(item_id == ITEM_ID for _buyer, item_id in notifier.notifications)

    # 3) The Item is upserted onto the Second-Chance shelf exactly once
    #    (idempotent placement): present once regardless of the ranking.
    assert ITEM_ID in shelf
    assert shelf.items == [ITEM_ID]
    assert shelf.upsert_counts[ITEM_ID] == 1

    # 4) Exactly one MATCHED event is emitted, identifying the listed Item.
    matched = publisher.events_of(EventType.MATCHED.value)
    assert len(matched) == 1
    assert matched[0].item_id == ITEM_ID
    assert matched[0].event_type == EventType.MATCHED.value
    assert result.event == matched[0]
