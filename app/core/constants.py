"""Shared backend constants for booking and live-service flows."""


class BookingStatus:
    PENDING = "pending"
    ACCEPTED = "accepted"
    ACTIVE = "active"
    PROVIDER_ARRIVING = "provider_arriving"
    PROVIDER_ARRIVED = "provider_arrived"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    CONFIRMED = "confirmed"


class UserRole:
    SEEKER = "seeker"
    PROVIDER = "provider"
    USER = "user"


ACTIVE_BOOKING_STATUSES = {
    BookingStatus.PENDING,
    BookingStatus.ACCEPTED,
    BookingStatus.ACTIVE,
    BookingStatus.PROVIDER_ARRIVING,
    BookingStatus.PROVIDER_ARRIVED,
    BookingStatus.IN_PROGRESS,
}

LIVE_COMMUNICATION_STATUSES = {
    BookingStatus.CONFIRMED,
    BookingStatus.ACCEPTED,
    BookingStatus.ACTIVE,
    BookingStatus.PROVIDER_ARRIVING,
    BookingStatus.PROVIDER_ARRIVED,
    BookingStatus.IN_PROGRESS,
}
