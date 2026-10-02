"""
FCM (Firebase Cloud Messaging) Service for Push Notifications
Replaces WebSocket for real-time notifications

Handles:
- Booking requests broadcast to providers
- Fare negotiation between seeker and provider
- Booking status updates
- Location updates (provider arriving/arrived)
"""

import asyncio
from typing import Dict, Optional, Any
from firebase_admin import messaging
from datetime import datetime
import logging
from ..constants import BookingStatus

logger = logging.getLogger(__name__)


class FCMNotificationType:
    """FCM notification types for structured communication"""
    
    # Booking lifecycle
    NEW_BOOKING_REQUEST = "new_booking_request"
    BOOKING_STATUS_UPDATE = "booking_status_update"
    BOOKING_CANCELLED = "booking_cancelled"
    BOOKING_ACCEPTED = "booking_accepted"
    BOOKING_REJECTED = "booking_rejected"
    
    # Fare negotiation
    NEW_FARE_OFFER = "new_fare_offer"
    FARE_OFFER_ACCEPTED = "fare_offer_accepted"
    FARE_OFFER_REJECTED = "fare_offer_rejected"
    COUNTER_OFFER = "counter_offer"
    OFFER_UPDATED = "offer_updated"
    OFFER_WITHDRAWN = "offer_withdrawn"
    
    # Location tracking
    LOCATION_UPDATE = "location_update"
    
    # Booking progress
    PROVIDER_ARRIVING = "provider_arriving"
    PROVIDER_ARRIVED = "provider_arrived"
    BOOKING_STARTED = "booking_started"
    BOOKING_COMPLETED = "booking_completed"


class FCMService:
    """
    Manages FCM push notifications for real-time features
    """
    
    def __init__(self):
        pass

    @staticmethod
    def _extract_fcm_token(user_data: Optional[Dict[str, Any]]) -> Optional[str]:
        if not user_data:
            return None

        token = user_data.get('fcmToken') or user_data.get('fcm_token')
        if token is None:
            return None

        token = str(token).strip()
        return token or None
    
    async def send_to_user(
        self,
        user_id: str,
        notification_type: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        booking_id: Optional[str] = None
    ) -> bool:
        """
        Send a notification to a specific user by their FCM token
        """
        from app.modules.users.repository import User
        
        try:
            # User.get_by_id is a synchronous Neo4j call — run it in a thread so
            # we don't block the asyncio event loop.
            user_data = await asyncio.to_thread(User.get_by_id, user_id)
            if not user_data:
                logger.warning(f"User not found: {user_id}")
                return False
            
            fcm_token = self._extract_fcm_token(user_data)
            if not fcm_token:
                logger.warning(f"No FCM token for user: {user_id}")
                return False
            
            return await self._send_notification(
                fcm_token=fcm_token,
                notification_type=notification_type,
                title=title,
                body=body,
                data=data,
                booking_id=booking_id
            )
        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {e}")
            return False
    
    async def send_to_token(
        self,
        fcm_token: str,
        notification_type: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        booking_id: Optional[str] = None
    ) -> bool:
        """
        Send a notification directly to an FCM token
        """
        return await self._send_notification(
            fcm_token=fcm_token,
            notification_type=notification_type,
            title=title,
            body=body,
            data=data,
            booking_id=booking_id
        )
    
    async def broadcast_to_providers(
        self,
        notification_type: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        booking_id: Optional[str] = None,
        category: Optional[str] = None,
        exclude_user: Optional[str] = None
    ) -> int:
        """
        Broadcast a notification to all providers (or filtered by category)
        Returns the number of successful sends
        """
        from ..database import neo4j_driver
        
        try:
            # Query all providers with FCM tokens.
            # isActive IS NULL check is intentional: providers without the field set
            # (legacy accounts) are treated as active so they still receive notifications.
            query = """
            MATCH (p:Provider)
            WHERE (p.isActive IS NULL OR p.isActive = true)
              AND (
                (p.fcmToken IS NOT NULL AND p.fcmToken <> '')
                OR (p.fcm_token IS NOT NULL AND p.fcm_token <> '')
              )
            """
            
            if exclude_user:
                query += " AND p.id <> $excludeUser"
            
            query += " RETURN p.id as id, coalesce(p.fcmToken, p.fcm_token) as fcmToken"
            
            params = {"excludeUser": exclude_user} if exclude_user else {}
            result = await asyncio.to_thread(neo4j_driver.execute_read, query, params)

            if not result:
                logger.info("No providers with FCM tokens found")
                return 0

            # Send to all providers concurrently instead of one-by-one so a
            # single slow FCM response doesn't serialise the whole broadcast.
            tasks = [
                self._send_notification(
                    fcm_token=record.get('fcmToken'),
                    notification_type=notification_type,
                    title=title,
                    body=body,
                    data=data,
                    booking_id=booking_id,
                )
                for record in result
                if record.get('fcmToken')
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if r is True)

            logger.info(f"Broadcast sent to {success_count} providers")
            return success_count
            
        except Exception as e:
            logger.error(f"Error broadcasting to providers: {e}")
            return 0
    
    async def _send_notification(
        self,
        fcm_token: str,
        notification_type: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        booking_id: Optional[str] = None
    ) -> bool:
        """
        Internal method to send FCM notification
        """
        try:
            # Build data payload
            payload_data = {
                'type': notification_type,
                'timestamp': datetime.now().isoformat(),
                'click_action': 'FLUTTER_NOTIFICATION_CLICK',
            }
            
            if booking_id:
                payload_data['bookingId'] = booking_id
            
            if data:
                # Convert all values to strings (FCM requirement)
                for key, value in data.items():
                    if value is not None:
                        payload_data[key] = str(value) if not isinstance(value, str) else value
            
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=payload_data,
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        channel_id='booking_channel',
                        priority='high',
                        sound='default',
                        click_action='FLUTTER_NOTIFICATION_CLICK',
                    ),
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound='default',
                            badge=1,
                            content_available=True,
                        )
                    )
                ),
                token=fcm_token,
            )
            
            # messaging.send is a blocking HTTP call — offload to thread pool so
            # the asyncio event loop is never stalled by FCM network latency.
            response = await asyncio.to_thread(messaging.send, message)
            logger.info(f"FCM notification sent: {response}")
            return True
            
        except messaging.UnregisteredError:
            logger.warning(f"FCM token is unregistered: {fcm_token[:20]}...")
            return False
        except Exception as e:
            logger.error(f"Error sending FCM notification: {e}")
            return False
    
    # Convenience methods for specific notification types
    
    async def notify_new_booking_request(
        self,
        booking_id: str,
        seeker_name: str,
        service_type: str,
        pickup_address: str,
        exclude_seeker_id: Optional[str] = None
    ) -> int:
        """Notify all providers about a new booking request"""
        return await self.broadcast_to_providers(
            notification_type=FCMNotificationType.NEW_BOOKING_REQUEST,
            title="🚚 New Booking Request",
            body=f"{seeker_name} needs {service_type} service",
            data={
                "bookingId": booking_id,
                "seekerName": seeker_name,
                "serviceType": service_type,
                "pickupAddress": pickup_address,
            },
            booking_id=booking_id,
            exclude_user=exclude_seeker_id
        )
    
    async def notify_booking_accepted(
        self,
        seeker_id: str,
        booking_id: str,
        provider_name: str,
        service_type: str
    ) -> bool:
        """Notify seeker that their booking was accepted"""
        return await self.send_to_user(
            user_id=seeker_id,
            notification_type=FCMNotificationType.BOOKING_ACCEPTED,
            title="✅ Booking Accepted",
            body=f"{provider_name} accepted your {service_type} booking",
            data={"providerName": provider_name, "serviceType": service_type},
            booking_id=booking_id
        )
    
    async def notify_booking_rejected(
        self,
        seeker_id: str,
        booking_id: str,
        provider_name: str
    ) -> bool:
        """Notify seeker that their booking was rejected"""
        return await self.send_to_user(
            user_id=seeker_id,
            notification_type=FCMNotificationType.BOOKING_REJECTED,
            title="❌ Booking Declined",
            body=f"{provider_name} is unavailable right now",
            booking_id=booking_id
        )
    
    async def notify_booking_cancelled(
        self,
        target_user_id: str,
        booking_id: str,
        cancelled_by_name: str
    ) -> bool:
        """Notify user that booking was cancelled"""
        return await self.send_to_user(
            user_id=target_user_id,
            notification_type=FCMNotificationType.BOOKING_CANCELLED,
            title="🚫 Booking Cancelled",
            body=f"Booking cancelled by {cancelled_by_name}",
            booking_id=booking_id
        )
    
    async def notify_new_fare_offer(
        self,
        seeker_id: str,
        booking_id: str,
        provider_name: str,
        fare_amount: float
    ) -> bool:
        """Notify seeker about new fare offer from provider"""
        return await self.send_to_user(
            user_id=seeker_id,
            notification_type=FCMNotificationType.NEW_FARE_OFFER,
            title="💰 New Fare Offer",
            body=f"{provider_name} offered Rs. {fare_amount:.0f}",
            data={
                "providerName": provider_name,
                "fareAmount": fare_amount
            },
            booking_id=booking_id
        )
    
    async def notify_counter_offer(
        self,
        provider_id: str,
        booking_id: str,
        seeker_name: str,
        fare_amount: float
    ) -> bool:
        """Notify provider about counter offer from seeker"""
        return await self.send_to_user(
            user_id=provider_id,
            notification_type=FCMNotificationType.COUNTER_OFFER,
            title="🔄 Counter Offer",
            body=f"{seeker_name} countered with Rs. {fare_amount:.0f}",
            data={
                "seekerName": seeker_name,
                "fareAmount": fare_amount
            },
            booking_id=booking_id
        )
    
    async def notify_fare_accepted(
        self,
        target_user_id: str,
        booking_id: str,
        accepter_name: str,
        fare_amount: float
    ) -> bool:
        """Notify user that fare offer was accepted"""
        return await self.send_to_user(
            user_id=target_user_id,
            notification_type=FCMNotificationType.FARE_OFFER_ACCEPTED,
            title="✅ Offer Accepted",
            body=f"{accepter_name} accepted Rs. {fare_amount:.0f}",
            data={
                "accepterName": accepter_name,
                "fareAmount": fare_amount
            },
            booking_id=booking_id
        )
    
    async def notify_fare_rejected(
        self,
        target_user_id: str,
        booking_id: str,
        rejecter_name: str
    ) -> bool:
        """Notify user that fare offer was rejected"""
        return await self.send_to_user(
            user_id=target_user_id,
            notification_type=FCMNotificationType.FARE_OFFER_REJECTED,
            title="❌ Offer Declined",
            body=f"{rejecter_name} declined your offer",
            booking_id=booking_id
        )
    
    async def notify_booking_status(
        self,
        target_user_id: str,
        booking_id: str,
        status: str,
        message: str
    ) -> bool:
        """Generic booking status update notification"""
        # Map status to notification type
        status_type_map = {
            BookingStatus.PROVIDER_ARRIVING: FCMNotificationType.PROVIDER_ARRIVING,
            BookingStatus.PROVIDER_ARRIVED: FCMNotificationType.PROVIDER_ARRIVED,
            BookingStatus.IN_PROGRESS: FCMNotificationType.BOOKING_STARTED,
            BookingStatus.COMPLETED: FCMNotificationType.BOOKING_COMPLETED,
        }
        
        notification_type = status_type_map.get(
            status, 
            FCMNotificationType.BOOKING_STATUS_UPDATE
        )
        
        # Map status to emoji
        status_emoji_map = {
            BookingStatus.PROVIDER_ARRIVING: "🚗",
            BookingStatus.PROVIDER_ARRIVED: "📍",
            BookingStatus.IN_PROGRESS: "▶️",
            BookingStatus.COMPLETED: "✅",
        }
        
        emoji = status_emoji_map.get(status, "📋")
        
        return await self.send_to_user(
            user_id=target_user_id,
            notification_type=notification_type,
            title=f"{emoji} Booking Update",
            body=message,
            data={"status": status},
            booking_id=booking_id
        )
    
    async def notify_location_update(
        self,
        target_user_id: str,
        booking_id: str,
        latitude: float,
        longitude: float,
        sender_name: str
    ) -> bool:
        """Send location update (for live tracking)"""
        return await self.send_to_user(
            user_id=target_user_id,
            notification_type=FCMNotificationType.LOCATION_UPDATE,
            title="📍 Location Update",
            body=f"{sender_name}'s location updated",
            data={
                "latitude": latitude,
                "longitude": longitude,
                "senderName": sender_name
            },
            booking_id=booking_id
        )


# Global FCM service instance
fcm_service = FCMService()
