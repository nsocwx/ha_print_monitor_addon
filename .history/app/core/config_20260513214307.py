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
CONFIG_FILE = DATA_DIR / "config.yaml"


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
    printing_states: List[str] = ["printing", "paused"]
    pause_service: PauseServiceConfig = Field(default_factory=PauseServiceConfig)
    notify_services: List[str] = Field(default_factory=lambda: ["notify.mobile_app_phone"])


class MonitoringConfig(BaseSettings):
    """Configuration for monitoring behavior."""
    enabled: bool = True
    frame_interval_seconds: int = 30
    confirmation_frames: int = 2
    detection_threshold: float = 0.5
    certainty_threshold_notify: float = 0.7
    certainty_threshold_auto_pause: float = 0.85
    auto_pause_delay_minutes: int = 15
    snooze_minutes: int = 15


class ModelConfig(BaseSettings):
    """Configuration for image analysis model."""
    model_config = {"protected_namespaces": ("settings_",)}
    provider: str = "onnx"
    model_path: Optional[str] = None
    device: str = "cpu"


class SecurityConfig(BaseSettings):
    """Configuration for security."""
    action_token: str = "change-me-in-production"


class RetentionConfig(BaseSettings):
    """Configuration for data retention."""
    keep_images_days: int = 7
    keep_events_days: int = 30


class AppConfig(BaseSettings):
    """Main application configuration."""
    app_base_url: str = "http://localhost:8080"
    home_assistant: HomeAssistantConfig = Field(default_factory=HomeAssistantConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)

    class Config:
        env_file = str(DATA_DIR / ".env")

    @field_validator("home_assistant", mode="before")
    @classmethod
    def load_ha_config(cls, v):
        if isinstance(v, dict):
            return HomeAssistantConfig(**v)
        return v

    @field_validator("monitoring", mode="before")
    @classmethod
    def load_monitoring_config(cls, v):
        if isinstance(v, dict):
            return MonitoringConfig(**v)
        return v

    @field_validator("model", mode="before")
    @classmethod
    def load_model_config(cls, v):
        if isinstance(v, dict):
            return ModelConfig(**v)
        return v

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


def load_config() -> AppConfig:
    """Load configuration from YAML file and environment variables."""
    # Create data directory if needed
    DATA_DIR.mkdir(parents=True, exist_ok=True)

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

    if detection_threshold := os.getenv("DETECTION_THRESHOLD"):
        try:
            config.monitoring.detection_threshold = float(detection_threshold)
        except ValueError:
            logger.warning(f"Invalid DETECTION_THRESHOLD: {detection_threshold}")

    if action_token := os.getenv("ACTION_TOKEN"):
        config.security.action_token = action_token

    return config


def save_config(config: AppConfig) -> None:
    """Save configuration to YAML file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    config_dict = {
        "app_base_url": config.app_base_url,
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
        "monitoring": {
            "enabled": config.monitoring.enabled,
            "frame_interval_seconds": config.monitoring.frame_interval_seconds,
            "confirmation_frames": config.monitoring.confirmation_frames,
            "detection_threshold": config.monitoring.detection_threshold,
            "certainty_threshold_notify": config.monitoring.certainty_threshold_notify,
            "certainty_threshold_auto_pause": config.monitoring.certainty_threshold_auto_pause,
            "auto_pause_delay_minutes": config.monitoring.auto_pause_delay_minutes,
            "snooze_minutes": config.monitoring.snooze_minutes,
        },
        "security": {
            "action_token": config.security.action_token,
        },
        "retention": {
            "keep_images_days": config.retention.keep_images_days,
            "keep_events_days": config.retention.keep_events_days,
        },
    }

    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config_dict, f, default_flow_style=False)

    logger.info(f"Configuration saved to {CONFIG_FILE}")
