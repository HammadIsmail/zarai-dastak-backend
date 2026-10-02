"""
Firebase Admin SDK wrapper for admin user auth.
- Signup -> firebase_admin.auth.create_user()
- Login  -> Firebase REST signInWithPassword API
- Profile -> stored in Neo4j AdminUser node alongside Firebase UID
"""

from __future__ import annotations
import httpx
from typing import Optional
from pathlib import Path
from .config import admin_settings
from app.core.config import settings


def _get_app():
    import firebase_admin
    from firebase_admin import credentials

    if firebase_admin._apps:
        return firebase_admin.get_app()

    cred_path_str = getattr(settings, "FIREBASE_CREDENTIALS_PATH", "./serviceAccountKey.json")
    p = Path(cred_path_str)
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[2] / p.name

    if not p.exists():
        # Check alternative common names in backend dir
        backend_dir = Path(__file__).resolve().parents[2]
        for candidate in backend_dir.glob("*.json"):
            if "firebase-adminsdk" in candidate.name or "serviceAccount" in candidate.name:
                p = candidate
                break

    if not p.exists():
        return None

    try:
        cred = credentials.Certificate(str(p))
        return firebase_admin.initialize_app(cred)
    except Exception:
        return None


def create_firebase_user(email: str, password: str, display_name: str) -> Optional[str]:
    """Create a Firebase Auth user. Returns UID on success, None on failure."""
    app = _get_app()
    if app is None:
        return None
    from firebase_admin import auth as fb_auth
    try:
        user = fb_auth.create_user(
            email=email,
            password=password,
            display_name=display_name,
            email_verified=False,
        )
        return user.uid
    except fb_auth.EmailAlreadyExistsError:
        raise ValueError("An account with this email already exists in Firebase.")
    except Exception as e:
        raise ValueError(f"Firebase signup error: {e}")


def sign_in_with_firebase(email: str, password: str) -> Optional[dict]:
    """Verify email+password against Firebase Auth REST API."""
    api_key = admin_settings.FIREBASE_WEB_API_KEY
    if not api_key or api_key.startswith("AIzaSyYOUR"):
        return None

    url = (
        "https://identitytoolkit.googleapis.com/v1/"
        f"accounts:signInWithPassword?key={api_key}"
    )
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(
                url,
                json={"email": email, "password": password, "returnSecureToken": True},
            )
            if r.status_code == 200:
                return r.json()
            data = r.json()
            msg = data.get("error", {}).get("message", "UNKNOWN")
            if msg in ("EMAIL_NOT_FOUND", "INVALID_PASSWORD", "INVALID_LOGIN_CREDENTIALS"):
                raise ValueError("Invalid credentials.")
            if msg == "USER_DISABLED":
                raise ValueError("This account has been disabled.")
            raise ValueError(f"Firebase auth error: {msg}")
    except httpx.RequestError as e:
        raise ValueError(f"Cannot reach Firebase: {e}")


def delete_firebase_user(uid: str) -> bool:
    app = _get_app()
    if app is None:
        return False
    from firebase_admin import auth as fb_auth
    try:
        fb_auth.delete_user(uid)
        return True
    except Exception:
        return False


def update_firebase_password(uid: str, new_password: str) -> bool:
    app = _get_app()
    if app is None:
        return False
    from firebase_admin import auth as fb_auth
    try:
        fb_auth.update_user(uid, password=new_password)
        return True
    except Exception:
        return False


def firebase_configured() -> bool:
    k = admin_settings.FIREBASE_WEB_API_KEY
    return bool(k) and not k.startswith("AIzaSyYOUR")
