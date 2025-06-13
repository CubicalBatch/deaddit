"""
WebSocket handlers for real-time admin interface updates.
"""

from datetime import datetime

from flask_socketio import emit, join_room, leave_room
from loguru import logger

from deaddit import socketio


@socketio.on("connect", namespace="/admin")
def admin_connect():
    """Handle admin WebSocket connection."""
    logger.info("Admin client connected to WebSocket")
    emit("connected", {"status": "Connected to admin WebSocket"})


@socketio.on("disconnect", namespace="/admin")
def admin_disconnect():
    """Handle admin WebSocket disconnection."""
    logger.info("Admin client disconnected from WebSocket")


@socketio.on("join_job_updates", namespace="/admin")
def join_job_updates(data):
    """Join job updates room for real-time job status."""
    join_room("job_updates")
    logger.info("Client joined job_updates room")
    emit("joined", {"room": "job_updates"})


@socketio.on("leave_job_updates", namespace="/admin")
def leave_job_updates(data):
    """Leave job updates room."""
    leave_room("job_updates")
    logger.info("Client left job_updates room")
    emit("left", {"room": "job_updates"})


@socketio.on("ping", namespace="/admin")
def handle_ping():
    """Handle ping for connection testing."""
    emit("pong", {"timestamp": datetime.utcnow().isoformat()})
