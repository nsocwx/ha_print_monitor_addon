"""Home Assistant integration service."""
import logging
import httpx
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class HomeAssistantError(Exception):
    """Base exception for Home Assistant errors."""
    pass


@dataclass
class CameraImage:
    """Camera response bytes plus HTTP metadata."""

    content: bytes
    content_type: str
    content_length: int
    status_code: int


class HAService:
    """Service for interacting with Home Assistant."""

    def __init__(self, url: str, token: str):
        """Initialize HA service.

        Args:
            url: Home Assistant URL (e.g., http://localhost:8123)
            token: Long-lived access token
        """
        self.url = url.rstrip("/")
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()

    async def get_state(self, entity_id: str) -> Dict[str, Any]:
        """Get entity state from Home Assistant.

        Args:
            entity_id: Entity ID (e.g., sensor.printer_status)

        Returns:
            State object with state, attributes, etc.

        Raises:
            HomeAssistantError: If request fails
        """
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=30.0) as client:
                resp = await client.get(
                    f"{self.url}/api/states/{entity_id}",
                    headers=self.headers
                )
                if resp.status_code == 404:
                    raise HomeAssistantError(f"Entity not found: {entity_id}")
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to get state for {entity_id}: {e}")
            raise HomeAssistantError(f"Failed to get state: {e}")

    async def get_camera_image(self, entity_id: str) -> CameraImage:
        """Get camera snapshot image from Home Assistant.

        Args:
            entity_id: Camera entity ID

        Returns:
            CameraImage with image bytes and response metadata

        Raises:
            HomeAssistantError: If request fails
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.url}/api/camera_proxy/{entity_id}",
                    headers=self.headers
                )
                resp.raise_for_status()
                return CameraImage(
                    content=resp.content,
                    content_type=resp.headers.get("content-type", ""),
                    content_length=len(resp.content),
                    status_code=resp.status_code,
                )
        except httpx.HTTPError as e:
            logger.error(f"Failed to get camera image for {entity_id}: {e}")
            raise HomeAssistantError(f"Failed to get camera image: {e}")

    async def call_service(
        self,
        domain: str,
        service: str,
        target: Optional[Dict[str, str]] = None,
        service_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Call a Home Assistant service.

        Args:
            domain: Service domain (e.g., button)
            service: Service name (e.g., press)
            target: Service target with entity_id
            service_data: Additional service data

        Returns:
            Response from Home Assistant

        Raises:
            HomeAssistantError: If request fails
        """
        try:
            payload = service_data or {}
            if target:
                payload["target"] = target

            async with httpx.AsyncClient(headers=self.headers, timeout=30.0) as client:
                resp = await client.post(
                    f"{self.url}/api/services/{domain}/{service}",
                    json=payload,
                    headers=self.headers
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to call service {domain}.{service}: {e}")
            raise HomeAssistantError(f"Failed to call service: {e}")

    async def send_notification(
        self,
        service: str,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send notification via Home Assistant notify service.

        Args:
            service: Notify service name (e.g., notify.mobile_app_phone)
            title: Notification title
            message: Notification message
            data: Additional notification data (images, actions, etc.)

        Returns:
            Response from Home Assistant

        Raises:
            HomeAssistantError: If request fails
        """
        try:
            # Extract domain and service from full service name
            if "." in service:
                parts = service.split(".")
                domain = parts[0]
                svc = parts[1]
            else:
                domain = "notify"
                svc = service

            payload = {
                "title": title,
                "message": message,
            }
            if data:
                payload["data"] = data

            async with httpx.AsyncClient(headers=self.headers, timeout=30.0) as client:
                resp = await client.post(
                    f"{self.url}/api/services/{domain}/{svc}",
                    json=payload,
                    headers=self.headers
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to send notification: {e}")
            raise HomeAssistantError(f"Failed to send notification: {e}")

    async def test_connection(self) -> bool:
        """Test Home Assistant connection.

        Returns:
            True if connection successful

        Raises:
            HomeAssistantError: If connection fails
        """
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=10.0) as client:
                resp = await client.get(
                    f"{self.url}/api/",
                    headers=self.headers
                )
                resp.raise_for_status()
                logger.info("Home Assistant connection successful")
                return True
        except httpx.HTTPError as e:
            logger.error(f"Home Assistant connection failed: {e}")
            raise HomeAssistantError(f"Connection failed: {e}")
