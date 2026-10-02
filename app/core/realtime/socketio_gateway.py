from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs

import socketio
from firebase_admin import auth

from ..config import settings
from ..database import redis_client

from ..services.fcm_service import fcm_service

logger = logging.getLogger(__name__)


def _create_sio_manager() -> socketio.AsyncRedisManager | None:
    """
    Build a Redis-backed Socket.IO manager so events emitted from REST handlers
    (possibly on a different Railway dyno) are routed to the correct instance via
    Redis pub/sub.  Falls back to the default in-memory manager on any error.
    """
    if not settings.REDIS_ENABLED:
        return None
    url = (settings.REDIS_URL or "").strip()
    if not url:
        return None

    # Pre-flight: verify credentials with a quick synchronous ping before handing
    # the URL to AsyncRedisManager.  Without this check, a bad URL causes the
    # AsyncRedisManager background thread to loop indefinitely with AuthenticationError.
    try:
        import redis as _sync_redis
        _r = _sync_redis.from_url(url, socket_connect_timeout=4, socket_timeout=4)
        _r.ping()
        _r.close()
    except Exception as _exc:
        logger.error(
            "Redis pre-flight check failed (%s). "
            "Socket.IO will use in-memory manager. "
            "Fix REDIS_URL in Railway env vars and redeploy.",
            _exc,
        )
        return None

    try:
        mgr = socketio.AsyncRedisManager(url)
        logger.warning("Socket.IO Redis manager ready (%s)", url.split("@")[-1])
        return mgr
    except Exception:
        logger.exception("Socket.IO Redis manager init failed — using in-memory manager")
        return None


sio = socketio.AsyncServer(
    async_mode="asgi",
    client_manager=_create_sio_manager(),
    cors_allowed_origins=settings.SOCKETIO_CORS_ORIGINS,
    ping_interval=settings.SOCKETIO_PING_INTERVAL,
    ping_timeout=settings.SOCKETIO_PING_TIMEOUT,
    logger=False,
    engineio_logger=False,
)

# Per-process session maps.  With the Redis manager, room membership is tracked
# in Redis so emits reach users on any instance.  These dicts are used only to
# determine *local* presence quickly; Redis is the authoritative presence store.
_sid_to_user: dict[str, str] = {}
_user_to_sids: dict[str, set[str]] = defaultdict(set)


def _room_for_user(user_id: str) -> str:
    return f"user:{user_id}"


def _parse_token(environ: dict[str, Any], auth_payload: Any) -> str | None:
    if isinstance(auth_payload, dict):
        token = auth_payload.get("token")
        if isinstance(token, str) and token.strip():
            return token.strip()

    query_string = environ.get("QUERY_STRING") or ""
    if query_string:
        parsed = parse_qs(query_string)
        token_values = parsed.get("token", [])
        if token_values and token_values[0].strip():
            return token_values[0].strip()

    authorization = environ.get("HTTP_AUTHORIZATION") or environ.get("Authorization")
    if isinstance(authorization, str) and authorization.startswith("Bearer "):
        return authorization.split("Bearer ", 1)[1].strip()

    return None


async def _broadcast_presence(user_id: str, online: bool) -> None:
    await sio.emit(
        "presence_update",
        {
            "userId": user_id,
            "online": online,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


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


_FCM_LARGE_FIELDS = {"callerProfileImageUrl", "signalData"}

async def _send_call_push(receiver_id: str, call_payload: dict[str, Any]) -> None:
    caller_name = call_payload.get("callerName") or "User"
    call_type = str(call_payload.get("callType") or "voice").lower()
    # FCM data payloads are capped at 4 KB. Profile images are stored as base64
    # data URIs (100–200 KB), so exclude them. The receiver fetches the image
    # via CallIdentityResolver → GET /auth/user/{callerId} when the screen opens.
    fcm_data = {
        k: str(v) if v is not None else ""
        for k, v in call_payload.items()
        if k not in _FCM_LARGE_FIELDS
    }
    await fcm_service.send_to_user(
        user_id=receiver_id,
        notification_type="call",
        title="📹 Incoming Video Call" if call_type == "video" else "📞 Incoming Call",
        body=f"Incoming {call_type} call from {caller_name}",
        data={"type": "call", **fcm_data},
        booking_id=str(call_payload.get("bookingId") or ""),
    )


async def _is_online(user_id: str) -> bool:
    """
    Fast path: check per-process dict.
    Slow path: check Redis presence (handles users on other instances after Redis
    manager routes the emit, or after a process restart that wiped in-memory state).
    """
    if _user_to_sids.get(user_id):
        return True
    cached = await redis_client.get_presence(user_id)
    return cached == "online"


async def emit_to_user_event(user_id: str, event_name: str, payload: dict[str, Any]) -> bool:
    room = _room_for_user(user_id)
    await sio.emit(event_name, payload, room=room)
    return await _is_online(user_id)


@sio.event
async def connect(sid: str, environ: dict[str, Any], auth_payload: Any):
    token = _parse_token(environ, auth_payload)
    if not token:
        logger.warning("Socket.IO connect rejected: missing Firebase token [sid=%s]", sid)
        raise ConnectionRefusedError("Missing Firebase ID token")

    try:
        decoded = auth.verify_id_token(token)
        user_id = decoded["uid"]
    except Exception:
        logger.warning("Socket.IO connect rejected: invalid Firebase token [sid=%s]", sid)
        raise ConnectionRefusedError("Invalid Firebase ID token")

    _sid_to_user[sid] = user_id
    _user_to_sids[user_id].add(sid)
    await sio.save_session(sid, {"user_id": user_id})
    await sio.enter_room(sid, _room_for_user(user_id))

    await redis_client.set_presence_online(user_id)
    await _broadcast_presence(user_id, True)

    await sio.emit("connected", {"userId": user_id, "online": True}, to=sid)

    pending = await redis_client.pop_all_pending(user_id)
    for item in pending:
        await sio.emit("chat_message", item, to=sid)

    logger.warning("Socket.IO connected: user=%s sid=%s", user_id, sid)


@sio.event
async def disconnect(sid: str):
    user_id = _sid_to_user.pop(sid, None)
    if not user_id:
        return

    bucket = _user_to_sids.get(user_id)
    if bucket is not None:
        bucket.discard(sid)
        if not bucket:
            _user_to_sids.pop(user_id, None)
            await redis_client.set_presence_offline(user_id)
            await _broadcast_presence(user_id, False)

    logger.warning("Socket.IO disconnected: user=%s sid=%s", user_id, sid)


@sio.on("ping")
async def ping_event(sid: str, _: dict[str, Any] | None = None):
    await sio.emit("pong", {"timestamp": datetime.utcnow().isoformat()}, to=sid)


@sio.on("presence_query")
async def presence_query(sid: str, data: dict[str, Any]):
    target_user_id = str(data.get("targetUserId") or "").strip()
    if not target_user_id:
        await sio.emit("error", {"message": "targetUserId is required"}, to=sid)
        return

    online = await _is_online(target_user_id)
    await sio.emit(
        "presence_state",
        {
            "userId": target_user_id,
            "online": online,
            "timestamp": datetime.utcnow().isoformat(),
        },
        to=sid,
    )


@sio.on("typing")
async def typing_event(sid: str, data: dict[str, Any]):
    from_user_id = _sid_to_user.get(sid, "")
    receiver_id = str(data.get("receiverId") or "").strip()
    booking_id = str(data.get("bookingId") or "").strip()

    if not receiver_id:
        await sio.emit("error", {"message": "receiverId is required"}, to=sid)
        return

    await sio.emit(
        "typing",
        {
            "fromUserId": from_user_id,
            "receiverId": receiver_id,
            "bookingId": booking_id,
            "isTyping": bool(data.get("isTyping")),
        },
        room=_room_for_user(receiver_id),
    )


@sio.on("chat_send")
async def chat_send(sid: str, data: dict[str, Any]):
    t0 = time.monotonic()

    sender_id = _sid_to_user.get(sid)
    if not sender_id:
        logger.warning("chat_send rejected: unauthenticated sid=%s", sid)
        return {"ok": False, "message": "Unauthenticated socket session"}

    receiver_id = str(data.get("receiverId") or "").strip()
    booking_id = str(data.get("bookingId") or "").strip()
    message_type = str(data.get("messageType") or "text").strip().lower()
    message_text = str(data.get("messageText") or "").strip()
    media_duration = data.get("mediaDuration")
    client_message_id = str(data.get("clientMessageId") or "").strip()

    def _log_result(ok: bool, reason: str, extra: dict | None = None) -> dict:
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        log = {
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "booking_id": booking_id,
            "message_type": message_type,
            "client_message_id": client_message_id,
            "ok": ok,
            "reason": reason,
            "elapsed_ms": elapsed_ms,
            **(extra or {}),
        }
        if ok:
            logger.info("chat_send ok", extra=log)
        else:
            logger.error("chat_send failed: %s", reason, extra=log)
        return {"ok": ok, "message": reason} if not ok else {}

    if not receiver_id or not booking_id:
        _log_result(False, "receiverId and bookingId are required")
        return {"ok": False, "message": "receiverId and bookingId are required"}

    if message_type == "text" and not message_text:
        _log_result(False, "messageText is required for text messages")
        return {"ok": False, "message": "messageText is required for text messages"}

    if client_message_id and await redis_client.is_duplicate_message(sender_id, client_message_id):
        logger.info("chat_send duplicate skipped: sender=%s client_id=%s", sender_id, client_message_id)
        return {"ok": True, "type": "chat_sent", "data": {"clientMessageId": client_message_id, "status": "duplicate"}}

    from app.modules.communications.messages_repository import Message
    created = Message.create_message(
        sender_id=sender_id,
        receiver_id=receiver_id,
        booking_id=booking_id,
        message_text=message_text,
        message_type=message_type,
        media_duration=int(media_duration) if isinstance(media_duration, int) else None,
    )

    if not created:
        # Most common causes: booking not found, participants mismatch, wrong booking status.
        _log_result(False, "Message.create_message returned None — check booking status and participant IDs")
        return {"ok": False, "message": "Failed to create message"}

    ack_payload = {
        "ok": True,
        "type": "chat_sent",
        "data": {
            "clientMessageId": client_message_id,
            "message": created,
            "status": "sent",
        },
    }

    receiver_payload = {
        "message": created,
        "status": "delivered",
    }

    # Always echo back to the sender via a chat_sent event so the sender's
    # socket listener can append the message instantly without a round-trip API
    # reload.  The ACK return value alone is not forwarded to the events stream.
    await sio.emit("chat_sent", ack_payload["data"], room=_room_for_user(sender_id))

    receiver_online = await _is_online(receiver_id)
    if receiver_online:
        await sio.emit("chat_message", receiver_payload, room=_room_for_user(receiver_id))
        await sio.emit(
            "message_status",
            {
                "messageId": created.get("id"),
                "status": "delivered",
            },
            room=_room_for_user(sender_id),
        )
        _log_result(True, "delivered via socket", {"receiver_online": True})
    else:
        await redis_client.enqueue_pending(receiver_id, receiver_payload)
        sender_name = created.get("senderName") or "User"
        preview = "📎 Media" if message_type != "text" else (message_text[:120] or "New message")
        asyncio.create_task(_send_chat_push(receiver_id, sender_name, preview, booking_id))
        _log_result(True, "queued + FCM push sent", {"receiver_online": False})

    return ack_payload


@sio.on("message_seen")
async def message_seen(sid: str, data: dict[str, Any]):
    user_id = _sid_to_user.get(sid)
    message_id = str(data.get("messageId") or "").strip()
    sender_id = str(data.get("senderId") or "").strip()

    if not user_id or not message_id or not sender_id:
        await sio.emit("error", {"message": "messageId and senderId are required"}, to=sid)
        return

    from app.modules.communications.messages_repository import Message
    Message.mark_as_read(message_id)
    await sio.emit(
        "message_status",
        {
            "messageId": message_id,
            "isRead": True,
            "status": "seen",
            "seenBy": user_id,
        },
        room=_room_for_user(sender_id),
    )


@sio.on("call_request")
async def call_request(sid: str, data: dict[str, Any]):
    caller_id = _sid_to_user.get(sid)
    receiver_id = str(data.get("receiverId") or "").strip()
    if not caller_id or not receiver_id:
        await sio.emit("error", {"message": "receiverId is required"}, to=sid)
        return

    # Fetch caller profile from Neo4j — Firebase photoURL is null for email/password users.
    from app.modules.users.repository import User as UserModel
    caller_data = UserModel.get_by_id(caller_id) or {}
    caller_profile_image_url = (
        caller_data.get("profileImageUrl")
        or caller_data.get("profile_image_url")
        or data.get("callerProfileImageUrl")
    )

    call_payload = {
        "callId": str(data.get("callId") or ""),
        "bookingId": str(data.get("bookingId") or ""),
        "callerId": caller_id,
        "receiverId": receiver_id,
        "callerName": str(data.get("callerName") or caller_data.get("name") or "User"),
        "callerRole": str(data.get("callerRole") or "user"),
        "callerProfileImageUrl": caller_profile_image_url,
        "callType": str(data.get("callType") or "voice").lower(),
        "signalData": data.get("signalData") if isinstance(data.get("signalData"), dict) else {},
    }

    # REST /calls/initiate already delivered call_incoming to online users via Socket.IO.
    # Only send FCM for offline users as a fallback — fire-and-forget so the ACK
    # is returned to the caller immediately without waiting for FCM network latency.
    if not await _is_online(receiver_id):
        asyncio.create_task(_send_call_push(receiver_id, call_payload))


async def _handle_call_status_event(event_name: str, sid: str, data: dict[str, Any]):
    from_user_id = _sid_to_user.get(sid)
    call_id = str(data.get("callId") or "").strip()
    target_user_id = str(data.get("targetUserId") or "").strip()

    if call_id:
        status_map = {
            "call_accept": "answered",
            "call_reject": "rejected",
            "call_end": "ended",
        }
        call_status = status_map.get(event_name)
        if call_status:
            try:
                from app.modules.communications.calls_repository import Call
                Call.update_call_status(call_id=call_id, status=call_status, duration=data.get("duration"))
            except Exception:
                logger.exception("Failed updating call status", extra={"callId": call_id, "status": call_status})

    if target_user_id:
        event_payload = {
            "callId": call_id,
            "fromUserId": from_user_id,
            "duration": data.get("duration"),
        }
        await sio.emit(event_name, event_payload, room=_room_for_user(target_user_id))

        # FCM fallback for offline targets — fire-and-forget so the Socket.IO
        # relay above is not blocked by FCM network latency.
        if event_name == "call_end" and not await _is_online(target_user_id):
            asyncio.create_task(fcm_service.send_to_user(
                user_id=target_user_id,
                notification_type="call_end",
                title="Call Ended",
                body="The call has ended.",
                data={
                    "type": "call_end",
                    "callId": call_id,
                    "fromUserId": str(from_user_id or ""),
                    "duration": str(data.get("duration") or "0"),
                },
                booking_id="",
            ))


@sio.on("call_accept")
async def call_accept_event(sid: str, data: dict[str, Any]):
    await _handle_call_status_event("call_accept", sid, data)


@sio.on("call_reject")
async def call_reject_event(sid: str, data: dict[str, Any]):
    await _handle_call_status_event("call_reject", sid, data)


@sio.on("call_end")
async def call_end_event(sid: str, data: dict[str, Any]):
    await _handle_call_status_event("call_end", sid, data)


async def _relay_webrtc_event(event_name: str, sid: str, data: dict[str, Any]):
    from_user_id = _sid_to_user.get(sid)
    target_user_id = str(data.get("targetUserId") or "").strip()

    if not from_user_id or not target_user_id:
        await sio.emit("error", {"message": "targetUserId is required"}, to=sid)
        return

    await sio.emit(
        event_name,
        {
            "callId": str(data.get("callId") or ""),
            "fromUserId": from_user_id,
            "sdp": data.get("sdp"),
            "type": data.get("type"),
            "candidate": data.get("candidate"),
            "sdpMid": data.get("sdpMid"),
            "sdpMLineIndex": data.get("sdpMLineIndex"),
        },
        room=_room_for_user(target_user_id),
    )


@sio.on("webrtc_offer")
async def webrtc_offer_event(sid: str, data: dict[str, Any]):
    await _relay_webrtc_event("webrtc_offer", sid, data)


@sio.on("webrtc_answer")
async def webrtc_answer_event(sid: str, data: dict[str, Any]):
    await _relay_webrtc_event("webrtc_answer", sid, data)


@sio.on("webrtc_ice_candidate")
async def webrtc_ice_candidate_event(sid: str, data: dict[str, Any]):
    await _relay_webrtc_event("webrtc_ice_candidate", sid, data)


@sio.on("location_update")
async def location_update_event(sid: str, data: dict[str, Any]):
    sender_id = _sid_to_user.get(sid)
    if not sender_id:
        return

    booking_id = str(data.get("bookingId") or "").strip()
    target_user_id = str(data.get("targetUserId") or "").strip()
    lat = data.get("latitude")
    lng = data.get("longitude")

    if not booking_id or lat is None or lng is None:
        return

    payload: dict[str, Any] = {
        "bookingId": booking_id,
        "userId": sender_id,
        "latitude": lat,
        "longitude": lng,
        "heading": data.get("heading"),
        "speed": data.get("speed"),
        "accuracy": data.get("accuracy"),
        "timestamp": datetime.utcnow().isoformat(),
    }

    await redis_client.cache_location(booking_id, sender_id, payload)

    if target_user_id:
        await sio.emit("location_update", payload, room=_room_for_user(target_user_id))

    # Fire-and-forget Neo4j persist — don't block the event loop
    from app.modules.locations.repository import LocationUpdate
    asyncio.create_task(asyncio.to_thread(
        LocationUpdate.update_location,
        sender_id, booking_id, lat, lng,
        data.get("heading"), data.get("speed"), data.get("accuracy"),
    ))
