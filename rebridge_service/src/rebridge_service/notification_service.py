from dataclasses import dataclass

from rebridge_data.interfaces import NotificationRepository
from rebridge_data.models import NotificationRecord

@dataclass
class NotificationService:
    """Service to handle notification-related logic."""
    repository: NotificationRepository

    def get_user_notifications(self, user_id: str, limit: int = 50) -> list[NotificationRecord]:
        return self.repository.get_user_notifications(user_id, limit)

    def mark_read(self, user_id: str, notif_id: str) -> None:
        self.repository.mark_read(user_id, notif_id)

    def mark_all_read(self, user_id: str) -> None:
        self.repository.mark_all_read(user_id)
