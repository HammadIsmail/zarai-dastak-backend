"""
Backward compatibility re-export.
Canonical constants now live in `app.core.constants`.
"""
from app.core.constants import *
from app.core.constants import BookingStatus, UserRole, ACTIVE_BOOKING_STATUSES, LIVE_COMMUNICATION_STATUSES

__all__ = ['BookingStatus', 'UserRole', 'ACTIVE_BOOKING_STATUSES', 'LIVE_COMMUNICATION_STATUSES']
