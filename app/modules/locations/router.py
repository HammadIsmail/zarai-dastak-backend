"""
Location REST API Controller
Handles real-time location tracking during active bookings
"""

from fastapi import APIRouter, HTTPException, status
from app.modules.locations.schemas import (
    LocationUpdateRequest, UserLocationUpdate,
    LocationResponse, BookingLocationsResponse
)
from app.modules.locations.repository import LocationUpdate
from app.modules.bookings.repository import Booking
from app.modules.users.repository import User
from app.core.services.fcm_service import fcm_service
from app.core.constants import LIVE_COMMUNICATION_STATUSES

router = APIRouter()

ACTIVE_TRACKING_STATUSES = LIVE_COMMUNICATION_STATUSES


@router.post("/update", response_model=LocationResponse)
async def update_booking_location(location: LocationUpdateRequest):
    """
    Update user location during an active booking
    This enables real-time tracking between seeker and provider
    """
    try:
        booking = Booking.get_by_id(location.bookingId)
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )

        seeker_id = booking.get('seekerId')
        provider_id = booking.get('providerId')
        if location.userId not in {seeker_id, provider_id}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a participant in this booking"
            )

        booking_status = str(booking.get('status') or '').lower()
        if booking_status not in ACTIVE_TRACKING_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location updates are only allowed during active service"
            )

        location_data = LocationUpdate.update_location(
            user_id=location.userId,
            booking_id=location.bookingId,
            latitude=location.latitude,
            longitude=location.longitude,
            heading=location.heading,
            speed=location.speed,
            accuracy=location.accuracy
        )
        
        if not location_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update location"
            )
        
        # Send location update to the other user in the booking via FCM
        target_user_id = None
        sender_name = "User"

        if location.userId == seeker_id:
            target_user_id = provider_id
            user_data = User.get_by_id(location.userId)
            sender_name = user_data.get('name', 'Customer') if user_data else 'Customer'
        else:
            target_user_id = seeker_id
            user_data = User.get_by_id(location.userId)
            sender_name = user_data.get('name', 'Provider') if user_data else 'Provider'

        if target_user_id:
            from app.core.realtime.socketio_gateway import emit_to_user_event
            from app.core.database.redis_client import cache_location

            loc_payload = {
                "bookingId": location.bookingId,
                "userId": location.userId,
                "latitude": location.latitude,
                "longitude": location.longitude,
                "heading": location.heading,
                "speed": location.speed,
                "accuracy": location.accuracy,
            }
            await cache_location(location.bookingId, location.userId, loc_payload)
            is_online = await emit_to_user_event(target_user_id, "location_update", loc_payload)
            if not is_online:
                # Partner offline — FCM for location updates is too high-frequency; skip
                pass
        
        return LocationResponse(
            success=True,
            message="Location updated successfully",
            location=location_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update location: {str(e)}"
        )


@router.post("/user", response_model=LocationResponse)
async def update_user_location(location: UserLocationUpdate):
    """
    Update provider's general location (for discoverability)
    Not tied to a specific booking
    """
    try:
        location_data = LocationUpdate.update_user_location(
            user_id=location.userId,
            latitude=location.latitude,
            longitude=location.longitude
        )
        
        if not location_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user location"
            )
        
        return LocationResponse(
            success=True,
            message="User location updated successfully",
            location=location_data
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user location: {str(e)}"
        )


@router.get("/booking/{booking_id}", response_model=BookingLocationsResponse)
async def get_booking_locations(booking_id: str):
    """
    Get current locations of both seeker and provider for an active booking
    """
    try:
        locations = LocationUpdate.get_booking_locations(booking_id)
        
        return BookingLocationsResponse(
            success=True,
            message="Locations retrieved successfully",
            bookingId=booking_id,
            seeker=locations.get('seeker'),
            provider=locations.get('provider')
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch locations: {str(e)}"
        )


@router.get("/user/{user_id}/booking/{booking_id}", response_model=LocationResponse)
async def get_user_booking_location(user_id: str, booking_id: str):
    """Get a specific user's location in a booking"""
    try:
        location = LocationUpdate.get_location(user_id, booking_id)
        
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Location not found"
            )
        
        return LocationResponse(
            success=True,
            message="Location retrieved successfully",
            location=location
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch location: {str(e)}"
        )


@router.delete("/booking/{booking_id}")
async def cleanup_booking_locations(booking_id: str):
    """
    Clean up location data after booking is completed
    Called automatically or manually after booking ends
    """
    try:
        LocationUpdate.delete_booking_locations(booking_id)
        
        return {
            "success": True,
            "message": "Booking locations cleaned up successfully"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup locations: {str(e)}"
        )
