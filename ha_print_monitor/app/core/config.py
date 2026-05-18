"""Configuration management for the Home Assistant add-on."""
import json
import os
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
OPTIONS_FILE = Path(os.getenv("OPTIONS_PATH", str(DATA_DIR / "options.json")))
CONFIG_FILE = OPTIONS_FILE
HA_API_URL = "http://supervisor/core"
HA_WS_URL = "ws://supervisor/core/websocket"


class PauseServiceConfig(BaseSettings):
    """Configuration for printer pause service."""
    domain: str = "button"
    service: str = "press"
    target: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


class HomeAssistantConfig(BaseSettings):
    """Supervisor-provided Home Assistant integration settings."""
    url: str = HA_API_URL
    websocket_url: str = HA_WS_URL
    token: str = Field(default="", repr=False)
    camera_entity: str = "camera.printer"
    printer_state_entity: str = "sensor.printer_status"
    printing_states: List[str] = ["printing"]
    pause_service: PauseServiceConfig = Field(default_factory=PauseServiceConfig)
    notify_services: List[str] = Field(default_factory=lambda: ["notify.mobile_app_phone"])


class PrinterConfig(BaseSettings):
    """Configuration for one monitored printer."""
    id: str = "default"
    printer_id: Optional[str] = None
    name: str = "Default Printer"
    enabled: bool = True
    camera_entity: str = "camera.printer"
    printer_state_entity: str = "sensor.printer_status"
    printing_states: List[str] = ["printing"]
    pause_service: PauseServiceConfig = Field(default_factory=PauseServiceConfig)
    pause_service_domain: Optional[str] = None
    pause_service_service: Optional[str] = None
    pause_service_target: Optional[str] = None
    pause_service_data_json: Optional[str] = None
    notify_services: Optional[List[str]] = None
    certainty_threshold_notify: Optional[float] = None
    certainty_threshold_auto_pause: Optional[float] = None

    @field_validator("pause_service", mode="before")
    @classmethod
    def load_pause_service_config(cls, v):
        if isinstance(v, dict):
            return PauseServiceConfig(**v)
        return v

    def model_post_init(self, __context: Any) -> None:
        if not any([self.pause_service_target, self.pause_service_data_json]):
            return

        data = {}
        if self.pause_service_data_json:
            try:
                data = json.loads(self.pause_service_data_json)
            except json.JSONDecodeError as err:
                raise ValueError("pause_service_data_json must be valid JSON") from err
            if not isinstance(data, dict):
                raise ValueError("pause_service_data_json must decode to a JSON object")

        self.pause_service = PauseServiceConfig(
            domain="button",
            service="press",
            target=self.pause_service_target or self.pause_service.target,
            data=data or self.pause_service.data,
        )


class MonitoringConfig(BaseSettings):
    """Configuration for monitoring behavior."""
    enabled: bool = True
    frame_interval_seconds: int = 30
    confirmation_frames: int = 2
    certainty_threshold_notify: float = 0.7
    auto_pause_enabled: bool = True
    certainty_threshold_auto_pause: float = 0.85
    auto_pause_delay_minutes: int = 15
    cooldown_minutes: int = 10
    snooze_minutes: int = 15
    min_analysis_interval_seconds: int = 0
    confirmation_window_minutes: int = 5
    required_issue_consistency: bool = True


class SafetyConfig(BaseSettings):
    """Configuration for pause safety interlocks."""
    require_recent_frame_seconds: int = 120
    require_printer_still_printing: bool = True
    require_issue_reconfirmation_before_pause: bool = True
    prevent_duplicate_pause: bool = True


class CameraConfig(BaseSettings):
    """Configuration for camera capture reliability."""
    stale_after_seconds: int = 120
    capture_timeout_seconds: int = 15
    retry_count: int = 2
    retry_backoff_seconds: int = 3
    fallback_snapshot_url: Optional[str] = None


class NotificationsConfig(BaseSettings):
    """Configuration for notifications."""
    enabled: bool = True
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    notify_on_low: bool = False
    notify_on_medium: bool = True
    notify_on_high: bool = True
    notify_on_critical: bool = True


class ModelConfig(BaseSettings):
    """Configuration for image analysis model."""
    model_config = {"protected_namespaces": ("settings_",)}
    provider: str = "baseline"
    model_path: Optional[str] = None
    options_path: Optional[str] = None
    prototypes_path: Optional[str] = None
    auto_download: bool = True
    models_dir: str = "/data/models/printguard"
    device: str = "cpu"
    max_inference_timeout_seconds: int = 30


class SecurityConfig(BaseSettings):
    """Configuration for security."""
    action_signing_secret: str = "change-me-to-a-long-random-signing-secret"
    action_token_expiration_hours: int = 24

    @property
    def action_token_ttl_hours(self) -> int:
        return self.action_token_expiration_hours


class RetentionConfig(BaseSettings):
    """Configuration for data retention."""
    keep_images_days: int = 7
    keep_events_days: int = 30
    keep_clear_captures_hours: int = 24
    keep_event_captures_days: int = 30
    max_capture_storage_mb: int = 2048


class LoggingConfig(BaseSettings):
    """Configuration for logging."""
    json_logs: bool = False
    log_level: str = "INFO"


class ProxyConfig(BaseSettings):
    """Configuration for reverse proxy behavior."""
    forwarded_headers: bool = False
    trusted_hosts: List[str] = Field(default_factory=list)


class AppConfig(BaseSettings):
    """Main application configuration."""
    app_base_url: str = ""
    timezone: str = ""
    home_assistant: HomeAssistantConfig = Field(default_factory=HomeAssistantConfig)
    printers: List[PrinterConfig] = Field(default_factory=list)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    camera: CameraConfig = Field(default_factory=CameraConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    advanced: LoggingConfig = Field(default_factory=LoggingConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)

    class Config:
        env_file = str(DATA_DIR / ".env")
        extra = "ignore"

    @field_validator("home_assistant", mode="before")
    @classmethod
    def load_ha_config(cls, v):
        if isinstance(v, dict):
            return HomeAssistantConfig(**v)
        return v

    @field_validator("printers", mode="before")
    @classmethod
    def load_printers_config(cls, v):
        if isinstance(v, list):
            return [PrinterConfig(**printer) if isinstance(printer, dict) else printer for printer in v]
        return v

    @field_validator("printers")
    @classmethod
    def normalize_printer_ids(cls, v):
        for printer in v:
            if printer.printer_id:
                printer.id = printer.printer_id
        return v

    @field_validator("monitoring", mode="before")
    @classmethod
    def load_monitoring_config(cls, v):
        if isinstance(v, dict):
            return MonitoringConfig(**v)
        return v

    @field_validator("safety", mode="before")
    @classmethod
    def load_safety_config(cls, v):
        if isinstance(v, dict):
            return SafetyConfig(**v)
        return v

    @field_validator("camera", mode="before")
    @classmethod
    def load_camera_config(cls, v):
        if isinstance(v, dict):
            return CameraConfig(**v)
        return v

    @field_validator("notifications", mode="before")
    @classmethod
    def load_notifications_config(cls, v):
        if isinstance(v, dict):
            return NotificationsConfig(**v)
        return v

    @field_validator("model", mode="before")
    @classmethod
    def load_model_config(cls, v):
        if isinstance(v, dict):
            return ModelConfig(**v)
        return v

    def get_printers(self) -> List[PrinterConfig]:
        """Return configured printers, falling back to legacy single-printer config."""
        if self.printers:
            return self.printers

        return [
            PrinterConfig(
                id="default",
                name="Default Printer",
                camera_entity=self.home_assistant.camera_entity,
                printer_state_entity=self.home_assistant.printer_state_entity,
                printing_states=self.home_assistant.printing_states,
                pause_service=self.home_assistant.pause_service,
                notify_services=self.home_assistant.notify_services,
            )
        ]

    def get_printer(self, printer_id: str) -> Optional[PrinterConfig]:
        """Get one printer config by ID."""
        for printer in self.get_printers():
            if printer.id == printer_id:
                return printer
        return None

    @field_validator("security", mode="before")
    @classmethod
    def load_security_config(cls, v):
        if isinstance(v, dict):
            return SecurityConfig(**v)
        return v

    @field_validator("retention", mode="before")
    @classmethod
    def load_retention_config(cls, v):
        if isinstance(v, dict):
            return RetentionConfig(**v)
        return v

    @field_validator("logging", mode="before")
    @classmethod
    def load_logging_config(cls, v):
        if isinstance(v, dict):
            return LoggingConfig(**v)
        return v

    @field_validator("proxy", mode="before")
    @classmethod
    def load_proxy_config(cls, v):
        if isinstance(v, dict):
            return ProxyConfig(**v)
        return v


def load_config() -> AppConfig:
    """Load add-on options from /data/options.json and SUPERVISOR_TOKEN."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OPTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

    config_dict = {}

    if OPTIONS_FILE.exists():
        logger.info("Loading Home Assistant add-on options from %s", OPTIONS_FILE)
        try:
            with open(OPTIONS_FILE, "r", encoding="utf-8") as f:
                config_dict = json.load(f) or {}
        except Exception as e:
            logger.error("Error loading add-on options: %s", redact_sensitive(str(e)))
            config_dict = {}

    config = AppConfig(**config_dict)
    config.logging = config.advanced
    config.home_assistant.url = HA_API_URL
    config.home_assistant.websocket_url = HA_WS_URL

    supervisor_token = os.getenv("SUPERVISOR_TOKEN")
    if not supervisor_token:
        raise RuntimeError(
            "SUPERVISOR_TOKEN is missing. This application must run as a "
            "Home Assistant add-on with homeassistant_api enabled."
        )
    config.home_assistant.token = supervisor_token
    if config.security.action_signing_secret.startswith("change-me"):
        config.security.action_signing_secret = hashlib.sha256(
            supervisor_token.encode("utf-8")
        ).hexdigest()

    if monitoring_enabled := os.getenv("MONITORING_ENABLED"):
        config.monitoring.enabled = monitoring_enabled.lower() in ("true", "1", "yes")

    if frame_interval := os.getenv("FRAME_INTERVAL_SECONDS"):
        try:
            config.monitoring.frame_interval_seconds = int(frame_interval)
        except ValueError:
            logger.warning(f"Invalid FRAME_INTERVAL_SECONDS: {frame_interval}")

    if signing_secret := os.getenv("ACTION_SIGNING_SECRET"):
        config.security.action_signing_secret = signing_secret

    if log_level := os.getenv("LOG_LEVEL"):
        config.logging.log_level = log_level

    if json_logs := os.getenv("JSON_LOGS"):
        config.logging.json_logs = json_logs.lower() in ("true", "1", "yes")

    if forwarded := os.getenv("FORWARDED_HEADERS"):
        config.proxy.forwarded_headers = forwarded.lower() in ("true", "1", "yes")

    return config


def redact_sensitive(value: str) -> str:
    """Redact the supervisor token from strings before logging or diagnostics."""
    token = os.getenv("SUPERVISOR_TOKEN")
    if token:
        value = value.replace(token, "[REDACTED]")
    return value


def save_config(config: AppConfig) -> None:
    """Configuration is managed by Home Assistant add-on options."""
    raise RuntimeError("Configuration is managed by /data/options.json")
