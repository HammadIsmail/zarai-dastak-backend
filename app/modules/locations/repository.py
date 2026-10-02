"""
Location Update Model - Handles real-time location tracking
For seeker-provider location sharing during active bookings
"""

from typing import Optional, Dict, Any
from datetime import datetime
from app.core.database.neo4j_driver import neo4j_driver


class LocationUpdate:
    """
    Location Update model - tracks real-time location of users during active bookings
    """
    
    def __init__(
        self,
        user_id: str,
        booking_id: str,
        latitude: float,
        longitude: float,
        heading: Optional[float] = None,
        speed: Optional[float] = None,
        accuracy: Optional[float] = None,
        updated_at: Optional[datetime] = None,
    ):
        self.user_id = user_id
        self.booking_id = booking_id
        self.latitude = latitude
        self.longitude = longitude
        self.heading = heading
        self.speed = speed
        self.accuracy = accuracy
        self.updated_at = updated_at or datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'userId': self.user_id,
            'bookingId': self.booking_id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'heading': self.heading,
            'speed': self.speed,
            'accuracy': self.accuracy,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    @staticmethod
    def _serialize_neo4j_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Neo4j data types to Python types for GraphQL"""
        from neo4j.time import DateTime as Neo4jDateTime
        
        serialized = {}
        for key, value in data.items():
            if isinstance(value, Neo4jDateTime):
                # Convert Neo4j DateTime to Python datetime for GraphQL
                serialized[key] = value.to_native()
            elif value is None:
                serialized[key] = None
            else:
                serialized[key] = value
        return serialized
    
    # Database Operations
    
    @staticmethod
    def update_location(
        user_id: str,
        booking_id: str,
        latitude: float,
        longitude: float,
        heading: Optional[float] = None,
        speed: Optional[float] = None,
        accuracy: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """Update or create location entry for a user in a booking"""
        query = """
        MERGE (loc:Location {userId: $userId, bookingId: $bookingId})
        SET loc.latitude = $latitude,
            loc.longitude = $longitude,
            loc.heading = $heading,
            loc.speed = $speed,
            loc.accuracy = $accuracy,
            loc.updatedAt = datetime()
        RETURN loc
        """
        
        params = {
            'userId': user_id,
            'bookingId': booking_id,
            'latitude': latitude,
            'longitude': longitude,
            'heading': heading,
            'speed': speed,
            'accuracy': accuracy,
        }
        
        result = neo4j_driver.execute_write(query, params)
        if result and result[0]['loc']:
            return LocationUpdate._serialize_neo4j_data(result[0]['loc'])
        return None
    
    @staticmethod
    def get_location(user_id: str, booking_id: str) -> Optional[Dict[str, Any]]:
        """Get latest location for a user in a booking"""
        query = """
        MATCH (loc:Location {userId: $userId, bookingId: $bookingId})
        RETURN loc
        """
        result = neo4j_driver.execute_read(query, {'userId': user_id, 'bookingId': booking_id})
        if result and result[0]['loc']:
            return LocationUpdate._serialize_neo4j_data(result[0]['loc'])
        return None
    
    @staticmethod
    def get_booking_locations(booking_id: str) -> Dict[str, Any]:
        """Get locations of both seeker and provider for a booking"""
        query = """
        MATCH (b:Booking {id: $bookingId})
        OPTIONAL MATCH (seekerLoc:Location {userId: b.seekerId, bookingId: $bookingId})
        OPTIONAL MATCH (providerLoc:Location {userId: b.providerId, bookingId: $bookingId})
        RETURN b.seekerId as seekerId, b.providerId as providerId,
               seekerLoc, providerLoc
        """
        result = neo4j_driver.execute_read(query, {'bookingId': booking_id})
        if result:
            record = result[0]
            return {
                'bookingId': booking_id,
                'seeker': {
                    'userId': record['seekerId'],
                    'location': LocationUpdate._serialize_neo4j_data(record['seekerLoc']) if record['seekerLoc'] else None
                },
                'provider': {
                    'userId': record['providerId'],
                    'location': LocationUpdate._serialize_neo4j_data(record['providerLoc']) if record['providerLoc'] else None
                }
            }
        return {'bookingId': booking_id, 'seeker': None, 'provider': None}
    
    @staticmethod
    def delete_booking_locations(booking_id: str) -> bool:
        """Delete all location entries for a booking (cleanup after completion)"""
        query = """
        MATCH (loc:Location {bookingId: $bookingId})
        DELETE loc
        RETURN count(loc) as deleted
        """
        result = neo4j_driver.execute_write(query, {'bookingId': booking_id})
        return result is not None
    
    @staticmethod
    def update_user_location(
        user_id: str,
        latitude: float,
        longitude: float
    ) -> Optional[Dict[str, Any]]:
        """Update user's general location (for providers to be discoverable)"""
        query = """
        MATCH (u:User {id: $userId})
        SET u.latitude = $latitude,
            u.longitude = $longitude,
            u.locationUpdatedAt = datetime()
        RETURN u.id as userId, u.latitude as latitude, u.longitude as longitude
        """
        
        params = {
            'userId': user_id,
            'latitude': latitude,
            'longitude': longitude,
        }
        
        result = neo4j_driver.execute_write(query, params)
        if result:
            return {
                'userId': result[0]['userId'],
                'latitude': result[0]['latitude'],
                'longitude': result[0]['longitude'],
            }
        return None
