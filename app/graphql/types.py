import graphene


class UserType(graphene.ObjectType):
    """GraphQL User Type"""
    id = graphene.ID(required=True)
    email = graphene.String(required=True)
    name = graphene.String(required=True)
    phone = graphene.String(required=True)
    role = graphene.String(required=True)
    profile_image_url = graphene.String()
    is_verified = graphene.Boolean()
    is_active = graphene.Boolean()
    cnic = graphene.String()
    driving_license = graphene.String()
    rating = graphene.Float()
    completed_bookings = graphene.Int()
    latitude = graphene.Float()
    longitude = graphene.Float()
    address = graphene.String()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()


class ServiceType(graphene.ObjectType):
    """GraphQL Service Type - Represents services offered by providers"""
    id = graphene.ID(required=True)
    providerId = graphene.ID(required=True)
    vehicleId = graphene.ID(required=True)
    name = graphene.String(required=True)
    description = graphene.String()
    imageUrl = graphene.String()
    basePrice = graphene.Float(required=True)
    pricePerKm = graphene.Float(required=True)
    pricePerHour = graphene.Float(required=True)
    category = graphene.String(required=True)
    isActive = graphene.Boolean()
    
    # Provider info (denormalized for convenience)
    providerName = graphene.String()
    providerRating = graphene.Float()
    providerLatitude = graphene.Float()
    providerLongitude = graphene.Float()
    providerImageUrl = graphene.String()
    
    # Vehicle info
    vehicleType = graphene.String()
    vehicleNumber = graphene.String()
    vehicleImageBase64 = graphene.String()
    
    createdAt = graphene.DateTime()
    updatedAt = graphene.DateTime()


class VehicleType(graphene.ObjectType):
    """GraphQL Vehicle Type"""
    id = graphene.ID(required=True)
    providerId = graphene.ID(required=True)
    vehicleType = graphene.String(required=True)
    vehicleNumber = graphene.String(required=True)
    vehicleModel = graphene.String()
    vehicleYear = graphene.String()
    vehicleImageUrl = graphene.String()
    vehicleImageBase64 = graphene.String()
    isAvailable = graphene.Boolean()
    capacity = graphene.Float()
    extraFields = graphene.String()
    vehicleLicenseImageBase64 = graphene.String()
    createdAt = graphene.DateTime()
    updatedAt = graphene.DateTime()
    
    provider = graphene.Field(lambda: UserType)
    
    # Resolvers to map from snake_case model attributes to camelCase GraphQL fields
    def resolve_providerId(self, info):
        return getattr(self, 'provider_id', None) or getattr(self, 'providerId', None)
    
    def resolve_vehicleType(self, info):
        return getattr(self, 'vehicle_type', None) or getattr(self, 'vehicleType', None)
    
    def resolve_vehicleNumber(self, info):
        return getattr(self, 'vehicle_number', None) or getattr(self, 'vehicleNumber', None)
    
    def resolve_vehicleModel(self, info):
        return getattr(self, 'vehicle_model', None) or getattr(self, 'vehicleModel', None)
    
    def resolve_vehicleYear(self, info):
        return getattr(self, 'vehicle_year', None) or getattr(self, 'vehicleYear', None)
    
    def resolve_vehicleImageUrl(self, info):
        return getattr(self, 'vehicle_image_url', None) or getattr(self, 'vehicleImageUrl', None)
    
    def resolve_vehicleImageBase64(self, info):
        return getattr(self, 'vehicle_image_base64', None) or getattr(self, 'vehicleImageBase64', None)
    
    def resolve_isAvailable(self, info):
        return getattr(self, 'is_available', None) if hasattr(self, 'is_available') else getattr(self, 'isAvailable', True)

    def resolve_extraFields(self, info):
        return getattr(self, 'extraFields', None) or getattr(self, 'extra_fields', None)

    def resolve_vehicleLicenseImageBase64(self, info):
        return getattr(self, 'vehicleLicenseImageBase64', None)

    def resolve_createdAt(self, info):
        return getattr(self, 'created_at', None) or getattr(self, 'createdAt', None)
    
    def resolve_updatedAt(self, info):
        return getattr(self, 'updated_at', None) or getattr(self, 'updatedAt', None)
    
    def resolve_provider(self, info):
        from app.modules.users.legacy_controller import UserController
        provider_id = getattr(self, 'provider_id', None) or getattr(self, 'providerId', None)
        if provider_id:
            controller = UserController()
            return controller.get_user_by_id(provider_id)
        return None


class BookingType(graphene.ObjectType):
    """GraphQL Booking Type"""
    id = graphene.ID(required=True)
    seekerId = graphene.ID(required=True)
    seekerName = graphene.String()
    providerId = graphene.ID()
    providerName = graphene.String()
    vehicleId = graphene.ID()
    serviceType = graphene.String(required=True)
    status = graphene.String(required=True)
    pickupLatitude = graphene.Float(required=True)
    pickupLongitude = graphene.Float(required=True)
    pickupAddress = graphene.String(required=True)
    dropLatitude = graphene.Float(required=True)
    dropLongitude = graphene.Float(required=True)
    dropAddress = graphene.String(required=True)
    distanceInKm = graphene.Float(required=True)
    estimatedPrice = graphene.Float(required=True)
    finalPrice = graphene.Float()
    hours = graphene.Int()
    isUrgent = graphene.Boolean()
    scheduledDateTime = graphene.DateTime()
    startedAt = graphene.DateTime()
    completedAt = graphene.DateTime()
    cancelledAt = graphene.DateTime()
    cancellationReason = graphene.String()
    notes = graphene.String()
    rating = graphene.Float()
    review = graphene.String()
    createdAt = graphene.DateTime()
    updatedAt = graphene.DateTime()
    
    seeker = graphene.Field(lambda: UserType)
    provider = graphene.Field(lambda: UserType)
    vehicle = graphene.Field(lambda: VehicleType)
    
    # Explicit resolvers for camelCase fields mapping to snake_case attributes
    def resolve_seekerId(self, info):
        return self.seeker_id
    
    def resolve_seekerName(self, info):
        return getattr(self, 'seeker_name', None)
    
    def resolve_providerId(self, info):
        return self.provider_id
    
    def resolve_providerName(self, info):
        return getattr(self, 'provider_name', None)
    
    def resolve_vehicleId(self, info):
        return self.vehicle_id
    
    def resolve_serviceType(self, info):
        return self.service_type
    
    def resolve_pickupLatitude(self, info):
        return self.pickup_latitude
    
    def resolve_pickupLongitude(self, info):
        return self.pickup_longitude
    
    def resolve_pickupAddress(self, info):
        return self.pickup_address
    
    def resolve_dropLatitude(self, info):
        return self.drop_latitude
    
    def resolve_dropLongitude(self, info):
        return self.drop_longitude
    
    def resolve_dropAddress(self, info):
        return self.drop_address
    
    def resolve_distanceInKm(self, info):
        return self.distance_in_km
    
    def resolve_estimatedPrice(self, info):
        return self.estimated_price
    
    def resolve_finalPrice(self, info):
        return self.final_price
    
    def resolve_isUrgent(self, info):
        return self.is_urgent
    
    def resolve_scheduledDateTime(self, info):
        return self.scheduled_date_time
    
    def resolve_startedAt(self, info):
        return self.started_at
    
    def resolve_completedAt(self, info):
        return self.completed_at
    
    def resolve_cancelledAt(self, info):
        return self.cancelled_at
    
    def resolve_cancellationReason(self, info):
        return self.cancellation_reason
    
    def resolve_createdAt(self, info):
        return self.created_at
    
    def resolve_updatedAt(self, info):
        return self.updated_at
    
    def resolve_seeker(self, info):
        from app.modules.users.legacy_controller import UserController
        controller = UserController()
        return controller.get_user_by_id(self.seeker_id)
    
    def resolve_provider(self, info):
        if not self.provider_id:
            return None
        from app.modules.users.legacy_controller import UserController
        controller = UserController()
        return controller.get_user_by_id(self.provider_id)
    
    def resolve_vehicle(self, info):
        if not self.vehicle_id:
            return None
        from app.modules.vehicles.legacy_controller import VehicleController
        controller = VehicleController()
        return controller.get_vehicle_by_id(self.vehicle_id)


class FareOfferType(graphene.ObjectType):
    """GraphQL Fare Offer Type - Represents a bid from a provider on a booking"""
    id = graphene.ID(required=True)
    bookingId = graphene.ID(required=True)
    providerId = graphene.ID(required=True)
    vehicleId = graphene.ID(required=True)
    offeredPrice = graphene.Float(required=True)
    counterPrice = graphene.Float()
    status = graphene.String(required=True)
    message = graphene.String()
    estimatedArrivalMinutes = graphene.Int()
    
    # Denormalized provider info for convenience
    providerName = graphene.String()
    providerRating = graphene.Float()
    providerPhone = graphene.String()
    providerImage = graphene.String()
    
    # Vehicle info
    vehicleType = graphene.String()
    vehicleNumber = graphene.String()
    
    createdAt = graphene.DateTime()
    updatedAt = graphene.DateTime()
    expiresAt = graphene.DateTime()
    
    provider = graphene.Field(lambda: UserType)
    vehicle = graphene.Field(lambda: VehicleType)
    booking = graphene.Field(lambda: BookingType)


# Input Types
class UserInput(graphene.InputObjectType):
    """Input type for creating/updating users"""
    email = graphene.String(required=True)
    name = graphene.String(required=True)
    phone = graphene.String(required=True)
    role = graphene.String(required=True)
    profile_image_url = graphene.String()
    cnic = graphene.String()
    driving_license = graphene.String()
    latitude = graphene.Float()
    longitude = graphene.Float()
    address = graphene.String()


class VehicleInput(graphene.InputObjectType):
    """Input type for creating/updating vehicles"""
    provider_id = graphene.ID(required=True)
    vehicle_type = graphene.String(required=True)
    vehicle_number = graphene.String(required=True)
    vehicle_model = graphene.String()
    vehicle_year = graphene.String()
    vehicle_image_url = graphene.String()
    capacity = graphene.Float()


class BookingInput(graphene.InputObjectType):
    """Input type for creating bookings"""
    seeker_id = graphene.ID(required=True)
    service_type = graphene.String(required=True)
    pickup_latitude = graphene.Float(required=True)
    pickup_longitude = graphene.Float(required=True)
    pickup_address = graphene.String(required=True)
    drop_latitude = graphene.Float(required=True)
    drop_longitude = graphene.Float(required=True)
    drop_address = graphene.String(required=True)
    distance_in_km = graphene.Float(required=True)
    estimated_price = graphene.Float(required=True)
    hours = graphene.Int()
    is_urgent = graphene.Boolean()
    scheduled_date_time = graphene.DateTime()
    notes = graphene.String()
