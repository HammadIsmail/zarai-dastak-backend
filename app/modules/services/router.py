"""
Service REST API Controller
Handles service management for providers
"""

from fastapi import APIRouter, HTTPException, status, Query
from typing import Optional
import asyncio
import logging
from app.modules.services.schemas import (
    ServiceCreate, ServiceUpdate, ServiceResponse, ServicesListResponse
)
from app.modules.services.repository import Service
from app.modules.users.repository import User
from app.modules.services.form_configs import get_form_config, list_service_types
from app.core.services.fcm_service import fcm_service, FCMNotificationType

logger = logging.getLogger(__name__)

router = APIRouter()


async def _notify_interested_seekers(category: str, service_data: dict) -> None:
    """Send a push notification to every seeker that listed this category as an interest."""
    try:
        seekers = await asyncio.to_thread(User.get_seekers_by_interest, category)
        if not seekers:
            return

        service_name = service_data.get('name') or category.replace('_', ' ').title()
        provider_name = service_data.get('providerName') or 'A provider'
        service_id = service_data.get('id', '')

        for seeker in seekers:
            token = seeker.get('fcmToken')
            if not token:
                continue
            try:
                await fcm_service.send_to_token(
                    fcm_token=token,
                    notification_type=FCMNotificationType.NEW_BOOKING_REQUEST,
                    title=f"New {service_name} available!",
                    body=f"{provider_name} just listed a {service_name} service near you.",
                    data={
                        'type': 'new_service_recommendation',
                        'category': category,
                        'serviceId': service_id,
                    },
                )
            except Exception as exc:
                logger.warning(f"FCM notification failed for seeker {seeker.get('id')}: {exc}")
    except Exception as exc:
        logger.error(f"_notify_interested_seekers error: {exc}")


def _require_verified_provider(provider_id: str) -> None:
    """Raise 403 if the provider is not admin-verified."""
    provider = User.get_by_id(provider_id)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found.",
        )
    if not provider.get('isVerified'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is pending admin approval. You cannot manage services until your account is verified.",
        )


@router.get("/form-config/all", tags=["Service Forms"])
async def get_all_form_configs():
    """Return form field configs for all known service types."""
    from app.modules.services.form_configs import SERVICE_FORM_CONFIGS
    return {"success": True, "configs": SERVICE_FORM_CONFIGS, "serviceTypes": list_service_types()}


@router.get("/form-config/{service_type}", tags=["Service Forms"])
async def get_service_form_config(service_type: str):
    """Return dynamic form field configuration for a given service type."""
    config = get_form_config(service_type)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No form config found for service type: {service_type}",
        )
    return {"success": True, "serviceType": service_type, "config": config}


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service(service: ServiceCreate):
    """Create a new service offering"""
    try:
        _require_verified_provider(service.providerId)

        service_data = Service.create(service.dict())

        if not service_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create service",
            )

        # Fire-and-forget: notify seekers interested in this category
        category = service_data.get('category') or service.category
        if category:
            asyncio.create_task(_notify_interested_seekers(category, service_data))

        return ServiceResponse(
            success=True,
            message="Service created successfully",
            service=service_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create service: {str(e)}",
        )


@router.get("", response_model=ServicesListResponse)
async def get_available_services(
    category: Optional[str] = Query(None, description="Filter by category"),
    latitude: Optional[float] = Query(None, description="User latitude for nearby search"),
    longitude: Optional[float] = Query(None, description="User longitude for nearby search"),
    radius: float = Query(50.0, description="Search radius in km")
):
    """Get all available services (for seekers to browse)"""
    try:
        services = Service.get_available_services(
            category=category,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius
        )
        
        return ServicesListResponse(
            success=True,
            message="Services retrieved successfully",
            services=services,
            total=len(services)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch services: {str(e)}"
        )


@router.get("/provider/{provider_id}", response_model=ServicesListResponse)
async def get_provider_services(provider_id: str):
    """Get all services offered by a provider (provider must be verified)"""
    try:
        _require_verified_provider(provider_id)

        services = Service.get_by_provider(provider_id)

        return ServicesListResponse(
            success=True,
            message="Provider services retrieved successfully",
            services=services,
            total=len(services),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch provider services: {str(e)}",
        )


@router.get("/vehicle/{vehicle_id}", response_model=ServicesListResponse)
async def get_vehicle_services(vehicle_id: str, provider_id: Optional[str] = Query(None)):
    """Get all services offered by a specific vehicle.
    Pass provider_id when called from the provider dashboard — it enforces verification.
    Omit provider_id for public/seeker-facing lookups."""
    try:
        if provider_id:
            _require_verified_provider(provider_id)

        services = Service.get_by_vehicle(vehicle_id)

        return ServicesListResponse(
            success=True,
            message="Vehicle services retrieved successfully",
            services=services,
            total=len(services),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch vehicle services: {str(e)}",
        )


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(service_id: str):
    """Get a specific service by ID"""
    try:
        service = Service.get_by_id(service_id)
        
        if not service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found"
            )
        
        return ServiceResponse(
            success=True,
            message="Service retrieved successfully",
            service=service
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch service: {str(e)}"
        )


@router.put("/{service_id}", response_model=ServiceResponse)
async def update_service(service_id: str, service_update: ServiceUpdate):
    """Update a service (provider must be verified)"""
    try:
        # Resolve the owning provider before mutating.
        existing = Service.get_by_id(service_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found",
            )
        _require_verified_provider(existing['providerId'])

        update_data = {k: v for k, v in service_update.dict().items() if v is not None}
        service_data = Service.update(service_id, update_data)

        if not service_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found",
            )

        return ServiceResponse(
            success=True,
            message="Service updated successfully",
            service=service_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update service: {str(e)}",
        )


@router.delete("/{service_id}", response_model=ServiceResponse)
async def delete_service(service_id: str):
    """Delete a service"""
    try:
        deleted = Service.delete(service_id)
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found"
            )
        
        return ServiceResponse(
            success=True,
            message="Service deleted successfully",
            service=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete service: {str(e)}"
        )
