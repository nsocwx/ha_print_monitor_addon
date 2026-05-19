"""Home Assistant mobile notification action event handling."""
import asyncio
import json
import logging
from typing import Any, Callable, Optional

import websockets
from fastapi import HTTPException
from sqlmodel import Session

from app.api.actions import ignore_event, pause_print
from app.api.schemas import ActionResponse
from app.core.config import AppConfig, redact_sensitive
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

ACTION_PREFIX = "HA_PRINT_MONITOR"
SUPPORTED_ACTIONS = {"pause", "ignore"}


def build_notification_action(action: str, token: str) -> str:
    """Build a unique HA mobile app action id containing a signed token."""
    if action not in SUPPORTED_ACTIONS:
        raise ValueError(f"Unsupported notification action: {action}")
    return f"{ACTION_PREFIX}:{action}:{token}"


def parse_notification_action(action_id: str) -> Optional[tuple[str, str]]:
    """Extract the print monitor action and token from a HA mobile action id."""
    parts = action_id.split(":", 2)
    if len(parts) != 3 or parts[0] != ACTION_PREFIX:
        return None
    action, token = parts[1], parts[2]
    if action not in SUPPORTED_ACTIONS or not token:
        return None
    return action, token


class HomeAssistantNotificationActionListener:
    """Subscribe to HA mobile notification action events and handle ours."""

    def __init__(
        self,
        config: AppConfig,
        session_factory: Callable[[], Session] = SessionLocal,
        reconnect_delay_seconds: float = 5.0,
    ):
        self.config = config
        self.session_factory = session_factory
        self.reconnect_delay_seconds = reconnect_delay_seconds
        self._stopped = asyncio.Event()

    async def stop(self) -> None:
        """Request listener shutdown."""
        self._stopped.set()

    async def run_forever(self) -> None:
        """Maintain a websocket subscription to Home Assistant events."""
        while not self._stopped.is_set():
            try:
                await self._listen_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Home Assistant notification action listener disconnected: %s",
                    redact_sensitive(str(exc)),
                )

            try:
                await asyncio.wait_for(
                    self._stopped.wait(),
                    timeout=self.reconnect_delay_seconds,
                )
            except asyncio.TimeoutError:
                continue

    async def _listen_once(self) -> None:
        async with websockets.connect(self.config.home_assistant.websocket_url) as websocket:
            await self._authenticate(websocket)
            await websocket.send(
                json.dumps(
                    {
                        "id": 1,
                        "type": "subscribe_events",
                        "event_type": "mobile_app_notification_action",
                    }
                )
            )
            subscribe_response = json.loads(await websocket.recv())
            if not subscribe_response.get("success"):
                raise RuntimeError("Home Assistant rejected notification action subscription")

            logger.info("Listening for Home Assistant mobile notification actions")
            async for raw_message in websocket:
                if self._stopped.is_set():
                    return
                await self.handle_message(json.loads(raw_message))

    async def _authenticate(self, websocket: Any) -> None:
        auth_required = json.loads(await websocket.recv())
        if auth_required.get("type") != "auth_required":
            raise RuntimeError("Unexpected Home Assistant websocket auth handshake")

        await websocket.send(
            json.dumps(
                {
                    "type": "auth",
                    "access_token": self.config.home_assistant.token,
                }
            )
        )
        auth_response = json.loads(await websocket.recv())
        if auth_response.get("type") != "auth_ok":
            raise RuntimeError("Home Assistant websocket authentication failed")

    async def handle_message(self, message: dict[str, Any]) -> Optional[ActionResponse]:
        """Handle one HA websocket event message if it belongs to this add-on."""
        if message.get("type") != "event":
            return None

        event = message.get("event") or {}
        if event.get("event_type") != "mobile_app_notification_action":
            return None

        data = event.get("data") or {}
        parsed = parse_notification_action(str(data.get("action", "")))
        if not parsed:
            return None

        action, token = parsed
        try:
            with self.session_factory() as session:
                response = await self._dispatch(action, token, session)
        except HTTPException as exc:
            logger.warning(
                "Rejected Home Assistant notification action %s: %s",
                action,
                exc.detail,
            )
            return None

        logger.info(
            "Handled Home Assistant notification action %s for event %s",
            response.action,
            response.event_id,
        )
        return response

    async def _dispatch(
        self,
        action: str,
        token: str,
        session: Session,
    ) -> ActionResponse:
        if action == "pause":
            return await pause_print(token=token, session=session, config=self.config)
        if action == "ignore":
            return ignore_event(token=token, session=session, config=self.config)
        raise HTTPException(status_code=400, detail="Unsupported action")
