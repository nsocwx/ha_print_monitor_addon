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
    printer_id: str = Field(default="default", index=True)
    printer_name: str = Field(default="Default Printer")
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
    first_seen_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    last_seen_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    notification_sent_at: Optional[datetime] = None
    user_action: Optional[str] = None
    user_action_at: Optional[datetime] = None
    pause_attempted_at: Optional[datetime] = None
    pause_result: Optional[str] = None
    pause_failure_reason: Optional[str] = None

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
    printer_id: str = Field(default="default", index=True)
    printer_name: str = Field(default="Default Printer")
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    file_path: str
    file_size: int
    event_id: Optional[str] = None  # Link to PrinterEvent if related


class AnalysisResult(SQLModel, table=True):
    """Model for storing recent analyzer results, including clear frames."""
    __tablename__ = "analysis_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    printer_id: str = Field(default="default", index=True)
    printer_name: str = Field(default="Default Printer")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    result: str
    issue_type: Optional[str] = None
    certainty: float = 0.0
    severity: str = "low"
    explanation: str = ""
    image_path: Optional[str] = None
    annotated_image_path: Optional[str] = None
    raw_model_output_json: Optional[str] = None
    inference_duration_ms: Optional[float] = None


class ActionTokenNonce(SQLModel, table=True):
    """Used one-time notification action token nonce."""
    __tablename__ = "action_token_nonces"

    id: Optional[int] = Field(default=None, primary_key=True)
    nonce: str = Field(unique=True, index=True)
    event_id: str = Field(index=True)
    action: str
    printer_id: str = Field(index=True)
    expires_at: datetime
    used_at: datetime = Field(default_factory=datetime.utcnow)


class SystemLog(SQLModel, table=True):
    """Model for storing system events and logs."""
    __tablename__ = "system_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str  # INFO, WARNING, ERROR, DEBUG
    component: str
    message: str
    details: Optional[str] = None
