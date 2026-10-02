"""
Pydantic schemas for Fare Offer (Bidding/Negotiation) API requests and responses
InDrive-style dynamic pricing negotiation
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class FareOfferCreate(BaseModel):
    """Schema for provider creating a fare offer on a booking"""
    bookingId: str = Field(..., description="ID of the booking to make offer on")
    providerId: str = Field(..., description="ID of the provider making the offer")
    vehicleId: str = Field(..., description="ID of the vehicle to use")
    offeredPrice: float = Field(..., description="Provider's offered price")
    message: Optional[str] = Field(None, description="Optional message to seeker")
    estimatedArrivalMinutes: Optional[int] = Field(None, description="ETA in minutes")

    class Config:
        json_schema_extra = {
            "example": {
                "bookingId": "booking123",
                "providerId": "provider456",
                "vehicleId": "vehicle789",
                "offeredPrice": 1500.0,
                "message": "I can be there in 15 minutes",
                "estimatedArrivalMinutes": 15
            }
        }


class CounterOfferRequest(BaseModel):
    """Schema for seeker making a counter offer"""
    counterPrice: float = Field(..., description="Seeker's counter price")

    class Config:
        json_schema_extra = {
            "example": {
                "counterPrice": 1200.0
            }
        }


class UpdateOfferPrice(BaseModel):
    """Schema for provider updating their offer price"""
    newPrice: float = Field(..., description="Updated offer price")
    message: Optional[str] = Field(None, description="Optional message")

    class Config:
        json_schema_extra = {
            "example": {
                "newPrice": 1300.0,
                "message": "I can accept this price"
            }
        }


class FareOfferResponse(BaseModel):
    """Schema for fare offer API responses"""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    offer: Optional[Dict[str, Any]] = Field(None, description="Fare offer data")


class FareOffersListResponse(BaseModel):
    """Schema for multiple fare offers response"""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    offers: List[Dict[str, Any]] = Field(default=[], description="List of fare offers")
    total: int = Field(default=0, description="Total count")
