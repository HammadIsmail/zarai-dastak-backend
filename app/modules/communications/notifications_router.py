from fastapi import APIRouter, HTTPException, status
from typing import Optional, Any
import json
from app.modules.communications.notifications_repository import Notification
from app.core.services.fcm_service import fcm_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _format(n: dict) -> dict:
    raw_data = n.get('data') or '{}'
    try:
        n['data'] = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
    except Exception:
        n['data'] = {}
    return n


@router.get("/{user_id}")
async def get_notifications(user_id: str, limit: int = 50):
    try:
        items = Notification.get_for_user(user_id, limit=limit)
        return {"success": True, "notifications": [_format(n) for n in items]}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{user_id}/unread-count")
async def get_unread_count(user_id: str):
    try:
        count = Notification.get_unread_count(user_id)
        return {"success": True, "unreadCount": count}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{notification_id}/read")
async def mark_read(notification_id: str):
    try:
        Notification.mark_read(notification_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/user/{user_id}/read-all")
async def mark_all_read(user_id: str):
    try:
        updated = Notification.mark_all_read(user_id)
        return {"success": True, "updated": updated}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/admin/send")
async def admin_send_notification(payload: dict[str, Any]):
    """Send a push notification to a user. Called from the admin dashboard
    after verification approval or rejection."""
    user_id = payload.get("userId")
    title = payload.get("title")
    body = payload.get("body")
    notif_type = payload.get("type", "admin_notification")
    extra_data: dict[str, Any] = payload.get("data") or {}

    if not user_id or not title or not body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="userId, title, and body are required",
        )

    sent = await fcm_service.send_to_user(
        user_id=user_id,
        notification_type=notif_type,
        title=title,
        body=body,
        data=extra_data,
    )
    return {"success": sent}
