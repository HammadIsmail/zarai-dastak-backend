"""
Call Controller
WebRTC call lifecycle endpoints.

Socket.IO is used for signaling events (offer/answer/ICE + call events),
with legacy WebSocket fallback kept for compatibility.
REST persists call history and call state.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, Header
from pydantic import BaseModel
from firebase_admin import messaging, auth

from app.core.constants import LIVE_COMMUNICATION_STATUSES
from app.modules.communications.calls_repository import Call
from app.core.realtime.websocket_gateway import manager, _event
from app.core.realtime.socketio_gateway import emit_to_user_event
from app.core.services.fcm_service import fcm_service
from app.core.services.turn_credentials import fetch_turn_credentials

router = APIRouter(prefix="/calls", tags=["calls"])
logger = logging.getLogger(__name__)
ACTIVE_COMMUNICATION_STATUSES = LIVE_COMMUNICATION_STATUSES


class InitiateCallRequest(BaseModel):
    callerId: str
    receiverId: str
    bookingId: str
    callType: str  # voice | video
    callerName: Optional[str] = None
    callerRole: Optional[str] = None
    callerProfileImageUrl: Optional[str] = None


class UpdateCallStatusRequest(BaseModel):
    callId: str
    status: str  # answered | ended | missed | rejected
    duration: Optional[int] = None
    userId: Optional[str] = None


class VoiceMessageRequest(BaseModel):
    senderId: str
    receiverId: str
    bookingId: str
    duration: int


class CallResponse(BaseModel):
    success: bool
    message: str
    call: Optional[dict] = None
    signalData: Optional[dict] = None


class VoiceMessageResponse(BaseModel):
    success: bool
    message: str
    voiceMessage: Optional[dict] = None


class CallHistoryResponse(BaseModel):
    success: bool
    calls: List[dict]


_FCM_LARGE_FIELDS = {"callerProfileImageUrl", "signalData"}

async def _send_call_push(receiver_fcm_token: str, payload: Dict[str, Any]) -> bool:
    try:
        # FCM data payloads are capped at 4 KB. Profile images are stored as base64
        # data URIs (can be 100–200 KB), so exclude them. The receiver fetches the
        # image via CallIdentityResolver → GET /auth/user/{callerId} when the screen
        # opens. signalData is also excluded (ICE servers, session details not needed
        # in the FCM wake-up packet — they are fetched via the call REST endpoint).
        fcm_data = {
            k: str(v) if v is not None else ""
            for k, v in payload.items()
            if k not in _FCM_LARGE_FIELDS
        }
        message = messaging.Message(
            notification=messaging.Notification(
                title="📹 Incoming Video Call" if payload.get("callType") == "video" else "📞 Incoming Call",
                body=f"Incoming {payload.get('callType', 'voice')} call from {payload.get('callerName', 'User')}",
            ),
            data={"type": "call", **fcm_data},
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="call_channel",
                    priority="max",
                    tag=str(payload.get("callId") or "call"),
                ),
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="call_ringtone.caf", badge=1, category="CALL")
                )
            ),
            token=receiver_fcm_token,
        )
        await asyncio.to_thread(messaging.send, message)
        return True
    except Exception:
        logger.exception("Failed to send offline call push")
        return False


@router.post("/initiate", response_model=CallResponse)
async def initiate_call(request: InitiateCallRequest):
    """Create call record + emit real-time incoming call event via Socket.IO."""
    try:
        from app.modules.users.repository import User

        if request.callerId == request.receiverId:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Caller and receiver must be different users",
            )

        caller_data = User.get_by_id(request.callerId)
        receiver_data = User.get_by_id(request.receiverId)

        if not caller_data or not receiver_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Caller or receiver not found",
            )

        signaling_channel = f"call_{request.bookingId}_{uuid.uuid4().hex[:8]}"
        signaling_session_id = uuid.uuid4().hex

        call_data = Call.create_call(
            caller_id=request.callerId,
            receiver_id=request.receiverId,
            booking_id=request.bookingId,
            call_type=request.callType,
            signaling_channel=signaling_channel,
            signaling_session_id=signaling_session_id,
        )

        if not call_data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Call not allowed. Communication requires an active service between booking participants.",
            )

        caller_name_actual = caller_data.get("name") or request.callerName or "User"
        caller_role = request.callerRole or caller_data.get("role", "user")
        caller_profile_image_url = (
            caller_data.get("profileImageUrl")
            or caller_data.get("profile_image_url")
            or request.callerProfileImageUrl
        )

        signal_data = {
            "callId": call_data["id"],
            "bookingId": request.bookingId,
            "callType": request.callType,
            "signalingChannel": signaling_channel,
            "sessionId": signaling_session_id,
            "callerId": request.callerId,
            "receiverId": request.receiverId,
        }

        ice_servers, turn_source = await fetch_turn_credentials()
        signal_data["iceServers"] = ice_servers
        signal_data["turnSource"] = turn_source

        incoming_event_payload = {
            "callId": call_data["id"],
            "bookingId": request.bookingId,
            "callerId": request.callerId,
            "callerName": caller_name_actual,
            "callerRole": caller_role,
            "callerProfileImageUrl": caller_profile_image_url,
            "receiverId": request.receiverId,
            "callType": request.callType,
            "signalData": signal_data,
        }

        delivered = 1 if await emit_to_user_event(request.receiverId, "call_incoming", incoming_event_payload) else 0
        if delivered == 0:
            delivered = await manager.send_to_user(request.receiverId, _event("call_incoming", incoming_event_payload))

        if delivered == 0:
            receiver_fcm_token = receiver_data.get("fcmToken") or receiver_data.get("fcm_token")
            if receiver_fcm_token:
                # Fire-and-forget: don't block the REST response waiting for FCM.
                # Socket.IO already emitted the event above; FCM is a background fallback.
                asyncio.create_task(_send_call_push(receiver_fcm_token, incoming_event_payload))

        return CallResponse(
            success=True,
            message="Call initiated successfully",
            call=call_data,
            signalData=signal_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to initiate call")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate call: {str(e)}",
        )


@router.post("/update-status", response_model=CallResponse)
async def update_call_status(request: UpdateCallStatusRequest):
    """Persist call state changes and notify both participants when online."""
    try:
        call_before = Call.get_call_by_id(request.callId)
        success = Call.update_call_status(
            call_id=request.callId,
            status=request.status,
            duration=request.duration,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call not found",
            )

        call_after = Call.get_call_by_id(request.callId) or call_before or {}

        caller_id = call_after.get("callerId")
        receiver_id = call_after.get("receiverId")

        for target_user_id in [uid for uid in [caller_id, receiver_id] if uid]:
            payload = {
                "callId": request.callId,
                "status": request.status,
                "duration": request.duration or 0,
                "callType": call_after.get("callType") or "voice",
                "otherUserName": call_after.get("receiverName") if target_user_id == caller_id else call_after.get("callerName"),
                "otherUserRole": call_after.get("receiverRole") if target_user_id == caller_id else call_after.get("callerRole"),
                "otherUserProfileImageUrl": call_after.get("receiverProfileImageUrl") if target_user_id == caller_id else call_after.get("callerProfileImageUrl"),
            }

            delivered_socketio = await emit_to_user_event(str(target_user_id), "call_status", payload)
            if delivered_socketio:
                continue

            delivered_ws = await manager.send_to_user(str(target_user_id), _event("call_status", payload))
            if delivered_ws > 0:
                continue

            # User is fully offline — FCM fallback for terminal call states so
            # a stale incoming-call screen is dismissed on the next foreground.
            if request.status in {"ended", "rejected", "missed"}:
                asyncio.create_task(
                    fcm_service.send_to_user(
                        user_id=str(target_user_id),
                        notification_type="call_end",
                        title="Call Ended",
                        body="The call has ended",
                        data={
                            "type": "call_end",
                            "callId": request.callId,
                            "status": request.status,
                            "duration": str(request.duration or 0),
                        },
                    )
                )

        return CallResponse(success=True, message=f"Call status updated to {request.status}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update call status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update call status: {str(e)}",
        )


@router.get("/turn-credentials")
async def get_turn_credentials(
    region: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = authorization.split("Bearer ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Firebase ID token",
        )

    try:
        auth.verify_id_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token",
        )

    ice_servers, source = await fetch_turn_credentials(region=region)
    return {
        "success": True,
        "iceServers": ice_servers,
        "source": source,
    }


@router.get("/history/{user_id}", response_model=CallHistoryResponse)
async def get_call_history(user_id: str, limit: int = 20):
    try:
        calls = Call.get_call_history(user_id, limit)
        return CallHistoryResponse(success=True, calls=calls)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch call history: {str(e)}",
        )


@router.get("/{call_id}", response_model=CallResponse)
async def get_call(call_id: str, user_id: Optional[str] = None):
    try:
        call = Call.get_call_by_id(call_id)
        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call not found",
            )

        signal_data = {
            "callId": call.get("id"),
            "bookingId": call.get("bookingId"),
            "callType": call.get("callType"),
            "signalingChannel": call.get("signalingChannel"),
            "sessionId": call.get("signalingSessionId"),
            "callerId": call.get("callerId"),
            "receiverId": call.get("receiverId"),
            "requestedBy": user_id,
        }

        return CallResponse(
            success=True,
            message="Call retrieved successfully",
            call=call,
            signalData=signal_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch call: {str(e)}",
        )


@router.post("/voice-message/upload", response_model=VoiceMessageResponse)
async def upload_voice_message(
    audio: UploadFile = File(...),
    senderId: str = Form(...),
    receiverId: str = Form(...),
    bookingId: str = Form(...),
    duration: int = Form(...),
):
    """Voice recording uploads are intentionally disabled (metadata-only policy)."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Voice recordings are disabled. Only call/chat metadata is stored in Aura.",
    )


@router.get("/voice-messages/{booking_id}")
async def get_voice_messages(booking_id: str, limit: int = 50):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Voice recordings are disabled. No voice message payloads are stored.",
    )


@router.post("/voice-messages/{message_id}/read")
async def mark_voice_message_read(message_id: str):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Voice recordings are disabled. Read state is not tracked for recording payloads.",
    )


@router.get("/voice-messages/unread/{user_id}")
async def get_unread_count(user_id: str):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Voice recordings are disabled. Unread counts for recording payloads are unavailable.",
    )
