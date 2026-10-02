from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid
from app.core.database.neo4j_driver import neo4j_driver
from app.core.constants import BookingStatus, ACTIVE_BOOKING_STATUSES


class Booking:
    """Booking model for service bookings"""
    
    def __init__(
        self,
        id: str,
        seeker_id: str,
        provider_id: Optional[str],
        vehicle_id: Optional[str],
        service_type: str,
        status: str,
        pickup_latitude: float,
        pickup_longitude: float,
        pickup_address: str,
        drop_latitude: float,
        drop_longitude: float,
        drop_address: str,
        distance_in_km: float,
        estimated_price: float,
        final_price: Optional[float] = None,
        hours: int = 1,
        is_urgent: bool = False,
        scheduled_date_time: Optional[datetime] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        cancelled_at: Optional[datetime] = None,
        cancellation_reason: Optional[str] = None,
        notes: Optional[str] = None,
        rating: Optional[float] = None,
        review: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        self.id = id
        self.seeker_id = seeker_id
        self.seeker_name = None  # Will be set from query joins
        self.provider_id = provider_id
        self.provider_name = None  # Will be set from query joins
        self.vehicle_id = vehicle_id
        self.service_type = service_type
        self.status = status
        self.pickup_latitude = pickup_latitude
        self.pickup_longitude = pickup_longitude
        self.pickup_address = pickup_address
        self.drop_latitude = drop_latitude
        self.drop_longitude = drop_longitude
        self.drop_address = drop_address
        self.distance_in_km = distance_in_km
        self.estimated_price = estimated_price
        self.final_price = final_price
        self.hours = hours
        self.is_urgent = is_urgent
        self.scheduled_date_time = scheduled_date_time or datetime.now()
        self.started_at = started_at
        self.completed_at = completed_at
        self.cancelled_at = cancelled_at
        self.cancellation_reason = cancellation_reason
        self.notes = notes
        self.rating = rating
        self.review = review
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Booking':
        """Create Booking instance from dictionary (supports both camelCase and snake_case)"""
        from neo4j.time import DateTime as Neo4jDateTime
        
        def get_value(camel_key: str, snake_key: str, default=None):
            """Get value with camelCase preference, fallback to snake_case"""
            value = data.get(camel_key)
            if value is not None:
                # Convert Neo4j DateTime to Python datetime
                if isinstance(value, Neo4jDateTime):
                    return value.to_native()
                return value
            value = data.get(snake_key, default)
            if isinstance(value, Neo4jDateTime):
                return value.to_native()
            return value
        
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            seeker_id=get_value('seekerId', 'seeker_id'),
            provider_id=get_value('providerId', 'provider_id'),
            vehicle_id=get_value('vehicleId', 'vehicle_id'),
            service_type=get_value('serviceType', 'service_type'),
            status=data.get('status', BookingStatus.PENDING),
            pickup_latitude=float(get_value('pickupLatitude', 'pickup_latitude')),
            pickup_longitude=float(get_value('pickupLongitude', 'pickup_longitude')),
            pickup_address=get_value('pickupAddress', 'pickup_address'),
            drop_latitude=float(get_value('dropLatitude', 'drop_latitude')),
            drop_longitude=float(get_value('dropLongitude', 'drop_longitude')),
            drop_address=get_value('dropAddress', 'drop_address'),
            distance_in_km=float(get_value('distanceInKm', 'distance_in_km')),
            estimated_price=float(get_value('estimatedPrice', 'estimated_price')),
            final_price=float(get_value('finalPrice', 'final_price')) if get_value('finalPrice', 'final_price') is not None else None,
            hours=data.get('hours', 1),
            is_urgent=get_value('isUrgent', 'is_urgent', False),
            scheduled_date_time=get_value('scheduledDateTime', 'scheduled_date_time'),
            started_at=get_value('startedAt', 'started_at'),
            completed_at=get_value('completedAt', 'completed_at'),
            cancelled_at=get_value('cancelledAt', 'cancelled_at'),
            cancellation_reason=get_value('cancellationReason', 'cancellation_reason'),
            notes=data.get('notes'),
            rating=float(data['rating']) if data.get('rating') else None,
            review=data.get('review'),
            created_at=get_value('createdAt', 'created_at'),
            updated_at=get_value('updatedAt', 'updated_at'),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Booking to dictionary"""
        return {
            'id': self.id,
            'seeker_id': self.seeker_id,
            'seeker_name': getattr(self, 'seeker_name', None),
            'provider_id': self.provider_id,
            'provider_name': getattr(self, 'provider_name', None),
            'vehicle_id': self.vehicle_id,
            'service_type': self.service_type,
            'status': self.status,
            'pickup_latitude': self.pickup_latitude,
            'pickup_longitude': self.pickup_longitude,
            'pickup_address': self.pickup_address,
            'drop_latitude': self.drop_latitude,
            'drop_longitude': self.drop_longitude,
            'drop_address': self.drop_address,
            'distance_in_km': self.distance_in_km,
            'estimated_price': self.estimated_price,
            'final_price': self.final_price,
            'hours': self.hours,
            'is_urgent': self.is_urgent,
            'scheduled_date_time': self.scheduled_date_time.isoformat() if self.scheduled_date_time else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'cancelled_at': self.cancelled_at.isoformat() if self.cancelled_at else None,
            'cancellation_reason': self.cancellation_reason,
            'notes': self.notes,
            'rating': self.rating,
            'review': self.review,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def to_neo4j_props(self) -> Dict[str, Any]:
        """Convert Booking to Neo4j properties"""
        return self.to_dict()
    
    # Database Operations (Model Layer)
    
    @staticmethod
    def _serialize_neo4j_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Neo4j data types to JSON-safe Python types."""
        from neo4j.time import DateTime as Neo4jDateTime

        serialized = {}
        for key, value in data.items():
            if isinstance(value, Neo4jDateTime):
                serialized[key] = value.to_native().isoformat()
            elif isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif value is None:
                serialized[key] = None
            else:
                serialized[key] = value
        return serialized
    
    @staticmethod
    def create(booking_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new booking with proper seeker→request→provider binding
        
        When seeker books a service:
        - providerId MUST be set (the provider who owns the service)
        - serviceId MUST be set (the specific service being booked)
        - vehicleId should be set (vehicle providing the service)
        
        Relationships created:
        - (Seeker)-[:CREATED]->(Booking)
        - (Booking)-[:ASSIGNED_TO]->(Provider)
        - (Booking)-[:USES_SERVICE]->(Service)
        """
        service_type = booking_data.get('serviceType', 'General')
        service_label = service_type.replace(' ', '').replace('-', '').replace('_', '') if service_type else 'General'
        
        query = f"""
        OPTIONAL MATCH (seeker)
        WHERE (seeker:Provider OR seeker:User OR seeker:Seeker) AND seeker.id = $seekerId
        OPTIONAL MATCH (provider)
        WHERE (provider:Provider OR provider:User OR provider:Seeker) AND provider.id = $providerId
        OPTIONAL MATCH (service:Service)
        WHERE service.id = $serviceId
        CREATE (b:Booking:{service_label} {{
            id: randomUUID(),
            seekerId: $seekerId,
            providerId: $providerId,
            vehicleId: $vehicleId,
            serviceId: $serviceId,
            serviceType: $serviceType,
            bookingMode: $bookingMode,
            status: $pendingStatus,
            pickupLatitude: $pickupLatitude,
            pickupLongitude: $pickupLongitude,
            pickupAddress: $pickupAddress,
            dropLatitude: $dropLatitude,
            dropLongitude: $dropLongitude,
            dropAddress: $dropAddress,
            distanceInKm: $distanceInKm,
            estimatedPrice: $estimatedPrice,
            hours: $hours,
            isUrgent: $isUrgent,
            scheduledDateTime: datetime($scheduledDateTime),
            notes: $notes,
            createdAt: datetime(),
            updatedAt: datetime()
        }})
        FOREACH (_ IN CASE WHEN seeker IS NOT NULL THEN [1] ELSE [] END |
            CREATE (b)-[:CREATED_BY]->(seeker)
        )
        FOREACH (_ IN CASE WHEN provider IS NOT NULL THEN [1] ELSE [] END |
            CREATE (b)-[:ASSIGNED_TO]->(provider)
        )
        FOREACH (_ IN CASE WHEN service IS NOT NULL THEN [1] ELSE [] END |
            CREATE (b)-[:USES_SERVICE]->(service)
        )
        RETURN b
        """

        booking_data.setdefault('serviceId', None)
        booking_data.setdefault('providerId', None)
        booking_data.setdefault('vehicleId', None)
        booking_data.setdefault('bookingMode', None)
        booking_data['pendingStatus'] = BookingStatus.PENDING

        result = neo4j_driver.execute_write(query, booking_data)
        if result and result[0]['b']:
            return Booking._serialize_neo4j_data(result[0]['b'])
        return None
    
    @staticmethod
    def update(booking_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update booking with dynamic fields - matches both Booking and Booking:ServiceType labels"""
        # Build dynamic SET clause
        set_clauses = []
        params = {"bookingId": booking_id}
        
        field_mapping = {
            'status': 'status',
            'finalPrice': 'finalPrice',
            'providerId': 'providerId',
            'vehicleId': 'vehicleId',
            'notes': 'notes'
        }
        
        for key, neo4j_key in field_mapping.items():
            if key in update_data and update_data[key] is not None:
                set_clauses.append(f"b.{neo4j_key} = ${key}")
                params[key] = update_data[key]
        
        set_clauses.append("b.updatedAt = datetime()")
        
        query = f"""
        MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking') AND b.id = $bookingId
        SET {", ".join(set_clauses)}
        RETURN b
        """
        
        result = neo4j_driver.execute_write(query, params)
        if result and result[0]['b']:
            return Booking._serialize_neo4j_data(result[0]['b'])
        return None
    
    @staticmethod
    def accept(booking_id: str, provider_id: str, vehicle_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Provider accepts a booking - creates ACCEPTED_BY relationship.
        Auto-starts the service (status = in_progress) so the provider doesn't
        need to click a separate 'Start Service' button.
        Matches both Booking and Booking:ServiceType labels."""
        query = """
        MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking') AND b.id = $bookingId
        MATCH (provider) WHERE provider.id = $providerId
        SET b.status = $inProgressStatus,
            b.providerId = $providerId,
            b.vehicleId = $vehicleId,
            b.startedAt = datetime(),
            b.updatedAt = datetime()
        MERGE (b)-[:ACCEPTED_BY]->(provider)
        WITH b, provider
        OPTIONAL MATCH (v:Vehicle {id: $vehicleId})
        FOREACH (_ IN CASE WHEN v IS NOT NULL THEN [1] ELSE [] END |
            MERGE (b)-[:USES_VEHICLE]->(v)
        )
        WITH b, provider
        OPTIONAL MATCH (seeker)
        WHERE (seeker:Seeker OR seeker:Provider OR seeker:User) AND seeker.id = b.seekerId
        RETURN b, seeker.name as seekerName, provider.name as providerName
        """

        params = {
            "bookingId": booking_id,
            "providerId": provider_id,
            "vehicleId": vehicle_id,
            "inProgressStatus": BookingStatus.IN_PROGRESS,
        }
        
        result = neo4j_driver.execute_write(query, params)
        if result and result[0]['b']:
            booking = Booking._serialize_neo4j_data(result[0]['b'])
            booking['seekerName'] = result[0].get('seekerName')
            booking['providerName'] = result[0].get('providerName')
            return booking
        return None
    
    @staticmethod
    def complete(booking_id: str, final_price: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Mark booking as completed - creates SERVED_BY and COMPLETED relationships.
        Matches both Booking and Booking:ServiceType labels."""
        query = """
        MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking') AND b.id = $bookingId
        OPTIONAL MATCH (provider) WHERE provider.id = b.providerId
        OPTIONAL MATCH (seeker) WHERE seeker.id = b.seekerId
        SET b.status = $completedStatus,
            b.finalPrice = COALESCE($finalPrice, b.estimatedPrice),
            b.completedAt = datetime(),
            b.updatedAt = datetime()
        FOREACH (_ IN CASE WHEN provider IS NOT NULL AND seeker IS NOT NULL THEN [1] ELSE [] END |
            MERGE (seeker)-[:SERVED_BY {bookingId: b.id, completedAt: datetime()}]->(provider)
        )
        RETURN b, seeker.name as seekerName, provider.name as providerName
        """
        
        params = {
            "bookingId": booking_id,
            "finalPrice": final_price,
            "completedStatus": BookingStatus.COMPLETED,
        }
        
        result = neo4j_driver.execute_write(query, params)
        if result and result[0]['b']:
            booking = Booking._serialize_neo4j_data(result[0]['b'])
            booking['seekerName'] = result[0].get('seekerName')
            booking['providerName'] = result[0].get('providerName')
            return booking
        return None
    
    @staticmethod
    def reject(booking_id: str, provider_id: str, reason: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Provider rejects a booking - sets status to rejected and creates REJECTED_BY relationship.
        Matches both Booking and Booking:ServiceType labels."""
        query = """
        MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking') AND b.id = $bookingId
        MATCH (provider)
        WHERE (provider:Provider OR provider:User OR provider:Seeker) AND provider.id = $providerId
        SET b.status = $rejectedStatus,
            b.rejectedBy = $providerId,
            b.rejectionReason = $reason,
            b.rejectedAt = datetime(),
            b.updatedAt = datetime()
        MERGE (b)-[:REJECTED_BY {reason: $reason, rejectedAt: datetime()}]->(provider)
        RETURN b
        """
        
        params = {
            "bookingId": booking_id,
            "providerId": provider_id,
            "reason": reason,
            "rejectedStatus": BookingStatus.REJECTED,
        }
        
        result = neo4j_driver.execute_write(query, params)
        if result and result[0]['b']:
            return Booking._serialize_neo4j_data(result[0]['b'])
        return None
    
    # ============================================
    # ADDITIONAL METHODS FOR COMPLETE LIFECYCLE
    # ============================================
    
    @staticmethod
    def get_by_id(booking_id: str) -> Optional[Dict[str, Any]]:
        """Get booking by ID with complete seeker→request→provider→service details"""
        query = """
        MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking') AND b.id = $bookingId
        OPTIONAL MATCH (seeker)
        WHERE (seeker:Seeker OR seeker:Provider OR seeker:User) AND seeker.id = b.seekerId
        OPTIONAL MATCH (provider)
        WHERE (provider:Seeker OR provider:Provider OR provider:User) AND provider.id = b.providerId
        OPTIONAL MATCH (vehicle:Vehicle {id: b.vehicleId})
        OPTIONAL MATCH (service:Service {id: b.serviceId})
        RETURN b,
               seeker.name as seekerName, seeker.phone as seekerPhone,
               seeker.profileImageUrl as seekerProfileImageUrl,
               seeker.rating as seekerRating,
               provider.name as providerName, provider.phone as providerPhone,
               provider.rating as providerRating,
               vehicle.vehicleType as vehicleType, vehicle.vehicleNumber as vehicleNumber,
               service.name as serviceName, service.description as serviceDescription,
               service.basePrice as serviceBasePrice
        """
        result = neo4j_driver.execute_read(query, {'bookingId': booking_id})
        if result and result[0]['b']:
            booking = Booking._serialize_neo4j_data(result[0]['b'])
            booking['seekerName'] = result[0]['seekerName']
            booking['seekerPhone'] = result[0]['seekerPhone']
            booking['seekerProfileImageUrl'] = result[0]['seekerProfileImageUrl']
            booking['seekerRating'] = result[0]['seekerRating']
            booking['providerName'] = result[0]['providerName']
            booking['providerPhone'] = result[0]['providerPhone']
            booking['providerRating'] = result[0]['providerRating']
            booking['vehicleType'] = result[0]['vehicleType']
            booking['vehicleNumber'] = result[0]['vehicleNumber']
            booking['serviceName'] = result[0]['serviceName']
            booking['serviceDescription'] = result[0]['serviceDescription']
            booking['serviceBasePrice'] = result[0]['serviceBasePrice']
            return booking
        return None
    
    @staticmethod
    def get_by_seeker(seeker_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all bookings for a seeker - matches both Booking and Booking:ServiceType labels"""
        query = """
        MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking') AND b.seekerId = $seekerId
        """
        params = {'seekerId': seeker_id}
        
        if status:
            query += " AND b.status = $status"
            params['status'] = status
        
        query += """
        OPTIONAL MATCH (provider)
        WHERE (provider:Seeker OR provider:Provider OR provider:User) AND provider.id = b.providerId
        OPTIONAL MATCH (seeker)
        WHERE (seeker:Seeker OR seeker:Provider OR seeker:User) AND seeker.id = b.seekerId
        RETURN b, provider.name as providerName, provider.rating as providerRating,
               seeker.name as seekerName
        ORDER BY b.createdAt DESC
        """
        
        result = neo4j_driver.execute_read(query, params)
        bookings = []
        if result:
            for record in result:
                if record['b']:
                    booking = Booking._serialize_neo4j_data(record['b'])
                    booking['providerName'] = record['providerName']
                    booking['providerRating'] = record['providerRating']
                    booking['seekerName'] = record['seekerName']
                    bookings.append(booking)
        return bookings
    
    @staticmethod
    def get_by_provider(provider_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all bookings assigned to a provider - matches both Booking and Booking:ServiceType labels"""
        query = """
        MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking') AND b.providerId = $providerId
        """
        params = {'providerId': provider_id}
        
        if status:
            query += " AND b.status = $status"
            params['status'] = status
        
        query += """
        OPTIONAL MATCH (seeker)
        WHERE (seeker:Seeker OR seeker:Provider OR seeker:User) AND seeker.id = b.seekerId
        OPTIONAL MATCH (provider)
        WHERE (provider:Seeker OR provider:Provider OR provider:User) AND provider.id = b.providerId
        RETURN b, seeker.name as seekerName, seeker.phone as seekerPhone,
               seeker.profileImageUrl as seekerProfileImageUrl,
               seeker.rating as seekerRating,
               provider.name as providerName
        ORDER BY b.createdAt DESC
        """

        result = neo4j_driver.execute_read(query, params)
        bookings = []
        if result:
            for record in result:
                if record['b']:
                    booking = Booking._serialize_neo4j_data(record['b'])
                    booking['seekerName'] = record['seekerName']
                    booking['seekerPhone'] = record['seekerPhone']
                    booking['seekerProfileImageUrl'] = record.get('seekerProfileImageUrl')
                    booking['seekerRating'] = record.get('seekerRating')
                    booking['providerName'] = record['providerName']
                    bookings.append(booking)
        return bookings
    
    @staticmethod
    def get_active_booking(user_id: str, role: str) -> Optional[Dict[str, Any]]:
        """Get active booking for a user (seeker or provider) - matches both Booking and Booking:ServiceType labels"""
        field = 'seekerId' if role == 'seeker' else 'providerId'
        query = f"""
        MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking') AND b.{field} = $userId
        AND b.status IN $activeStatuses
        OPTIONAL MATCH (seeker)
        WHERE (seeker:Seeker OR seeker:Provider OR seeker:User) AND seeker.id = b.seekerId
        OPTIONAL MATCH (provider)
        WHERE (provider:Seeker OR provider:Provider OR provider:User) AND provider.id = b.providerId
        RETURN b, seeker.name as seekerName, seeker.phone as seekerPhone,
               provider.name as providerName, provider.phone as providerPhone
        ORDER BY b.createdAt DESC
        LIMIT 1
        """
        result = neo4j_driver.execute_read(query, {
            'userId': user_id,
            'activeStatuses': list(ACTIVE_BOOKING_STATUSES),
        })
        if result and result[0]['b']:
            booking = Booking._serialize_neo4j_data(result[0]['b'])
            booking['seekerName'] = result[0]['seekerName']
            booking['seekerPhone'] = result[0]['seekerPhone']
            booking['providerName'] = result[0]['providerName']
            booking['providerPhone'] = result[0]['providerPhone']
            return booking
        return None
    
    @staticmethod
    def get_available_bookings(
        service_type: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: float = 50.0
    ) -> List[Dict[str, Any]]:
        """Get available bookings for providers to bid on - matches both Booking and Booking:ServiceType labels"""
        query = """
        MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking')
        AND b.status = $pendingStatus AND b.providerId IS NULL
        """
        params = {}
        
        if service_type:
            query += " AND b.serviceType = $serviceType"
            params['serviceType'] = service_type
        
        query += """
        OPTIONAL MATCH (seeker)
        WHERE (seeker:Seeker OR seeker:Provider OR seeker:User) AND seeker.id = b.seekerId
        RETURN b, seeker.name as seekerName,
               seeker.profileImageUrl as seekerProfileImageUrl,
               seeker.rating as seekerRating
        ORDER BY b.createdAt DESC
        """

        params['pendingStatus'] = BookingStatus.PENDING
        # Use execute_query (session.run) so the query always hits the leader on
        # Neo4j Aura — execute_read routes to read replicas which can lag behind
        # the leader by several seconds after a fresh write.
        result = neo4j_driver.execute_query(query, params)
        bookings = []
        if result:
            for record in result:
                if record['b']:
                    booking = Booking._serialize_neo4j_data(record['b'])
                    booking['seekerName'] = record['seekerName']
                    booking['seekerProfileImageUrl'] = record.get('seekerProfileImageUrl')
                    booking['seekerRating'] = record.get('seekerRating')
                    bookings.append(booking)
        return bookings
    
    @staticmethod
    def update_status(booking_id: str, status: str) -> Optional[Dict[str, Any]]:
        """Update booking status - matches both Booking and Booking:ServiceType labels"""
        query = """
        MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking') AND b.id = $bookingId
        SET b.status = $status,
            b.updatedAt = datetime()
        WITH b
        OPTIONAL MATCH (seeker)
        WHERE (seeker:Seeker OR seeker:Provider OR seeker:User) AND seeker.id = b.seekerId
        OPTIONAL MATCH (provider)
        WHERE (provider:Seeker OR provider:Provider OR provider:User) AND provider.id = b.providerId
        RETURN b, seeker.name as seekerName, provider.name as providerName
        """
        result = neo4j_driver.execute_write(query, {'bookingId': booking_id, 'status': status})
        if result and result[0]['b']:
            booking = Booking._serialize_neo4j_data(result[0]['b'])
            booking['seekerName'] = result[0].get('seekerName')
            booking['providerName'] = result[0].get('providerName')
            return booking
        return None
    
    @staticmethod
    def start(booking_id: str) -> Optional[Dict[str, Any]]:
        """Start the booking service - matches both Booking and Booking:ServiceType labels"""
        query = """
        MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking') AND b.id = $bookingId
        SET b.status = $inProgressStatus,
            b.startedAt = datetime(),
            b.updatedAt = datetime()
        WITH b
        OPTIONAL MATCH (seeker)
        WHERE (seeker:Seeker OR seeker:Provider OR seeker:User) AND seeker.id = b.seekerId
        OPTIONAL MATCH (provider)
        WHERE (provider:Seeker OR provider:Provider OR provider:User) AND provider.id = b.providerId
        RETURN b, seeker.name as seekerName, provider.name as providerName
        """
        result = neo4j_driver.execute_write(query, {
            'bookingId': booking_id,
            'inProgressStatus': BookingStatus.IN_PROGRESS,
        })
        if result and result[0]['b']:
            booking = Booking._serialize_neo4j_data(result[0]['b'])
            booking['seekerName'] = result[0].get('seekerName')
            booking['providerName'] = result[0].get('providerName')
            return booking
        return None
    
    @staticmethod
    def cancel(booking_id: str, reason: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Cancel a booking - matches both Booking and Booking:ServiceType labels"""
        query = """
        MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking') AND b.id = $bookingId
        SET b.status = $cancelledStatus,
            b.cancellationReason = $reason,
            b.cancelledAt = datetime(),
            b.updatedAt = datetime()
        RETURN b
        """
        result = neo4j_driver.execute_write(query, {
            'bookingId': booking_id,
            'reason': reason,
            'cancelledStatus': BookingStatus.CANCELLED,
        })
        if result and result[0]['b']:
            return Booking._serialize_neo4j_data(result[0]['b'])
        return None
    
    @staticmethod
    def add_rating(booking_id: str, rating: float, review: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Add rating to a completed booking and update provider's average rating - matches both Booking and Booking:ServiceType labels"""
        query = """
        MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking') AND b.id = $bookingId
        SET b.rating = $rating,
            b.review = $review,
            b.updatedAt = datetime()
        
        WITH b
        MATCH (provider)
        WHERE (provider:Seeker OR provider:Provider OR provider:User) AND provider.id = b.providerId
        
        // Update provider's average rating
        OPTIONAL MATCH (allBookings)
        WHERE any(label IN labels(allBookings) WHERE label STARTS WITH 'Booking') 
        AND allBookings.providerId = provider.id
        AND allBookings.rating IS NOT NULL
        WITH b, provider, avg(allBookings.rating) as avgRating, count(allBookings) as totalRated
        SET provider.rating = avgRating,
            provider.completedBookings = totalRated
        
        RETURN b
        """
        result = neo4j_driver.execute_write(query, {
            'bookingId': booking_id,
            'rating': rating,
            'review': review
        })
        if result and result[0]['b']:
            return Booking._serialize_neo4j_data(result[0]['b'])
        return None
