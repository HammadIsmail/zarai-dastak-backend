"""
Messages Controller
Handles text messaging endpoints with REST persistence.

Realtime delivery is handled by backend WebSocket gateway (/ws/realtime).
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from app.modules.communications.messages_repository import Message

router = APIRouter(prefix="/messages", tags=["messages"])


# Request Models
class MarkAsReadRequest(BaseModel):
    messageId: Optional[str] = None
    receiverId: Optional[str] = None
    bookingId: Optional[str] = None


# Response Models
class MessageResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


class MessagesListResponse(BaseModel):
    success: bool
    messages: List[dict]
    unreadCount: Optional[int] = None


class ConversationsListResponse(BaseModel):
    success: bool
    conversations: List[dict]


@router.get("/booking/{booking_id}", response_model=MessagesListResponse)
async def get_messages_for_booking(booking_id: str, limit: int = 100):
    """Get all messages for a booking"""
    try:
        messages = Message.get_messages_for_booking(booking_id, limit)
        
        return MessagesListResponse(
            success=True,
            messages=messages
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch messages: {str(e)}"
        )


@router.get("/conversations/{user_id}", response_model=ConversationsListResponse)
async def get_user_conversations(user_id: str, limit: int = 50):
    """Get conversation summaries for chat list screen."""
    try:
        conversations = Message.get_user_conversations(user_id, limit)
        return ConversationsListResponse(success=True, conversations=conversations)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch conversations: {str(e)}"
        )


@router.get("/conversation/{user1_id}/{user2_id}/{booking_id}", response_model=MessagesListResponse)
async def get_conversation_messages(
    user1_id: str,
    user2_id: str,
    booking_id: str,
    limit: int = 100
):
    """Get conversation between two users for a specific booking"""
    try:
        messages = Message.get_conversation_messages(user1_id, user2_id, booking_id, limit)
        
        return MessagesListResponse(
            success=True,
            messages=messages
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch conversation: {str(e)}"
        )


@router.post("/mark-read", response_model=MessageResponse)
async def mark_message_as_read(request: MarkAsReadRequest):
    """Mark message(s) as read"""
    try:
        if request.messageId:
            # Mark a specific message as read
            success = Message.mark_as_read(request.messageId)
            
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Message not found"
                )
            
            return MessageResponse(
                success=True,
                message="Message marked as read"
            )
        
        elif request.receiverId and request.bookingId:
            # Mark all messages for a receiver in a booking as read
            success = Message.mark_all_as_read(request.receiverId, request.bookingId)
            
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No messages found"
                )
            
            return MessageResponse(
                success=True,
                message="All messages marked as read"
            )
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either messageId or (receiverId and bookingId) must be provided"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mark message as read: {str(e)}"
        )


@router.get("/unread/{user_id}", response_model=MessageResponse)
async def get_unread_count(user_id: str, booking_id: Optional[str] = None):
    """Get unread message count for a user"""
    try:
        count = Message.get_unread_count(user_id, booking_id)
        
        return MessageResponse(
            success=True,
            message="Unread count retrieved successfully",
            data={"unreadCount": count}
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch unread count: {str(e)}"
        )
