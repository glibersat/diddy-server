import asyncio
import logging
from collections import defaultdict

from fastapi import WebSocket

from app.config import settings

logger = logging.getLogger("diddy.notify.ws")


class ConnectionManager:
    """Tracks the companion app's live WebSocket(s) per user.

    A user may have more than one phone connected; a `trigger` goes out to all of them (mirrors
    the BLE service being single-owner per watch, but nothing stops two phones both trying).
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._closing: set[asyncio.Task] = set()  # keeps close tasks referenced until done

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        sockets = self._connections.get(user_id)
        if sockets is None:
            return
        sockets.discard(websocket)
        if not sockets:
            del self._connections[user_id]

    def is_connected(self, user_id: str) -> bool:
        return bool(self._connections.get(user_id))

    async def send_to_user(self, user_id: str, payload: dict) -> bool:
        """Best-effort send to every socket for this user, concurrently. Returns True if at
        least one worked."""
        sockets = list(self._connections.get(user_id, ()))
        results = await asyncio.gather(*(self._send(user_id, websocket, payload) for websocket in sockets))
        return any(results)

    async def _send(self, user_id: str, websocket: WebSocket, payload: dict) -> bool:
        try:
            await asyncio.wait_for(websocket.send_json(payload), timeout=settings.ws_send_timeout_seconds)
            return True
        except Exception:
            logger.warning("Dropping dead websocket for user %s", user_id, exc_info=True)
            self._drop(user_id, websocket)
            return False

    def _drop(self, user_id: str, websocket: WebSocket) -> None:
        """Forget the socket and close it in the background - a stalled socket's close could
        stall too, and just forgetting it would leave the phone thinking it's still connected
        (so it would never reconnect and send `watch_ready`)."""
        self.disconnect(user_id, websocket)
        task = asyncio.create_task(self._close(websocket))
        self._closing.add(task)
        task.add_done_callback(self._closing.discard)

    @staticmethod
    async def _close(websocket: WebSocket) -> None:
        try:
            await asyncio.wait_for(websocket.close(code=1011), timeout=settings.ws_send_timeout_seconds)
        except Exception:
            pass


manager = ConnectionManager()
