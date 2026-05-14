"""Test event creation and management."""
import pytest
from datetime import datetime
from app.models.event import PrinterEvent


def test_create_event():
    """Test creating an event."""
    event = PrinterEvent(
        event_id="test_1",
        printer_state="printing",
        printer_state_at=datetime.utcnow(),
        issue_type="spaghetti_failure",
        certainty=0.9,
        severity="high",
        explanation="Detected spaghetti failure",
        status="active",
        recommended_action="notify",
    )
    
    assert event.event_id == "test_1"
    assert event.issue_type == "spaghetti_failure"
    assert event.certainty == 0.9
    assert event.severity == "high"
    assert event.status == "active"


def test_event_action_history():
    """Test adding actions to event."""
    event = PrinterEvent(
        event_id="test_2",
        printer_state="printing",
        printer_state_at=datetime.utcnow(),
        issue_type="blob_detection",
        certainty=0.75,
        severity="medium",
        explanation="Blob detected",
        status="active",
        recommended_action="notify",
    )
    
    # Add action
    event.add_action("user_pause", {"reason": "manual"})
    
    # Check history
    history = event.action_history
    assert len(history) == 1
    assert history[0]["action"] == "user_pause"
    assert history[0]["details"]["reason"] == "manual"
    
    # Add another action
    event.add_action("acknowledged")
    assert len(event.action_history) == 2


def test_event_status_transitions():
    """Test event status transitions."""
    event = PrinterEvent(
        event_id="test_3",
        printer_state="printing",
        printer_state_at=datetime.utcnow(),
        issue_type="layer_shift",
        certainty=0.8,
        severity="high",
        explanation="Layer shift detected",
        status="active",
        recommended_action="notify",
    )
    
    assert event.status == "active"
    
    event.status = "acknowledged"
    assert event.status == "acknowledged"
    
    event.status = "ignored"
    assert event.status == "ignored"
    
    event.status = "resolved"
    assert event.status == "resolved"
