import graphene
from .types import UserType, VehicleType, BookingType, ServiceType, FareOfferType
from app.modules.users.legacy_controller import UserController
from app.modules.vehicles.legacy_controller import VehicleController
from app.modules.bookings.legacy_controller import BookingController
from app.modules.services.repository import Service
from app.modules.fare_offers.repository import FareOffer


class Query(graphene.ObjectType):
    """GraphQL Query Root"""
    
    # User Queries
    getUser = graphene.Field(
        UserType,
        id=graphene.ID(required=True),
        description="Get a user by ID"
    )
    
    getUserByEmail = graphene.Field(
        UserType,
        email=graphene.String(required=True),
        description="Get a user by email"
    )
    
    getProvidersByService = graphene.List(
        UserType,
        serviceType=graphene.String(required=True),
        description="Get all providers offering a specific service"
    )
    
    # Service Queries
    getAvailableServices = graphene.List(
        ServiceType,
        category=graphene.String(),
        description="Get all available services from verified providers"
    )
    
    searchServices = graphene.List(
        ServiceType,
        query=graphene.String(required=True),
        description="Search services by name or category"
    )
    
    getServiceById = graphene.Field(
        ServiceType,
        serviceId=graphene.String(required=True),
        description="Get a service by ID"
    )
    
    # Vehicle Queries
    getVehicle = graphene.Field(
        VehicleType,
        id=graphene.ID(required=True),
        description="Get a vehicle by ID"
    )
    
    getProviderVehicles = graphene.List(
        VehicleType,
        providerId=graphene.ID(required=True),
        description="Get all vehicles owned by a provider"
    )
    
    getAvailableVehicles = graphene.List(
        VehicleType,
        serviceType=graphene.String(required=True),
        description="Get all available vehicles for a service type"
    )
    
    # Booking Queries
    getBooking = graphene.Field(
        BookingType,
        id=graphene.ID(required=True),
        description="Get a booking by ID"
    )
    
    getUserBookings = graphene.List(
        BookingType,
        userId=graphene.ID(required=True),
        description="Get all bookings for a user (seeker or provider)"
    )
    
    getBookingHistory = graphene.List(
        BookingType,
        userId=graphene.ID(required=True),
        status=graphene.String(),
        description="Get booking history with optional status filter"
    )
    
    # Fare Offer Queries
    getBookingOffers = graphene.List(
        FareOfferType,
        bookingId=graphene.ID(required=True),
        description="Get all fare offers for a booking"
    )
    
    getProviderOffers = graphene.List(
        FareOfferType,
        providerId=graphene.ID(required=True),
        status=graphene.String(),
        description="Get all offers made by a provider"
    )
    
    getOfferById = graphene.Field(
        FareOfferType,
        offerId=graphene.ID(required=True),
        description="Get a fare offer by ID"
    )
    
    # Resolvers
    def resolve_getUser(self, info, id):
        controller = UserController()
        return controller.get_user_by_id(id)
    
    def resolve_getUserByEmail(self, info, email):
        controller = UserController()
        return controller.get_user_by_email(email)
    
    def resolve_getProvidersByService(self, info, serviceType):
        controller = UserController()
        return controller.get_providers_by_service_type(serviceType)
    
    def resolve_getAvailableServices(self, info, category=None):
        """Get all available services from verified providers"""
        services = Service.get_available_services(category=category)
        return services
    
    def resolve_searchServices(self, info, query):
        """Search services by name or category"""
        # Get all services and filter by query
        all_services = Service.get_available_services()
        query_lower = query.lower()
        filtered = [
            s for s in all_services
            if query_lower in s.get('name', '').lower() 
            or query_lower in s.get('category', '').lower()
            or query_lower in s.get('description', '').lower()
        ]
        return filtered
    
    def resolve_getServiceById(self, info, serviceId):
        """Get a service by ID"""
        return Service.get_by_id(serviceId)
    
    def resolve_getVehicle(self, info, id):
        controller = VehicleController()
        return controller.get_vehicle_by_id(id)
    
    def resolve_getProviderVehicles(self, info, providerId):
        controller = VehicleController()
        return controller.get_provider_vehicles(providerId)
    
    def resolve_getAvailableVehicles(self, info, serviceType):
        controller = VehicleController()
        return controller.get_available_vehicles(serviceType)
    
    def resolve_getBooking(self, info, id):
        controller = BookingController()
        return controller.get_booking_by_id(id)
    
    def resolve_getUserBookings(self, info, userId):
        controller = BookingController()
        return controller.get_user_bookings(userId)
    
    def resolve_getBookingHistory(self, info, userId, status=None):
        controller = BookingController()
        return controller.get_booking_history(userId, status)
    
    def resolve_getBookingOffers(self, info, bookingId):
        """Get all fare offers for a booking"""
        return FareOffer.get_offers_for_booking(bookingId)
    
    def resolve_getProviderOffers(self, info, providerId, status=None):
        """Get all offers made by a provider"""
        return FareOffer.get_provider_offers(providerId, status)
    
    def resolve_getOfferById(self, info, offerId):
        """Get a fare offer by ID"""
        return FareOffer.get_by_id(offerId)
