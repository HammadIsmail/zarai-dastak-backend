"""
Pydantic schemas for Booking API requests and responses
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class BookingCreate(BaseModel):
    """Schema for creating a new booking"""
    seekerId: str = Field(..., description="ID of the service seeker")
    providerId: Optional[str] = Field(None, description="ID of the service provider")
    vehicleId: Optional[str] = Field(None, description="ID of the vehicle")
    serviceId: Optional[str] = Field(None, description="ID of the service being booked")
    serviceType: str = Field(..., description="Type of service (e.g., hauling, delivery)")
    bookingMode: Optional[str] = Field(None, description="'fixedOrigin' or 'transport'")
    pickupLatitude: float = Field(..., description="Pickup location latitude")
    pickupLongitude: float = Field(..., description="Pickup location longitude")
    pickupAddress: str = Field(..., description="Pickup address")
    dropLatitude: float = Field(..., description="Drop location latitude")
    dropLongitude: float = Field(..., description="Drop location longitude")
    dropAddress: str = Field(..., description="Drop address")
    distanceInKm: float = Field(..., description="Distance in kilometers")
    estimatedPrice: float = Field(..., description="Estimated price for the service")
    hours: int = Field(default=1, description="Duration in hours")
    isUrgent: bool = Field(default=False, description="Whether the booking is urgent")
    scheduledDateTime: str = Field(..., description="Scheduled date and time")
    notes: Optional[str] = Field(None, description="Additional notes")

    class Config:
        json_schema_extra = {
            "example": {
                "seekerId": "user123",
                "serviceType": "hauling",
                "pickupLatitude": 37.7749,
                "pickupLongitude": -122.4194,
                "pickupAddress": "123 Main St, San Francisco",
                "dropLatitude": 37.8044,
                "dropLongitude": -122.2712,
                "dropAddress": "456 Oak Ave, Oakland",
                "distanceInKm": 15.5,
                "estimatedPrice": 75.00,
                "hours": 2,
                "isUrgent": False,
                "scheduledDateTime": "2026-01-20T10:00:00",
                "notes": "Handle with care"
            }
        }


class BookingUpdate(BaseModel):
    """Schema for updating an existing booking"""
    status: Optional[str] = Field(None, description="Booking status")
    finalPrice: Optional[float] = Field(None, description="Final price")
    providerId: Optional[str] = Field(None, description="Provider ID")
    vehicleId: Optional[str] = Field(None, description="Vehicle ID")
    notes: Optional[str] = Field(None, description="Additional notes")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "in_progress",
                "finalPrice": 80.00,
                "notes": "Updated delivery instructions"
            }
        }


class BookingResponse(BaseModel):
    """Schema for booking API responses"""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    booking: Optional[Dict[str, Any]] = Field(None, description="Booking data")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Booking created successfully",
                "booking": {
                    "id": "booking123",
                    "seekerId": "user123",
                    "status": "pending",
                    "estimatedPrice": 75.00
                }
            }
        }
