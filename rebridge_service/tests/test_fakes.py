"""Tests that the in-memory fakes satisfy the data-layer interfaces.

These assert each fake is a genuine subclass/instance of its abstract base
class (so it honors the same contract the service layer is programmed against)
and exercise the contract-critical behaviors:

* idempotent conditional grade write (Requirement 7.3),
* review-queue priority-descending ordering (Requirement 14.1),
* presigned-URL TTL echo (Requirement 2.2),
* HMAC sign/verify round-trip and tamper detection (Requirements 11.2, 12.x),
* programmable grading-provider replay (Requirements 8.1-8.4),
* buyer-persona candidate filtering (Requirement 13.1).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from rebridge_data.interfaces import (
    BuyerPersonaRepository,
    CardSigner,
    EventPublisher,
    GradingProvider,
    ItemRepository,
    ObjectStore,
    QueueClient,
    ReviewQueueRepository,
)
from rebridge_data.models import (
    BuyerPersona,
    CardRecord,
    CatalogContext,
    DecisionRecord,
    GradeRecord,
    GradingMessage,
    ItemMeta,
    ItemStatus,
    LifecycleEvent,
    ListingPatch,
    ListingRecord,
    RawModelResponse,
    ReviewQueueEntry,
)

from tests.fakes import (
    FakeBuyerPersonaRepository,
    FakeCardSigner,
    FakeEventPublisher,
    FakeGradingProvider,
    FakeItemRepository,
    FakeObjectStore,
    FakeQueueClient,
    FakeReviewQueueRepository,
)


def _meta(item_id: str = "i1", status: ItemStatus = ItemStatus.CREATED) -> ItemMeta:
    return ItemMeta(
        item_id=item_id,
        status=status,
        category="electronics",
        age_months=12,
        context_source="manual",
        created_at="2024-01-01T00:00:00Z",
    )


def _grade(confidence: float = 0.9, summary: str = "ok") -> GradeRecord:
    return GradeRecord(grade="Good", confidence=confidence, summary=summary)


def _listing(item_id: str = "i1") -> ListingRecord:
    return ListingRecord(
        item_id=item_id,
        status="ACTIVE",
        category="electronics",
        price=Decimal("49.99"),
        geohash5="9q8yy",
        listed_at="2024-01-01T00:00:00Z",
    )


def test_fakes_are_instances_of_their_interfaces():
    assert isinstance(FakeItemRepository(), ItemRepository)
    assert isinstance(FakeReviewQueueRepository(), ReviewQueueRepository)
    assert isinstance(FakeObjectStore(), ObjectStore)
    assert isinstance(FakeQueueClient(), QueueClient)
    assert isinstance(FakeCardSigner(), CardSigner)
    assert isinstance(FakeEventPublisher(), EventPublisher)
    assert isinstance(FakeGradingProvider("nova"), GradingProvider)
    assert isinstance(FakeBuyerPersonaRepository(), BuyerPersonaRepository)


def test_item_repo_meta_and_status_round_trip():
    repo = FakeItemRepository()
    assert repo.get_item("i1") is None
    repo.put_item_meta(_meta())
    agg = repo.get_item("i1")
    assert agg is not None
    assert agg.meta.status is ItemStatus.CREATED
    assert agg.grade is None and agg.card is None

    repo.update_status("i1", ItemStatus.GRADED)
    assert repo.get_item("i1").meta.status is ItemStatus.GRADED

    with pytest.raises(KeyError):
        repo.update_status("missing", ItemStatus.GRADED)


def test_item_repo_returns_exactly_persisted_facets():
    repo = FakeItemRepository()
    repo.put_item_meta(_meta())
    repo.put_grade("i1", _grade())
    repo.put_listing("i1", _listing())

    agg = repo.get_item("i1")
    assert agg.grade is not None
    assert agg.listing is not None
    assert agg.card is None
    assert agg.decision is None


def test_put_grade_if_absent_is_idempotent():
    repo = FakeItemRepository()
    repo.put_item_meta(_meta())

    first = repo.put_grade_if_absent("i1", "idem-1", _grade(summary="first"))
    assert first is True
    assert repo.get_grade("i1").summary == "first"

    # Same idem_key -> retained unchanged, returns False (Requirement 7.3).
    second = repo.put_grade_if_absent("i1", "idem-1", _grade(summary="second"))
    assert second is False
    assert repo.get_grade("i1").summary == "first"

    # A different idem_key writes.
    third = repo.put_grade_if_absent("i1", "idem-2", _grade(summary="third"))
    assert third is True
    assert repo.get_grade("i1").summary == "third"


def test_item_repo_persisted_state_is_isolated_from_caller():
    repo = FakeItemRepository()
    repo.put_item_meta(_meta())
    grade = _grade(summary="original")
    repo.put_grade("i1", grade)
    grade.summary = "mutated-by-caller"
    assert repo.get_grade("i1").summary == "original"


def test_card_lookup_by_card_id():
    repo = FakeItemRepository()
    card = CardRecord(
        card_id="card-1",
        item_id="i1",
        signature="sig",
        qr_target="/cards/card-1/verify",
        graded_at="2024-01-01T00:00:00Z",
        warranty_stance="30-day",
    )
    repo.put_card("i1", card)
    assert repo.get_card("card-1").item_id == "i1"
    assert repo.get_card("nope") is None
    assert repo.get_item("i1") is None  # no meta persisted


def test_listing_crud_and_marketplace_query():
    repo = FakeItemRepository()
    repo.put_item_meta(_meta())
    repo.put_listing("i1", _listing())
    assert repo.get_listing("i1").status == "ACTIVE"

    updated = repo.update_listing("i1", ListingPatch(price=Decimal("10.00")))
    assert updated.price == Decimal("10.00")
    assert repo.get_listing("i1").price == Decimal("10.00")

    found = repo.query_marketplace("electronics", geo="9q8")
    assert len(found) == 1
    assert repo.query_marketplace("toys") == []

    repo.delete_listing("i1")
    assert repo.get_listing("i1") is None

    with pytest.raises(KeyError):
        repo.update_listing("i1", ListingPatch(price=Decimal("1")))


def test_put_decision_round_trip():
    repo = FakeItemRepository()
    repo.put_item_meta(_meta())
    decision = DecisionRecord(
        disposition="RESELL",
        price=Decimal("20"),
        value=Decimal("30"),
        cost=Decimal("10"),
        margin=Decimal("20"),
        rationale="value 30, cost 10, margin 20",
    )
    repo.put_decision("i1", decision)
    assert repo.get_item("i1").decision.disposition == "RESELL"


def test_review_queue_orders_by_priority_descending():
    repo = FakeReviewQueueRepository()
    repo.enqueue(ReviewQueueEntry(item_id="low", value=Decimal("10"), confidence=0.5, priority=5.0))
    repo.enqueue(ReviewQueueEntry(item_id="high", value=Decimal("100"), confidence=0.2, priority=80.0))
    repo.enqueue(ReviewQueueEntry(item_id="mid", value=Decimal("50"), confidence=0.4, priority=30.0))

    pending = repo.list_pending(limit=10)
    assert [e.item_id for e in pending] == ["high", "mid", "low"]
    assert [e.item_id for e in repo.list_pending(limit=2)] == ["high", "mid"]

    assert repo.get("high").item_id == "high"
    repo.resolve("high")
    assert repo.get("high") is None
    assert [e.item_id for e in repo.list_pending(limit=10)] == ["mid", "low"]


def test_object_store_presign_echoes_ttl_and_round_trips_bytes():
    store = FakeObjectStore()
    url = store.presign_put("items/i1/photo-0.jpg", ttl_seconds=300)
    assert url.method == "PUT"
    assert url.expires_in == 300
    assert "items/i1/photo-0.jpg" in url.url
    assert store.presigned == [url]

    custom = store.presign_put("k", ttl_seconds=60)
    assert custom.expires_in == 60

    store.put_object("k", b"bytes")
    assert store.get_bytes("k") == b"bytes"
    with pytest.raises(KeyError):
        store.get_bytes("missing")


def test_queue_client_captures_messages():
    queue = FakeQueueClient()
    msg = GradingMessage(item_id="i1", idem_key="idem-1", photo_keys=["a", "b"])
    queue.send_grading_message(msg)
    assert len(queue.messages) == 1
    assert queue.messages[0].item_id == "i1"


def test_card_signer_sign_verify_and_tamper_detection():
    signer = FakeCardSigner()
    payload = b"card-1|i1|Good|2024-01-01T00:00:00Z"
    sig = signer.sign(payload)
    assert signer.verify(payload, sig) is True
    # Any change to payload or signature fails verification.
    assert signer.verify(payload + b"x", sig) is False
    assert signer.verify(payload, sig[:-1] + ("0" if sig[-1] != "0" else "1")) is False
    # Deterministic.
    assert signer.sign(payload) == sig


def test_event_publisher_captures_and_filters_events():
    pub = FakeEventPublisher()
    pub.publish(LifecycleEvent(event_type="GRADED", item_id="i1"))
    pub.publish(LifecycleEvent(event_type="ROUTED", item_id="i1", payload={"disposition": "RESELL"}))
    assert len(pub.events) == 2
    assert [e.item_id for e in pub.events_of("GRADED")] == ["i1"]


def test_grading_provider_replays_script_in_order():
    catalog = CatalogContext(category="electronics")
    provider = FakeGradingProvider(
        "nova",
        script=[
            RawModelResponse(provider_name="nova", content='{"grade": "Good"}'),
            "not json",
        ],
    )
    assert provider.name == "nova"
    first = provider.grade([b"img"], catalog)
    assert first.content == '{"grade": "Good"}'
    second = provider.grade([b"img"], catalog)
    assert second.content == "not json"
    assert second.provider_name == "nova"
    assert len(provider.calls) == 2


def test_grading_provider_can_script_exceptions_and_repeat_last():
    catalog = CatalogContext(category="electronics")
    timeout = TimeoutError("model timed out")
    provider = FakeGradingProvider("claude", script=[timeout])
    # Single-element script repeats: always raises.
    with pytest.raises(TimeoutError):
        provider.grade([b"img"], catalog)
    with pytest.raises(TimeoutError):
        provider.grade([b"img"], catalog)
    assert len(provider.calls) == 2


def test_grading_provider_without_script_raises():
    provider = FakeGradingProvider("empty")
    with pytest.raises(RuntimeError):
        provider.grade([b"img"], CatalogContext(category="x"))


def test_buyer_persona_repository_filters_by_geo_and_category():
    repo = FakeBuyerPersonaRepository(
        personas=[
            BuyerPersona(buyer_id="b1", geohash5="9q8yy", persona_type="deal_seeker", category_interests=["electronics"]),
            BuyerPersona(buyer_id="b2", geohash5="9q8yy", persona_type="price_balker", category_interests=["toys"]),
            BuyerPersona(buyer_id="b3", geohash5="dr5ru", persona_type="deal_seeker", category_interests=["electronics"]),
        ]
    )
    candidates = repo.candidates(geo="9q8", category="electronics")
    assert [c.buyer_id for c in candidates] == ["b1"]

    repo.add(BuyerPersona(buyer_id="b4", geohash5="9q8yz", persona_type="deal_seeker", category_interests=["electronics"]))
    assert {c.buyer_id for c in repo.candidates(geo="9q8", category="electronics")} == {"b1", "b4"}
