"""
Fare Offer REST API Controller
Handles InDrive-style bidding and negotiation between seekers and providers
"""

from fastapi import APIRouter, HTTPException, status
from typing import Optional
from app.modules.fare_offers.schemas import (
    FareOfferCreate, CounterOfferRequest, UpdateOfferPrice,
    FareOfferResponse, FareOffersListResponse
)
from app.modules.fare_offers.repository import FareOffer
from app.core.services.fcm_service import fcm_service, FCMNotificationType
from app.core.realtime.socketio_gateway import emit_to_user_event

router = APIRouter()


@router.post("", response_model=FareOfferResponse, status_code=status.HTTP_201_CREATED)
async def create_fare_offer(offer: FareOfferCreate):
    """
    Provider creates a fare offer on a booking request (bid)
    This is the InDrive-style bidding mechanism
    """
    try:
        offer_data = FareOffer.create(offer.dict())
        
        if not offer_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create fare offer"
            )
        
        # Notify seeker via FCM about the new offer
        from app.modules.bookings.repository import Booking
        booking = Booking.get_by_id(offer.bookingId)
        if booking:
            await fcm_service.notify_new_fare_offer(
                seeker_id=booking['seekerId'],
                booking_id=offer.bookingId,
                provider_name=offer_data.get('providerName', 'Provider'),
                fare_amount=offer_data.get('offeredPrice', 0)
            )
        
        return FareOfferResponse(
            success=True,
            message="Fare offer created successfully",
            offer=offer_data
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create fare offer: {str(e)}"
        )


@router.get("/booking/{booking_id}", response_model=FareOffersListResponse)
async def get_booking_offers(booking_id: str):
    """Get all fare offers for a specific booking (for seeker to view bids)"""
    try:
        offers = FareOffer.get_offers_for_booking(booking_id)
        
        return FareOffersListResponse(
            success=True,
            message="Offers retrieved successfully",
            offers=offers,
            total=len(offers)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch offers: {str(e)}"
        )


@router.get("/provider/{provider_id}", response_model=FareOffersListResponse)
async def get_provider_offers(provider_id: str, status: Optional[str] = None):
    """Get all offers made by a provider"""
    try:
        offers = FareOffer.get_provider_offers(provider_id, status)
        
        return FareOffersListResponse(
            success=True,
            message="Provider offers retrieved successfully",
            offers=offers,
            total=len(offers)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch provider offers: {str(e)}"
        )


@router.get("/{offer_id}", response_model=FareOfferResponse)
async def get_offer(offer_id: str):
    """Get a specific fare offer by ID"""
    try:
        offer = FareOffer.get_by_id(offer_id)
        
        if not offer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offer not found"
            )
        
        return FareOfferResponse(
            success=True,
            message="Offer retrieved successfully",
            offer=offer
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch offer: {str(e)}"
        )


@router.put("/{offer_id}/accept", response_model=FareOfferResponse)
async def accept_offer(offer_id: str):
    """
    Seeker accepts a fare offer
    This confirms the booking with the selected provider
    """
    try:
        offer_data = FareOffer.accept_offer(offer_id)
        
        if not offer_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offer not found"
            )
        
        seeker_name = offer_data.get('booking', {}).get('seekerName', 'Customer')
        accepted_price = offer_data.get('acceptedPrice', offer_data.get('offeredPrice', 0))

        # Notify provider via Socket.IO (instant when online) and FCM (fallback)
        await emit_to_user_event(
            offer_data['providerId'],
            'fare_offer_accepted',
            {
                'offerId': offer_id,
                'bookingId': offer_data['bookingId'],
                'acceptedPrice': accepted_price,
                'seekerName': seeker_name,
                'status': 'accepted',
            }
        )
        await fcm_service.notify_fare_accepted(
            target_user_id=offer_data['providerId'],
            booking_id=offer_data['bookingId'],
            accepter_name=seeker_name,
            fare_amount=accepted_price
        )

        return FareOfferResponse(
            success=True,
            message="Offer accepted - booking confirmed!",
            offer=offer_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to accept offer: {str(e)}"
        )


@router.put("/{offer_id}/reject", response_model=FareOfferResponse)
async def reject_offer(offer_id: str):
    """Seeker rejects a fare offer"""
    try:
        # Get offer first to notify provider
        existing = FareOffer.get_by_id(offer_id)
        
        offer_data = FareOffer.reject_offer(offer_id)
        
        if not offer_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offer not found"
            )
        
        # Notify provider via Socket.IO (instant when online) and FCM (fallback)
        if existing:
            from app.modules.bookings.repository import Booking
            booking = Booking.get_by_id(existing['bookingId'])
            seeker_name = booking.get('seekerName', 'Customer') if booking else 'Customer'
            await emit_to_user_event(
                existing['providerId'],
                'fare_offer_rejected',
                {
                    'offerId': offer_id,
                    'bookingId': existing['bookingId'],
                    'seekerName': seeker_name,
                    'status': 'rejected',
                }
            )
            await fcm_service.notify_fare_rejected(
                target_user_id=existing['providerId'],
                booking_id=existing['bookingId'],
                rejecter_name=seeker_name
            )
        
        return FareOfferResponse(
            success=True,
            message="Offer rejected successfully",
            offer=offer_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reject offer: {str(e)}"
        )


@router.put("/{offer_id}/counter", response_model=FareOfferResponse)
async def counter_offer(offer_id: str, counter: CounterOfferRequest):
    """
    Seeker makes a counter offer
    Provider can then accept, reject, or update their price
    """
    try:
        # Get offer first to notify provider
        existing = FareOffer.get_by_id(offer_id)
        
        offer_data = FareOffer.counter_offer(offer_id, counter.counterPrice)
        
        if not offer_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offer not found"
            )
        
        # Notify provider via Socket.IO (instant when online) and FCM (fallback)
        if existing:
            from app.modules.bookings.repository import Booking
            booking = Booking.get_by_id(existing['bookingId'])
            seeker_name = booking.get('seekerName', 'Customer') if booking else 'Customer'
            await emit_to_user_event(
                existing['providerId'],
                'counter_offer',
                {
                    'offerId': offer_id,
                    'bookingId': existing['bookingId'],
                    'counterPrice': counter.counterPrice,
                    'seekerName': seeker_name,
                    'status': 'counter_offered',
                }
            )
            await fcm_service.notify_counter_offer(
                provider_id=existing['providerId'],
                booking_id=existing['bookingId'],
                seeker_name=seeker_name,
                fare_amount=counter.counterPrice
            )
        
        return FareOfferResponse(
            success=True,
            message="Counter offer sent successfully",
            offer=offer_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send counter offer: {str(e)}"
        )


@router.put("/{offer_id}/update-price", response_model=FareOfferResponse)
async def update_offer_price(offer_id: str, update: UpdateOfferPrice):
    """
    Provider updates their offer price (in response to counter offer)
    """
    try:
        # Get offer and booking to notify seeker
        existing = FareOffer.get_by_id(offer_id)
        
        offer_data = FareOffer.update_offer_price(offer_id, update.newPrice, update.message)
        
        if not offer_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offer not found"
            )
        
        # Notify seeker via Socket.IO (instant when online) and FCM (fallback)
        if existing:
            from app.modules.bookings.repository import Booking
            booking = Booking.get_by_id(existing['bookingId'])
            if booking:
                await emit_to_user_event(
                    booking['seekerId'],
                    'fare_offer_updated',
                    {
                        'offerId': offer_id,
                        'bookingId': existing['bookingId'],
                        'newPrice': update.newPrice,
                        'providerName': existing.get('providerName', 'Provider'),
                        'status': 'updated',
                    }
                )
                await fcm_service.notify_new_fare_offer(
                    seeker_id=booking['seekerId'],
                    booking_id=existing['bookingId'],
                    provider_name=existing.get('providerName', 'Provider'),
                    fare_amount=update.newPrice
                )
        
        return FareOfferResponse(
            success=True,
            message="Offer price updated successfully",
            offer=offer_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update offer price: {str(e)}"
        )


@router.put("/{offer_id}/withdraw", response_model=FareOfferResponse)
async def withdraw_offer(offer_id: str):
    """Provider withdraws their offer"""
    try:
        # Get offer and booking to notify seeker
        existing = FareOffer.get_by_id(offer_id)
        
        offer_data = FareOffer.withdraw_offer(offer_id)
        
        if not offer_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offer not found"
            )
        
        # Notify seeker about withdrawn offer via FCM
        if existing:
            from app.modules.bookings.repository import Booking
            booking = Booking.get_by_id(existing['bookingId'])
            if booking:
                await fcm_service.send_to_user(
                    user_id=booking['seekerId'],
                    notification_type=FCMNotificationType.OFFER_WITHDRAWN,
                    title="Offer Withdrawn",
                    body=f"{existing.get('providerName', 'Provider')} withdrew their offer",
                    booking_id=existing['bookingId']
                )
        
        return FareOfferResponse(
            success=True,
            message="Offer withdrawn successfully",
            offer=offer_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to withdraw offer: {str(e)}"
        )
