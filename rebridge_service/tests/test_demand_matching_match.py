"""Unit tests for the Demand_Matching_Engine top-N push, placement, emission.

Covers the part of Requirement 13 beyond ranking, plus Requirement 15.4:
- 13.5 push a proactive notification to exactly the top min(N, count) ranked
  buyers and upsert the Item onto the Second-Chance PDP shelf
- 15.4 emit a MATCHED event identifying the Item when the engine pushes to
  ranked buyers

These exercise real business logic against the in-memory fakes
(FakeBuyerPersonaRepository, FakeBuyerNotifier, FakeSecondChanceShelf,
FakeEventPublisher) wired through the real EventingService — no AWS, no mocks.
"""

from __future__ import annotations

import pytest

from rebridge_data.models import BuyerPersona

from rebridge_service.demand_matching_engine import (
    DemandMatchingEngine,
    MatchResult,
)
from rebridge_service.eventing_service import EventingService
from rebridge_service.models import EventType

from .fakes import (
    FakeBuyerNotifier,
    FakeBuyerPersonaRepository,
    FakeEventPublisher,
    FakeSecondChanceShelf,
)

ITEM_ID = "item-123"
GEO = "9q8yy"
CATEGORY = "electronics"


def _persona(
    buyer_id: str,
    *,
    geohash5: str = GEO,
    persona_type: str = "browser",
    category_interests: list[str] | None = None,
    intent: float = 0.0,
    lifecycle: float = 0.0,
    price_sensitivity: float = 0.0,
) -> BuyerPersona:
    return BuyerPersona(
        buyer_id=buyer_id,
        geohash5=geohash5,
        persona_type=persona_type,
        category_interests=(
            category_interests if category_interests is not None else [CATEGORY]
        ),
        intent=intent,
        lifecycle=lifecycle,
        price_sensitivity=price_sensitivity,
    )


def _build_engine(
    personas: list[BuyerPersona],
    *,
    top_n: int = 5,
):
    """Wire an engine with all match collaborators and return it plus the fakes."""
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
        top_n=top_n,
    )
    return engine, notifier, shelf, publisher


# --------------------------------------------------------------------------
# Exact top-N selection (Requirement 13.5)
# --------------------------------------------------------------------------
def test_match_notifies_exactly_top_n_in_rank_order():
    # Five ranked candidates, N=2 -> exactly the two highest-scoring notified.
    engine, notifier, _shelf, _pub = _build_engine(
        [
            _persona("a", intent=0.1),
            _persona("b", intent=0.9),
            _persona("c", intent=0.5),
            _persona("d", intent=0.7),
            _persona("e", intent=0.3),
        ],
        top_n=2,
    )

    result = engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY)

    # Highest scores are b (0.9) then d (0.7).
    assert notifier.buyers_for(ITEM_ID) == ["b", "d"]
    assert [c.persona.buyer_id for c in result.notified] == ["b", "d"]
    # notified is the prefix of the full ranking.
    assert result.notified == result.ranking[:2]


def test_match_caps_notifications_at_count_when_n_exceeds_count():
    # N=10 but only 3 candidates -> notify exactly min(N, count) == 3.
    engine, notifier, _shelf, _pub = _build_engine(
        [
            _persona("a", intent=0.2),
            _persona("b", intent=0.8),
            _persona("c", intent=0.5),
        ],
        top_n=10,
    )

    result = engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY)

    assert set(notifier.buyers_for(ITEM_ID)) == {"a", "b", "c"}
    assert len(result.notified) == 3
    assert len(result.notified) == len(result.ranking)


def test_match_with_n_equal_to_count_notifies_all():
    engine, notifier, _shelf, _pub = _build_engine(
        [_persona("a", intent=0.3), _persona("b", intent=0.6)],
        top_n=2,
    )

    engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY)

    assert sorted(notifier.buyers_for(ITEM_ID)) == ["a", "b"]


def test_match_with_no_candidates_notifies_no_one_but_still_places_and_emits():
    engine, notifier, shelf, publisher = _build_engine([], top_n=3)

    result = engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY)

    assert notifier.notifications == []
    assert result.notified == ()
    # Placement and MATCHED still happen for an empty ranking.
    assert ITEM_ID in shelf
    assert len(publisher.events_of(EventType.MATCHED.value)) == 1


def test_match_per_call_top_n_overrides_configured_default():
    engine, notifier, _shelf, _pub = _build_engine(
        [
            _persona("a", intent=0.9),
            _persona("b", intent=0.7),
            _persona("c", intent=0.5),
        ],
        top_n=3,
    )

    engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY, top_n=1)

    assert notifier.buyers_for(ITEM_ID) == ["a"]


# --------------------------------------------------------------------------
# Shelf upsert (Requirement 13.5)
# --------------------------------------------------------------------------
def test_match_upserts_item_onto_second_chance_shelf():
    engine, _notifier, shelf, _pub = _build_engine([_persona("a", intent=0.5)])

    engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY)

    assert ITEM_ID in shelf
    assert shelf.items == [ITEM_ID]
    assert shelf.upsert_counts[ITEM_ID] == 1


def test_repeated_match_keeps_single_shelf_placement():
    # Upsert is idempotent on identity: the Item appears once regardless of
    # how many times it is matched.
    engine, _notifier, shelf, _pub = _build_engine([_persona("a", intent=0.5)])

    engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY)
    engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY)

    assert shelf.items == [ITEM_ID]
    assert shelf.upsert_counts[ITEM_ID] == 2


# --------------------------------------------------------------------------
# MATCHED emission (Requirement 15.4)
# --------------------------------------------------------------------------
def test_match_emits_exactly_one_matched_event_identifying_the_item():
    engine, _notifier, _shelf, publisher = _build_engine(
        [_persona("a", intent=0.5), _persona("b", intent=0.9)]
    )

    result = engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY)

    matched = publisher.events_of(EventType.MATCHED.value)
    assert len(matched) == 1
    assert matched[0].item_id == ITEM_ID
    assert matched[0].event_type == EventType.MATCHED.value
    # The returned event is the one that was published.
    assert result.event == matched[0]


def test_match_emits_matched_even_with_no_candidates():
    engine, _notifier, _shelf, publisher = _build_engine([])

    engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY)

    matched = publisher.events_of(EventType.MATCHED.value)
    assert len(matched) == 1
    assert matched[0].item_id == ITEM_ID


# --------------------------------------------------------------------------
# Result shape and ordering integration
# --------------------------------------------------------------------------
def test_match_result_ranking_is_descending_and_notified_is_its_prefix():
    engine, _notifier, _shelf, _pub = _build_engine(
        [
            _persona("low", intent=0.1),
            _persona("high", intent=0.9),
            _persona("mid", intent=0.5),
        ],
        top_n=2,
    )

    result = engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY)

    assert isinstance(result, MatchResult)
    assert [c.persona.buyer_id for c in result.ranking] == ["high", "mid", "low"]
    assert result.notified == result.ranking[:2]
    scores = [c.score for c in result.ranking]
    assert scores == sorted(scores, reverse=True)


# --------------------------------------------------------------------------
# Configuration / wiring validation
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad_top_n", [0, -1, True, 1.5])
def test_invalid_top_n_rejected_at_construction(bad_top_n):
    with pytest.raises(ValueError):
        DemandMatchingEngine(
            FakeBuyerPersonaRepository(),
            notifier=FakeBuyerNotifier(),
            shelf=FakeSecondChanceShelf(),
            eventing=EventingService(FakeEventPublisher()),
            top_n=bad_top_n,
        )


@pytest.mark.parametrize("bad_top_n", [0, -5])
def test_invalid_per_call_top_n_rejected(bad_top_n):
    engine, _notifier, _shelf, _pub = _build_engine([_persona("a", intent=0.5)])
    with pytest.raises(ValueError):
        engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY, top_n=bad_top_n)


def test_match_without_injected_collaborators_raises():
    # The filtering/scoring/ranking core can be built without match seams, but
    # match() must fail clearly until they are injected.
    engine = DemandMatchingEngine(FakeBuyerPersonaRepository())
    with pytest.raises(RuntimeError):
        engine.match(item_id=ITEM_ID, geo=GEO, category=CATEGORY)
