"""Home Assistant Supervisor/Core API integration service."""
import logging
import asyncio
import httpx
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class HomeAssistantError(Exception):
    """Base exception for Home Assistant errors."""
    pass


class HomeAssistantAuthError(HomeAssistantError):
    """Raised for Home Assistant authentication failures."""


class HomeAssistantNetworkError(HomeAssistantError):
    """Raised for transient Home Assistant network failures."""


@dataclass
class CameraImage:
    """Camera response bytes plus HTTP metadata."""

    content: bytes
    content_type: str
    content_length: int
    status_code: int


class HAService:
    """Service for interacting with Home Assistant."""

    def __init__(
        self,
        url: str,
        token: str,
        timeout_seconds: float = 30.0,
        retry_count: int = 2,
        retry_backoff_seconds: float = 1.0,
    ):
        """Initialize HA service with the Supervisor-provided bearer token."""
        self.url = url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count
        self.retry_backoff_seconds = retry_backoff_seconds
        self.last_success_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._client: Optional[httpx.Client] = None

    @staticmethod
    def redact(value: str) -> str:
        token = os.getenv("SUPERVISOR_TOKEN")
        if token:
            value = value.replace(token, "[REDACTED]")
        return value

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout_seconds)
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client:
            self._client.close()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Run one HA request with retries for transient failures."""
        last_exc: Optional[Exception] = None
        for attempt in range(self.retry_count + 1):
            try:
                async with httpx.AsyncClient(
                    headers=self.headers,
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                ) as client:
                    response = await client.request(
                        method,
                        f"{self.url}{path}",
                        headers=self.headers,
                        **kwargs,
                    )
                if response.status_code in (401, 403):
                    self.last_error = "Home Assistant authentication failed"
                    raise HomeAssistantAuthError("Home Assistant authentication failed")
                response.raise_for_status()
                self.last_success_at = datetime.utcnow()
                self.last_error = None
                return response
            except HomeAssistantAuthError:
                raise
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                self.last_error = self.redact(f"Home Assistant network error: {exc}")
                logger.warning(
                    "Transient Home Assistant failure on %s %s: %s",
                    method,
                    path,
                    self.redact(str(exc)),
                )
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                self.last_error = f"Home Assistant HTTP {status}"
                if status < 500:
                    raise HomeAssistantError(f"Home Assistant request failed with HTTP {status}")
                last_exc = exc

            if attempt < self.retry_count:
                await asyncio.sleep(self.retry_backoff_seconds * (attempt + 1))

        raise HomeAssistantNetworkError(
            self.redact(f"Home Assistant request failed: {last_exc}")
        ) from last_exc

    async def get_state(self, entity_id: str) -> Dict[str, Any]:
        """Get entity state from Home Assistant.

        Args:
            entity_id: Entity ID (e.g., sensor.printer_status)

        Returns:
            State object with state, attributes, etc.

        Raises:
            HomeAssistantError: If request fails
        """
        resp = await self._request("GET", f"/api/states/{entity_id}")
        if resp.status_code == 404:
            raise HomeAssistantError(f"Entity not found: {entity_id}")
        return resp.json()

    async def get_home_assistant_config(self) -> Dict[str, Any]:
        """Get Home Assistant Core configuration metadata."""
        resp = await self._request("GET", "/api/config")
        return resp.json()

    async def get_camera_image(self, entity_id: str) -> CameraImage:
        """Get camera snapshot image from Home Assistant.

        Args:
            entity_id: Camera entity ID

        Returns:
            CameraImage with image bytes and response metadata

        Raises:
            HomeAssistantError: If request fails
        """
        resp = await self._request("GET", f"/api/camera_proxy/{entity_id}")
        return CameraImage(
            content=resp.content,
            content_type=resp.headers.get("content-type", ""),
            content_length=len(resp.content),
            status_code=resp.status_code,
        )

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

            resp = await self._request(
                "POST",
                f"/api/services/{domain}/{service}",
                json=payload,
            )
            return resp.json()
        except HomeAssistantError as e:
            logger.error("Failed to call Home Assistant service %s.%s: %s", domain, service, e)
            raise

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

            resp = await self._request(
                "POST",
                f"/api/services/{domain}/{svc}",
                json=payload,
            )
            return resp.json()
        except HomeAssistantError as e:
            logger.error("Failed to send notification via %s: %s", service, e)
            raise

    async def test_connection(self) -> bool:
        """Test Home Assistant connection.

        Returns:
            True if connection successful

        Raises:
            HomeAssistantError: If connection fails
        """
        await self._request("GET", "/api/")
        logger.info("Home Assistant connection successful")
        return True
