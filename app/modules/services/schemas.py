"""
Pydantic schemas for Service API requests and responses
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class ServiceCreate(BaseModel):
    """Schema for creating a new service"""
    providerId: str = Field(..., description="ID of the service provider")
    vehicleId: str = Field(..., description="ID of the vehicle offering this service")
    name: str = Field(..., description="Service name (e.g., Sand Delivery, Brick Transport)")
    description: Optional[str] = Field(None, description="Service description")
    imageUrl: Optional[str] = Field(None, description="Service image URL")
    basePrice: float = Field(default=0.0, description="Base price for the service")
    pricePerKm: float = Field(default=0.0, description="Price per kilometer")
    pricePerHour: float = Field(default=0.0, description="Price per hour")
    category: str = Field(default="general", description="Service category")
    extraFields: Optional[str] = Field(None, description="JSON string of service-specific extra fields")
    serviceBaseLatitude: Optional[float] = Field(None, description="Latitude of the machine's base/garage location")
    serviceBaseLongitude: Optional[float] = Field(None, description="Longitude of the machine's base/garage location")
    serviceBaseAddress: Optional[str] = Field(None, description="Human-readable address of the machine's base location")

    class Config:
        json_schema_extra = {
            "example": {
                "providerId": "provider123",
                "vehicleId": "vehicle456",
                "name": "Sand Delivery",
                "description": "Fast sand delivery within city limits",
                "basePrice": 500.0,
                "pricePerKm": 50.0,
                "pricePerHour": 200.0,
                "category": "construction"
            }
        }


class ServiceUpdate(BaseModel):
    """Schema for updating a service"""
    name: Optional[str] = Field(None, description="Service name")
    description: Optional[str] = Field(None, description="Service description")
    imageUrl: Optional[str] = Field(None, description="Service image URL")
    basePrice: Optional[float] = Field(None, description="Base price")
    pricePerKm: Optional[float] = Field(None, description="Price per kilometer")
    pricePerHour: Optional[float] = Field(None, description="Price per hour")
    category: Optional[str] = Field(None, description="Service category")
    isActive: Optional[bool] = Field(None, description="Service availability")
    extraFields: Optional[str] = Field(None, description="JSON string of service-specific extra fields")
    serviceBaseLatitude: Optional[float] = Field(None, description="Latitude of the machine's base/garage location")
    serviceBaseLongitude: Optional[float] = Field(None, description="Longitude of the machine's base/garage location")
    serviceBaseAddress: Optional[str] = Field(None, description="Human-readable address of the machine's base location")


class ServiceResponse(BaseModel):
    """Schema for service API responses"""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    service: Optional[Dict[str, Any]] = Field(None, description="Service data")


class ServicesListResponse(BaseModel):
    """Schema for multiple services response"""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    services: List[Dict[str, Any]] = Field(default=[], description="List of services")
    total: int = Field(default=0, description="Total count")
