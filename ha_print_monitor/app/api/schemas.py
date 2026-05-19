"""API response schemas."""
from pydantic import BaseModel
from pydantic import field_serializer
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


class TimestampedResponse(BaseModel):
    """Base response that serializes naive app datetimes as UTC."""

    model_config = {"protected_namespaces": ()}

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_datetimes(self, value):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.isoformat().replace("+00:00", "Z")
        return value


class EventResponse(TimestampedResponse):
    """Response for event data."""
    id: int
    event_id: str
    printer_id: str
    printer_name: str
    created_at: datetime
    updated_at: datetime
    printer_state: str
    issue_type: Optional[str]
    certainty: float
    severity: str
    explanation: str
    status: str
    recommended_action: str
    image_path: Optional[str]
    annotated_image_path: Optional[str]
    auto_pause_deadline: Optional[datetime]
    auto_paused: bool
    snoozed_until: Optional[datetime]
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    notification_sent_at: Optional[datetime] = None
    user_action: Optional[str] = None
    user_action_at: Optional[datetime] = None
    pause_attempted_at: Optional[datetime] = None
    pause_result: Optional[str] = None
    pause_failure_reason: Optional[str] = None


class StatusResponse(TimestampedResponse):
    """Response for current status."""
    app_version: str
    printer_id: str
    printer_name: str
    running: bool
    monitoring_enabled: bool
    printer_state: Optional[str]
    print_progress: Optional[float] = None
    printer_printing: bool
    last_capture_time: Optional[datetime]
    last_capture_image_url: Optional[str]
    last_capture_status: str
    last_capture_error: Optional[str]
    last_successful_capture_time: Optional[datetime] = None
    capture_success_count: int = 0
    capture_failure_count: int = 0
    camera_stale: bool = False
    last_analysis_time: Optional[datetime]
    latest_analysis_result: Optional[Dict[str, Any]]
    last_analysis_error: Optional[str] = None
    last_inference_duration_ms: Optional[float] = None
    model_status: str = "unknown"
    active_event: Optional[EventResponse]
    health_status: str


class PrinterStatusResponse(TimestampedResponse):
    """Summary status for one configured printer."""
    printer_id: str
    printer_name: str
    camera_entity: str
    printer_state_entity: str
    print_progress_entity: Optional[str] = None
    running: bool
    monitoring_enabled: bool
    printer_state: Optional[str]
    print_progress: Optional[float] = None
    printer_printing: bool
    last_capture_time: Optional[datetime]
    last_capture_image_url: Optional[str]
    last_capture_status: str
    last_capture_error: Optional[str]
    last_successful_capture_time: Optional[datetime] = None
    capture_success_count: int = 0
    capture_failure_count: int = 0
    camera_stale: bool = False
    last_analysis_time: Optional[datetime]
    latest_analysis_result: Optional[Dict[str, Any]]
    last_analysis_error: Optional[str] = None
    last_inference_duration_ms: Optional[float] = None
    model_status: str = "unknown"
    active_event: Optional[EventResponse]


class AnalysisResultResponse(TimestampedResponse):
    """Response for one analyzer history row."""
    id: Optional[int]
    printer_id: str
    created_at: datetime
    result: str
    issue_type: Optional[str]
    certainty: float
    severity: str
    explanation: str
    image_url: Optional[str]
    annotated_image_url: Optional[str]


class ConfigResponse(BaseModel):
    """Response for configuration."""

    app_base_url: str
    timezone: str
    home_assistant_url: str
    camera_entity: str
    printer_state_entity: str
    print_progress_entity: Optional[str] = None
    selected_printer: Dict[str, Any]
    analyzer_provider: str
    analyzer_device: str
    frame_interval_seconds: int
    confirmation_frames: int
    certainty_threshold_notify: float
    auto_pause_enabled: bool
    certainty_threshold_auto_pause: float
    auto_pause_delay_minutes: int
    cooldown_minutes: int
    printers: List[Dict[str, Any]]
    safety: Dict[str, Any] = {}
    camera: Dict[str, Any] = {}
    notifications: Dict[str, Any] = {}
    retention: Dict[str, Any] = {}


class ActionResponse(BaseModel):
    """Response for action."""
    success: bool
    action: str
    event_id: str
    message: str


class HealthResponse(BaseModel):
    """Response for health check."""
    status: str  # healthy, degraded, unhealthy
    database: str
    home_assistant: str
    analyzer: str
    addon: str = "unknown"
    uptime_seconds: float
    app_version: str = "unknown"
    build_date: str = "unknown"
    git_commit: str = "unknown"
