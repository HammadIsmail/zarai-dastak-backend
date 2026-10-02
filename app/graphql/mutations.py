import graphene
from .types import (
    UserType, VehicleType, BookingType, FareOfferType,
    UserInput, VehicleInput, BookingInput
)
from app.modules.users.legacy_controller import UserController
from app.modules.vehicles.legacy_controller import VehicleController
from app.modules.bookings.legacy_controller import BookingController
from app.modules.fare_offers.repository import FareOffer
from app.core.constants import BookingStatus


class CreateUser(graphene.Mutation):
    """Create a new user"""
    class Arguments:
        input = UserInput(required=True)
    
    user = graphene.Field(UserType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, input):
        try:
            controller = UserController()
            user = controller.create_user(input.__dict__)
            return CreateUser(user=user, success=True, message="User created successfully")
        except Exception as e:
            return CreateUser(user=None, success=False, message=str(e))


class UpdateUser(graphene.Mutation):
    """Update user information"""
    class Arguments:
        id = graphene.ID(required=True)
        input = UserInput(required=True)
    
    user = graphene.Field(UserType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, id, input):
        try:
            controller = UserController()
            user = controller.update_user(id, input.__dict__)
            if user:
                return UpdateUser(user=user, success=True, message="User updated successfully")
            return UpdateUser(user=None, success=False, message="User not found")
        except Exception as e:
            return UpdateUser(user=None, success=False, message=str(e))


class CreateVehicle(graphene.Mutation):
    """Create a new vehicle"""
    class Arguments:
        input = VehicleInput(required=True)
    
    vehicle = graphene.Field(VehicleType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, input):
        try:
            controller = VehicleController()
            vehicle = controller.create_vehicle(input.__dict__)
            return CreateVehicle(vehicle=vehicle, success=True, message="Vehicle created successfully")
        except Exception as e:
            return CreateVehicle(vehicle=None, success=False, message=str(e))


class UpdateVehicle(graphene.Mutation):
    """Update vehicle information"""
    class Arguments:
        id = graphene.ID(required=True)
        is_available = graphene.Boolean()
        vehicle_model = graphene.String()
        vehicle_year = graphene.String()
        capacity = graphene.Float()
    
    vehicle = graphene.Field(VehicleType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, id, **kwargs):
        try:
            controller = VehicleController()
            updates = {k: v for k, v in kwargs.items() if v is not None}
            vehicle = controller.update_vehicle(id, updates)
            if vehicle:
                return UpdateVehicle(vehicle=vehicle, success=True, message="Vehicle updated successfully")
            return UpdateVehicle(vehicle=None, success=False, message="Vehicle not found")
        except Exception as e:
            return UpdateVehicle(vehicle=None, success=False, message=str(e))


class CreateBooking(graphene.Mutation):
    """Create a new booking"""
    class Arguments:
        input = BookingInput(required=True)
    
    booking = graphene.Field(BookingType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, input):
        try:
            controller = BookingController()
            booking_data = input.__dict__
            booking_data['status'] = BookingStatus.PENDING
            booking = controller.create_booking(booking_data)
            return CreateBooking(booking=booking, success=True, message="Booking created successfully")
        except Exception as e:
            return CreateBooking(booking=None, success=False, message=str(e))


class UpdateBookingStatus(graphene.Mutation):
    """Update booking status"""
    class Arguments:
        id = graphene.ID(required=True)
        status = graphene.String(required=True)
        provider_id = graphene.ID()
        vehicle_id = graphene.ID()
    
    booking = graphene.Field(BookingType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, id, status, provider_id=None, vehicle_id=None):
        try:
            controller = BookingController()
            booking = controller.update_booking_status(id, status, provider_id, vehicle_id)
            if booking:
                return UpdateBookingStatus(booking=booking, success=True, message=f"Booking status updated to {status}")
            return UpdateBookingStatus(booking=None, success=False, message="Booking not found")
        except Exception as e:
            return UpdateBookingStatus(booking=None, success=False, message=str(e))


class RateBooking(graphene.Mutation):
    """Rate a completed booking"""
    class Arguments:
        booking_id = graphene.ID(required=True)
        rating = graphene.Float(required=True)
        review = graphene.String()
    
    booking = graphene.Field(BookingType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, booking_id, rating, review=None):
        try:
            if rating < 0 or rating > 5:
                return RateBooking(booking=None, success=False, message="Rating must be between 0 and 5")
            
            controller = BookingController()
            booking = controller.rate_booking(booking_id, rating, review)
            if booking:
                return RateBooking(booking=booking, success=True, message="Booking rated successfully")
            return RateBooking(booking=None, success=False, message="Booking not found or not completed")
        except Exception as e:
            return RateBooking(booking=None, success=False, message=str(e))


class CancelBooking(graphene.Mutation):
    """Cancel a booking"""
    class Arguments:
        booking_id = graphene.ID(required=True)
        cancellation_reason = graphene.String(required=True)
    
    booking = graphene.Field(BookingType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, booking_id, cancellation_reason):
        try:
            controller = BookingController()
            booking = controller.cancel_booking(booking_id, cancellation_reason)
            if booking:
                return CancelBooking(booking=booking, success=True, message="Booking cancelled successfully")
            return CancelBooking(booking=None, success=False, message="Booking not found or cannot be cancelled")
        except Exception as e:
            return CancelBooking(booking=None, success=False, message=str(e))


# ============================================
# FARE OFFER MUTATIONS (InDrive-style bidding)
# ============================================

class CreateFareOffer(graphene.Mutation):
    """Provider creates a fare offer on a booking"""
    class Arguments:
        booking_id = graphene.ID(required=True)
        provider_id = graphene.ID(required=True)
        vehicle_id = graphene.ID(required=True)
        offered_price = graphene.Float(required=True)
        message = graphene.String()
        estimated_arrival_minutes = graphene.Int()
    
    offer = graphene.Field(FareOfferType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, booking_id, provider_id, vehicle_id, offered_price, 
               message=None, estimated_arrival_minutes=None):
        try:
            offer_data = {
                'bookingId': booking_id,
                'providerId': provider_id,
                'vehicleId': vehicle_id,
                'offeredPrice': offered_price,
                'message': message,
                'estimatedArrivalMinutes': estimated_arrival_minutes,
            }
            offer = FareOffer.create(offer_data)
            if offer:
                return CreateFareOffer(offer=offer, success=True, message="Offer created successfully")
            return CreateFareOffer(offer=None, success=False, message="Failed to create offer")
        except Exception as e:
            return CreateFareOffer(offer=None, success=False, message=str(e))


class AcceptFareOffer(graphene.Mutation):
    """Seeker accepts a fare offer"""
    class Arguments:
        offer_id = graphene.ID(required=True)
    
    offer = graphene.Field(FareOfferType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, offer_id):
        try:
            offer = FareOffer.accept_offer(offer_id)
            if offer:
                return AcceptFareOffer(offer=offer, success=True, message="Offer accepted! Provider is on the way.")
            return AcceptFareOffer(offer=None, success=False, message="Offer not found or already processed")
        except Exception as e:
            return AcceptFareOffer(offer=None, success=False, message=str(e))


class RejectFareOffer(graphene.Mutation):
    """Seeker rejects a fare offer"""
    class Arguments:
        offer_id = graphene.ID(required=True)
    
    offer = graphene.Field(FareOfferType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, offer_id):
        try:
            offer = FareOffer.reject_offer(offer_id)
            if offer:
                return RejectFareOffer(offer=offer, success=True, message="Offer rejected")
            return RejectFareOffer(offer=None, success=False, message="Offer not found")
        except Exception as e:
            return RejectFareOffer(offer=None, success=False, message=str(e))


class CounterFareOffer(graphene.Mutation):
    """Seeker sends a counter offer"""
    class Arguments:
        offer_id = graphene.ID(required=True)
        counter_price = graphene.Float(required=True)
    
    offer = graphene.Field(FareOfferType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, offer_id, counter_price):
        try:
            offer = FareOffer.counter_offer(offer_id, counter_price)
            if offer:
                return CounterFareOffer(offer=offer, success=True, message=f"Counter offer of Rs. {counter_price:.0f} sent")
            return CounterFareOffer(offer=None, success=False, message="Offer not found")
        except Exception as e:
            return CounterFareOffer(offer=None, success=False, message=str(e))


class UpdateFareOfferPrice(graphene.Mutation):
    """Provider updates their offer price (in response to counter offer)"""
    class Arguments:
        offer_id = graphene.ID(required=True)
        new_price = graphene.Float(required=True)
        message = graphene.String()
    
    offer = graphene.Field(FareOfferType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, offer_id, new_price, message=None):
        try:
            offer = FareOffer.update_offer_price(offer_id, new_price, message)
            if offer:
                return UpdateFareOfferPrice(offer=offer, success=True, message=f"Price updated to Rs. {new_price:.0f}")
            return UpdateFareOfferPrice(offer=None, success=False, message="Offer not found")
        except Exception as e:
            return UpdateFareOfferPrice(offer=None, success=False, message=str(e))


class WithdrawFareOffer(graphene.Mutation):
    """Provider withdraws their offer"""
    class Arguments:
        offer_id = graphene.ID(required=True)
    
    offer = graphene.Field(FareOfferType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, offer_id):
        try:
            offer = FareOffer.withdraw_offer(offer_id)
            if offer:
                return WithdrawFareOffer(offer=offer, success=True, message="Offer withdrawn")
            return WithdrawFareOffer(offer=None, success=False, message="Offer not found")
        except Exception as e:
            return WithdrawFareOffer(offer=None, success=False, message=str(e))


class Mutation(graphene.ObjectType):
    """GraphQL Mutation Root"""
    # User mutations
    create_user = CreateUser.Field()
    update_user = UpdateUser.Field()
    
    # Vehicle mutations
    create_vehicle = CreateVehicle.Field()
    update_vehicle = UpdateVehicle.Field()
    
    # Booking mutations
    create_booking = CreateBooking.Field()
    update_booking_status = UpdateBookingStatus.Field()
    rate_booking = RateBooking.Field()
    cancel_booking = CancelBooking.Field()
    
    # Fare Offer mutations (InDrive-style bidding)
    create_fare_offer = CreateFareOffer.Field()
    accept_fare_offer = AcceptFareOffer.Field()
    reject_fare_offer = RejectFareOffer.Field()
    counter_fare_offer = CounterFareOffer.Field()
    update_fare_offer_price = UpdateFareOfferPrice.Field()
    withdraw_fare_offer = WithdrawFareOffer.Field()
