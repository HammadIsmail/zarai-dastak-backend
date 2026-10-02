"""
Pydantic schemas for custom phone OTP authentication.

These request/response models are intentionally independent from Firebase so
Flutter clients can use plain HTTP calls to this backend.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any


class SendOtpRequest(BaseModel):
    """Request payload for sending an OTP to a phone number."""

    phone: str = Field(..., description="Phone number (local or E.164 format)")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        phone = (value or "").strip()
        if not phone:
            raise ValueError("Phone number is required")
        if len(phone) < 10 or len(phone) > 16:
            raise ValueError("Phone number length looks invalid")
        return phone


class VerifyOtpRequest(BaseModel):
    """Request payload for verifying a previously issued OTP."""

    phone: str = Field(..., description="Phone number used during send-otp")
    otp: str = Field(..., description="6-digit OTP code")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        phone = (value or "").strip()
        if not phone:
            raise ValueError("Phone number is required")
        return phone

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, value: str) -> str:
        otp = (value or "").strip()
        if not otp:
            raise ValueError("OTP is required")
        if len(otp) != 6 or not otp.isdigit():
            raise ValueError("OTP must be exactly 6 digits")
        return otp


class OtpApiResponse(BaseModel):
    """Standard JSON response shape for OTP APIs."""

    success: bool = Field(..., description="Whether request succeeded")
    message: str = Field(..., description="Human readable message")
    expiresInSeconds: Optional[int] = Field(None, description="OTP TTL when generated")
    retryAfterSeconds: Optional[int] = Field(None, description="Seconds to wait before retry")
    data: Optional[Dict[str, Any]] = Field(None, description="Optional payload")
