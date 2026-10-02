"""
Backward compatibility re-export.
Realtime gateways now live in `app.core.realtime`.
"""
from app.core.realtime.socketio_gateway import sio
from app.core.realtime.websocket_gateway import router, manager

__all__ = ['sio', 'router', 'manager']
