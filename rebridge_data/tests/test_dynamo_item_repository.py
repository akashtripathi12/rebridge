"""Unit tests for :class:`DynamoItemRepository` (Requirements 1.6, 3.3, 7.3, 13.1).

The table + GSIs are created inside a moto ``mock_aws`` fixture so the tests run
fully in-process with no real AWS calls. The schema mirrors design.md: base
table ``PK``/``SK`` plus GSI1 (marketplace), GSI2 (geo), GSI3 (review queue).
"""

from __future__ import annotations

from decimal import Decimal

import boto3
import pytest
from moto import mock_aws

from rebridge_data.dynamo_item_repository import (
    GSI1_MARKETPLACE,
    GSI1_PK,
    GSI1_SK,
    GSI2_GEO,
    GSI2_PK,
    GSI2_SK,
    GSI3_PK,
    GSI3_REVIEW,
    GSI3_SK,
    DynamoItemRepository,
)
from rebridge_data.models import (
    CardRecord,
    CompletenessResult,
    DecisionRecord,
    Defect,
    GradeRecord,
    ItemMeta,
    ItemStatus,
    ListingPatch,
    ListingRecord,
)

TABLE_NAME = "rebridge"
REGION = "us-east-1"


def _create_table(dynamodb):
    """Create the single-table schema with all three GSIs (design.md)."""
    attribute_definitions = [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"},
        {"AttributeName": GSI1_PK, "AttributeType": "S"},
        {"AttributeName": GSI1_SK, "AttributeType": "S"},
        {"AttributeName": GSI2_PK, "AttributeType": "S"},
        {"AttributeName": GSI2_SK, "AttributeType": "S"},
        {"AttributeName": GSI3_PK, "AttributeType": "S"},
        {"AttributeName": GSI3_SK, "AttributeType": "S"},
    ]
    gsis = [
        {
            "IndexName": GSI1_MARKETPLACE,
            "KeySchema": [
                {"AttributeName": GSI1_PK, "KeyType": "HASH"},
                {"AttributeName": GSI1_SK, "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        },
        {
            "IndexName": GSI2_GEO,
            "KeySchema": [
                {"AttributeName": GSI2_PK, "KeyType": "HASH"},
                {"AttributeName": GSI2_SK, "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        },
        {
            "IndexName": GSI3_REVIEW,
            "KeySchema": [
                {"AttributeName": GSI3_PK, "KeyType": "HASH"},
                {"AttributeName": GSI3_SK, "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        },
    ]
    dynamodb.create_table(
        TableName=TABLE_NAME,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=attribute_definitions,
        GlobalSecondaryIndexes=gsis,
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture()
def repo():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(dynamodb)
        yield DynamoItemRepository(TABLE_NAME, dynamodb_resource=dynamodb)


# --- builders -------------------------------------------------------------------


def _meta(item_id="i1", status=ItemStatus.CREATED, context_ref=None):
    return ItemMeta(
        item_id=item_id,
        status=status,
        category="headphones",
        age_months=14,
        context_source="manual",
        created_at="2024-01-01T00:00:00Z",
        context_ref=context_ref,
    )


def _grade(grade="B", confidence=0.91, idem_key=None):
    return GradeRecord(
        grade=grade,
        confidence=confidence,
        summary="light scuffs",
        defects=[Defect(location="left cup", severity="minor")],
        completeness=CompletenessResult(complete=False, missing_components=["cable"]),
        idem_key=idem_key,
    )


def _listing(item_id="i1", status="LISTED", category="headphones", price="49.99",
             geohash5="9q5cc", listed_at="2024-02-01T00:00:00Z"):
    return ListingRecord(
        item_id=item_id,
        status=status,
        category=category,
        price=Decimal(price),
        geohash5=geohash5,
        listed_at=listed_at,
    )


# --- META facet -----------------------------------------------------------------


def test_put_and_get_item_meta_only(repo):
    repo.put_item_meta(_meta())
    agg = repo.get_item("i1")
    assert agg is not None
    assert agg.meta.item_id == "i1"
    assert agg.meta.status is ItemStatus.CREATED
    assert agg.grade is None and agg.card is None
    assert agg.decision is None and agg.listing is None


def test_get_unknown_item_returns_none(repo):
    assert repo.get_item("missing") is None


def test_context_ref_round_trips_when_set(repo):
    repo.put_item_meta(_meta(context_ref="ORDER#123"))
    agg = repo.get_item("i1")
    assert agg.meta.context_ref == "ORDER#123"


def test_context_ref_none_when_absent(repo):
    repo.put_item_meta(_meta(context_ref=None))
    agg = repo.get_item("i1")
    assert agg.meta.context_ref is None


def test_update_status(repo):
    repo.put_item_meta(_meta())
    repo.update_status("i1", ItemStatus.GRADED)
    assert repo.get_item("i1").meta.status is ItemStatus.GRADED


# --- GRADE facet ----------------------------------------------------------------


def test_put_and_get_grade(repo):
    repo.put_item_meta(_meta())
    repo.put_grade("i1", _grade())
    g = repo.get_grade("i1")
    assert g is not None
    assert g.grade == "B"
    assert g.confidence == pytest.approx(0.91)
    assert g.defects[0].location == "left cup"
    assert g.completeness.missing_components == ["cable"]


def test_get_grade_none_when_absent(repo):
    repo.put_item_meta(_meta())
    assert repo.get_grade("i1") is None


# --- put_grade_if_absent (Requirement 7.3) --------------------------------------


def test_put_grade_if_absent_writes_when_absent(repo):
    repo.put_item_meta(_meta())
    wrote = repo.put_grade_if_absent("i1", "idem-1", _grade(grade="A"))
    assert wrote is True
    assert repo.get_grade("i1").grade == "A"


def test_put_grade_if_absent_retains_existing(repo):
    repo.put_item_meta(_meta())
    assert repo.put_grade_if_absent("i1", "idem-1", _grade(grade="A")) is True
    # A second submission must not overwrite; the original grade is retained.
    assert repo.put_grade_if_absent("i1", "idem-1", _grade(grade="D")) is False
    assert repo.get_grade("i1").grade == "A"


# --- CARD facet -----------------------------------------------------------------


def test_put_and_get_card_by_card_id(repo):
    repo.put_item_meta(_meta())
    card = CardRecord(
        card_id="card-1",
        item_id="i1",
        signature="sig",
        qr_target="https://verify/card-1",
        graded_at="2024-02-01T00:00:00Z",
        warranty_stance="30-day",
        annotated_photo_keys=["k1", "k2"],
    )
    repo.put_card("i1", card)
    fetched = repo.get_card("card-1")
    assert fetched is not None
    assert fetched.item_id == "i1"
    assert fetched.annotated_photo_keys == ["k1", "k2"]


def test_get_card_unknown_returns_none(repo):
    assert repo.get_card("nope") is None


# --- DECISION facet -------------------------------------------------------------


def test_put_decision_round_trips_money_as_decimal(repo):
    repo.put_item_meta(_meta())
    decision = DecisionRecord(
        disposition="RESELL",
        price=Decimal("49.99"),
        value=Decimal("60.00"),
        cost=Decimal("8.50"),
        margin=Decimal("41.49"),
        rationale="value 60.00 - cost 8.50 = margin 41.49",
    )
    repo.put_decision("i1", decision)
    got = repo.get_item("i1").decision
    assert got.price == Decimal("49.99")
    assert got.margin == Decimal("41.49")
    assert isinstance(got.value, Decimal)


# --- LISTING facet --------------------------------------------------------------


def test_put_get_update_delete_listing(repo):
    repo.put_item_meta(_meta())
    repo.put_listing("i1", _listing())
    assert repo.get_listing("i1").price == Decimal("49.99")

    updated = repo.update_listing("i1", ListingPatch(price=Decimal("39.99")))
    assert updated.price == Decimal("39.99")
    assert repo.get_listing("i1").price == Decimal("39.99")
    # untouched fields preserved
    assert updated.geohash5 == "9q5cc"

    repo.delete_listing("i1")
    assert repo.get_listing("i1") is None


def test_update_listing_missing_raises(repo):
    repo.put_item_meta(_meta())
    with pytest.raises(KeyError):
        repo.update_listing("i1", ListingPatch(price=Decimal("1.00")))


def test_get_item_includes_listing_facet(repo):
    repo.put_item_meta(_meta())
    repo.put_listing("i1", _listing())
    agg = repo.get_item("i1")
    assert agg.listing is not None
    assert agg.listing.category == "headphones"


# --- marketplace query (Requirements 3.3, 13.1) ---------------------------------


def test_query_marketplace_by_category_via_gsi1(repo):
    repo.put_item_meta(_meta(item_id="a"))
    repo.put_item_meta(_meta(item_id="b"))
    repo.put_item_meta(_meta(item_id="c"))
    repo.put_listing("a", _listing(item_id="a", category="headphones", price="20.00"))
    repo.put_listing("b", _listing(item_id="b", category="headphones", price="80.00"))
    repo.put_listing("c", _listing(item_id="c", category="laptops", price="500.00"))

    results = repo.query_marketplace("headphones")
    ids = {r.item_id for r in results}
    assert ids == {"a", "b"}  # laptops excluded


def test_query_marketplace_orders_by_price(repo):
    repo.put_item_meta(_meta(item_id="a"))
    repo.put_item_meta(_meta(item_id="b"))
    repo.put_item_meta(_meta(item_id="c"))
    # Out-of-order insert; numeric ordering must hold despite string sort keys.
    repo.put_listing("a", _listing(item_id="a", price="100.00"))
    repo.put_listing("b", _listing(item_id="b", price="9.00"))
    repo.put_listing("c", _listing(item_id="c", price="40.00"))

    prices = [r.price for r in repo.query_marketplace("headphones")]
    assert prices == [Decimal("9.00"), Decimal("40.00"), Decimal("100.00")]


def test_query_marketplace_with_geo_via_gsi2(repo):
    repo.put_item_meta(_meta(item_id="a"))
    repo.put_item_meta(_meta(item_id="b"))
    repo.put_listing("a", _listing(item_id="a", geohash5="9q5cc"))
    repo.put_listing("b", _listing(item_id="b", geohash5="dr5ru"))

    results = repo.query_marketplace("headphones", geo="9q5cc")
    assert {r.item_id for r in results} == {"a"}


def test_query_marketplace_respects_limit(repo):
    for i in range(5):
        repo.put_item_meta(_meta(item_id=f"i{i}"))
        repo.put_listing(f"i{i}", _listing(item_id=f"i{i}", price=f"{i + 1}.00"))
    assert len(repo.query_marketplace("headphones", limit=2)) == 2
