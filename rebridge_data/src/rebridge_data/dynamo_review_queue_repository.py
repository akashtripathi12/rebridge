"""DynamoDB-backed :class:`ReviewQueueRepository` implementation.

This is one of the boto3-backed concretes that live exclusively in
``rebridge_data``. It persists low-confidence grade records as a ``REVIEW``
facet on the single table and exposes them, ordered by priority descending,
through GSI3.

Storage model (see design.md "DynamoDB Single-Table Model"):

* Base item — ``PK = ITEM#<item_id>``, ``SK = REVIEW``. Carries ``value``,
  ``confidence``, ``priority`` and the serialized pending grade.
* GSI3 review queue — ``GSI3PK = REVIEW#PENDING``, ``GSI3SK = <priority>``
  (a Number attribute). ``list_pending`` queries this index with
  ``ScanIndexForward=False`` to obtain ``value * uncertainty`` descending order
  (Requirement 14.1).

``priority`` is authoritative: ``enqueue`` recomputes it as
``value * (1 - confidence)`` regardless of any value carried on the incoming
entry, guaranteeing the queue ordering invariant.

All numeric attributes are stored as :class:`~decimal.Decimal` so reads and
writes round-trip without binary-float surprises; floats are converted via
``str()`` to preserve their decimal representation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from rebridge_data.interfaces import ReviewQueueRepository
from rebridge_data.models import (
    CompletenessResult,
    Defect,
    GradeRecord,
    ReviewQueueEntry,
)

# Single-table key constants.
_REVIEW_SK = "REVIEW"
_GSI3_NAME = "GSI3"
_GSI3_PENDING_PK = "REVIEW#PENDING"

_ONE = Decimal("1")


def _item_pk(item_id: str) -> str:
    return f"ITEM#{item_id}"


def _to_decimal(value: Any) -> Decimal:
    """Coerce a number (Decimal/int/float/str) to a Decimal without float noise."""
    if isinstance(value, Decimal):
        return value
    # Route through str() so a float like 0.1 stores as Decimal('0.1').
    return Decimal(str(value))


def _serialize_grade(grade: GradeRecord | None) -> dict[str, Any] | None:
    if grade is None:
        return None
    completeness: dict[str, Any] | None = None
    if grade.completeness is not None:
        completeness = {
            "complete": grade.completeness.complete,
            "missing_components": list(grade.completeness.missing_components),
        }
    return {
        "grade": grade.grade,
        "confidence": _to_decimal(grade.confidence),
        "summary": grade.summary,
        "defects": [
            {"location": d.location, "severity": d.severity} for d in grade.defects
        ],
        "completeness": completeness,
        "idem_key": grade.idem_key,
        "confirmed": grade.confirmed,
    }


def _deserialize_grade(raw: dict[str, Any] | None) -> GradeRecord | None:
    if not raw:
        return None
    completeness_raw = raw.get("completeness")
    completeness: CompletenessResult | None = None
    if completeness_raw is not None:
        completeness = CompletenessResult(
            complete=bool(completeness_raw.get("complete")),
            missing_components=list(completeness_raw.get("missing_components", [])),
        )
    return GradeRecord(
        grade=raw["grade"],
        confidence=float(raw["confidence"]),
        summary=raw.get("summary", ""),
        defects=[
            Defect(location=d["location"], severity=d["severity"])
            for d in raw.get("defects", [])
        ],
        completeness=completeness,
        idem_key=raw.get("idem_key"),
        confirmed=bool(raw.get("confirmed", False)),
    )


class DynamoReviewQueueRepository(ReviewQueueRepository):
    """Prioritized review queue stored on the DynamoDB single table.

    Implements :class:`rebridge_data.interfaces.ReviewQueueRepository`.
    """

    def __init__(self, table_name: str, *, dynamodb_resource: Any | None = None) -> None:
        self._table_name = table_name
        resource = dynamodb_resource or boto3.resource("dynamodb")
        self._table = resource.Table(table_name)

    # -- ReviewQueueRepository ------------------------------------------------

    def enqueue(self, entry: ReviewQueueEntry) -> None:
        """Add an entry with priority = value * (1 - confidence)."""
        value = _to_decimal(entry.value)
        confidence = _to_decimal(entry.confidence)
        priority = value * (_ONE - confidence)

        item: dict[str, Any] = {
            "PK": _item_pk(entry.item_id),
            "SK": _REVIEW_SK,
            "item_id": entry.item_id,
            "value": value,
            "confidence": confidence,
            "priority": priority,
            "GSI3PK": _GSI3_PENDING_PK,
            "GSI3SK": priority,
        }
        grade = _serialize_grade(entry.grade)
        if grade is not None:
            item["grade"] = grade
        self._table.put_item(Item=item)

    def list_pending(self, limit: int) -> list[ReviewQueueEntry]:
        """Return pending entries ordered by priority descending (Requirement 14.1)."""
        if limit <= 0:
            return []
        response = self._table.query(
            IndexName=_GSI3_NAME,
            KeyConditionExpression=Key("GSI3PK").eq(_GSI3_PENDING_PK),
            ScanIndexForward=False,  # priority descending
            Limit=limit,
        )
        return [self._to_entry(item) for item in response.get("Items", [])]

    def get(self, item_id: str) -> ReviewQueueEntry | None:
        """Return the pending entry for an Item, or None if not pending."""
        response = self._table.get_item(
            Key={"PK": _item_pk(item_id), "SK": _REVIEW_SK}
        )
        item = response.get("Item")
        if not item:
            return None
        return self._to_entry(item)

    def resolve(self, item_id: str) -> None:
        """Remove an Item from the review queue."""
        self._table.delete_item(Key={"PK": _item_pk(item_id), "SK": _REVIEW_SK})

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _to_entry(item: dict[str, Any]) -> ReviewQueueEntry:
        return ReviewQueueEntry(
            item_id=item["item_id"],
            value=_to_decimal(item["value"]),
            confidence=float(item["confidence"]),
            priority=float(item["priority"]),
            grade=_deserialize_grade(item.get("grade")),
        )
