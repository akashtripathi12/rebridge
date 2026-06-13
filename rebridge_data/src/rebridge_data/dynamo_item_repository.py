"""DynamoDB-backed :class:`ItemRepository` (Requirements 1.6, 3.3, 7.3, 13.1).

This is the only kind of module permitted to import ``boto3``: the data layer
is the single seam where concrete AWS clients live. The single-table model and
GSI layout it implements are defined in ``design.md``:

Base table (partition key ``PK``, sort key ``SK``)::

    | Entity    | PK            | SK        |
    | Item meta | ITEM#<id>     | META      |
    | Grade     | ITEM#<id>     | GRADE     |
    | Card      | ITEM#<id>     | CARD      |
    | Decision  | ITEM#<id>     | DECISION  |
    | Listing   | ITEM#<id>     | LISTING   |

Global secondary indexes::

    | Index            | PK             | SK                       | Purpose            |
    | GSI1 marketplace | LIST#<status>  | <category>#<price>       | marketplace browse |
    | GSI2 geo         | GEO#<geohash5> | <category>#<listed_at>   | geo candidate      |
    | GSI3 review queue| REVIEW#PENDING | <value*uncertainty desc> | review queue       |

Money fields are stored as DynamoDB ``Number`` values through
``decimal.Decimal`` so no float precision is lost. All read paths convert the
stored ``Decimal`` values back into the record types from
:mod:`rebridge_data.models`.
"""

from __future__ import annotations

from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from rebridge_data.interfaces import ItemRepository
from rebridge_data.models import (
    CardRecord,
    CompletenessResult,
    DecisionRecord,
    Defect,
    GradeRecord,
    ItemAggregate,
    ItemMeta,
    ItemStatus,
    ListingPatch,
    ListingRecord,
)

# --- Single-table key constants -------------------------------------------------

#: Sort-key facet names on the base table.
SK_META = "META"
SK_GRADE = "GRADE"
SK_CARD = "CARD"
SK_DECISION = "DECISION"
SK_LISTING = "LISTING"

#: Global secondary index names.
GSI1_MARKETPLACE = "GSI1"
GSI2_GEO = "GSI2"
GSI3_REVIEW = "GSI3"

#: GSI attribute names (composite partition/sort keys live as plain attributes).
GSI1_PK = "GSI1PK"
GSI1_SK = "GSI1SK"
GSI2_PK = "GSI2PK"
GSI2_SK = "GSI2SK"
GSI3_PK = "GSI3PK"
GSI3_SK = "GSI3SK"

#: Number of fractional digits used to make the marketplace GSI sort key
#: lexicographically order by price. Prices are zero-padded to this width.
_PRICE_SORT_WIDTH = 12


def _item_pk(item_id: str) -> str:
    return f"ITEM#{item_id}"


def _price_sort_token(price: Decimal) -> str:
    """Zero-pad an integer-cent price so string ordering matches numeric order.

    DynamoDB sorts the GSI1 sort key (``<category>#<price>``) as a string, so a
    raw ``"9"`` would sort after ``"10"``. We render cents as a fixed-width,
    zero-padded integer to preserve numeric ordering for marketplace browse.
    """
    cents = int((price * 100).to_integral_value())
    return f"{cents:0{_PRICE_SORT_WIDTH}d}"


class DynamoItemRepository(ItemRepository):
    """Single-table :class:`ItemRepository` backed by a DynamoDB table resource."""

    def __init__(self, table_name: str, *, dynamodb_resource=None, region_name: str | None = None):
        """Bind the repository to a DynamoDB table.

        ``dynamodb_resource`` lets the composition root (or tests) inject a
        pre-built ``boto3.resource('dynamodb')``. When omitted, a resource is
        created with the default credential/region chain.
        """
        if dynamodb_resource is None:
            dynamodb_resource = boto3.resource("dynamodb", region_name=region_name)
        self._table = dynamodb_resource.Table(table_name)

    # --- META facet ------------------------------------------------------------

    def put_item_meta(self, item: ItemMeta) -> None:
        self._table.put_item(Item=self._meta_to_attrs(item))

    def get_item(self, item_id: str) -> ItemAggregate | None:
        resp = self._table.query(
            KeyConditionExpression=Key("PK").eq(_item_pk(item_id)),
        )
        items = resp.get("Items", [])
        by_sk = {row["SK"]: row for row in items}
        meta_attrs = by_sk.get(SK_META)
        if meta_attrs is None:
            return None
        return ItemAggregate(
            meta=self._attrs_to_meta(meta_attrs),
            grade=self._attrs_to_grade(by_sk[SK_GRADE]) if SK_GRADE in by_sk else None,
            card=self._attrs_to_card(by_sk[SK_CARD]) if SK_CARD in by_sk else None,
            decision=(
                self._attrs_to_decision(by_sk[SK_DECISION]) if SK_DECISION in by_sk else None
            ),
            listing=(
                self._attrs_to_listing(by_sk[SK_LISTING]) if SK_LISTING in by_sk else None
            ),
        )

    def update_status(self, item_id: str, status: ItemStatus) -> None:
        self._table.update_item(
            Key={"PK": _item_pk(item_id), "SK": SK_META},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status.value},
        )

    # --- GRADE facet -----------------------------------------------------------

    def put_grade(self, item_id: str, grade: GradeRecord) -> None:
        self._table.put_item(Item=self._grade_to_attrs(item_id, grade))

    def get_grade(self, item_id: str) -> GradeRecord | None:
        resp = self._table.get_item(Key={"PK": _item_pk(item_id), "SK": SK_GRADE})
        attrs = resp.get("Item")
        return self._attrs_to_grade(attrs) if attrs else None

    def put_grade_if_absent(self, item_id: str, idem_key: str, grade: GradeRecord) -> bool:
        """Conditionally write the GRADE facet (Requirement 7.3).

        Uses a DynamoDB ``ConditionExpression`` of ``attribute_not_exists(PK)``
        so the write only succeeds when no GRADE facet exists for the Item. A
        ``ConditionalCheckFailedException`` means a grade was already persisted;
        we swallow it and return ``False`` so the existing grade is retained
        unchanged.
        """
        attrs = self._grade_to_attrs(item_id, grade)
        attrs["idem_key"] = idem_key
        try:
            self._table.put_item(
                Item=attrs,
                ConditionExpression="attribute_not_exists(PK)",
            )
            return True
        except self._table.meta.client.exceptions.ConditionalCheckFailedException:
            return False

    # --- CARD facet ------------------------------------------------------------

    def put_card(self, item_id: str, card: CardRecord) -> None:
        self._table.put_item(Item=self._card_to_attrs(item_id, card))

    def get_card(self, card_id: str) -> CardRecord | None:
        # A card is addressed by its own card_id, not the item_id, so we look it
        # up through a scan filter on the CARD facet. (Stage 0 cardinality is
        # tiny; a dedicated GSI is a later-stage optimization.)
        resp = self._table.scan(
            FilterExpression=Key("SK").eq(SK_CARD) & Key("card_id").eq(card_id),
        )
        items = resp.get("Items", [])
        if not items:
            return None
        return self._attrs_to_card(items[0])

    # --- DECISION facet --------------------------------------------------------

    def put_decision(self, item_id: str, decision: DecisionRecord) -> None:
        self._table.put_item(Item=self._decision_to_attrs(item_id, decision))

    # --- LISTING facet ---------------------------------------------------------

    def put_listing(self, item_id: str, listing: ListingRecord) -> None:
        self._table.put_item(Item=self._listing_to_attrs(item_id, listing))

    def update_listing(self, item_id: str, patch: ListingPatch) -> ListingRecord:
        current = self.get_listing(item_id)
        if current is None:
            raise KeyError(f"no LISTING facet for item {item_id!r}")
        updated = ListingRecord(
            item_id=current.item_id,
            status=patch.status if patch.status is not None else current.status,
            category=patch.category if patch.category is not None else current.category,
            price=patch.price if patch.price is not None else current.price,
            geohash5=patch.geohash5 if patch.geohash5 is not None else current.geohash5,
            listed_at=current.listed_at,
        )
        self._table.put_item(Item=self._listing_to_attrs(item_id, updated))
        return updated

    def get_listing(self, item_id: str) -> ListingRecord | None:
        resp = self._table.get_item(Key={"PK": _item_pk(item_id), "SK": SK_LISTING})
        attrs = resp.get("Item")
        return self._attrs_to_listing(attrs) if attrs else None

    def delete_listing(self, item_id: str) -> None:
        self._table.delete_item(Key={"PK": _item_pk(item_id), "SK": SK_LISTING})

    def query_marketplace(
        self,
        category: str,
        geo: str | None = None,
        limit: int = 50,
    ) -> list[ListingRecord]:
        """Query listed items for marketplace browse (Requirements 3.3, 13.1).

        When ``geo`` is omitted, listings are read from GSI1 keyed by
        ``LIST#LISTED`` and filtered to the requested category by the sort-key
        prefix ``<category>#``. When ``geo`` is provided, the geo index (GSI2),
        keyed by ``GEO#<geohash5>``, is used instead so callers can do a
        geo-radius candidate lookup constrained to one category.
        """
        if geo is None:
            resp = self._table.query(
                IndexName=GSI1_MARKETPLACE,
                KeyConditionExpression=(
                    Key(GSI1_PK).eq(f"LIST#{ItemStatus.LISTED.value}")
                    & Key(GSI1_SK).begins_with(f"{category}#")
                ),
                Limit=limit,
            )
        else:
            resp = self._table.query(
                IndexName=GSI2_GEO,
                KeyConditionExpression=(
                    Key(GSI2_PK).eq(f"GEO#{geo}")
                    & Key(GSI2_SK).begins_with(f"{category}#")
                ),
                Limit=limit,
            )
        return [self._attrs_to_listing(row) for row in resp.get("Items", [])]

    # --- item <-> dynamo attribute mapping -------------------------------------

    @staticmethod
    def _meta_to_attrs(item: ItemMeta) -> dict:
        attrs = {
            "PK": _item_pk(item.item_id),
            "SK": SK_META,
            "item_id": item.item_id,
            "status": item.status.value,
            "category": item.category,
            "age_months": item.age_months,
            "context_source": item.context_source,
            "created_at": item.created_at,
        }
        # context_ref is optional: present for order-scan contexts, None for
        # manual ones. Only persist it when set so the META facet stays clean.
        if item.context_ref is not None:
            attrs["context_ref"] = item.context_ref
        return attrs

    @staticmethod
    def _attrs_to_meta(attrs: dict) -> ItemMeta:
        return ItemMeta(
            item_id=attrs["item_id"],
            status=ItemStatus(attrs["status"]),
            category=attrs["category"],
            age_months=int(attrs["age_months"]),
            context_source=attrs["context_source"],
            created_at=attrs["created_at"],
            context_ref=attrs.get("context_ref"),
        )

    @staticmethod
    def _grade_to_attrs(item_id: str, grade: GradeRecord) -> dict:
        attrs = {
            "PK": _item_pk(item_id),
            "SK": SK_GRADE,
            "grade": grade.grade,
            # Confidence is a probability in [0, 1]; store as Decimal so it round
            # trips through DynamoDB's Number type without float coercion.
            "confidence": Decimal(str(grade.confidence)),
            "summary": grade.summary,
            "defects": [
                {"location": d.location, "severity": d.severity} for d in grade.defects
            ],
            "confirmed": grade.confirmed,
        }
        if grade.completeness is not None:
            attrs["completeness"] = {
                "complete": grade.completeness.complete,
                "missing_components": list(grade.completeness.missing_components),
            }
        if grade.idem_key is not None:
            attrs["idem_key"] = grade.idem_key
        return attrs

    @staticmethod
    def _attrs_to_grade(attrs: dict) -> GradeRecord:
        completeness = None
        raw_completeness = attrs.get("completeness")
        if raw_completeness is not None:
            completeness = CompletenessResult(
                complete=bool(raw_completeness["complete"]),
                missing_components=list(raw_completeness.get("missing_components", [])),
            )
        return GradeRecord(
            grade=attrs["grade"],
            confidence=float(attrs["confidence"]),
            summary=attrs["summary"],
            defects=[
                Defect(location=d["location"], severity=d["severity"])
                for d in attrs.get("defects", [])
            ],
            completeness=completeness,
            idem_key=attrs.get("idem_key"),
            confirmed=bool(attrs.get("confirmed", False)),
        )

    @staticmethod
    def _card_to_attrs(item_id: str, card: CardRecord) -> dict:
        return {
            "PK": _item_pk(item_id),
            "SK": SK_CARD,
            "card_id": card.card_id,
            "item_id": card.item_id,
            "signature": card.signature,
            "qr_target": card.qr_target,
            "graded_at": card.graded_at,
            "warranty_stance": card.warranty_stance,
            "annotated_photo_keys": list(card.annotated_photo_keys),
        }

    @staticmethod
    def _attrs_to_card(attrs: dict) -> CardRecord:
        return CardRecord(
            card_id=attrs["card_id"],
            item_id=attrs["item_id"],
            signature=attrs["signature"],
            qr_target=attrs["qr_target"],
            graded_at=attrs["graded_at"],
            warranty_stance=attrs["warranty_stance"],
            annotated_photo_keys=list(attrs.get("annotated_photo_keys", [])),
        )

    @staticmethod
    def _decision_to_attrs(item_id: str, decision: DecisionRecord) -> dict:
        return {
            "PK": _item_pk(item_id),
            "SK": SK_DECISION,
            "disposition": decision.disposition,
            # Money fields stored as Decimal Numbers (no float precision loss).
            "price": decision.price,
            "value": decision.value,
            "cost": decision.cost,
            "margin": decision.margin,
            "rationale": decision.rationale,
        }

    @staticmethod
    def _attrs_to_decision(attrs: dict) -> DecisionRecord:
        return DecisionRecord(
            disposition=attrs["disposition"],
            price=Decimal(attrs["price"]),
            value=Decimal(attrs["value"]),
            cost=Decimal(attrs["cost"]),
            margin=Decimal(attrs["margin"]),
            rationale=attrs["rationale"],
        )

    @staticmethod
    def _listing_to_attrs(item_id: str, listing: ListingRecord) -> dict:
        return {
            "PK": _item_pk(item_id),
            "SK": SK_LISTING,
            "item_id": listing.item_id,
            "status": listing.status,
            "category": listing.category,
            "price": listing.price,
            "geohash5": listing.geohash5,
            "listed_at": listing.listed_at,
            # GSI1 marketplace browse: LIST#<status> / <category>#<price>.
            GSI1_PK: f"LIST#{listing.status}",
            GSI1_SK: f"{listing.category}#{_price_sort_token(listing.price)}",
            # GSI2 geo candidate lookup: GEO#<geohash5> / <category>#<listed_at>.
            GSI2_PK: f"GEO#{listing.geohash5}",
            GSI2_SK: f"{listing.category}#{listing.listed_at}",
        }

    @staticmethod
    def _attrs_to_listing(attrs: dict) -> ListingRecord:
        return ListingRecord(
            item_id=attrs["item_id"],
            status=attrs["status"],
            category=attrs["category"],
            price=Decimal(attrs["price"]),
            geohash5=attrs["geohash5"],
            listed_at=attrs["listed_at"],
        )
