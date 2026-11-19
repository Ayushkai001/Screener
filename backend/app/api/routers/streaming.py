"""STRATLAB Real-Time Streaming Multiplexer (WebSockets)."""

import json
from typing import Dict, List, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect


router = APIRouter(tags=["Streaming Distribution"])


class ConnectionManager:
    """Manages active WebSocket connections and channel subscriptions."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.subscriptions: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        for channel in self.subscriptions:
            self.subscriptions[channel].discard(websocket)

    def subscribe(self, websocket: WebSocket, channel: str):
        self.subscriptions.setdefault(channel, set()).add(websocket)

    def unsubscribe(self, websocket: WebSocket, channel: str):
        if channel in self.subscriptions:
            self.subscriptions[channel].discard(websocket)

    async def broadcast(self, channel: str, message: dict):
        if channel in self.subscriptions:
            dead_sockets = []
            for connection in self.subscriptions[channel]:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead_sockets.append(connection)
            for dead in dead_sockets:
                self.disconnect(dead)


stream_manager = ConnectionManager()


@router.websocket("/ws/market/stream")
async def market_stream_endpoint(websocket: WebSocket):
    """
    Multiplexed WebSocket streaming connection for candles, footprint, and execution fills.
    """
    await stream_manager.connect(websocket)
    try:
        while True:
            data_text = await websocket.receive_text()
            try:
                msg = json.loads(data_text)
                action = msg.get("action")
                channel = msg.get("channel")

                if action == "subscribe" and channel:
                    stream_manager.subscribe(websocket, channel)
                    await websocket.send_json({"status": "subscribed", "channel": channel})

                elif action == "unsubscribe" and channel:
                    stream_manager.unsubscribe(websocket, channel)
                    await websocket.send_json({"status": "unsubscribed", "channel": channel})

                elif action == "ping":
                    await websocket.send_json({"action": "pong"})

            except json.JSONDecodeError:
                await websocket.send_json({"error": "INVALID_JSON"})
    except WebSocketDisconnect:
        stream_manager.disconnect(websocket)
