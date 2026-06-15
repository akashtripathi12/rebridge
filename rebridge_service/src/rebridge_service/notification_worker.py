import json
import logging
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

from rebridge_data.interfaces import NotificationRepository, ItemRepository
from rebridge_data.models import NotificationRecord

logger = logging.getLogger(__name__)

@dataclass
class NotificationWorker:
    """Consumes lifecycle events and persists user notifications."""

    repository: NotificationRepository
    item_repo: ItemRepository

    def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        """Process an SQS event containing EventBridge payloads."""
        records = event.get("Records", [])
        for record in records:
            try:
                body = record.get("body", "")
                # The body is either the direct EventBridge payload or SQS wrapped payload.
                payload = json.loads(body)
                
                # If it's an EventBridge wrapped event
                if "detail-type" in payload and "detail" in payload:
                    detail_type = payload["detail-type"]
                    detail = payload["detail"]
                else:
                    # If it's just the raw LifecycleEvent JSON (like in direct tests)
                    detail_type = payload.get("event_type")
                    detail = payload

                if detail_type == "BUYER_NOTIFIED":
                    self._handle_buyer_notified(detail)
                elif detail_type == "SELLER_NOTIFIED":
                    self._handle_seller_notified(detail)
                else:
                    logger.debug(f"Ignoring irrelevant event type: {detail_type}")

            except Exception as e:
                logger.error(f"Failed to process notification message: {e}", exc_info=True)
                # In production, we might raise to send to DLQ, but we'll swallow here for simplicity.
        return {"statusCode": 200}

    def _handle_buyer_notified(self, detail: dict[str, Any]) -> None:
        item_id = detail.get("item_id")
        payload = detail.get("payload", {})
        buyer_id = payload.get("buyer_id")
        
        item = self.item_repo.get_item(item_id)
        if not item:
            logger.warning(f"Item {item_id} not found for BUYER_NOTIFIED")
            return
            
        title = payload.get("title") or (f"{item.meta.category.capitalize()} item")
        price = payload.get("price") or (item.listing.price if item.listing else "0.00")
        grade = payload.get("grade") or (item.grade.grade if item.grade else "Unknown")
        
        body_parts = []
        if title:
            body_parts.append(title)
        if grade:
            body_parts.append(f"Grade: {grade}")
        if price:
            body_parts.append(f"Price: ₹{price}")
            
        body = " — ".join(body_parts) if body_parts else f"Item {item_id} matches your preferences."

        notif = NotificationRecord(
            notif_id=f"n_{uuid.uuid4().hex[:8]}",
            user_id=buyer_id,
            variant="buyer",
            title="A graded match near you",
            body=body,
            href="/market",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repository.put_notification(notif)
        logger.info(f"Generated BUYER_NOTIFIED for buyer {buyer_id}")

    def _handle_seller_notified(self, detail: dict[str, Any]) -> None:
        item_id = detail.get("item_id")
        payload = detail.get("payload", {})
        seller_id = payload.get("seller_id")
        
        item = self.item_repo.get_item(item_id)
        if not item:
            logger.warning(f"Item {item_id} not found for SELLER_NOTIFIED")
            return
            
        match_count = payload.get("match_count", 0)
        title = payload.get("title") or (f"{item.meta.category.capitalize()} item")
        price = payload.get("price") or (item.listing.price if item.listing else "0.00")
        grade = payload.get("grade") or (item.grade.grade if item.grade else "Unknown")
        
        body = f"{title} — {grade}, listed for ₹{price}. AI matched {match_count} nearby buyer{'s' if match_count != 1 else ''}."

        notif = NotificationRecord(
            notif_id=f"n_{uuid.uuid4().hex[:8]}",
            user_id=seller_id,
            variant="seller",
            title=f"Routed to {match_count} buyer{'s' if match_count != 1 else ''} < 5 km",
            body=body,
            href="/resell/listings",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repository.put_notification(notif)
        logger.info(f"Generated SELLER_NOTIFIED for seller {seller_id}")
