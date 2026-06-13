"""Unit tests for :class:`DynamoReviewQueueRepository` (Requirement 14.1).

These exercise the real implementation against a moto-mocked DynamoDB table,
including the GSI3 review-queue index used for priority-descending ordering.
"""

from __future__ import annotations

from decimal import Decimal

import boto3
import pytest
from moto import mock_aws

from rebridge_data import DynamoReviewQueueRepository
from rebridge_data.models import (
    CompletenessResult,
    Defect,
    GradeRecord,
    ReviewQueueEntry,
)

TABLE_NAME = "rebridge-test"


def _create_table(resource) -> None:
    """Create the single table with the GSI3 review-queue index."""
    resource.create_table(
        TableName=TABLE_NAME,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI3PK", "AttributeType": "S"},
            {"AttributeName": "GSI3SK", "AttributeType": "N"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI3",
                "KeySchema": [
                    {"AttributeName": "GSI3PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI3SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture()
def repo():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        _create_table(resource)
        yield DynamoReviewQueueRepository(TABLE_NAME, dynamodb_resource=resource)


def _entry(item_id: str, value: str, confidence: float, **kw) -> ReviewQueueEntry:
    return ReviewQueueEntry(
        item_id=item_id,
        value=Decimal(value),
        confidence=confidence,
        # priority is recomputed by enqueue; pass a bogus value to prove that.
        priority=kw.get("priority", -999.0),
        grade=kw.get("grade"),
    )


def test_enqueue_then_get_roundtrips(repo):
    grade = GradeRecord(
        grade="GOOD",
        confidence=0.5,
        summary="minor scuffs",
        defects=[Defect(location="corner", severity="low")],
        completeness=CompletenessResult(complete=False, missing_components=["cable"]),
        idem_key="abc123",
        confirmed=False,
    )
    repo.enqueue(_entry("item-1", "100", 0.5, grade=grade))

    fetched = repo.get("item-1")
    assert fetched is not None
    assert fetched.item_id == "item-1"
    assert fetched.value == Decimal("100")
    assert fetched.confidence == 0.5
    # priority = value * (1 - confidence) = 100 * 0.5 = 50
    assert fetched.priority == 50.0
    assert fetched.grade is not None
    assert fetched.grade.grade == "GOOD"
    assert fetched.grade.defects[0].location == "corner"
    assert fetched.grade.completeness is not None
    assert fetched.grade.completeness.missing_components == ["cable"]
    assert fetched.grade.idem_key == "abc123"


def test_enqueue_recomputes_priority_from_value_and_confidence(repo):
    # confidence 0.8 -> uncertainty 0.2; value 200 -> priority 40.
    repo.enqueue(_entry("item-x", "200", 0.8, priority=12345.0))
    fetched = repo.get("item-x")
    assert fetched is not None
    assert fetched.priority == pytest.approx(40.0)


def test_get_returns_none_when_absent(repo):
    assert repo.get("missing") is None


def test_list_pending_orders_by_priority_descending(repo):
    # priority = value * (1 - confidence)
    repo.enqueue(_entry("low", "10", 0.5))      # 10 * 0.5  = 5.0
    repo.enqueue(_entry("high", "500", 0.2))    # 500 * 0.8 = 400.0
    repo.enqueue(_entry("mid", "100", 0.4))     # 100 * 0.6 = 60.0

    pending = repo.list_pending(limit=10)
    ids = [e.item_id for e in pending]
    assert ids == ["high", "mid", "low"]

    priorities = [e.priority for e in pending]
    assert priorities == sorted(priorities, reverse=True)
    assert priorities[0] == pytest.approx(400.0)


def test_list_pending_respects_limit(repo):
    repo.enqueue(_entry("a", "10", 0.1))
    repo.enqueue(_entry("b", "20", 0.1))
    repo.enqueue(_entry("c", "30", 0.1))

    top = repo.list_pending(limit=2)
    assert len(top) == 2
    # Highest priority first: c (27) then b (18).
    assert [e.item_id for e in top] == ["c", "b"]


def test_list_pending_non_positive_limit_returns_empty(repo):
    repo.enqueue(_entry("a", "10", 0.1))
    assert repo.list_pending(limit=0) == []
    assert repo.list_pending(limit=-3) == []


def test_list_pending_empty_queue(repo):
    assert repo.list_pending(limit=5) == []


def test_resolve_removes_entry_from_queue_and_get(repo):
    repo.enqueue(_entry("item-1", "100", 0.5))
    repo.enqueue(_entry("item-2", "100", 0.5))

    repo.resolve("item-1")

    assert repo.get("item-1") is None
    remaining = [e.item_id for e in repo.list_pending(limit=10)]
    assert remaining == ["item-2"]


def test_resolve_is_safe_when_absent(repo):
    # Deleting a non-existent entry should not raise.
    repo.resolve("never-existed")
    assert repo.get("never-existed") is None
