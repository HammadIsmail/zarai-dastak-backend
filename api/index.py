"""
ASGI entry point for Haulistry backend.

For Railway/Render, this serves FastAPI + Socket.IO using a single ASGI app.
"""

from app.main import combined_app as app  # noqa: F401  — re-exported ASGI handler
