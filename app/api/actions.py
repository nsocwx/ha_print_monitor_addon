"""API routes for operator and notification actions."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.schemas import ActionResponse
from app.core.config import AppConfig, load_config
from app.core.database import get_session
from app.models.event import PrinterEvent
from app.security import ActionTokenError, create_action_token, verify_action_token
from app.services.home_assistant import HAService, HomeAssistantAuthError, HomeAssistantError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/actions", tags=["actions"])

PROTECTED_ACTIONS = {"pause", "acknowledge", "snooze", "ignore"}


class TokenResponse(BaseModel):
    """Response containing a short-lived one-time action token."""

    token: str
    expires_in_hours: int


def get_app_config() -> AppConfig:
    """Load current application config for action routes."""
    return load_config()


def _consume_action_token(
    action: str,
    token: str,
    session: Session,
    config: AppConfig,
) -> PrinterEvent:
    try:
        claims = verify_action_token(token, action, config, session)
    except ActionTokenError as exc:
        logger.warning("Rejected %s action token: %s", action, exc)
        raise HTTPException(status_code=401, detail=str(exc)) from None

    event = session.exec(
        select(PrinterEvent).where(PrinterEvent.event_id == claims.event_id)
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.printer_id != claims.printer_id:
        raise HTTPException(status_code=403, detail="Action token does not match event")
    return event


@router.post("/token", response_model=TokenResponse)
def create_dashboard_action_token(
    event_id: str = Query(...),
    action: str = Query(...),
    session: Session = Depends(get_session),
    config: AppConfig = Depends(get_app_config),
) -> TokenResponse:
    """Create a short-lived one-time action token for the ingress dashboard."""
    if action not in PROTECTED_ACTIONS:
        raise HTTPException(status_code=400, detail="Unsupported action")

    event = session.exec(
        select(PrinterEvent).where(PrinterEvent.event_id == event_id)
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    token = create_action_token(config, event.event_id, action, event.printer_id)
    return TokenResponse(
        token=token,
        expires_in_hours=config.security.action_token_ttl_hours,
    )


@router.post("/test-notification", response_model=ActionResponse)
async def send_test_notification(
    printer_id: Optional[str] = Query(None),
    config: AppConfig = Depends(get_app_config),
) -> ActionResponse:
    """Send a safe test notification through the selected printer route."""
    printer = config.get_printer(printer_id) if printer_id else config.get_printers()[0]
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    ha_service = HAService(
        config.home_assistant.url,
        config.home_assistant.token,
        timeout_seconds=config.camera.capture_timeout_seconds,
    )
    notify_services = printer.notify_services or config.home_assistant.notify_services
    for notify_service in notify_services:
        await ha_service.send_notification(
            service=notify_service,
            title=f"HA Print Monitor Test: {printer.name}",
            message="Test notification delivered. No printer action was taken.",
        )
    return ActionResponse(
        success=True,
        action="test-notification",
        event_id="none",
        message="Test notification sent",
    )


async def _ensure_pause_is_safe(
    event: PrinterEvent,
    config: AppConfig,
    session: Session,
    auto_pause: bool = False,
) -> tuple[bool, str]:
    """Return whether a pause may proceed, recording the decision on the event."""
    event.pause_attempted_at = datetime.utcnow()

    if config.safety.prevent_duplicate_pause and event.pause_result == "success":
        event.pause_result = "skipped"
        event.pause_failure_reason = "pause already executed for this event"
        session.add(event)
        session.commit()
        return False, event.pause_failure_reason

    printer = config.get_printer(event.printer_id)
    if not printer:
        event.pause_result = "skipped"
        event.pause_failure_reason = "printer is no longer configured"
        session.add(event)
        session.commit()
        return False, event.pause_failure_reason

    if config.safety.require_recent_frame_seconds:
        latest_seen = event.last_seen_at or event.updated_at
        age = (datetime.utcnow() - latest_seen).total_seconds()
        if age > config.safety.require_recent_frame_seconds:
            event.pause_result = "skipped"
            event.pause_failure_reason = "latest issue frame is stale"
            session.add(event)
            session.commit()
            return False, event.pause_failure_reason

    if config.safety.require_printer_still_printing:
        ha_service = HAService(
            config.home_assistant.url,
            config.home_assistant.token,
            timeout_seconds=config.camera.capture_timeout_seconds,
        )
        try:
            state_response = await ha_service.get_state(printer.printer_state_entity)
            current_state = (state_response.get("state") or "").strip().lower()
            configured = {state.strip().lower() for state in printer.printing_states}
            if current_state not in configured or not current_state.startswith("printing"):
                event.pause_result = "skipped"
                event.pause_failure_reason = (
                    f"printer state changed before pause: {current_state or 'unknown'}"
                )
                session.add(event)
                session.commit()
                return False, event.pause_failure_reason
        except HomeAssistantAuthError:
            event.pause_result = "skipped"
            event.pause_failure_reason = "Home Assistant authentication failed"
            session.add(event)
            session.commit()
            return False, event.pause_failure_reason
        except HomeAssistantError:
            event.pause_result = "skipped"
            event.pause_failure_reason = "Home Assistant is unreachable"
            session.add(event)
            session.commit()
            return False, event.pause_failure_reason

    if auto_pause:
        threshold = (
            printer.certainty_threshold_auto_pause
            if printer.certainty_threshold_auto_pause is not None
            else config.monitoring.certainty_threshold_auto_pause
        )
        if event.certainty < threshold:
            event.pause_result = "skipped"
            event.pause_failure_reason = "event certainty below auto-pause threshold"
            session.add(event)
            session.commit()
            return False, event.pause_failure_reason
        if event.severity not in ("high", "critical"):
            event.pause_result = "skipped"
            event.pause_failure_reason = "event severity below auto-pause threshold"
            session.add(event)
            session.commit()
            return False, event.pause_failure_reason

    return True, "pause safety checks passed"


async def _pause_event(
    event: PrinterEvent,
    config: AppConfig,
    session: Session,
    auto_pause: bool = False,
) -> ActionResponse:
    safe, reason = await _ensure_pause_is_safe(event, config, session, auto_pause=auto_pause)
    if not safe:
        event.status = "auto_pause_skipped" if auto_pause else event.status
        event.add_action("pause_skipped", {"reason": reason, "auto_pause": auto_pause})
        session.add(event)
        session.commit()
        return ActionResponse(
            success=False,
            action="pause",
            event_id=event.event_id,
            message=f"Pause skipped: {reason}",
        )

    printer = config.get_printer(event.printer_id) or config.get_printers()[0]
    ha_service = HAService(
        config.home_assistant.url,
        config.home_assistant.token,
        timeout_seconds=config.camera.capture_timeout_seconds,
    )

    try:
        await ha_service.call_service(
            domain=printer.pause_service.domain,
            service=printer.pause_service.service,
            target={"entity_id": printer.pause_service.target},
            service_data=printer.pause_service.data,
        )
    except Exception as exc:
        event.pause_result = "failed"
        event.pause_failure_reason = "Home Assistant pause service failed"
        event.add_action("pause_failed", {"reason": event.pause_failure_reason})
        session.add(event)
        session.commit()
        logger.error("Failed to pause event %s: %s", event.event_id, exc)
        raise HTTPException(status_code=502, detail="Pause service failed") from None

    event.status = "paused"
    event.auto_paused = auto_pause
    event.auto_pause_at = datetime.utcnow() if auto_pause else event.auto_pause_at
    event.pause_result = "success"
    event.pause_failure_reason = None
    event.user_action = "pause"
    event.user_action_at = datetime.utcnow()
    event.add_action("auto_paused" if auto_pause else "pause", {"reason": reason})
    session.add(event)
    session.commit()

    logger.warning("Print paused for event %s using safe pause path", event.event_id)
    return ActionResponse(
        success=True,
        action="pause",
        event_id=event.event_id,
        message="Print paused successfully",
    )


@router.post("/pause", response_model=ActionResponse)
async def pause_print(
    token: str = Query(...),
    session: Session = Depends(get_session),
    config: AppConfig = Depends(get_app_config),
) -> ActionResponse:
    """Pause the printer using a signed one-time action token."""
    event = _consume_action_token("pause", token, session, config)
    return await _pause_event(event, config, session, auto_pause=False)


@router.get("/pause", response_model=ActionResponse)
async def pause_print_from_notification(
    token: str = Query(...),
    session: Session = Depends(get_session),
    config: AppConfig = Depends(get_app_config),
) -> ActionResponse:
    """Notification-compatible GET action."""
    return await pause_print(token=token, session=session, config=config)


@router.post("/ignore", response_model=ActionResponse)
def ignore_event(
    token: str = Query(...),
    session: Session = Depends(get_session),
    config: AppConfig = Depends(get_app_config),
) -> ActionResponse:
    """Ignore a print issue."""
    event = _consume_action_token("ignore", token, session, config)
    event.status = "ignored"
    event.auto_pause_deadline = None
    event.user_action = "ignore"
    event.user_action_at = datetime.utcnow()
    event.add_action("ignore")
    session.add(event)
    session.commit()
    return ActionResponse(success=True, action="ignore", event_id=event.event_id, message="Event ignored")


@router.get("/ignore", response_model=ActionResponse)
def ignore_event_from_notification(
    token: str = Query(...),
    session: Session = Depends(get_session),
    config: AppConfig = Depends(get_app_config),
) -> ActionResponse:
    """Notification-compatible GET action."""
    return ignore_event(token=token, session=session, config=config)


@router.post("/snooze", response_model=ActionResponse)
def snooze_event(
    minutes: int = Query(15),
    token: str = Query(...),
    session: Session = Depends(get_session),
    config: AppConfig = Depends(get_app_config),
) -> ActionResponse:
    """Snooze notifications for an event."""
    event = _consume_action_token("snooze", token, session, config)
    event.status = "snoozed"
    event.snoozed_until = datetime.utcnow() + timedelta(minutes=minutes)
    event.auto_pause_deadline = None
    event.user_action = "snooze"
    event.user_action_at = datetime.utcnow()
    event.add_action("snooze", {"minutes": minutes, "until": event.snoozed_until.isoformat()})
    session.add(event)
    session.commit()
    return ActionResponse(
        success=True,
        action="snooze",
        event_id=event.event_id,
        message=f"Event snoozed for {minutes} minutes",
    )


@router.get("/snooze", response_model=ActionResponse)
def snooze_event_from_notification(
    minutes: int = Query(15),
    token: str = Query(...),
    session: Session = Depends(get_session),
    config: AppConfig = Depends(get_app_config),
) -> ActionResponse:
    """Notification-compatible GET action."""
    return snooze_event(minutes=minutes, token=token, session=session, config=config)


@router.post("/acknowledge", response_model=ActionResponse)
def acknowledge_event(
    token: str = Query(...),
    session: Session = Depends(get_session),
    config: AppConfig = Depends(get_app_config),
) -> ActionResponse:
    """Acknowledge an event without ignoring it."""
    event = _consume_action_token("acknowledge", token, session, config)
    event.status = "acknowledged"
    event.auto_pause_deadline = None
    event.user_action = "acknowledge"
    event.user_action_at = datetime.utcnow()
    event.add_action("acknowledge")
    session.add(event)
    session.commit()
    return ActionResponse(
        success=True,
        action="acknowledge",
        event_id=event.event_id,
        message="Event acknowledged",
    )


@router.get("/acknowledge", response_model=ActionResponse)
def acknowledge_event_from_notification(
    token: str = Query(...),
    session: Session = Depends(get_session),
    config: AppConfig = Depends(get_app_config),
) -> ActionResponse:
    """Notification-compatible GET action."""
    return acknowledge_event(token=token, session=session, config=config)
