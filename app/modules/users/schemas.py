"""
Pydantic schemas for User/Auth API requests and responses
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Dict, Any, List



class UserCreate(BaseModel):
    """Schema for creating/syncing a user from Firebase"""
    firebaseUid: str = Field(..., description="Firebase user ID")
    email: EmailStr = Field(..., description="User email")
    name: str = Field(..., description="User full name")
    phone: str = Field(..., description="User phone number")
    role: str = Field(..., description="User role: 'seeker' or 'provider'")
    profileImageUrl: Optional[str] = Field(None, description="Profile image URL")
    cnic: Optional[str] = Field(None, description="CNIC number for providers")
    cnicFrontImageBase64: Optional[str] = Field(None, description="Base64 CNIC front image")
    cnicBackImageBase64: Optional[str] = Field(None, description="Base64 CNIC back image")
    licenseImageBase64: Optional[str] = Field(None, description="Base64 license image")
    isVerified: bool = Field(default=False, description="Admin-verified status (always computed server-side)")
    isActive: bool = Field(default=True, description="Account active status")
    interests: Optional[List[str]] = Field(default=None, description="Seeker interest categories")
    latitude: Optional[float] = Field(None, description="User latitude")
    longitude: Optional[float] = Field(None, description="User longitude")

    class Config:
        json_schema_extra = {
            "example": {
                "firebaseUid": "abc123xyz456",
                "email": "user@example.com",
                "name": "John Doe",
                "phone": "+923001234567",
                "role": "provider",
                "cnic": "12345-1234567-1",
                "isVerified": True,
                "isActive": True
            }
        }


class UserUpdate(BaseModel):
    """Schema for updating user information"""
    name: Optional[str] = Field(None, description="User full name")
    phone: Optional[str] = Field(None, description="User phone number")
    profileImageUrl: Optional[str] = Field(None, description="Profile image URL")
    cnic: Optional[str] = Field(None, description="CNIC number")
    drivingLicense: Optional[str] = Field(None, description="Driving license number")
    latitude: Optional[float] = Field(None, description="User latitude")
    longitude: Optional[float] = Field(None, description="User longitude")
    address: Optional[str] = Field(None, description="User address")
    isActive: Optional[bool] = Field(None, description="Account active status")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe Updated",
                "phone": "+923001234567",
                "address": "123 Main St, Lahore",
                "cnic": "12345-1234567-1"
            }
        }


class UserResponse(BaseModel):
    """Schema for user API responses"""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    user: Optional[Dict[str, Any]] = Field(None, description="User data")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "User synced successfully",
                "user": {
                    "id": "abc123xyz456",
                    "email": "user@example.com",
                    "name": "John Doe",
                    "role": "seeker",
                    "isVerified": True
                }
            }
        }


class TokenVerifyRequest(BaseModel):
    """Schema for Firebase token verification"""
    idToken: str = Field(..., description="Firebase ID token")

    class Config:
        json_schema_extra = {
            "example": {
                "idToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6..."
            }
        }


class TokenVerifyResponse(BaseModel):
    """Schema for token verification response"""
    success: bool = Field(..., description="Whether verification was successful")
    message: str = Field(..., description="Response message")
    user: Optional[Dict[str, Any]] = Field(None, description="User data from Neo4j")
    firebaseUid: Optional[str] = Field(None, description="Firebase user ID")
    email: Optional[str] = Field(None, description="User email")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Token verified successfully",
                "firebaseUid": "abc123xyz456",
                "email": "user@example.com",
                "user": {
                    "id": "abc123xyz456",
                    "email": "user@example.com",
                    "name": "John Doe",
                    "role": "seeker"
                }
            }
        }


class PhoneUserSyncRequest(BaseModel):
    """Schema for syncing a Firebase phone-authenticated user to Neo4j"""
    name: Optional[str] = Field(None, description="Display name for first-time user creation")
    role: Optional[str] = Field("seeker", description="User role: 'seeker' or 'provider'")
    email: Optional[str] = Field(None, description="Optional email fallback for phone users")
    profileImageUrl: Optional[str] = Field(None, description="Optional profile image URL")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Ali Khan",
                "role": "seeker",
                "email": "optional@example.com"
            }
        }


class SignupPrecheckRequest(BaseModel):
    """Schema for validating duplicate constraints before OTP is sent"""
    email: EmailStr = Field(..., description="User email")
    phone: str = Field(..., description="User phone number in E.164")
    role: str = Field(..., description="User role: 'seeker' or 'provider'")
    cnic: Optional[str] = Field(None, description="CNIC for providers")


class SignupPrecheckResponse(BaseModel):
    """Schema for signup precheck response"""
    success: bool = Field(..., description="Whether precheck succeeded")
    message: str = Field(..., description="Response message")
    isPhoneAvailable: bool = Field(..., description="Phone availability")
    isEmailAvailable: bool = Field(..., description="Email availability")
    isCnicAvailable: Optional[bool] = Field(None, description="CNIC availability for provider")


class SignupCompleteRequest(BaseModel):
    """Schema for finalizing signup after OTP verification"""
    email: EmailStr = Field(..., description="User email")
    name: str = Field(..., description="User full name")
    phone: str = Field(..., description="User phone number")
    role: str = Field(..., description="User role: 'seeker' or 'provider'")
    profileImageUrl: Optional[str] = Field(None, description="Profile image data/url")

    # Provider-specific fields
    cnic: Optional[str] = Field(None, description="CNIC number for provider")
    cnicFrontImageBase64: Optional[str] = Field(None, description="Base64 CNIC front image")
    cnicBackImageBase64: Optional[str] = Field(None, description="Base64 CNIC back image")
    licenseImageBase64: Optional[str] = Field(None, description="Base64 license image")
    vehicleImageBase64: Optional[str] = Field(None, description="Base64 vehicle image")
    cnicFrontImageUrl: Optional[str] = Field(None, description="Finalized CNIC front image URL")
    cnicBackImageUrl: Optional[str] = Field(None, description="Finalized CNIC back image URL")
    licenseImageUrl: Optional[str] = Field(None, description="Finalized license image URL")
    vehicleImageUrl: Optional[str] = Field(None, description="Finalized vehicle image URL")

    vehicleType: Optional[str] = Field(None, description="Vehicle type")
    vehicleNumber: Optional[str] = Field(None, description="Vehicle registration number")
    vehicleModel: Optional[str] = Field(None, description="Vehicle model")
    vehicleYear: Optional[str] = Field(None, description="Vehicle year")
    vehicleCapacity: Optional[float] = Field(None, description="Vehicle capacity")

    # Seeker-specific preference data (collected during signup)
    interests: Optional[List[str]] = Field(
        default=None,
        description="List of service category keys seeker is interested in (e.g. ['harvester', 'crane'])"
    )
    latitude: Optional[float] = Field(None, description="User latitude from GPS during signup")
    longitude: Optional[float] = Field(None, description="User longitude from GPS during signup")
