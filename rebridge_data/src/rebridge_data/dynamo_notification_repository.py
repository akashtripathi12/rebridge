"""DynamoDB-backed :class:`NotificationRepository`."""

from __future__ import annotations

import boto3
from boto3.dynamodb.conditions import Key

from rebridge_data.interfaces import NotificationRepository
from rebridge_data.models import NotificationRecord


class DynamoDbNotificationRepository(NotificationRepository):
    """Stores notifications in the main single table using USER#<id> / NOTIF#<id>."""

    def __init__(self, table) -> None:  # type: ignore # boto3 types
        """
        Args:
            table: A boto3 DynamoDB Table resource.
        """
        self._table = table

    def put_notification(self, notif: NotificationRecord) -> None:
        """Create a notification record for a user."""
        item = {
            "PK": f"USER#{notif.user_id}",
            "SK": f"NOTIF#{notif.notif_id}",
            "variant": notif.variant,
            "title": notif.title,
            "body": notif.body,
            "created_at": notif.created_at,
            "unread": notif.unread,
        }
        if notif.meta_text is not None:
            item["meta_text"] = notif.meta_text
        if notif.href is not None:
            item["href"] = notif.href

        self._table.put_item(Item=item)

    def get_user_notifications(self, user_id: str, limit: int = 50) -> list[NotificationRecord]:
        """Return the latest notifications for a user."""
        response = self._table.query(
            KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("NOTIF#"),
            ScanIndexForward=False,  # If SK includes timestamp, this sorts descending. Wait, SK is just NOTIF#<notif_id>. We might need to sort in memory.
        )
        
        items = response.get("Items", [])
        
        records = []
        for i in items:
            records.append(
                NotificationRecord(
                    notif_id=i["SK"].split("#", 1)[1],
                    user_id=user_id,
                    variant=i["variant"],
                    title=i["title"],
                    body=i["body"],
                    created_at=i["created_at"],
                    unread=i.get("unread", True),
                    meta_text=i.get("meta_text"),
                    href=i.get("href"),
                )
            )
        
        # Sort by created_at descending
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    def mark_read(self, user_id: str, notif_id: str) -> None:
        """Mark a specific notification as read."""
        self._table.update_item(
            Key={
                "PK": f"USER#{user_id}",
                "SK": f"NOTIF#{notif_id}",
            },
            UpdateExpression="SET unread = :false",
            ExpressionAttributeValues={":false": False},
        )

    def mark_all_read(self, user_id: str) -> None:
        """Mark all notifications for a user as read.
        Note: Since DynamoDB doesn't support bulk updates easily, we query and update individually.
        In a high-scale app we might use batch_write_item, but for this demo this is sufficient.
        """
        response = self._table.query(
            KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("NOTIF#"),
        )
        items = response.get("Items", [])
        for item in items:
            if item.get("unread"):
                self.mark_read(user_id, item["SK"].split("#", 1)[1])
