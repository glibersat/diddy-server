import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger("diddy.notify.ws")


class ConnectionManager:
    """Tracks the companion app's live WebSocket(s) per user.

    A user may have more than one phone connected; a `trigger` goes out to all of them (mirrors
    the BLE service being single-owner per watch, but nothing stops two phones both trying).
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        self._connections[user_id].discard(websocket)
        if not self._connections[user_id]:
            del self._connections[user_id]

    def is_connected(self, user_id: str) -> bool:
        return bool(self._connections.get(user_id))

    async def send_to_user(self, user_id: str, payload: dict) -> bool:
        """Best-effort send to every socket for this user. Returns True if at least one worked."""
        sockets = list(self._connections.get(user_id, ()))
        delivered = False
        for websocket in sockets:
            try:
                await websocket.send_json(payload)
                delivered = True
            except Exception:
                logger.warning("Dropping dead websocket for user %s", user_id, exc_info=True)
                self.disconnect(user_id, websocket)
        return delivered


manager = ConnectionManager()
