"""
Backward compatibility re-export.
Canonical configuration now lives in `app.core.config`.
"""
from app.core.config import Settings, settings

def get_settings():
    return settings

__all__ = ['Settings', 'settings', 'get_settings']
