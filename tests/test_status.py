"""Test shared event status rules."""

from app.event_status import is_active_event_status


def test_only_actionable_events_are_active():
    assert is_active_event_status("active") is True
    assert is_active_event_status("pending_pause") is True
    assert is_active_event_status("ignored") is False
    assert is_active_event_status("snoozed") is False
    assert is_active_event_status("paused") is False
    assert is_active_event_status("resolved") is False
