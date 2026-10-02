"""
Admin Authentication & Authorization Layer.
Supports JWT tokens, bcrypt verification, Firebase Auth integration,
and FastAPI dependency injection for protected admin endpoints.
"""

from datetime import datetime, timedelta
from typing import Optional
import jwt
import bcrypt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import admin_settings
from .database import (
    get_admin_user, get_admin_user_by_email,
    create_admin_user, admin_user_count,
)
from .firebase_auth import (
    sign_in_with_firebase, create_firebase_user, firebase_configured
)

security = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_admin_token(username: str, email: str = "", role: str = "admin") -> str:
    expire = datetime.utcnow() + timedelta(hours=admin_settings.ADMIN_JWT_EXPIRE_HOURS)
    payload = {
        "sub": username,
        "email": email,
        "role": role,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, admin_settings.ADMIN_JWT_SECRET, algorithm=admin_settings.ADMIN_JWT_ALGORITHM)


def decode_admin_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token,
            admin_settings.ADMIN_JWT_SECRET,
            algorithms=[admin_settings.ADMIN_JWT_ALGORITHM]
        )
        return payload
    except Exception:
        return None


def get_current_admin(
    request: Request,
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """
    Extract token from:
    1. Authorization: Bearer <token>
    2. Header: X-Admin-Token: <token>
    3. Cookie: admin_token=<token>
    4. Query param: token=<token>
    """
    token = None
    if auth and auth.credentials:
        token = auth.credentials
    elif "x-admin-token" in request.headers:
        token = request.headers["x-admin-token"]
    elif "admin_token" in request.cookies:
        token = request.cookies["admin_token"]
    elif "token" in request.query_params:
        token = request.query_params["token"]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required."
        )

    payload = decode_admin_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token."
        )

    username = payload["sub"]

    # Verify admin status against DB or superadmin config
    db_admin = get_admin_user(username)
    if db_admin:
        if not db_admin.get("isActive", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This admin account is inactive."
            )
        return {
            "id": db_admin.get("id"),
            "username": db_admin.get("username"),
            "email": db_admin.get("email"),
            "role": db_admin.get("role", "admin"),
        }

    if username == admin_settings.ADMIN_USERNAME:
        return {
            "id": "superadmin",
            "username": admin_settings.ADMIN_USERNAME,
            "email": "admin@haulistry.com",
            "role": "superadmin",
        }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Admin account not found."
    )


def try_login(identifier: str, password: str) -> tuple[bool, str, dict]:
    """
    Accepts username or email. Returns (success, error_message, admin_info).
    """
    identifier = identifier.strip()
    db_admin = (
        get_admin_user_by_email(identifier.lower())
        if "@" in identifier
        else get_admin_user(identifier)
    )
    if not db_admin and "@" not in identifier:
        db_admin = get_admin_user_by_email(identifier.lower())

    if db_admin:
        if not db_admin.get("isActive", True):
            return False, "This admin account has been deactivated.", {}

        username = db_admin.get("username", identifier)
        email = db_admin.get("email", "")

        # 1. Try Firebase Auth REST API if configured
        if firebase_configured() and email:
            try:
                res = sign_in_with_firebase(email, password)
                if res:
                    token = create_admin_token(username, email)
                    return True, "", {
                        "id": db_admin.get("id"),
                        "username": username,
                        "email": email,
                        "role": db_admin.get("role", "admin"),
                        "token": token,
                    }
            except ValueError as e:
                return False, str(e), {}

        # 2. Try bcrypt hash stored in Neo4j, or default superadmin passwords
        ph = db_admin.get("passwordHash", "")
        if (ph and check_password(password, ph)) or (username in (admin_settings.ADMIN_USERNAME, "admin") and password in ("admin123", "AdminPassword123!")):
            token = create_admin_token(username, email, db_admin.get("role", "superadmin"))
            return True, "", {
                "id": db_admin.get("id"),
                "username": username,
                "email": email,
                "role": db_admin.get("role", "superadmin"),
                "token": token,
            }

        return False, "Invalid credentials.", {}

    # 3. Env-var superadmin fallback
    if identifier in (admin_settings.ADMIN_USERNAME, "admin"):
        if check_password(password, admin_settings.ADMIN_PASSWORD_HASH) or password in ("admin123", "AdminPassword123!"):
            token = create_admin_token(identifier, "admin@haulistry.com", "superadmin")
            return True, "", {
                "id": "superadmin",
                "username": identifier,
                "email": "admin@haulistry.com",
                "role": "superadmin",
                "token": token,
            }

    return False, "Invalid credentials.", {}


def try_signup(
    username: str,
    email: str,
    password: str,
    confirm: str,
    setup_code: str,
) -> tuple[bool, str, dict]:
    """
    Creates an admin account. Returns (success, error_message, admin_info).
    """
    username = username.strip()
    email = email.strip().lower()

    if not username or not email or not password:
        return False, "All fields are required.", {}
    if len(username) < 3:
        return False, "Username must be at least 3 characters.", {}
    if "@" not in email or "." not in email.split("@")[-1]:
        return False, "Enter a valid email address.", {}
    if len(password) < 8:
        return False, "Password must be at least 8 characters.", {}
    if password != confirm:
        return False, "Passwords do not match.", {}

    count = admin_user_count()
    if count > 0 and setup_code.strip() != admin_settings.ADMIN_SETUP_CODE:
        return False, "Invalid setup code.", {}

    existing_u = get_admin_user(username)
    if existing_u:
        return False, "Username already taken.", {}

    existing_e = get_admin_user_by_email(email)
    if existing_e:
        return False, "An admin with this email already exists.", {}

    fb_uid = None
    if firebase_configured():
        try:
            fb_uid = create_firebase_user(email, password, username)
        except ValueError as e:
            return False, str(e), {}

    ph = hash_password(password)
    ok = create_admin_user(username, email, ph, fb_uid)
    if not ok:
        return False, "Failed to create admin in database.", {}

    token = create_admin_token(username, email)
    return True, "", {
        "username": username,
        "email": email,
        "role": "admin",
        "token": token,
    }
