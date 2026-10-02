"""
Fare Offer Model - Represents fare offers/bids from providers (InDrive-style bidding)
Handles the negotiation flow between seekers and providers
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from app.core.database.neo4j_driver import neo4j_driver
from app.core.constants import BookingStatus


class OfferStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTER_OFFERED = "counter_offered"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


class FareOffer:
    """
    Fare Offer model - represents a bid from a provider on a booking request
    Enables InDrive-style negotiation
    """
    
    def __init__(
        self,
        id: str,
        booking_id: str,
        provider_id: str,
        vehicle_id: str,
        offered_price: float,
        counter_price: Optional[float] = None,  # Seeker's counter offer
        status: str = OfferStatus.PENDING,
        message: Optional[str] = None,
        estimated_arrival_minutes: Optional[int] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
    ):
        self.id = id
        self.booking_id = booking_id
        self.provider_id = provider_id
        self.vehicle_id = vehicle_id
        self.offered_price = offered_price
        self.counter_price = counter_price
        self.status = status
        self.message = message
        self.estimated_arrival_minutes = estimated_arrival_minutes
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
        self.expires_at = expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'bookingId': self.booking_id,
            'providerId': self.provider_id,
            'vehicleId': self.vehicle_id,
            'offeredPrice': self.offered_price,
            'counterPrice': self.counter_price,
            'status': self.status,
            'message': self.message,
            'estimatedArrivalMinutes': self.estimated_arrival_minutes,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
            'expiresAt': self.expires_at.isoformat() if self.expires_at else None,
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
    def create(offer_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new fare offer"""
        query = """
        MATCH (b:Booking {id: $bookingId})
        MATCH (p)
        WHERE (p:Provider OR p:User OR p:Seeker) AND p.id = $providerId
        MATCH (v:Vehicle {id: $vehicleId})
        CREATE (o:FareOffer {
            id: randomUUID(),
            bookingId: $bookingId,
            providerId: $providerId,
            vehicleId: $vehicleId,
            offeredPrice: $offeredPrice,
            status: $pendingStatus,
            message: $message,
            estimatedArrivalMinutes: $estimatedArrivalMinutes,
            createdAt: datetime(),
            updatedAt: datetime(),
            expiresAt: datetime() + duration({minutes: 10})
        })
        CREATE (b)-[:HAS_OFFER]->(o)
        CREATE (p)-[:MADE_OFFER]->(o)
        RETURN o, p.name as providerName, p.rating as providerRating,
               v.vehicleType as vehicleType, v.vehicleNumber as vehicleNumber
        """
        
        params = {
            'bookingId': offer_data.get('bookingId'),
            'providerId': offer_data.get('providerId'),
            'vehicleId': offer_data.get('vehicleId'),
            'offeredPrice': offer_data.get('offeredPrice'),
            'message': offer_data.get('message'),
            'estimatedArrivalMinutes': offer_data.get('estimatedArrivalMinutes'),
            'pendingStatus': OfferStatus.PENDING.value,
        }
        
        result = neo4j_driver.execute_write(query, params)
        if result and result[0]['o']:
            offer = FareOffer._serialize_neo4j_data(result[0]['o'])
            offer['providerName'] = result[0]['providerName']
            offer['providerRating'] = result[0]['providerRating']
            offer['vehicleType'] = result[0]['vehicleType']
            offer['vehicleNumber'] = result[0]['vehicleNumber']
            return offer
        return None
    
    @staticmethod
    def get_by_id(offer_id: str) -> Optional[Dict[str, Any]]:
        """Get offer by ID"""
        query = """
        MATCH (o:FareOffer {id: $offerId})
        OPTIONAL MATCH (p)-[:MADE_OFFER]->(o)
        WHERE p:Provider OR p:User OR p:Seeker
        OPTIONAL MATCH (v:Vehicle {id: o.vehicleId})
        RETURN o, p.name as providerName, p.rating as providerRating,
               v.vehicleType as vehicleType, v.vehicleNumber as vehicleNumber
        """
        result = neo4j_driver.execute_read(query, {'offerId': offer_id})
        if result and result[0]['o']:
            offer = FareOffer._serialize_neo4j_data(result[0]['o'])
            offer['providerName'] = result[0]['providerName']
            offer['providerRating'] = result[0]['providerRating']
            offer['vehicleType'] = result[0]['vehicleType']
            offer['vehicleNumber'] = result[0]['vehicleNumber']
            return offer
        return None
    
    @staticmethod
    def get_offers_for_booking(booking_id: str) -> List[Dict[str, Any]]:
        """Get all offers for a booking"""
        query = """
        MATCH (b:Booking {id: $bookingId})-[:HAS_OFFER]->(o:FareOffer)
        MATCH (p)-[:MADE_OFFER]->(o)
        WHERE p:Provider OR p:User OR p:Seeker
        OPTIONAL MATCH (v:Vehicle {id: o.vehicleId})
        WHERE o.status IN $activeOfferStatuses
        RETURN o, p.id as providerId, p.name as providerName, p.rating as providerRating,
               p.phone as providerPhone, p.profileImageUrl as providerImage,
               v.vehicleType as vehicleType, v.vehicleNumber as vehicleNumber
        ORDER BY o.createdAt DESC
        """
        result = neo4j_driver.execute_read(query, {
            'bookingId': booking_id,
            'activeOfferStatuses': [OfferStatus.PENDING.value, OfferStatus.COUNTER_OFFERED.value],
        })
        offers = []
        if result:
            for record in result:
                if record['o']:
                    offer = FareOffer._serialize_neo4j_data(record['o'])
                    offer['providerId'] = record['providerId']
                    offer['providerName'] = record['providerName']
                    offer['providerRating'] = record['providerRating']
                    offer['providerPhone'] = record['providerPhone']
                    offer['providerImage'] = record['providerImage']
                    offer['vehicleType'] = record['vehicleType']
                    offer['vehicleNumber'] = record['vehicleNumber']
                    offers.append(offer)
        return offers
    
    @staticmethod
    def get_provider_offers(provider_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all offers made by a provider"""
        query = """
        MATCH (p)-[:MADE_OFFER]->(o:FareOffer)
        WHERE (p:Provider OR p:User OR p:Seeker) AND p.id = $providerId
        MATCH (b:Booking)-[:HAS_OFFER]->(o)
        OPTIONAL MATCH (s)
        WHERE (s:Provider OR s:User OR s:Seeker) AND s.id = b.seekerId
        WITH o, b, s
        """
        
        params = {'providerId': provider_id}
        
        if status:
            query += " WHERE o.status = $status"
            params['status'] = status
        
        query += """
        RETURN o, b.id as bookingId, b.pickupAddress as pickupAddress, 
               b.dropAddress as dropAddress, b.serviceType as serviceType,
               s.name as seekerName
        ORDER BY o.createdAt DESC
        """
        
        result = neo4j_driver.execute_read(query, params)
        offers = []
        if result:
            for record in result:
                if record['o']:
                    offer = FareOffer._serialize_neo4j_data(record['o'])
                    offer['pickupAddress'] = record['pickupAddress']
                    offer['dropAddress'] = record['dropAddress']
                    offer['serviceType'] = record['serviceType']
                    offer['seekerName'] = record['seekerName']
                    offers.append(offer)
        return offers
    
    @staticmethod
    def accept_offer(offer_id: str) -> Optional[Dict[str, Any]]:
        """Accept an offer - updates both offer and booking.
        Booking auto-starts (in_progress) — removes the need for a separate
        'Start Service' click on the provider side."""
        query = """
        MATCH (b:Booking)-[:HAS_OFFER]->(o:FareOffer {id: $offerId})
        // Reject all other pending offers for this booking
        OPTIONAL MATCH (b)-[:HAS_OFFER]->(other:FareOffer)
        WHERE other.id <> $offerId AND other.status = $pendingStatus
        SET other.status = $rejectedStatus, other.updatedAt = datetime()

        WITH b, o
        SET o.status = $acceptedOfferStatus,
            o.updatedAt = datetime(),
            b.status = $inProgressBookingStatus,
            b.providerId = o.providerId,
            b.vehicleId = o.vehicleId,
            b.finalPrice = COALESCE(o.counterPrice, o.offeredPrice),
            b.startedAt = datetime(),
            b.updatedAt = datetime()
        RETURN o, b
        """

        result = neo4j_driver.execute_write(query, {
            'offerId': offer_id,
            'pendingStatus': OfferStatus.PENDING.value,
            'rejectedStatus': OfferStatus.REJECTED.value,
            'acceptedOfferStatus': OfferStatus.ACCEPTED.value,
            'inProgressBookingStatus': BookingStatus.IN_PROGRESS,
        })
        if result and result[0]['o']:
            offer = FareOffer._serialize_neo4j_data(result[0]['o'])
            offer['booking'] = FareOffer._serialize_neo4j_data(result[0]['b'])
            return offer
        return None
    
    @staticmethod
    def reject_offer(offer_id: str) -> Optional[Dict[str, Any]]:
        """Reject an offer"""
        query = """
        MATCH (o:FareOffer {id: $offerId})
        SET o.status = $rejectedStatus,
            o.updatedAt = datetime()
        RETURN o
        """
        
        result = neo4j_driver.execute_write(query, {
            'offerId': offer_id,
            'rejectedStatus': OfferStatus.REJECTED.value,
        })
        if result and result[0]['o']:
            return FareOffer._serialize_neo4j_data(result[0]['o'])
        return None
    
    @staticmethod
    def counter_offer(offer_id: str, counter_price: float) -> Optional[Dict[str, Any]]:
        """Seeker makes a counter offer"""
        query = """
        MATCH (o:FareOffer {id: $offerId})
        SET o.status = $counterOfferedStatus,
            o.counterPrice = $counterPrice,
            o.updatedAt = datetime()
        RETURN o
        """
        
        result = neo4j_driver.execute_write(query, {
            'offerId': offer_id,
            'counterPrice': counter_price,
            'counterOfferedStatus': OfferStatus.COUNTER_OFFERED.value,
        })
        if result and result[0]['o']:
            return FareOffer._serialize_neo4j_data(result[0]['o'])
        return None
    
    @staticmethod
    def withdraw_offer(offer_id: str) -> Optional[Dict[str, Any]]:
        """Provider withdraws their offer"""
        query = """
        MATCH (o:FareOffer {id: $offerId})
        SET o.status = $withdrawnStatus,
            o.updatedAt = datetime()
        RETURN o
        """
        
        result = neo4j_driver.execute_write(query, {
            'offerId': offer_id,
            'withdrawnStatus': OfferStatus.WITHDRAWN.value,
        })
        if result and result[0]['o']:
            return FareOffer._serialize_neo4j_data(result[0]['o'])
        return None
    
    @staticmethod
    def update_offer_price(offer_id: str, new_price: float, message: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Provider updates their offer price (in response to counter offer)"""
        query = """
        MATCH (o:FareOffer {id: $offerId})
        SET o.offeredPrice = $newPrice,
            o.status = $pendingStatus,
            o.message = COALESCE($message, o.message),
            o.updatedAt = datetime()
        RETURN o
        """
        
        result = neo4j_driver.execute_write(query, {
            'offerId': offer_id,
            'newPrice': new_price,
            'message': message,
            'pendingStatus': OfferStatus.PENDING.value,
        })
        if result and result[0]['o']:
            return FareOffer._serialize_neo4j_data(result[0]['o'])
        return None
