from typing import List, Optional, Dict, Any
from datetime import datetime
from app.core.database import get_neo4j_driver
from app.modules.bookings.repository import Booking
from app.core.config import settings
from app.core.constants import BookingStatus


class BookingController:
    """Controller for Booking operations (MVC Pattern)"""
    
    def __init__(self):
        self.db = get_neo4j_driver()
    
    def create_booking(self, booking_data: Dict[str, Any]) -> Booking:
        """Create a new booking"""
        booking = Booking.from_dict(booking_data)
        
        # Sanitize serviceType for use as label (remove spaces, special chars)
        service_label = booking.service_type.replace(' ', '').replace('-', '').replace('_', '') if booking.service_type else 'General'
        
        query = f"""
        MATCH (s {{id: $seeker_id}})
        WHERE s:Seeker OR s:User
        CREATE (b:Booking:{service_label} {{
            id: $id,
            seekerId: $seeker_id,
            providerId: $provider_id,
            vehicleId: $vehicle_id,
            serviceType: $service_type,
            status: $status,
            pickupLatitude: $pickup_latitude,
            pickupLongitude: $pickup_longitude,
            pickupAddress: $pickup_address,
            dropLatitude: $drop_latitude,
            dropLongitude: $drop_longitude,
            dropAddress: $drop_address,
            distanceInKm: $distance_in_km,
            estimatedPrice: $estimated_price,
            finalPrice: $final_price,
            hours: $hours,
            isUrgent: $is_urgent,
            scheduledDateTime: datetime($scheduled_date_time),
            notes: $notes,
            createdAt: datetime($created_at),
            updatedAt: datetime($updated_at)
        }})
        CREATE (s)-[:CREATED]->(b)
        RETURN b
        """
        
        self.db.execute_write(query, booking.to_neo4j_props())
        return booking
    
    def get_booking_by_id(self, booking_id: str) -> Optional[Booking]:
        """Get booking by ID"""
        query = """
        MATCH (b:Booking {id: $booking_id})
        RETURN b
        """
        
        result = self.db.execute_read(query, {'booking_id': booking_id})
        
        if result and len(result) > 0:
            booking_data = result[0]['b']
            return Booking.from_dict(booking_data)
        return None
    
    def get_user_bookings(self, user_id: str) -> List[Booking]:
        """Get all bookings for a user (as seeker or provider)"""
        query = """
        MATCH (b:Booking)
        WHERE b.seekerId = $user_id OR (b.providerId IS NOT NULL AND b.providerId = $user_id)
        OPTIONAL MATCH (seeker) WHERE (seeker:Seeker OR seeker:User) AND seeker.id = b.seekerId
        OPTIONAL MATCH (provider) WHERE (provider:Provider OR provider:User) AND provider.id = b.providerId
        WITH b, seeker.name AS seekerName, provider.name AS providerName
        RETURN b, seekerName, providerName
        ORDER BY b.createdAt DESC
        """
        
        result = self.db.execute_read(query, {'user_id': user_id})
        bookings = []
        for record in result:
            booking = Booking.from_dict(record['b'])
            booking.seeker_name = record.get('seekerName')
            booking.provider_name = record.get('providerName')
            bookings.append(booking)
        return bookings
    
    def get_booking_history(self, user_id: str, status: Optional[str] = None) -> List[Booking]:
        """Get booking history with optional status filter"""
        if status:
            query = """
            MATCH (b:Booking)
            WHERE (b.seekerId = $user_id OR (b.providerId IS NOT NULL AND b.providerId = $user_id))
              AND b.status = $status
            OPTIONAL MATCH (seeker) WHERE (seeker:Seeker OR seeker:User) AND seeker.id = b.seekerId
            OPTIONAL MATCH (provider) WHERE (provider:Provider OR provider:User) AND provider.id = b.providerId
            WITH b, seeker.name AS seekerName, provider.name AS providerName
            RETURN b, seekerName, providerName
            ORDER BY b.createdAt DESC
            """
            params = {'user_id': user_id, 'status': status}
        else:
            query = """
            MATCH (b:Booking)
            WHERE b.seekerId = $user_id OR (b.providerId IS NOT NULL AND b.providerId = $user_id)
            OPTIONAL MATCH (seeker) WHERE (seeker:Seeker OR seeker:User) AND seeker.id = b.seekerId
            OPTIONAL MATCH (provider) WHERE (provider:Provider OR provider:User) AND provider.id = b.providerId
            WITH b, seeker.name AS seekerName, provider.name AS providerName
            RETURN b, seekerName, providerName
            ORDER BY b.createdAt DESC
            """
            params = {'user_id': user_id}
        
        result = self.db.execute_read(query, params)
        bookings = []
        for record in result:
            booking = Booking.from_dict(record['b'])
            booking.seeker_name = record.get('seekerName')
            booking.provider_name = record.get('providerName')
            bookings.append(booking)
        return bookings
    
    def update_booking_status(
        self,
        booking_id: str,
        status: str,
        provider_id: Optional[str] = None,
        vehicle_id: Optional[str] = None
    ) -> Optional[Booking]:
        """Update booking status and optionally assign provider/vehicle"""
        updates = {
            'status': status,
            'updated_at': datetime.now().isoformat()
        }
        
        if status == settings.STATUS_ACCEPTED and provider_id:
            updates['provider_id'] = provider_id
            if vehicle_id:
                updates['vehicle_id'] = vehicle_id
        
        if status == BookingStatus.IN_PROGRESS:
            updates['started_at'] = datetime.now().isoformat()
        
        if status == BookingStatus.COMPLETED:
            updates['completed_at'] = datetime.now().isoformat()
        
        if status == BookingStatus.CANCELLED:
            updates['cancelled_at'] = datetime.now().isoformat()
        
        set_clause = ', '.join([f'b.{key} = ${key}' for key in updates.keys()])
        
        query = f"""
        MATCH (b:Booking {{id: $booking_id}})
        SET {set_clause}
        RETURN b
        """
        
        params = {'booking_id': booking_id, **updates}
        result = self.db.execute_write(query, params)
        
        # If accepted, create relationship to provider and vehicle
        if status == settings.STATUS_ACCEPTED and provider_id:
            self._link_booking_to_provider(booking_id, provider_id, vehicle_id)
        
        if result and len(result) > 0:
            booking_data = result[0]['b']
            return Booking.from_dict(booking_data)
        return None
    
    def _link_booking_to_provider(
        self,
        booking_id: str,
        provider_id: str,
        vehicle_id: Optional[str] = None
    ):
        """Create relationships between booking, provider, and vehicle"""
        query = """
        MATCH (b:Booking {id: $booking_id})
        MATCH (p:User {id: $provider_id})
        MERGE (p)-[:ACCEPTED]->(b)
        """
        
        self.db.execute_write(query, {
            'booking_id': booking_id,
            'provider_id': provider_id
        })
        
        if vehicle_id:
            vehicle_query = """
            MATCH (b:Booking {id: $booking_id})
            MATCH (v:Vehicle {id: $vehicle_id})
            MERGE (b)-[:USES]->(v)
            """
            
            self.db.execute_write(vehicle_query, {
                'booking_id': booking_id,
                'vehicle_id': vehicle_id
            })
    
    def rate_booking(
        self,
        booking_id: str,
        rating: float,
        review: Optional[str] = None
    ) -> Optional[Booking]:
        """Rate a completed booking"""
        updates = {
            'rating': rating,
            'review': review,
            'updated_at': datetime.now().isoformat()
        }
        
        query = """
        MATCH (b:Booking {id: $booking_id, status: $completedStatus})
        SET b.rating = $rating,
            b.review = $review,
            b.updated_at = datetime($updated_at)
        RETURN b
        """
        
        result = self.db.execute_write(query, {
            'booking_id': booking_id,
            **updates,
            'completedStatus': BookingStatus.COMPLETED,
        })
        
        if result and len(result) > 0:
            # Update provider's average rating
            booking_data = result[0]['b']
            booking = Booking.from_dict(booking_data)
            
            if booking.provider_id:
                self._update_provider_rating(booking.provider_id)
            
            return booking
        return None
    
    def _update_provider_rating(self, provider_id: str):
        """Calculate and update provider's average rating"""
        query = """
        MATCH (p:User {id: $provider_id})-[:ACCEPTED]->(b:Booking)
        WHERE b.rating IS NOT NULL
        WITH p, AVG(b.rating) as avg_rating, COUNT(b) as total_bookings
        SET p.rating = avg_rating,
            p.completed_bookings = total_bookings,
            p.updated_at = datetime()
        RETURN p
        """
        
        self.db.execute_write(query, {'provider_id': provider_id})
    
    def cancel_booking(
        self,
        booking_id: str,
        cancellation_reason: str
    ) -> Optional[Booking]:
        """Cancel a booking"""
        query = """
        MATCH (b:Booking {id: $booking_id})
        WHERE b.status IN $cancellableStatuses
        SET b.status = $cancelledStatus,
            b.cancelled_at = datetime(),
            b.cancellation_reason = $cancellation_reason,
            b.updated_at = datetime()
        RETURN b
        """
        
        result = self.db.execute_write(query, {
            'booking_id': booking_id,
            'cancellation_reason': cancellation_reason,
            # Includes IN_PROGRESS because Booking.accept() now jumps directly
            # to in_progress (auto-start), skipping the legacy ACCEPTED state.
            'cancellableStatuses': [
                BookingStatus.PENDING,
                BookingStatus.ACCEPTED,
                BookingStatus.IN_PROGRESS,
            ],
            'cancelledStatus': BookingStatus.CANCELLED,
        })
        
        if result and len(result) > 0:
            booking_data = result[0]['b']
            return Booking.from_dict(booking_data)
        return None
    
    def get_pending_bookings_by_service(self, service_type: str) -> List[Booking]:
        """Get all pending bookings for a specific service type"""
        query = """
        MATCH (b:Booking {
            service_type: $service_type,
            status: $pendingStatus
        })
        RETURN b
        ORDER BY b.created_at ASC
        """
        
        result = self.db.execute_read(query, {'service_type': service_type, 'pendingStatus': BookingStatus.PENDING})
        return [Booking.from_dict(record['b']) for record in result]
