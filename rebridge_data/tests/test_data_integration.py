"""Data-layer integration tests exercising the boto3 concretes together.

Where the per-module unit tests (``test_dynamo_item_repository.py``,
``test_s3_object_store.py``, ``test_kms_card_signer.py``) check each gateway in
isolation, this module wires the concretes against a single moto-mocked AWS
environment and drives an item end to end across facets: it provisions the real
single-table schema (base table + GSI1/GSI2/GSI3 per design.md), writes the
META/GRADE/CARD/DECISION/LISTING facets through ``DynamoItemRepository``, reads
the aggregate back, browses through the marketplace GSIs, exercises the
conditional idempotent grade write, presigns + round-trips photo bytes through
``S3ObjectStore``, and runs a KMS sign/verify smoke through ``KmsCardSigner``.

moto stands in for DynamoDB and S3 so no real AWS calls are made. KMS
``GenerateMac``/``VerifyMac`` is not reliably modeled by moto (its MAC is not a
stable, verifiable HMAC), so the KMS signer is exercised against an injected
fake client that computes a real HMAC-SHA256 — this validates the genuine
sign/verify/tamper logic in ``KmsCardSigner`` deterministically.

Requirements covered:
- 1.6  single-table reads/writes of all item facets
- 2.2  presigned upload URL 5-minute (300s) TTL + object byte round-trip
- 7.3  conditional idempotent grade write (write-once, retain existing)
- 11.2 HMAC-SHA256 card sign/verify round-trip and tamper detection
"""

from __future__ import annotations

import hashlib
import hmac
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
from rebridge_data.kms_card_signer import KmsCardSigner
from rebridge_data.models import (
    CardRecord,
    CompletenessResult,
    DecisionRecord,
    Defect,
    GradeRecord,
    ItemMeta,
    ItemStatus,
    ListingRecord,
)
from rebridge_data.s3_object_store import S3ObjectStore

REGION = "us-east-1"
TABLE_NAME = "rebridge"
BUCKET = "rebridge-photos"
KMS_KEY_ID = "alias/rebridge-card-hmac"
_FAKE_KEY_MATERIAL = b"integration-test-hmac-key-material-0123456789"


# --- schema provisioning --------------------------------------------------------


def _create_table(dynamodb) -> None:
    """Provision the single-table schema with all three GSIs (design.md)."""
    attribute_definitions = [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"},
        {"AttributeName": GSI1_PK, "AttributeType": "S"},
        {"AttributeName": GSI1_SK, "AttributeType": "S"},
        {"AttributeName": GSI2_PK, "AttributeType": "S"},
        {"AttributeName": GSI2_SK, "AttributeType": "S"},
        {"AttributeName": GSI3_PK, "AttributeType": "S"},
        {"AttributeName": GSI3_SK, "AttributeType": "N"},
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


class _FakeKmsClient:
    """Deterministic stand-in for a boto3 KMS client's ``generate_mac``.

    moto's GenerateMac does not return a stable, verifiable HMAC, so we inject a
    fake that computes a real HMAC-SHA256 with a fixed key. This lets the
    sign/verify round-trip and tamper detection in ``KmsCardSigner`` be
    validated for real while staying free of AWS calls.
    """

    def __init__(self, key_material: bytes = _FAKE_KEY_MATERIAL) -> None:
        self._key_material = key_material

    def generate_mac(self, *, KeyId: str, Message: bytes, MacAlgorithm: str) -> dict:
        assert MacAlgorithm == "HMAC_SHA_256"
        mac = hmac.new(self._key_material, Message, hashlib.sha256).digest()
        return {"Mac": mac, "MacAlgorithm": MacAlgorithm, "KeyId": KeyId}


@pytest.fixture
def aws_stack():
    """Wire the data-layer concretes against one moto-mocked AWS environment."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(dynamodb)

        s3_client = boto3.client("s3", region_name=REGION)
        s3_client.create_bucket(Bucket=BUCKET)

        yield {
            "items": DynamoItemRepository(TABLE_NAME, dynamodb_resource=dynamodb),
            "store": S3ObjectStore(BUCKET, client=s3_client),
            "signer": KmsCardSigner(KMS_KEY_ID, client=_FakeKmsClient()),
            "s3_client": s3_client,
        }


# --- builders -------------------------------------------------------------------


def _meta(item_id, status=ItemStatus.CREATED, category="headphones"):
    return ItemMeta(
        item_id=item_id,
        status=status,
        category=category,
        age_months=12,
        context_source="order_scan",
        created_at="2024-01-01T00:00:00Z",
        context_ref="ORDER#42",
    )


def _grade(grade="B", confidence=0.91, idem_key=None):
    return GradeRecord(
        grade=grade,
        confidence=confidence,
        summary="light scuffs on the left ear cup",
        defects=[Defect(location="left cup", severity="minor")],
        completeness=CompletenessResult(complete=False, missing_components=["cable"]),
        idem_key=idem_key,
    )


def _listing(item_id, category="headphones", price="49.99",
             geohash5="9q5cc", listed_at="2024-02-01T00:00:00Z"):
    return ListingRecord(
        item_id=item_id,
        status=ItemStatus.LISTED.value,
        category=category,
        price=Decimal(price),
        geohash5=geohash5,
        listed_at=listed_at,
    )


# --- single-table reads/writes across all facets (Requirement 1.6) --------------


def test_full_item_lifecycle_persists_and_reads_back_all_facets(aws_stack):
    """Write META/GRADE/CARD/DECISION/LISTING and read the aggregate back."""
    items = aws_stack["items"]
    item_id = "itm-1"

    items.put_item_meta(_meta(item_id))
    items.put_grade(item_id, _grade(grade="A", confidence=0.94))
    items.update_status(item_id, ItemStatus.GRADED)
    items.put_card(
        item_id,
        CardRecord(
            card_id="card-1",
            item_id=item_id,
            signature="sig-placeholder",
            qr_target="https://verify.example/card-1",
            graded_at="2024-02-01T00:00:00Z",
            warranty_stance="30-day",
            annotated_photo_keys=["items/itm-1/p1.jpg", "items/itm-1/p2.jpg"],
        ),
    )
    items.put_decision(
        item_id,
        DecisionRecord(
            disposition="RESELL",
            price=Decimal("49.99"),
            value=Decimal("60.00"),
            cost=Decimal("8.50"),
            margin=Decimal("51.50"),
            rationale="value 60.00 - cost 8.50 = margin 51.50",
        ),
    )
    items.put_listing(item_id, _listing(item_id))

    agg = items.get_item(item_id)
    assert agg is not None
    # META reflects the latest status transition.
    assert agg.meta.item_id == item_id
    assert agg.meta.status is ItemStatus.GRADED
    assert agg.meta.context_ref == "ORDER#42"
    # GRADE facet round-trips, including nested defects/completeness.
    assert agg.grade.grade == "A"
    assert agg.grade.confidence == pytest.approx(0.94)
    assert agg.grade.defects[0].location == "left cup"
    assert agg.grade.completeness.missing_components == ["cable"]
    # CARD facet round-trips with its annotated photo keys.
    assert agg.card.card_id == "card-1"
    assert agg.card.annotated_photo_keys == [
        "items/itm-1/p1.jpg",
        "items/itm-1/p2.jpg",
    ]
    # DECISION money fields survive as Decimal (no float coercion).
    assert agg.decision.disposition == "RESELL"
    assert agg.decision.margin == Decimal("51.50")
    assert isinstance(agg.decision.value, Decimal)
    # LISTING facet round-trips.
    assert agg.listing.price == Decimal("49.99")
    assert agg.listing.geohash5 == "9q5cc"


def test_card_lookup_by_card_id_across_table(aws_stack):
    """A persisted CARD facet is retrievable by its own card_id."""
    items = aws_stack["items"]
    items.put_item_meta(_meta("itm-card"))
    items.put_card(
        "itm-card",
        CardRecord(
            card_id="card-xyz",
            item_id="itm-card",
            signature="sig",
            qr_target="https://verify.example/card-xyz",
            graded_at="2024-02-01T00:00:00Z",
            warranty_stance="as-is",
            annotated_photo_keys=[],
        ),
    )
    fetched = items.get_card("card-xyz")
    assert fetched is not None and fetched.item_id == "itm-card"


# --- GSI marketplace queries (Requirements 1.6 / 3.3 / 13.1) --------------------


def test_marketplace_gsi1_filters_category_and_orders_by_price(aws_stack):
    items = aws_stack["items"]
    for iid, cat, price in [
        ("a", "headphones", "100.00"),
        ("b", "headphones", "9.00"),
        ("c", "headphones", "40.00"),
        ("d", "laptops", "500.00"),
    ]:
        items.put_item_meta(_meta(iid, category=cat))
        items.put_listing(iid, _listing(iid, category=cat, price=price))

    results = items.query_marketplace("headphones")
    assert {r.item_id for r in results} == {"a", "b", "c"}  # laptops excluded
    # String GSI sort key still yields numeric price ordering.
    assert [r.price for r in results] == [
        Decimal("9.00"),
        Decimal("40.00"),
        Decimal("100.00"),
    ]


def test_marketplace_gsi2_geo_candidate_lookup(aws_stack):
    items = aws_stack["items"]
    items.put_item_meta(_meta("near"))
    items.put_item_meta(_meta("far"))
    items.put_listing("near", _listing("near", geohash5="9q5cc"))
    items.put_listing("far", _listing("far", geohash5="dr5ru"))

    results = items.query_marketplace("headphones", geo="9q5cc")
    assert {r.item_id for r in results} == {"near"}


# --- conditional idempotent grade write (Requirement 7.3) -----------------------


def test_conditional_idempotent_grade_write(aws_stack):
    """First write wins; a duplicate idempotency key never overwrites it."""
    items = aws_stack["items"]
    items.put_item_meta(_meta("idem-itm"))

    first = items.put_grade_if_absent("idem-itm", "idem-key-1", _grade(grade="A"))
    assert first is True
    assert items.get_grade("idem-itm").grade == "A"

    # Re-processing the same work (same item) must be a no-op write.
    duplicate = items.put_grade_if_absent("idem-itm", "idem-key-1", _grade(grade="D"))
    assert duplicate is False
    # The originally persisted grade is retained unchanged.
    assert items.get_grade("idem-itm").grade == "A"


# --- presign TTL + byte round-trip (Requirement 2.2) ----------------------------


def test_presign_put_ttl_is_300_and_targets_key(aws_stack):
    store = aws_stack["store"]
    presigned = store.presign_put("items/itm-1/photo-1.jpg")

    assert presigned.method == "PUT"
    assert presigned.expires_in == 300  # 5-minute TTL (Requirement 2.2)
    assert presigned.url.startswith("https://")
    assert BUCKET in presigned.url
    assert "items/itm-1/photo-1.jpg" in presigned.url


def test_object_bytes_round_trip(aws_stack):
    store = aws_stack["store"]
    key = "items/itm-1/photo-1.jpg"
    body = b"\x89PNG\r\n\x1a\n integration photo bytes"
    aws_stack["s3_client"].put_object(Bucket=BUCKET, Key=key, Body=body)

    assert store.get_bytes(key) == body


# --- KMS sign/verify smoke (Requirement 11.2) -----------------------------------


def test_card_signer_sign_verify_round_trip_and_tamper(aws_stack):
    """Sign a canonical card payload, verify it, and reject a tampered one."""
    signer = aws_stack["signer"]
    # Canonical payload: card_id | item_id | grade | graded_at.
    payload = b"card-1|itm-1|A|2024-02-01T00:00:00Z"

    signature = signer.sign(payload)
    assert signer.verify(payload, signature) is True

    tampered = b"card-1|itm-1|D|2024-02-01T00:00:00Z"
    assert signer.verify(tampered, signature) is False


def test_signed_card_signature_persists_and_verifies_from_store(aws_stack):
    """End-to-end: sign a card, persist the signature, reload and verify it."""
    items = aws_stack["items"]
    signer = aws_stack["signer"]
    item_id = "itm-signed"
    items.put_item_meta(_meta(item_id))

    payload = b"card-signed|itm-signed|A|2024-02-01T00:00:00Z"
    signature = signer.sign(payload)
    items.put_card(
        item_id,
        CardRecord(
            card_id="card-signed",
            item_id=item_id,
            signature=signature,
            qr_target="https://verify.example/card-signed",
            graded_at="2024-02-01T00:00:00Z",
            warranty_stance="30-day",
            annotated_photo_keys=[],
        ),
    )

    reloaded = items.get_card("card-signed")
    assert reloaded is not None
    assert signer.verify(payload, reloaded.signature) is True
