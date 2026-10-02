"""
Admin Module Configuration for Haulistry Backend.
Reads from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Ensure environment variables are loaded
_env_path = Path(__file__).resolve().parents[3] / "backend" / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=False)


class AdminSettings(BaseSettings):
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    # Default bcrypt hash of "admin123"
    ADMIN_PASSWORD_HASH: str = os.getenv(
        "ADMIN_PASSWORD_HASH",
        "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",
    )
    ADMIN_SETUP_CODE: str = os.getenv("ADMIN_SETUP_CODE", "haulistry-setup-2025")
    ADMIN_JWT_SECRET: str = os.getenv("ADMIN_JWT_SECRET", "haulistry-admin-secret-key-2025-super-secure")
    ADMIN_JWT_ALGORITHM: str = "HS256"
    ADMIN_JWT_EXPIRE_HOURS: int = 24
    FIREBASE_WEB_API_KEY: str = os.getenv("FIREBASE_WEB_API_KEY", "")
    PLATFORM_COMMISSION_RATE: float = 0.10


admin_settings = AdminSettings()
