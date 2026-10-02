"""
Pydantic schemas for Location tracking API requests and responses
Real-time location sharing during active bookings
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class LocationUpdateRequest(BaseModel):
    """Schema for updating user location during active booking"""
    bookingId: str = Field(..., description="ID of the active booking")
    userId: str = Field(..., description="ID of the user updating location")
    latitude: float = Field(..., description="Current latitude")
    longitude: float = Field(..., description="Current longitude")
    heading: Optional[float] = Field(None, description="Direction of travel in degrees")
    speed: Optional[float] = Field(None, description="Speed in km/h")
    accuracy: Optional[float] = Field(None, description="Location accuracy in meters")

    class Config:
        json_schema_extra = {
            "example": {
                "bookingId": "booking123",
                "userId": "user456",
                "latitude": 31.5204,
                "longitude": 74.3587,
                "heading": 45.0,
                "speed": 30.0,
                "accuracy": 10.0
            }
        }


class UserLocationUpdate(BaseModel):
    """Schema for updating user's general location (for providers)"""
    userId: str = Field(..., description="ID of the user")
    latitude: float = Field(..., description="Current latitude")
    longitude: float = Field(..., description="Current longitude")

    class Config:
        json_schema_extra = {
            "example": {
                "userId": "provider123",
                "latitude": 31.5204,
                "longitude": 74.3587
            }
        }


class LocationResponse(BaseModel):
    """Schema for location API responses"""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    location: Optional[Dict[str, Any]] = Field(None, description="Location data")


class BookingLocationsResponse(BaseModel):
    """Schema for getting both seeker and provider locations"""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    bookingId: str = Field(..., description="Booking ID")
    seeker: Optional[Dict[str, Any]] = Field(None, description="Seeker location data")
    provider: Optional[Dict[str, Any]] = Field(None, description="Provider location data")
