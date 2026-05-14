from typing import Set

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def send_json(self, websocket: WebSocket, payload: dict) -> None:
        await websocket.send_json(payload)

    async def broadcast(self, payload: dict) -> None:
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(payload)
            except Exception:
                disconnected.append(connection)
        for connection in disconnected:
            self.disconnect(connection)
