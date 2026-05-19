"""Shared event status rules."""

ACTIVE_EVENT_STATUSES = {"active", "pending_pause"}


def is_active_event_status(status: str) -> bool:
    """Return true when an event should be shown as the active issue."""
    return status in ACTIVE_EVENT_STATUSES
