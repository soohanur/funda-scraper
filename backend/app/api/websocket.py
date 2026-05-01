"""
WebSocket connection for real-time job updates
"""
import json
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import Job
from ..schemas.schemas import WebSocketMessage
from ..core.security import decode_access_token

router = APIRouter(prefix="/ws", tags=["WebSocket"])


class ConnectionManager:
    """Manage WebSocket connections."""
    
    def __init__(self):
        # user_id -> set of websockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # job_uuid -> set of websockets
        self.job_subscriptions: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept new WebSocket connection."""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        
        self.active_connections[user_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove WebSocket connection."""
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        
        # Remove from all job subscriptions
        for job_uuid in list(self.job_subscriptions.keys()):
            self.job_subscriptions[job_uuid].discard(websocket)
            if not self.job_subscriptions[job_uuid]:
                del self.job_subscriptions[job_uuid]
    
    def subscribe_to_job(self, websocket: WebSocket, job_uuid: str):
        """Subscribe WebSocket to job updates."""
        if job_uuid not in self.job_subscriptions:
            self.job_subscriptions[job_uuid] = set()
        
        self.job_subscriptions[job_uuid].add(websocket)
    
    def unsubscribe_from_job(self, websocket: WebSocket, job_uuid: str):
        """Unsubscribe WebSocket from job updates."""
        if job_uuid in self.job_subscriptions:
            self.job_subscriptions[job_uuid].discard(websocket)
            
            if not self.job_subscriptions[job_uuid]:
                del self.job_subscriptions[job_uuid]
    
    async def send_to_user(self, user_id: str, message: dict):
        """Send message to all connections of a user."""
        if user_id in self.active_connections:
            dead_connections = set()
            
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead_connections.add(connection)
            
            # Clean up dead connections
            for connection in dead_connections:
                self.disconnect(connection, user_id)
    
    async def send_job_update(self, job_uuid: str, message: dict):
        """Send update to all subscribers of a job."""
        if job_uuid in self.job_subscriptions:
            dead_connections = set()
            
            for connection in self.job_subscriptions[job_uuid]:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead_connections.add(connection)
            
            # Clean up dead connections
            for connection in dead_connections:
                self.job_subscriptions[job_uuid].discard(connection)
    
    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        for user_id in list(self.active_connections.keys()):
            await self.send_to_user(user_id, message)


# Global connection manager
manager = ConnectionManager()


@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token")
):
    """
    WebSocket endpoint for real-time updates.
    
    Client should connect with JWT token as query parameter:
    ws://host/api/v1/ws?token=<jwt_token>
    
    Messages from client:
    - {"action": "subscribe", "job_uuid": "<uuid>"}  # Subscribe to job updates
    - {"action": "unsubscribe", "job_uuid": "<uuid>"}  # Unsubscribe from job
    - {"action": "ping"}  # Keep-alive ping
    
    Messages to client:
    - {"type": "job_update", "job_uuid": "<uuid>", "data": {...}}
    - {"type": "log", "job_uuid": "<uuid>", "data": {...}}
    - {"type": "system_alert", "data": {...}}
    - {"type": "pong"}  # Response to ping
    """
    # Authenticate
    user_id = decode_access_token(token)
    
    if not user_id:
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    # Connect
    await manager.connect(websocket, user_id)
    
    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "user_id": user_id,
            "message": "WebSocket connected successfully"
        })
        
        # Message loop
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            action = message.get("action")
            
            if action == "subscribe":
                job_uuid = message.get("job_uuid")
                if job_uuid:
                    manager.subscribe_to_job(websocket, job_uuid)
                    await websocket.send_json({
                        "type": "subscribed",
                        "job_uuid": job_uuid
                    })
            
            elif action == "unsubscribe":
                job_uuid = message.get("job_uuid")
                if job_uuid:
                    manager.unsubscribe_from_job(websocket, job_uuid)
                    await websocket.send_json({
                        "type": "unsubscribed",
                        "job_uuid": job_uuid
                    })
            
            elif action == "ping":
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    
    except Exception as e:
        manager.disconnect(websocket, user_id)
        try:
            await websocket.close(code=1011, reason=str(e))
        except:
            pass


# Helper function for tasks to send updates
async def send_job_update(job_uuid: str, update_type: str, data: dict):
    """
    Send job update to all subscribers.
    
    Args:
        job_uuid: Job UUID
        update_type: Type of update (e.g., "progress", "status", "log")
        data: Update data
    """
    message = {
        "type": "job_update",
        "job_uuid": job_uuid,
        "update_type": update_type,
        "data": data
    }
    
    await manager.send_job_update(job_uuid, message)
