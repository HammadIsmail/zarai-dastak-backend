"""
Haulistry Modular Monolith Domain Aggregation
Aggregates all bounded-context domain routers into api_router with identical paths.
"""

from fastapi import APIRouter

from .auth import router as auth_router, otp_router
from .bookings import router as bookings_router
from .vehicles import router as vehicles_router
from .services import router as services_router
from .fare_offers import router as fare_offers_router
from .locations import router as locations_router
from .communications import (
    calls_router,
    messages_router,
    notifications_router,
)
from .feedback import router as feedback_router
from .exploration import (
    explore_router,
    recommendations_router,
)
from .admin import router as admin_router

# Central API Router
api_router = APIRouter(prefix="/api")

# Mount domain routers
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(bookings_router, prefix="/bookings", tags=["bookings"])
api_router.include_router(vehicles_router, prefix="/vehicles", tags=["vehicles"])
api_router.include_router(services_router, prefix="/services", tags=["services"])
api_router.include_router(fare_offers_router, prefix="/fare-offers", tags=["fare-offers"])
api_router.include_router(locations_router, prefix="/locations", tags=["locations"])
api_router.include_router(feedback_router, tags=["feedback"])
api_router.include_router(calls_router, tags=["calls"])
api_router.include_router(messages_router, tags=["messages"])
api_router.include_router(notifications_router)
api_router.include_router(recommendations_router, prefix="/recommendations", tags=["recommendations"])
api_router.include_router(explore_router, prefix="/providers/explore", tags=["providers-explore"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])

__all__ = ["api_router", "otp_router"]
