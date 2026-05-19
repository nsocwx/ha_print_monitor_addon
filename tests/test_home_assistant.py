"""Test Home Assistant service call payloads."""

import pytest

from app.services.home_assistant import HAService


@pytest.mark.asyncio
async def test_call_service_sends_entity_id_as_service_data(monkeypatch):
    service = HAService("http://supervisor/core", "token")
    captured = {}

    class FakeResponse:
        def json(self):
            return {"ok": True}

    async def fake_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs["json"]
        return FakeResponse()

    monkeypatch.setattr(service, "_request", fake_request)

    response = await service.call_service(
        "button",
        "press",
        target={"entity_id": "button.octoprint_pause_job"},
        service_data={"extra": "value"},
    )

    assert response == {"ok": True}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/services/button/press"
    assert captured["json"] == {
        "extra": "value",
        "entity_id": "button.octoprint_pause_job",
    }
