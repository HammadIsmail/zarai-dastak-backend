"""
Booking REST API Controller - Complete Booking Lifecycle
Handles: Request → Negotiation → Confirmation → Tracking → Completion

Booking Status Flow:
1. pending - Seeker creates booking request
2. bidding - Providers are making fare offers
3. accepted - Seeker accepted a fare offer
4. provider_arriving - Provider is on the way
5. provider_arrived - Provider reached pickup location
6. in_progress - Service has started
7. completed - Service completed successfully
8. cancelled - Booking was cancelled
"""

import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Query
from typing import Optional, List
from pydantic import BaseModel, Field
from app.modules.bookings.schemas import BookingCreate, BookingUpdate, BookingResponse
from app.modules.bookings.repository import Booking
from app.modules.locations.repository import LocationUpdate
from app.core.services.fcm_service import fcm_service
from app.core.constants import BookingStatus, UserRole
from app.core.realtime.socketio_gateway import sio


def _to_iso(value) -> str:
    """Safely convert a datetime (or string) to an ISO-8601 string."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value:
        return value
    return datetime.utcnow().isoformat()


def _snake_to_camel(snake_str: str) -> str:
    """Convert snake_case string to camelCase"""
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


def _to_camel_case(data: dict) -> dict:
    """Convert dictionary keys from snake_case to camelCase"""
    if not isinstance(data, dict):
        return data
    
    camel_dict = {}
    for key, value in data.items():
        camel_key = _snake_to_camel(key)
        if isinstance(value, dict):
            camel_dict[camel_key] = _to_camel_case(value)
        elif isinstance(value, list):
            camel_dict[camel_key] = [_to_camel_case(item) if isinstance(item, dict) else item for item in value]
        else:
            camel_dict[camel_key] = value
    return camel_dict


router = APIRouter()


async def _notify(user_id: str, type: str, title: str, body: str, data: Optional[dict] = None) -> None:
    """Create a Neo4j notification and emit it in real-time via Socket.IO."""
    try:
        from app.modules.communications.notifications_repository import Notification
        from app.core.realtime.socketio_gateway import emit_to_user_event
        import asyncio
        notification = await asyncio.to_thread(
            Notification.create, user_id, type, title, body, data or {}
        )
        if notification:
            import json
            payload = dict(notification)
            raw = payload.get('data')
            payload['data'] = json.loads(raw) if isinstance(raw, str) else (raw or {})
            await emit_to_user_event(user_id, 'notification', payload)
    except Exception:
        pass  # notifications are non-critical


# Additional schemas for this controller
class BookingsListResponse(BaseModel):
    success: bool
    message: str
    bookings: List[dict] = []
    total: int = 0


class RatingRequest(BaseModel):
    rating: float = Field(..., ge=1, le=5, description="Rating from 1-5")
    review: Optional[str] = Field(None, description="Optional review text")


class AcceptBookingRequest(BaseModel):
    providerId: str = Field(..., description="Provider user ID")
    vehicleId: Optional[str] = Field(None, description="Provider vehicle ID")


class ProviderArrivingRequest(BaseModel):
    estimatedMinutes: Optional[int] = Field(None, description="Estimated arrival time in minutes")


class CompleteBookingRequest(BaseModel):
    finalPrice: Optional[float] = Field(None, description="Final booking price")


class CancelBookingRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Cancellation reason")
    cancelledBy: Optional[str] = Field(None, description="User ID who cancelled")


# ============================================
# SEEKER ENDPOINTS
# ============================================

@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(booking: BookingCreate):
    """
    SEEKER: Create a new booking request
    This broadcasts to online providers who can make fare offers
    """
    try:
        active_booking = Booking.get_active_booking(booking.seekerId, UserRole.SEEKER)
        if active_booking:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have an active booking. Please complete or cancel it before creating a new request."
            )

        booking_data = Booking.create(booking.dict())

        if not booking_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create booking"
            )

        # Fetch seeker profile so providers see real name/image/rating on request cards
        from app.modules.users.repository import User
        seeker_profile = await asyncio.to_thread(User.get_by_id, booking.seekerId)
        seeker_name = (seeker_profile or {}).get('name') or 'Customer'
        seeker_image = (seeker_profile or {}).get('profileImageUrl')
        seeker_rating = (seeker_profile or {}).get('rating')

        # Handle notifications based on booking type:
        # If providerId is set (direct booking): notify only that provider
        # If providerId is null (open request): broadcast to all providers
        if booking_data.get('providerId'):
            # Direct booking - notify only the assigned provider
            await fcm_service.send_to_user(
                user_id=booking_data['providerId'],
                notification_type='new_booking_request',
                title="🚚 New Booking Request",
                body=f"{seeker_name} needs {booking.serviceType} service",
                data={
                    "bookingId": booking_data['id'],
                    "seekerName": seeker_name,
                    "serviceType": booking.serviceType,
                    "pickupAddress": booking.pickupAddress,
                },
                booking_id=booking_data['id']
            )
        else:
            # Open request - broadcast to all providers
            await fcm_service.notify_new_booking_request(
                booking_id=booking_data['id'],
                seeker_name=seeker_name,
                service_type=booking.serviceType,
                pickup_address=booking.pickupAddress,
                exclude_seeker_id=booking.seekerId
            )

        # Broadcast via Socket.IO for real-time delivery to connected providers.
        # If providerId is set, only emit to that provider; otherwise broadcast to all
        now_iso = _to_iso(booking_data.get('createdAt'))
        booking_payload = {
            # Primary ID used by BookingEntity.fromJson
            'id': booking_data['id'],
            # Kept for backward-compatibility with any existing listeners
            'bookingId': booking_data['id'],
            'seekerId': booking.seekerId,
            'seekerName': seeker_name,
            'seekerProfileImageUrl': seeker_image,
            'seekerRating': seeker_rating,
            'providerId': booking.providerId,
            'serviceId': booking.serviceId,
            'vehicleId': booking.vehicleId,
            'serviceType': booking.serviceType,
            'status': BookingStatus.PENDING,
            'pickupAddress': booking.pickupAddress,
            'pickupLatitude': booking.pickupLatitude,
            'pickupLongitude': booking.pickupLongitude,
            'dropAddress': booking.dropAddress,
            'dropLatitude': booking.dropLatitude,
            'dropLongitude': booking.dropLongitude,
            'distanceInKm': booking.distanceInKm,
            'estimatedPrice': booking.estimatedPrice,
            'hours': booking.hours,
            'isUrgent': booking.isUrgent,
            'scheduledDateTime': _to_iso(booking_data.get('scheduledDateTime')) or booking.scheduledDateTime,
            'createdAt': now_iso,
            'updatedAt': now_iso,
        }
        
        if booking_data.get('providerId'):
            # Direct booking — emit only to the assigned provider via their user room.
            # NOTE: the gateway creates rooms named "user:{userId}", NOT "provider_{userId}".
            from app.core.realtime.socketio_gateway import emit_to_user_event
            await emit_to_user_event(booking_data['providerId'], 'new_booking_request', booking_payload)
            asyncio.create_task(_notify(
                booking_data['providerId'], 'new_booking_request',
                'New Booking Request',
                f"{booking_data.get('seekerName', 'Customer')} needs {booking.serviceType} service",
                {'bookingId': booking_data['id']},
            ))
        else:
            # Open request — broadcast to all connected clients (providers will handle it).
            await sio.emit('new_booking_request', booking_payload)

        return BookingResponse(
            success=True,
            message="Booking created successfully." if not booking.providerId else f"Booking assigned to provider.",
            booking=_to_camel_case(booking_data)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create booking: {str(e)}"
        )


@router.get("/seeker/{seeker_id}", response_model=BookingsListResponse)
async def get_seeker_bookings(
    seeker_id: str,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status")
):
    """SEEKER: Get all bookings for a seeker"""
    try:
        bookings = Booking.get_by_seeker(seeker_id, status_filter)
        
        # Convert snake_case to camelCase for Flutter frontend
        camel_bookings = [_to_camel_case(b) for b in bookings]
        
        return BookingsListResponse(
            success=True,
            message="Bookings retrieved successfully",
            bookings=camel_bookings,
            total=len(camel_bookings)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch bookings: {str(e)}"
        )


@router.get("/seeker/{seeker_id}/active", response_model=BookingResponse)
async def get_seeker_active_booking(seeker_id: str):
    """SEEKER: Get current active booking (if any)"""
    try:
        booking = Booking.get_active_booking(seeker_id, UserRole.SEEKER)
        
        # Convert snake_case to camelCase for Flutter frontend
        booking_camel = _to_camel_case(booking) if booking else None
        
        return BookingResponse(
            success=True,
            message="Active booking retrieved" if booking else "No active booking",
            booking=booking_camel
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch active booking: {str(e)}"
        )


# ============================================
# PROVIDER ENDPOINTS
# ============================================

@router.get("/provider/{provider_id}", response_model=BookingsListResponse)
async def get_provider_bookings(
    provider_id: str,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status")
):
    """PROVIDER: Get all bookings assigned to a provider"""
    try:
        bookings = Booking.get_by_provider(provider_id, status_filter)
        
        # Convert snake_case to camelCase for Flutter frontend
        camel_bookings = [_to_camel_case(b) for b in bookings]
        
        return BookingsListResponse(
            success=True,
            message="Bookings retrieved successfully",
            bookings=camel_bookings,
            total=len(camel_bookings)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch bookings: {str(e)}"
        )


@router.get("/provider/{provider_id}/active", response_model=BookingResponse)
async def get_provider_active_booking(provider_id: str):
    """PROVIDER: Get current active booking (if any)"""
    try:
        booking = Booking.get_active_booking(provider_id, UserRole.PROVIDER)
        
        # Convert snake_case to camelCase for Flutter frontend
        booking_camel = _to_camel_case(booking) if booking else None
        
        return BookingResponse(
            success=True,
            message="Active booking retrieved" if booking else "No active booking",
            booking=booking_camel
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch active booking: {str(e)}"
        )


@router.get("/available", response_model=BookingsListResponse)
async def get_available_bookings(
    service_type: Optional[str] = Query(None, description="Filter by service type"),
    latitude: Optional[float] = Query(None, description="Provider's current latitude"),
    longitude: Optional[float] = Query(None, description="Provider's current longitude"),
    radius_km: float = Query(50.0, description="Search radius in kilometers")
):
    """PROVIDER: Get available booking requests to bid on"""
    try:
        bookings = Booking.get_available_bookings(
            service_type=service_type,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km
        )
        
        # Convert snake_case to camelCase for Flutter frontend
        camel_bookings = [_to_camel_case(b) for b in bookings]
        
        return BookingsListResponse(
            success=True,
            message="Available bookings retrieved successfully",
            bookings=camel_bookings,
            total=len(camel_bookings)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch available bookings: {str(e)}"
        )


# ============================================
# BOOKING LIFECYCLE ENDPOINTS
# ============================================

@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(booking_id: str):
    """Get booking details by ID"""
    try:
        booking = Booking.get_by_id(booking_id)
        
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )
        
        # Convert snake_case to camelCase for Flutter frontend
        booking_camel = _to_camel_case(booking)
        
        return BookingResponse(
            success=True,
            message="Booking retrieved successfully",
            booking=booking_camel
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch booking: {str(e)}"
        )


@router.put("/{booking_id}", response_model=BookingResponse)
async def update_booking(booking_id: str, booking_update: BookingUpdate):
    """Update booking details"""
    try:
        update_data = {k: v for k, v in booking_update.dict().items() if v is not None}
        booking_data = Booking.update(booking_id, update_data)
        
        if not booking_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )
        
        return BookingResponse(
            success=True,
            message="Booking updated successfully",
            booking=_to_camel_case(booking_data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update booking: {str(e)}"
        )


@router.put("/{booking_id}/arriving", response_model=BookingResponse)
async def provider_arriving(booking_id: str, payload: Optional[ProviderArrivingRequest] = None):
    """PROVIDER: Mark that provider is on the way to pickup"""
    try:
        booking_data = Booking.update_status(booking_id, BookingStatus.PROVIDER_ARRIVING)
        
        if not booking_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )
        
        # Notify seeker via FCM
        await fcm_service.notify_booking_status(
            target_user_id=booking_data['seekerId'],
            booking_id=booking_id,
            status=BookingStatus.PROVIDER_ARRIVING,
            message="Your provider is on the way!"
        )
        
        return BookingResponse(
            success=True,
            message=(
                f"Provider is arriving in {payload.estimatedMinutes} min - seeker notified"
                if payload and payload.estimatedMinutes is not None
                else "Provider is arriving - seeker notified"
            ),
            booking=_to_camel_case(booking_data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update booking: {str(e)}"
        )


@router.put("/{booking_id}/arrived", response_model=BookingResponse)
async def provider_arrived(booking_id: str):
    """PROVIDER: Mark that provider has arrived at pickup location"""
    try:
        booking_data = Booking.update_status(booking_id, BookingStatus.PROVIDER_ARRIVED)
        
        if not booking_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )
        
        # Notify seeker via FCM
        await fcm_service.notify_booking_status(
            target_user_id=booking_data['seekerId'],
            booking_id=booking_id,
            status=BookingStatus.PROVIDER_ARRIVED,
            message="Your provider has arrived at the pickup location!"
        )
        
        return BookingResponse(
            success=True,
            message="Provider has arrived - seeker notified",
            booking=_to_camel_case(booking_data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update booking: {str(e)}"
        )


@router.put("/{booking_id}/start", response_model=BookingResponse)
async def start_booking(booking_id: str):
    """PROVIDER: Start the service"""
    try:
        booking_data = Booking.start(booking_id)
        
        if not booking_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )
        
        # Notify seeker via FCM
        await fcm_service.notify_booking_status(
            target_user_id=booking_data['seekerId'],
            booking_id=booking_id,
            status=BookingStatus.IN_PROGRESS,
            message="Service has started!"
        )
        
        return BookingResponse(
            success=True,
            message="Booking started - service in progress",
            booking=_to_camel_case(booking_data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start booking: {str(e)}"
        )


@router.put("/{booking_id}/complete", response_model=BookingResponse)
async def complete_booking(
    booking_id: str,
    payload: Optional[CompleteBookingRequest] = None,
    final_price: Optional[float] = None,
):
    """PROVIDER: Complete the booking"""
    try:
        resolved_final_price = (
            payload.finalPrice
            if payload and payload.finalPrice is not None
            else final_price
        )

        booking_data = Booking.complete(booking_id, resolved_final_price)

        if not booking_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )

        # Increment provider's completed bookings counter (fire-and-forget).
        _provider_id_for_increment = booking_data.get('providerId')
        if _provider_id_for_increment:
            try:
                from app.modules.users.legacy_controller import UserController
                UserController().increment_completed_bookings(_provider_id_for_increment)
            except Exception:
                pass  # counter drift is acceptable; get_by_id() recomputes dynamically

        # Emit real-time booking_completed Socket.IO event to BOTH parties FIRST.
        # This is what drives the dual-review redirect, so it must fire before we return.
        from app.core.realtime.socketio_gateway import emit_to_user_event
        completion_payload = {
            "bookingId": booking_id,
            "status": BookingStatus.COMPLETED,
            "seekerId": booking_data.get('seekerId'),
            "seekerName": booking_data.get('seekerName') or 'Customer',
            "providerId": booking_data.get('providerId'),
            "providerName": booking_data.get('providerName') or 'Provider',
            "finalPrice": booking_data.get('finalPrice'),
            "serviceType": booking_data.get('serviceType'),
        }
        seeker_id = booking_data.get('seekerId')
        provider_id = booking_data.get('providerId')
        if seeker_id:
            await emit_to_user_event(seeker_id, "booking_completed", completion_payload)
        if provider_id:
            await emit_to_user_event(provider_id, "booking_completed", completion_payload)

        # Non-critical side effects: fire-and-forget so the HTTP response returns
        # immediately. FCM is for offline delivery (slow); location cleanup is housekeeping.
        if seeker_id:
            asyncio.create_task(fcm_service.notify_booking_status(
                target_user_id=seeker_id,
                booking_id=booking_id,
                status=BookingStatus.COMPLETED,
                message="Service completed! Please rate your experience."
            ))
        asyncio.create_task(asyncio.to_thread(LocationUpdate.delete_booking_locations, booking_id))

        # Persist in-app notifications for both parties.
        service_type = booking_data.get('serviceType', 'service')
        if seeker_id:
            asyncio.create_task(_notify(
                seeker_id, 'booking_completed',
                'Service Completed',
                f'Your {service_type} booking is complete. Please rate your experience.',
                {'bookingId': booking_id},
            ))
        if provider_id:
            asyncio.create_task(_notify(
                provider_id, 'booking_completed',
                'Job Completed',
                f'{service_type} job done. Great work!',
                {'bookingId': booking_id},
            ))

        return BookingResponse(
            success=True,
            message="Booking completed successfully",
            booking=_to_camel_case(booking_data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete booking: {str(e)}"
        )


@router.put("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: str,
    payload: Optional[CancelBookingRequest] = None,
    reason: Optional[str] = None,
    cancelled_by: Optional[str] = None,
):
    """Cancel a booking (can be called by seeker or provider)"""
    try:
        # Get booking first to know who to notify
        existing = Booking.get_by_id(booking_id)
        
        resolved_reason = payload.reason if payload and payload.reason is not None else reason
        resolved_cancelled_by = (
            payload.cancelledBy if payload and payload.cancelledBy is not None else cancelled_by
        )

        booking_data = Booking.cancel(booking_id, resolved_reason)
        
        if not booking_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )
        
        # Notify the other party via FCM
        if existing:
            target_user = existing['seekerId'] if resolved_cancelled_by == existing.get('providerId') else existing.get('providerId')
            if target_user:
                cancelled_by_name = existing.get('providerName') if resolved_cancelled_by == existing.get('providerId') else existing.get('seekerName', 'User')
                await fcm_service.notify_booking_cancelled(
                    target_user_id=target_user,
                    booking_id=booking_id,
                    cancelled_by_name=cancelled_by_name or 'User'
                )
        
        # Clean up location data
        LocationUpdate.delete_booking_locations(booking_id)
        
        return BookingResponse(
            success=True,
            message="Booking cancelled successfully",
            booking=_to_camel_case(booking_data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel booking: {str(e)}"
        )


@router.put("/{booking_id}/rate", response_model=BookingResponse)
async def rate_booking(booking_id: str, rating_req: RatingRequest):
    """SEEKER: Rate a completed booking"""
    try:
        booking_data = Booking.add_rating(booking_id, rating_req.rating, rating_req.review)
        
        if not booking_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )
        
        return BookingResponse(
            success=True,
            message="Rating submitted successfully",
            booking=_to_camel_case(booking_data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit rating: {str(e)}"
        )


# ============================================
# LEGACY ENDPOINTS (for backward compatibility)
# ============================================

@router.put("/{booking_id}/accept", response_model=BookingResponse)
async def accept_booking(
    booking_id: str,
    payload: Optional[AcceptBookingRequest] = None,
    provider_id: Optional[str] = Query(None, alias="provider_id"),
    vehicle_id: Optional[str] = Query(None, alias="vehicle_id"),
):
    """
    DEPRECATED: Use fare offers instead
    Provider directly accepts a booking (legacy flow)
    """
    try:
        resolved_provider_id = provider_id or (payload.providerId if payload else None)
        resolved_vehicle_id = vehicle_id or (payload.vehicleId if payload else None)

        if not resolved_provider_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="provider_id (query) or providerId (body) is required"
            )

        active_booking = Booking.get_active_booking(resolved_provider_id, UserRole.PROVIDER)
        if active_booking and active_booking.get('id') != booking_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This provider already has an active service. Please complete or reject the current booking before accepting a new one."
            )

        booking_data = Booking.accept(booking_id, resolved_provider_id, resolved_vehicle_id)
        
        if not booking_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )
        
        # Notify seeker via FCM
        await fcm_service.notify_booking_status(
            target_user_id=booking_data['seekerId'],
            booking_id=booking_id,
            status=BookingStatus.ACTIVE,
            message='Your provider has accepted the booking. Live tracking is now available.'
        )
        
        return BookingResponse(
            success=True,
            message="Booking accepted successfully",
            booking=_to_camel_case(booking_data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to accept booking: {str(e)}"
        )


@router.put("/{booking_id}/reject", response_model=BookingResponse)
async def reject_booking(booking_id: str, provider_id: str, reason: Optional[str] = None):
    """Provider rejects a booking"""
    try:
        booking_data = Booking.reject(booking_id, provider_id, reason)
        
        if not booking_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )

        # Notify seeker via FCM for request-status flow
        seeker_id = booking_data.get('seekerId')
        if seeker_id:
            await fcm_service.notify_booking_status(
                target_user_id=seeker_id,
                booking_id=booking_id,
                status=BookingStatus.REJECTED,
                message="Your service request was rejected by the provider."
            )
        
        return BookingResponse(
            success=True,
            message="Booking rejected successfully",
            booking=_to_camel_case(booking_data)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reject booking: {str(e)}"
        )
