"""Test configuration loading."""
import pytest
from pathlib import Path
from app.core.config import AppConfig, load_config, save_config


def test_load_config_defaults():
    """Test loading config with defaults."""
    config = AppConfig()
    assert config.app_base_url == ""
    assert config.monitoring.enabled is True
    assert config.monitoring.frame_interval_seconds == 30


def test_config_serialization():
    """Test config can be serialized."""
    config = AppConfig()
    config.external_base_url = "https://example.ui"

    assert config.home_assistant.url == "http://supervisor/core/api"
    assert config.external_base_url == "https://example.ui"


def test_pause_service_config():
    """Test pause service configuration."""
    config = AppConfig()
    config.home_assistant.pause_service.domain = "button"
    config.home_assistant.pause_service.service = "press"
    config.home_assistant.pause_service.target = "button.pause"
    
    assert config.home_assistant.pause_service.domain == "button"
    assert config.home_assistant.pause_service.target == "button.pause"


def test_monitoring_thresholds():
    """Test monitoring threshold configuration."""
    config = AppConfig()
    
    assert config.monitoring.certainty_threshold_notify == 0.7
    assert config.monitoring.certainty_threshold_auto_pause == 0.85
    assert config.monitoring.auto_pause_delay_minutes == 15
    assert config.safety.require_printer_still_printing is True
    assert config.camera.stale_after_seconds == 120
    assert config.notifications.notify_on_high is True
    assert config.retention.max_capture_storage_mb == 2048


def test_security_config():
    """Test security configuration."""
    config = AppConfig()
    config.security.action_token_expiration_hours = 12
    
    assert config.security.action_token_ttl_hours == 12
