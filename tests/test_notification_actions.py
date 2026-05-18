"""Test Home Assistant mobile notification action handling."""
from datetime import datetime

import pytest

from app.core.config import AppConfig, PrinterConfig
from app.models.event import PrinterEvent
from app.security import create_action_token
from app.services import monitor as monitor_module
from app.services.monitor import PrintMonitorService
from app.services.notification_actions import (
    ACTION_PREFIX,
    build_notification_action,
    parse_notification_action,
)


class FakeHAService:
    def __init__(self):
        self.notifications = []

    async def send_notification(self, service, title, message, data=None):
        self.notifications.append(
            {
                "service": service,
                "title": title,
                "message": message,
                "data": data,
            }
        )
        return {}


def make_event(image_path="/data/captures/event_1.jpg") -> PrinterEvent:
    now = datetime.utcnow()
    return PrinterEvent(
        event_id="event_1",
        printer_id="printer_1",
        printer_name="Printer 1",
        printer_state="printing",
        printer_state_at=now,
        issue_type="spaghetti_failure",
        certainty=0.93,
        severity="high",
        explanation="Test issue",
        image_path=str(image_path),
        recommended_action="notify",
    )


def test_notification_action_round_trip():
    action_id = build_notification_action("pause", "signed.token")

    assert action_id == f"{ACTION_PREFIX}:pause:signed.token"
    assert parse_notification_action(action_id) == ("pause", "signed.token")
    assert parse_notification_action("OTHER:pause:signed.token") is None
    assert parse_notification_action(f"{ACTION_PREFIX}:acknowledge:signed.token") is None


@pytest.mark.asyncio
async def test_monitor_sends_native_actions_with_home_assistant_media_image(tmp_path, monkeypatch):
    config = AppConfig()
    config.security.action_signing_secret = "test-secret"
    config.monitoring.snooze_minutes = 20
    printer = PrinterConfig(
        id="printer_1",
        name="Printer 1",
        notify_services=["notify.mobile_app_phone"],
    )
    service = object.__new__(PrintMonitorService)
    service.config = config
    service.printer = printer
    service.printer_name = printer.name
    service.ha_service = FakeHAService()
    image_path = tmp_path / "event_1.jpg"
    image_path.write_bytes(b"fake-jpeg")
    media_dir = tmp_path / "media" / "ha_print_monitor"
    monkeypatch.setattr(monitor_module, "MEDIA_NOTIFICATION_DIR", media_dir)

    await service._send_notification(make_event(image_path), session=None)

    data = service.ha_service.notifications[0]["data"]
    assert data["image"] == "/media/local/ha_print_monitor/event_1.jpg"
    assert (media_dir / "event_1.jpg").read_bytes() == b"fake-jpeg"
    assert [action["title"] for action in data["actions"]] == [
        "Pause Print",
        "Ignore",
        "Snooze 20m",
    ]
    assert all(
        parse_notification_action(action["action"])
        for action in data["actions"]
    )


def test_notification_tokens_remain_verifiable_after_parsing():
    config = AppConfig()
    config.security.action_signing_secret = "test-secret"
    token = create_action_token(config, "event_1", "ignore", "printer_1")

    parsed = parse_notification_action(build_notification_action("ignore", token))

    assert parsed == ("ignore", token)
