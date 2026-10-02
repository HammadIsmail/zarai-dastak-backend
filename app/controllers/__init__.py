"""
Backward compatibility re-export.
Canonical routers now live in `app.modules`.
"""
from app.modules import api_router
from app.modules.users.legacy_controller import UserController
from app.modules.vehicles.legacy_controller import VehicleController
from app.modules.bookings.legacy_controller import BookingController

__all__ = ['UserController', 'VehicleController', 'BookingController', 'api_router']
