from fastapi import APIRouter, Depends
from typing import List, Any
from pydantic import BaseModel

from rebridge_api.dependencies import CurrentUser, get_current_user, Services, get_services

router = APIRouter(tags=["notifications"])

class NotificationResponse(BaseModel):
    id: str
    variant: str
    title: str
    body: str
    created_at: str
    unread: bool
    meta_text: str | None = None
    href: str | None = None

class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]

@router.get("/notifications", response_model=NotificationListResponse)
def get_notifications(
    user: CurrentUser = Depends(get_current_user),
    services: Services = Depends(get_services),
):
    """Get the latest notifications for the current user."""
    records = services.notification_service.get_user_notifications(user.subject, limit=50)
    
    responses = []
    for r in records:
        responses.append(
            NotificationResponse(
                id=r.notif_id,
                variant=r.variant,
                title=r.title,
                body=r.body,
                created_at=r.created_at,
                unread=r.unread,
                meta_text=r.meta_text,
                href=r.href,
            )
        )
    return NotificationListResponse(notifications=responses)

@router.post("/notifications/{notif_id}/read")
def mark_read(
    notif_id: str,
    user: CurrentUser = Depends(get_current_user),
    services: Services = Depends(get_services),
):
    """Mark a specific notification as read."""
    services.notification_service.mark_read(user.subject, notif_id)
    return {"status": "ok"}

@router.post("/notifications/read-all")
def mark_all_read(
    user: CurrentUser = Depends(get_current_user),
    services: Services = Depends(get_services),
):
    """Mark all notifications as read."""
    services.notification_service.mark_all_read(user.subject)
    return {"status": "ok"}
