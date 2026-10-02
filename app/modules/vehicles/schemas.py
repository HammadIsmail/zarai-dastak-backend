"""
Pydantic schemas for Vehicle API requests and responses
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class VehicleCreate(BaseModel):
    """Schema for creating a new vehicle — pure entity (type, number, model, year, images)"""
    providerId: str = Field(..., description="ID of the service provider")
    vehicleType: str = Field(..., description="Type of vehicle")
    vehicleNumber: str = Field(..., description="Vehicle registration number")
    vehicleModel: Optional[str] = Field(None, description="Vehicle model")
    vehicleYear: Optional[str] = Field(None, description="Vehicle year")
    vehicleImageBase64: Optional[str] = Field(None, description="Base64 encoded vehicle photo")
    vehicleLicenseImageBase64: Optional[str] = Field(None, description="Base64 encoded vehicle registration document")
    isAvailable: bool = Field(default=True, description="Whether vehicle is available")
    capacity: Optional[float] = Field(None, description="Legacy capacity field")
    extraFields: Optional[str] = Field(None, description="JSON-encoded dynamic form fields")

    class Config:
        json_schema_extra = {
            "example": {
                "providerId": "provider123",
                "vehicleType": "truck",
                "vehicleNumber": "ABC-1234",
                "vehicleModel": "Ford F-150",
                "vehicleYear": "2023",
                "isAvailable": True,
                "capacity": 2.5
            }
        }


class VehicleUpdate(BaseModel):
    """Schema for updating an existing vehicle"""
    vehicleType: Optional[str] = Field(None, description="Vehicle type")
    vehicleNumber: Optional[str] = Field(None, description="Vehicle registration number")
    vehicleModel: Optional[str] = Field(None, description="Vehicle model")
    vehicleYear: Optional[str] = Field(None, description="Vehicle year")
    vehicleImageUrl: Optional[str] = Field(None, description="Vehicle image URL")
    vehicleImageBase64: Optional[str] = Field(None, description="Base64 encoded vehicle photo")
    vehicleLicenseImageBase64: Optional[str] = Field(None, description="Base64 encoded vehicle registration document")
    isAvailable: Optional[bool] = Field(None, description="Availability status")
    capacity: Optional[float] = Field(None, description="Vehicle capacity (legacy, prefer extraFields)")
    extraFields: Optional[str] = Field(None, description="JSON-encoded dynamic form fields")

    class Config:
        json_schema_extra = {
            "example": {
                "vehicleModel": "Ford F-250",
                "isAvailable": False,
                "capacity": 3.0
            }
        }


class VehicleResponse(BaseModel):
    """Schema for vehicle API responses"""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    vehicle: Optional[Dict[str, Any]] = Field(None, description="Vehicle data")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Vehicle created successfully",
                "vehicle": {
                    "id": "vehicle123",
                    "providerId": "provider123",
                    "vehicleType": "truck",
                    "vehicleNumber": "ABC-1234",
                    "isAvailable": True
                }
            }
        }
