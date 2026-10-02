"""
Auth REST API Controller
Handles Firebase authentication and Neo4j user data sync
"""

from fastapi import APIRouter, HTTPException, status, Header, Body
from typing import Optional
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, auth
from app.modules.users.schemas import (
    UserCreate, UserUpdate, UserResponse,
    TokenVerifyRequest, TokenVerifyResponse, PhoneUserSyncRequest,
    SignupPrecheckRequest, SignupPrecheckResponse, SignupCompleteRequest
)
from app.modules.users.repository import User
from app.modules.vehicles.repository import Vehicle
from app.core.config import settings
import os
import json
import base64
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)
router = APIRouter()


class FcmTokenUpdateRequest(BaseModel):
    fcm_token: Optional[str] = None
    fcmToken: Optional[str] = None


def _resolve_storage_bucket(service_account_info: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Resolve Firebase Storage bucket from env vars or project id."""
    explicit_bucket = (
        os.getenv("FIREBASE_STORAGE_BUCKET")
        or os.getenv("FIREBASE_BUCKET_NAME")
        or ""
    ).strip()
    if explicit_bucket:
        return explicit_bucket

    project_id = (
        (service_account_info or {}).get("project_id")
        or os.getenv("FIREBASE_PROJECT_ID")
        or ""
    ).strip()
    if project_id:
        return f"{project_id}.appspot.com"

    return None


def _init_firebase() -> firebase_admin.App:
    """
    Initialise Firebase Admin SDK.

    Priority order (supports both local dev and serverless environments):
      1. FIREBASE_CREDENTIALS_JSON  – base64-encoded service-account JSON
                                      (set this env var on Vercel / any serverless host)
      2. FIREBASE_CREDENTIALS_PATH  – path to a local service-account JSON file
                                      (used for local development)
      3. Project-ID fallback         – minimal init when neither is available
    """
    raw_b64 = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if raw_b64:
        try:
            service_account_info = json.loads(base64.b64decode(raw_b64).decode("utf-8"))
            cred = credentials.Certificate(service_account_info)
            bucket_name = _resolve_storage_bucket(service_account_info)
            options = {"storageBucket": bucket_name} if bucket_name else None
            app = firebase_admin.initialize_app(cred, options=options)
            logger.info("Firebase initialised from FIREBASE_CREDENTIALS_JSON env var")
            return app
        except Exception as exc:
            logger.error(f"Failed to parse FIREBASE_CREDENTIALS_JSON: {exc}")

    service_account_path = os.path.abspath(settings.FIREBASE_CREDENTIALS_PATH)
    if os.path.exists(service_account_path):
        cred = credentials.Certificate(service_account_path)
        service_account_info = {}
        try:
            with open(service_account_path, "r", encoding="utf-8") as fp:
                service_account_info = json.load(fp)
        except Exception:
            # Keep startup resilient; credential-based init can still work.
            service_account_info = {}

        bucket_name = _resolve_storage_bucket(service_account_info)
        options = {"storageBucket": bucket_name} if bucket_name else None
        app = firebase_admin.initialize_app(cred, options=options)
        logger.info(f"Firebase initialised from file: {service_account_path}")
        return app

    # Last-resort fallback — auth token verification will not work
    fallback_project_id = (os.getenv("FIREBASE_PROJECT_ID") or "haulistry-1b835").strip()
    fallback_bucket = _resolve_storage_bucket({"project_id": fallback_project_id})
    options = {
        "projectId": fallback_project_id,
        "storageBucket": fallback_bucket,
    }
    app = firebase_admin.initialize_app(options=options)
    logger.warning("Firebase initialised with project ID only (no service account — token verification disabled)")
    return app


# Initialize Firebase Admin SDK (idempotent — won't re-init if already done)
try:
    firebase_app = firebase_admin.get_app()
except ValueError:
    firebase_app = _init_firebase()


@router.get("/test")
async def test_endpoint():
    """Test endpoint to verify auth router is working"""
    return {"message": "Auth router is working!", "status": "ok"}


def _normalize_phone(phone: str) -> str:
    digits = ''.join(ch for ch in phone if ch.isdigit() or ch == '+')
    if digits.startswith('+'):
        return digits
    if digits.startswith('03') and len(digits) == 11:
        return f"+92{digits[1:]}"
    if digits.startswith('92') and len(digits) == 12:
        return f"+{digits}"
    if digits.startswith('3') and len(digits) == 10:
        return f"+92{digits}"
    return digits


@router.post("/signup/precheck", response_model=SignupPrecheckResponse)
async def signup_precheck(payload: SignupPrecheckRequest):
    """
    Validate duplicate constraints before OTP is sent.
    No permanent writes happen here.
    """
    try:
        normalized_phone = _normalize_phone(payload.phone)
        role = (payload.role or 'seeker').lower()

        existing_phone = User.get_by_phone(normalized_phone)
        existing_email = User.get_by_email(payload.email)

        cnic_available = None
        if role == 'provider' and payload.cnic:
            cnic_available = User.get_by_cnic(payload.cnic.strip()) is None

        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account already exists with this phone number"
            )

        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account already exists with this email"
            )

        if cnic_available is False:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A provider account already exists with this CNIC"
            )

        return SignupPrecheckResponse(
            success=True,
            message="Signup precheck passed",
            isPhoneAvailable=True,
            isEmailAvailable=True,
            isCnicAvailable=cnic_available,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup precheck failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Signup precheck failed: {str(e)}"
        )


@router.post("/signup/complete", response_model=UserResponse)
async def signup_complete(
    payload: SignupCompleteRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Finalize signup after OTP verification.
    Requires Firebase ID token from verified phone-auth session.
    """
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )

    try:
        id_token = authorization.split('Bearer ')[1]
        decoded_token = auth.verify_id_token(id_token)

        firebase_uid = decoded_token['uid']
        verified_phone = decoded_token.get('phone_number')

        if not verified_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number is not verified in Firebase token"
            )

        normalized_payload_phone = _normalize_phone(payload.phone)
        normalized_verified_phone = _normalize_phone(verified_phone)

        if normalized_payload_phone != normalized_verified_phone:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Phone mismatch between signup payload and verified OTP phone"
            )

        role = (payload.role or 'seeker').lower()
        if role not in ('seeker', 'provider'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role. Must be 'seeker' or 'provider'"
            )

        # Duplicate checks with ownership allowance for same firebase uid
        existing_phone = User.get_by_phone(normalized_payload_phone)
        if existing_phone and existing_phone.get('id') != firebase_uid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account already exists with this phone number"
            )

        existing_email = User.get_by_email(payload.email)
        if existing_email and existing_email.get('id') != firebase_uid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account already exists with this email"
            )

        if role == 'provider' and payload.cnic:
            existing_cnic = User.get_by_cnic(payload.cnic.strip())
            if existing_cnic and existing_cnic.get('id') != firebase_uid:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A provider account already exists with this CNIC"
                )

        user_data = User.create({
            'firebaseUid': firebase_uid,
            'email': payload.email,
            'name': payload.name,
            'phone': normalized_payload_phone,
            'role': role,
            'profileImageUrl': payload.profileImageUrl,
            'cnic': payload.cnic,
            'cnicFrontImageBase64': payload.cnicFrontImageBase64,
            'cnicBackImageBase64': payload.cnicBackImageBase64,
            'licenseImageBase64': payload.licenseImageBase64,
            'cnicFrontImageUrl': payload.cnicFrontImageUrl,
            'cnicBackImageUrl': payload.cnicBackImageUrl,
            'licenseImageUrl': payload.licenseImageUrl,
            'vehicleImageUrl': payload.vehicleImageUrl,
            'isVerified': role != 'provider',
            'isActive': True,
            'interests': payload.interests or [],
            'latitude': payload.latitude,
            'longitude': payload.longitude,
        })

        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user profile"
            )

        # Provider post-verification setup
        if role == 'provider':
            if not payload.vehicleType or not payload.vehicleNumber:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Vehicle details are required for provider signup"
                )

            vehicle_created = Vehicle.create({
                'providerId': firebase_uid,
                'vehicleType': payload.vehicleType,
                'vehicleNumber': payload.vehicleNumber,
                'vehicleModel': payload.vehicleModel,
                'vehicleYear': payload.vehicleYear,
                'capacity': payload.vehicleCapacity or 0.0,
                'vehicleImageBase64': payload.vehicleImageBase64 or payload.vehicleImageUrl,
                'isAvailable': True,
            })

            if not vehicle_created:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to finalize provider vehicle profile"
                )

        return UserResponse(
            success=True,
            message="Signup completed successfully",
            user=user_data,
        )
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token"
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase token has expired"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup completion failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete signup: {str(e)}"
        )


@router.post("/sync", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def sync_user(user: UserCreate):
    """
    Sync user data from Firebase to Neo4j
    Called after successful Firebase signup/login
    """
    try:
        user_dict = user.dict()
        # Always compute isVerified server-side — never trust the client value.
        # Providers start unverified; seekers are verified immediately.
        user_dict['isVerified'] = user_dict.get('role', 'seeker').lower() != 'provider'
        user_data = User.create(user_dict)

        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to sync user to Neo4j"
            )
        return UserResponse(
            success=True,
            message="User synced successfully to Neo4j",
            user=user_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to sync user: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync user: {str(e)}"
        )


@router.post("/verify-token", response_model=TokenVerifyResponse)
async def verify_token(token_request: TokenVerifyRequest):
    """
    Verify Firebase ID token and return user data from Neo4j
    """
    try:
        # Verify the Firebase token
        decoded_token = auth.verify_id_token(token_request.idToken)
        firebase_uid = decoded_token['uid']
        email = decoded_token.get('email', '')
        
        # Get user from Neo4j
        user_data = User.get_by_id(firebase_uid)
        
        if not user_data:
            return TokenVerifyResponse(
                success=False,
                message="User not found in Neo4j. Please sync user data first.",
                firebaseUid=firebase_uid,
                email=email,
                user=None
            )
        
        return TokenVerifyResponse(
            success=True,
            message="Token verified successfully",
            firebaseUid=firebase_uid,
            email=email,
            user=user_data
        )
        
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token"
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase token has expired"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token verification failed: {str(e)}"
        )


@router.post("/phone/sync", response_model=UserResponse)
async def sync_phone_user(
    payload: PhoneUserSyncRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Sync a Firebase Phone-Auth user to Neo4j.

    Workflow:
      1) Verify Firebase ID token from Authorization header
      2) Read uid + phone_number claims from token
      3) Return existing user if found (with minor updates)
      4) Otherwise create a new user node in Neo4j
    """
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )

    try:
        id_token = authorization.split('Bearer ')[1]
        decoded_token = auth.verify_id_token(id_token)

        firebase_uid = decoded_token['uid']
        phone_number = decoded_token.get('phone_number')
        token_email = decoded_token.get('email')

        if not phone_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token does not contain a verified phone number"
            )

        role = (payload.role or 'seeker').lower()
        if role not in ('seeker', 'provider'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role. Must be 'seeker' or 'provider'"
            )

        # If user exists already, keep record and apply safe updates only
        existing_user = User.get_by_id(firebase_uid)
        if existing_user:
            update_data = {}

            if existing_user.get('phone') != phone_number:
                update_data['phone'] = phone_number

            # Never auto-verify providers — admin must approve manually

            if payload.name and not existing_user.get('name'):
                update_data['name'] = payload.name.strip()

            if payload.profileImageUrl and not existing_user.get('profileImageUrl'):
                update_data['profileImageUrl'] = payload.profileImageUrl

            user_data = User.update(firebase_uid, update_data) if update_data else existing_user

            return UserResponse(
                success=True,
                message="Phone-auth user synced successfully",
                user=user_data
            )

        # Create first-time user from phone-auth context
        fallback_email = payload.email or token_email or f"{firebase_uid}@phone.local"
        fallback_name = (payload.name or "").strip() or f"User {phone_number[-4:]}"

        create_payload = {
            "firebaseUid": firebase_uid,
            "email": fallback_email,
            "name": fallback_name,
            "phone": phone_number,
            "role": role,
            "isVerified": role != 'provider',
            "isActive": True,
            "profileImageUrl": payload.profileImageUrl,
        }

        user_data = User.create(create_payload)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to sync phone-auth user to Neo4j"
            )

        return UserResponse(
            success=True,
            message="Phone-auth user created successfully",
            user=user_data
        )

    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token"
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase token has expired"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Phone-auth sync failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync phone-auth user: {str(e)}"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current user data from Neo4j using Firebase token"""
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    try:
        id_token = authorization.split('Bearer ')[1]
        decoded_token = auth.verify_id_token(id_token)
        firebase_uid = decoded_token['uid']
        
        user_data = User.get_by_id(firebase_uid)
        
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User data not found in database"
            )
        
        return UserResponse(
            success=True,
            message="User retrieved successfully",
            user=user_data
        )
        
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token"
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase token has expired"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user: {str(e)}"
        )


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    authorization: Optional[str] = Header(None)
):
    """
    Update current user data in Neo4j
    """
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    try:
        # Extract token
        id_token = authorization.split('Bearer ')[1]
        
        # Verify token
        decoded_token = auth.verify_id_token(id_token)
        firebase_uid = decoded_token['uid']
        
        # Filter out None values
        update_data = {k: v for k, v in user_update.dict().items() if v is not None}
        
        # Update user in Neo4j
        user_data = User.update(firebase_uid, update_data)
        
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found in Neo4j"
            )
        
        return UserResponse(
            success=True,
            message="User updated successfully",
            user=user_data
        )
        
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token"
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase token has expired"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user: {str(e)}"
        )


@router.get("/user/{user_id}", response_model=UserResponse)
async def get_user_by_id(user_id: str):
    """
    Get user data by Firebase UID (useful for retrieving phone numbers for calls)
    """
    try:
        user_data = User.get_by_id(user_id)
        
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found in Neo4j"
            )
        
        return UserResponse(
            success=True,
            message="User retrieved successfully",
            user=user_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user: {str(e)}"
        )


@router.post("/fcm-token")
async def update_fcm_token(
    authorization: Optional[str] = Header(None),
    payload: Optional[FcmTokenUpdateRequest] = Body(None),
    fcm_token: Optional[str] = None,
):
    """
    Update user's FCM token for push notifications
    Called when app starts or token refreshes
    """
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    resolved_fcm_token = (
        fcm_token
        or (payload.fcm_token if payload else None)
        or (payload.fcmToken if payload else None)
        or ""
    ).strip()

    if not resolved_fcm_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="FCM token is required"
        )
    
    try:
        id_token = authorization.split('Bearer ')[1]
        decoded_token = auth.verify_id_token(id_token)
        firebase_uid = decoded_token['uid']
        
        # Update FCM token in Neo4j
        user_data = User.update(firebase_uid, {'fcmToken': resolved_fcm_token})
        
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found in database"
            )
        
        return {
            "success": True,
            "message": "FCM token updated successfully"
        }
        
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token"
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase token has expired"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update FCM token: {str(e)}"
        )


@router.get("/profile/{user_id}", response_model=UserResponse)
async def get_user_profile(user_id: str):
    """Get user profile by Firebase UID — used by frontend to check verification status."""
    user = User.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return UserResponse(success=True, message="Profile retrieved", user=user)
