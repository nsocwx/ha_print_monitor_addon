"""Database models using SQLModel."""
from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, Column, String
import json


class PrinterEvent(SQLModel, table=True):
    """Model for storing detection events."""
    __tablename__ = "printer_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Printer context
    printer_state: str  # e.g., "printing", "paused"
    printer_state_at: datetime

    # Detection details
    issue_type: str  # e.g., "spaghetti_failure"
    certainty: float  # 0.0 to 1.0
    severity: str  # low, medium, high, critical
    explanation: str

    # Images
    image_path: Optional[str] = None
    annotated_image_path: Optional[str] = None

    # Status tracking
    status: str = Field(default="active")  # active, acknowledged, ignored, snoozed, paused, resolved
    recommended_action: str  # continue, notify, pause

    # Auto-pause tracking
    auto_pause_deadline: Optional[datetime] = None
    auto_paused: bool = False
    auto_pause_at: Optional[datetime] = None

    # User actions (stored as JSON string)
    action_history_json: str = Field(default_factory=lambda: json.dumps([]))

    # Snooze info
    snoozed_until: Optional[datetime] = None

    @property
    def action_history(self) -> List[dict]:
        return json.loads(self.action_history_json)

    @action_history.setter
    def action_history(self, value: List[dict]):
        self.action_history_json = json.dumps(value)

    def add_action(self, action: str, details: Optional[dict] = None):
        """Add an action to history."""
        history = self.action_history
        history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "details": details or {},
        })
        self.action_history = history
        self.updated_at = datetime.utcnow()


class CameraCapture(SQLModel, table=True):
    """Model for storing camera captures."""
    __tablename__ = "camera_captures"

    id: Optional[int] = Field(default=None, primary_key=True)
    capture_id: str = Field(unique=True, index=True)
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    file_path: str
    file_size: int
    event_id: Optional[str] = None  # Link to PrinterEvent if related


class SystemLog(SQLModel, table=True):
    """Model for storing system events and logs."""
    __tablename__ = "system_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str  # INFO, WARNING, ERROR, DEBUG
    component: str
    message: str
    details: Optional[str] = None
