"""Configuration management for HA Print Monitor."""
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings
import yaml

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
CONFIG_FILE = Path(os.getenv("CONFIG_PATH", str(DATA_DIR / "config.yaml")))


class PauseServiceConfig(BaseSettings):
    """Configuration for printer pause service."""
    domain: str = "button"
    service: str = "press"
    target: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


class HomeAssistantConfig(BaseSettings):
    """Configuration for Home Assistant integration."""
    url: str = "http://localhost:8123"
    token: str = ""
    camera_entity: str = "camera.printer"
    printer_state_entity: str = "sensor.printer_status"
    printing_states: List[str] = ["printing"]
    pause_service: PauseServiceConfig = Field(default_factory=PauseServiceConfig)
    notify_services: List[str] = Field(default_factory=lambda: ["notify.mobile_app_phone"])


class PrinterConfig(BaseSettings):
    """Configuration for one monitored printer."""
    id: str = "default"
    name: str = "Default Printer"
    enabled: bool = True
    camera_entity: str = "camera.printer"
    printer_state_entity: str = "sensor.printer_status"
    printing_states: List[str] = ["printing"]
    pause_service: PauseServiceConfig = Field(default_factory=PauseServiceConfig)
    notify_services: Optional[List[str]] = None
    certainty_threshold_notify: Optional[float] = None
    certainty_threshold_auto_pause: Optional[float] = None


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
    action_token: str = "change-me-in-production"
    action_signing_secret: str = "change-me-to-a-long-random-signing-secret"
    action_token_ttl_hours: int = 24


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
    app_base_url: str = "http://localhost:8080"
    timezone: str = "UTC"
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
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)

    class Config:
        env_file = str(DATA_DIR / ".env")

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
    """Load configuration from YAML file and environment variables."""
    # Create data directory if needed
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

    config_dict = {}

    # Load YAML config if exists
    if CONFIG_FILE.exists():
        logger.info(f"Loading config from {CONFIG_FILE}")
        try:
            with open(CONFIG_FILE, "r") as f:
                config_dict = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            config_dict = {}

    # Create AppConfig with merged env vars and file config
    config = AppConfig(**config_dict)

    # Override with environment variables
    if url := os.getenv("HA_URL"):
        config.home_assistant.url = url
    if token := os.getenv("HA_TOKEN"):
        config.home_assistant.token = token
    if camera := os.getenv("HA_CAMERA_ENTITY"):
        config.home_assistant.camera_entity = camera
    if state_entity := os.getenv("HA_PRINTER_STATE_ENTITY"):
        config.home_assistant.printer_state_entity = state_entity

    if app_url := os.getenv("APP_BASE_URL"):
        config.app_base_url = app_url

    if monitoring_enabled := os.getenv("MONITORING_ENABLED"):
        config.monitoring.enabled = monitoring_enabled.lower() in ("true", "1", "yes")

    if frame_interval := os.getenv("FRAME_INTERVAL_SECONDS"):
        try:
            config.monitoring.frame_interval_seconds = int(frame_interval)
        except ValueError:
            logger.warning(f"Invalid FRAME_INTERVAL_SECONDS: {frame_interval}")

    if action_token := os.getenv("ACTION_TOKEN"):
        config.security.action_token = action_token

    if signing_secret := os.getenv("ACTION_SIGNING_SECRET"):
        config.security.action_signing_secret = signing_secret

    if log_level := os.getenv("LOG_LEVEL"):
        config.logging.log_level = log_level

    if json_logs := os.getenv("JSON_LOGS"):
        config.logging.json_logs = json_logs.lower() in ("true", "1", "yes")

    if forwarded := os.getenv("FORWARDED_HEADERS"):
        config.proxy.forwarded_headers = forwarded.lower() in ("true", "1", "yes")

    return config


def save_config(config: AppConfig) -> None:
    """Save configuration to YAML file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    config_dict = {
        "app_base_url": config.app_base_url,
        "timezone": config.timezone,
        "home_assistant": {
            "url": config.home_assistant.url,
            "token": config.home_assistant.token,
            "camera_entity": config.home_assistant.camera_entity,
            "printer_state_entity": config.home_assistant.printer_state_entity,
            "printing_states": config.home_assistant.printing_states,
            "pause_service": {
                "domain": config.home_assistant.pause_service.domain,
                "service": config.home_assistant.pause_service.service,
                "target": config.home_assistant.pause_service.target,
                "data": config.home_assistant.pause_service.data,
            },
            "notify_services": config.home_assistant.notify_services,
        },
        "printers": [
            {
                "id": printer.id,
                "name": printer.name,
                "enabled": printer.enabled,
                "camera_entity": printer.camera_entity,
                "printer_state_entity": printer.printer_state_entity,
                "printing_states": printer.printing_states,
                "pause_service": {
                    "domain": printer.pause_service.domain,
                    "service": printer.pause_service.service,
                    "target": printer.pause_service.target,
                    "data": printer.pause_service.data,
                },
                "notify_services": printer.notify_services,
                "certainty_threshold_notify": printer.certainty_threshold_notify,
                "certainty_threshold_auto_pause": printer.certainty_threshold_auto_pause,
            }
            for printer in config.printers
        ],
        "monitoring": {
            "enabled": config.monitoring.enabled,
            "frame_interval_seconds": config.monitoring.frame_interval_seconds,
            "confirmation_frames": config.monitoring.confirmation_frames,
            "certainty_threshold_notify": config.monitoring.certainty_threshold_notify,
            "auto_pause_enabled": config.monitoring.auto_pause_enabled,
            "certainty_threshold_auto_pause": config.monitoring.certainty_threshold_auto_pause,
            "auto_pause_delay_minutes": config.monitoring.auto_pause_delay_minutes,
            "cooldown_minutes": config.monitoring.cooldown_minutes,
            "snooze_minutes": config.monitoring.snooze_minutes,
            "min_analysis_interval_seconds": config.monitoring.min_analysis_interval_seconds,
            "confirmation_window_minutes": config.monitoring.confirmation_window_minutes,
            "required_issue_consistency": config.monitoring.required_issue_consistency,
        },
        "safety": {
            "require_recent_frame_seconds": config.safety.require_recent_frame_seconds,
            "require_printer_still_printing": config.safety.require_printer_still_printing,
            "require_issue_reconfirmation_before_pause": (
                config.safety.require_issue_reconfirmation_before_pause
            ),
            "prevent_duplicate_pause": config.safety.prevent_duplicate_pause,
        },
        "camera": {
            "stale_after_seconds": config.camera.stale_after_seconds,
            "capture_timeout_seconds": config.camera.capture_timeout_seconds,
            "retry_count": config.camera.retry_count,
            "retry_backoff_seconds": config.camera.retry_backoff_seconds,
            "fallback_snapshot_url": config.camera.fallback_snapshot_url,
        },
        "notifications": {
            "enabled": config.notifications.enabled,
            "quiet_hours_enabled": config.notifications.quiet_hours_enabled,
            "quiet_hours_start": config.notifications.quiet_hours_start,
            "quiet_hours_end": config.notifications.quiet_hours_end,
            "notify_on_low": config.notifications.notify_on_low,
            "notify_on_medium": config.notifications.notify_on_medium,
            "notify_on_high": config.notifications.notify_on_high,
            "notify_on_critical": config.notifications.notify_on_critical,
        },
        "model": {
            "provider": config.model.provider,
            "model_path": config.model.model_path,
            "options_path": config.model.options_path,
            "prototypes_path": config.model.prototypes_path,
            "auto_download": config.model.auto_download,
            "models_dir": config.model.models_dir,
            "device": config.model.device,
            "max_inference_timeout_seconds": config.model.max_inference_timeout_seconds,
        },
        "security": {
            "action_token": config.security.action_token,
            "action_signing_secret": config.security.action_signing_secret,
            "action_token_ttl_hours": config.security.action_token_ttl_hours,
        },
        "retention": {
            "keep_images_days": config.retention.keep_images_days,
            "keep_events_days": config.retention.keep_events_days,
            "keep_clear_captures_hours": config.retention.keep_clear_captures_hours,
            "keep_event_captures_days": config.retention.keep_event_captures_days,
            "max_capture_storage_mb": config.retention.max_capture_storage_mb,
        },
        "logging": {
            "json_logs": config.logging.json_logs,
            "log_level": config.logging.log_level,
        },
        "proxy": {
            "forwarded_headers": config.proxy.forwarded_headers,
            "trusted_hosts": config.proxy.trusted_hosts,
        },
    }

    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config_dict, f, default_flow_style=False)

    logger.info(f"Configuration saved to {CONFIG_FILE}")
