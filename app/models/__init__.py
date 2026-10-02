"""
Backward compatibility re-export.
Domain models now live in `app.modules.*.repository`.
"""
from app.modules.users.repository import User
from app.modules.vehicles.repository import Vehicle
from app.modules.bookings.repository import Booking
from app.modules.services.repository import Service
from app.modules.fare_offers.repository import FareOffer
from app.modules.locations.repository import LocationUpdate

__all__ = ['User', 'Vehicle', 'Booking', 'Service', 'FareOffer', 'LocationUpdate']
