import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from firebase_admin import auth


from ..services.fcm_service import fcm_service

logger = logging.getLogger(__name__)

router = APIRouter()


@dataclass
class ConnectionInfo:
    websocket: WebSocket
    connected_at: datetime


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, dict[int, ConnectionInfo]] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        bucket = self._connections.setdefault(user_id, {})
        bucket[id(websocket)] = ConnectionInfo(websocket=websocket, connected_at=datetime.utcnow())

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        bucket = self._connections.get(user_id)
        if not bucket:
            return
        bucket.pop(id(websocket), None)
        if not bucket:
            self._connections.pop(user_id, None)

    def is_online(self, user_id: str) -> bool:
        return bool(self._connections.get(user_id))

    async def send_to_user(self, user_id: str, payload: dict[str, Any]) -> int:
        bucket = self._connections.get(user_id, {})
        if not bucket:
            return 0

        stale: list[int] = []
        delivered = 0
        for key, info in list(bucket.items()):
            try:
                await info.websocket.send_text(json.dumps(payload))
                delivered += 1
            except Exception:
                stale.append(key)

        for key in stale:
            bucket.pop(key, None)
        if not bucket:
            self._connections.pop(user_id, None)

        return delivered

    async def send_to_all(self, payload: dict[str, Any], *, exclude_user_id: Optional[str] = None) -> int:
        delivered = 0
        for target_user_id in list(self._connections.keys()):
            if exclude_user_id and target_user_id == exclude_user_id:
                continue
            delivered += await self.send_to_user(target_user_id, payload)
        return delivered


manager = ConnectionManager()


def _event(event_type: str, data: dict[str, Any], *, ok: bool = True) -> dict[str, Any]:
    return {
        "type": event_type,
        "ok": ok,
        "timestamp": datetime.utcnow().isoformat(),
        "data": data,
    }


def _parse_token(websocket: WebSocket) -> Optional[str]:
    token = websocket.query_params.get("token")
    if token:
        return token

    authorization = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if authorization and authorization.startswith("Bearer "):
        return authorization.split("Bearer ", 1)[1].strip()

    return None


async def _send_chat_push(receiver_id: str, sender_name: str, message_preview: str, booking_id: str) -> None:
    await fcm_service.send_to_user(
        user_id=receiver_id,
        notification_type="chat",
        title=sender_name,
        body=message_preview,
        data={
            "type": "chat",
            "bookingId": booking_id,
        },
        booking_id=booking_id,
    )


async def _send_call_push(receiver_id: str, call_payload: dict[str, Any]) -> None:
    caller_name = call_payload.get("callerName") or "User"
    call_type = str(call_payload.get("callType") or "voice").lower()
    await fcm_service.send_to_user(
        user_id=receiver_id,
        notification_type="call",
        title="📹 Incoming Video Call" if call_type == "video" else "📞 Incoming Call",
        body=f"Incoming {call_type} call from {caller_name}",
        data={
            "type": "call",
            **{k: str(v) if v is not None else "" for k, v in call_payload.items()},
        },
        booking_id=str(call_payload.get("bookingId") or ""),
    )


async def _broadcast_presence(user_id: str, *, online: bool) -> None:
    await manager.send_to_all(
        _event("presence_update", {"userId": user_id, "online": online}),
        exclude_user_id=user_id,
    )


@router.websocket("/ws/realtime")
async def realtime_socket(websocket: WebSocket) -> None:
    token = _parse_token(websocket)
    if not token:
        await websocket.close(code=1008, reason="Missing Firebase ID token")
        return

    try:
        decoded = auth.verify_id_token(token)
        user_id = decoded["uid"]
    except Exception:
        await websocket.close(code=1008, reason="Invalid Firebase ID token")
        return

    await manager.connect(user_id, websocket)
    await websocket.send_text(json.dumps(_event("connected", {"userId": user_id, "online": True})))
    await _broadcast_presence(user_id, online=True)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except Exception:
                await websocket.send_text(json.dumps(_event("error", {"message": "Invalid JSON payload"}, ok=False)))
                continue

            event_type = str(payload.get("type") or "").strip()
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

            if event_type == "ping":
                await websocket.send_text(json.dumps(_event("pong", {"userId": user_id})))
                continue

            if event_type == "presence_query":
                target_user_id = str(data.get("targetUserId") or "").strip()
                if not target_user_id:
                    await websocket.send_text(json.dumps(_event("error", {"message": "targetUserId is required"}, ok=False)))
                    continue

                await websocket.send_text(json.dumps(_event("presence_state", {
                    "userId": target_user_id,
                    "online": manager.is_online(target_user_id),
                })))
                continue

            if event_type == "typing":
                receiver_id = str(data.get("receiverId") or "").strip()
                booking_id = str(data.get("bookingId") or "").strip()
                is_typing = bool(data.get("isTyping"))

                if not receiver_id:
                    await websocket.send_text(json.dumps(_event("error", {"message": "receiverId is required"}, ok=False)))
                    continue

                await manager.send_to_user(receiver_id, _event("typing", {
                    "fromUserId": user_id,
                    "receiverId": receiver_id,
                    "bookingId": booking_id,
                    "isTyping": is_typing,
                }))
                continue

            if event_type == "chat_send":
                receiver_id = str(data.get("receiverId") or "").strip()
                booking_id = str(data.get("bookingId") or "").strip()
                message_type = str(data.get("messageType") or "text").strip().lower()
                message_text = str(data.get("messageText") or "").strip()
                media_duration = data.get("mediaDuration")
                client_message_id = str(data.get("clientMessageId") or "").strip()

                if not receiver_id or not booking_id:
                    await websocket.send_text(json.dumps(_event("error", {"message": "receiverId and bookingId are required"}, ok=False)))
                    continue

                if message_type == "text" and not message_text:
                    await websocket.send_text(json.dumps(_event("error", {"message": "messageText is required for text messages"}, ok=False)))
                    continue

                from app.modules.communications.messages_repository import Message
                created = Message.create_message(
                    sender_id=user_id,
                    receiver_id=receiver_id,
                    booking_id=booking_id,
                    message_text=message_text,
                    message_type=message_type,
                    media_duration=int(media_duration) if isinstance(media_duration, int) else None,
                )

                if not created:
                    await websocket.send_text(json.dumps(_event("error", {"message": "Failed to create message"}, ok=False)))
                    continue

                await websocket.send_text(json.dumps(_event("chat_sent", {
                    "clientMessageId": client_message_id,
                    "message": created,
                    "status": "sent",
                })))

                delivered = await manager.send_to_user(receiver_id, _event("chat_message", {"message": created, "status": "delivered"}))

                if delivered > 0:
                    await manager.send_to_user(user_id, _event("message_status", {
                        "messageId": created.get("id"),
                        "status": "delivered",
                    }))
                else:
                    sender_name = created.get("senderName") or "User"
                    preview = "📎 Media" if message_type != "text" else (message_text[:120] or "New message")
                    asyncio.create_task(_send_chat_push(receiver_id, sender_name, preview, booking_id))
                continue

            if event_type == "message_seen":
                message_id = str(data.get("messageId") or "").strip()
                sender_id = str(data.get("senderId") or "").strip()

                if not message_id or not sender_id:
                    await websocket.send_text(json.dumps(_event("error", {"message": "messageId and senderId are required"}, ok=False)))
                    continue

                Message.mark_as_read(message_id)
                await manager.send_to_user(sender_id, _event("message_status", {
                    "messageId": message_id,
                    "status": "seen",
                    "seenBy": user_id,
                }))
                continue

            if event_type == "call_request":
                receiver_id = str(data.get("receiverId") or "").strip()
                if not receiver_id:
                    await websocket.send_text(json.dumps(_event("error", {"message": "receiverId is required"}, ok=False)))
                    continue

                call_payload = {
                    "callId": str(data.get("callId") or ""),
                    "bookingId": str(data.get("bookingId") or ""),
                    "callerId": user_id,
                    "receiverId": receiver_id,
                    "callerName": str(data.get("callerName") or "User"),
                    "callerRole": str(data.get("callerRole") or "user"),
                    "callerProfileImageUrl": data.get("callerProfileImageUrl"),
                    "callType": str(data.get("callType") or "voice").lower(),
                    "signalData": data.get("signalData") if isinstance(data.get("signalData"), dict) else {},
                }

                delivered = await manager.send_to_user(receiver_id, _event("call_incoming", call_payload))
                if delivered == 0:
                    asyncio.create_task(_send_call_push(receiver_id, call_payload))
                continue

            if event_type in {"call_accept", "call_reject", "call_end"}:
                call_id = str(data.get("callId") or "").strip()
                target_user_id = str(data.get("targetUserId") or "").strip()
                call_status = {
                    "call_accept": "answered",
                    "call_reject": "rejected",
                    "call_end": "ended",
                }[event_type]

                if call_id:
                    try:
                        from app.modules.communications.calls_repository import Call
                        Call.update_call_status(call_id=call_id, status=call_status, duration=data.get("duration"))
                    except Exception:
                        logger.exception("Failed updating call status", extra={"callId": call_id, "status": call_status})

                if target_user_id:
                    await manager.send_to_user(target_user_id, _event(event_type, {
                        "callId": call_id,
                        "fromUserId": user_id,
                        "duration": data.get("duration"),
                    }))
                continue

            if event_type in {"webrtc_offer", "webrtc_answer", "webrtc_ice_candidate"}:
                target_user_id = str(data.get("targetUserId") or "").strip()
                if not target_user_id:
                    await websocket.send_text(json.dumps(_event("error", {"message": "targetUserId is required"}, ok=False)))
                    continue

                await manager.send_to_user(target_user_id, _event(event_type, {
                    "callId": str(data.get("callId") or ""),
                    "fromUserId": user_id,
                    "sdp": data.get("sdp"),
                    "type": data.get("type"),
                    "candidate": data.get("candidate"),
                    "sdpMid": data.get("sdpMid"),
                    "sdpMLineIndex": data.get("sdpMLineIndex"),
                }))
                continue

            await websocket.send_text(json.dumps(_event("error", {"message": f"Unsupported event type: {event_type}"}, ok=False)))

    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
        if not manager.is_online(user_id):
            await _broadcast_presence(user_id, online=False)
    except Exception:
        manager.disconnect(user_id, websocket)
        if not manager.is_online(user_id):
            await _broadcast_presence(user_id, online=False)
        logger.exception("Realtime websocket crashed", extra={"userId": user_id})
