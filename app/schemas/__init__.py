"""
Backward compatibility re-export.
Domain schemas now live in `app.modules.*.schemas`.
"""
from app.modules.bookings.schemas import BookingCreate, BookingUpdate, BookingResponse
from app.modules.vehicles.schemas import VehicleCreate, VehicleUpdate, VehicleResponse
from app.modules.users.schemas import UserCreate, UserUpdate, UserResponse, TokenVerifyRequest, TokenVerifyResponse
from app.modules.services.schemas import ServiceCreate, ServiceUpdate, ServiceResponse, ServicesListResponse
from app.modules.fare_offers.schemas import FareOfferCreate, CounterOfferRequest, UpdateOfferPrice, FareOfferResponse, FareOffersListResponse
from app.modules.locations.schemas import LocationUpdateRequest, UserLocationUpdate, LocationResponse, BookingLocationsResponse

__all__ = [
    'BookingCreate', 'BookingUpdate', 'BookingResponse',
    'VehicleCreate', 'VehicleUpdate', 'VehicleResponse',
    'UserCreate', 'UserUpdate', 'UserResponse',
    'TokenVerifyRequest', 'TokenVerifyResponse',
    'ServiceCreate', 'ServiceUpdate', 'ServiceResponse', 'ServicesListResponse',
    'FareOfferCreate', 'CounterOfferRequest', 'UpdateOfferPrice', 'FareOfferResponse', 'FareOffersListResponse',
    'LocationUpdateRequest', 'UserLocationUpdate', 'LocationResponse', 'BookingLocationsResponse',
]
