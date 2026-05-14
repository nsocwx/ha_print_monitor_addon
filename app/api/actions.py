"""API routes for actions."""
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from app.core.config import AppConfig, load_config
from app.core.database import get_session
from app.models.event import PrinterEvent
from app.api.schemas import ActionResponse
from app.services.home_assistant import HAService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/actions", tags=["actions"])


def get_app_config() -> AppConfig:
    """Load current application config for action routes."""
    return load_config()


def verify_action_token(token: str, config: AppConfig) -> bool:
    """Verify action token."""
    return token == config.security.action_token


@router.post("/pause", response_model=ActionResponse)
async def pause_print(
    event_id: str = Query(...),
    token: str = Query(...),
    session: Session = Depends(get_session),
    config: AppConfig = Depends(get_app_config),
) -> ActionResponse:
    """Pause the printer."""
    if not verify_action_token(token, config):
        raise HTTPException(status_code=401, detail="Invalid token")

    # Find event
    event = session.exec(
        select(PrinterEvent).where(PrinterEvent.event_id == event_id)
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    try:
        # Call Home Assistant service
        ha_service = HAService(config.home_assistant.url, config.home_assistant.token)
        printer = config.get_printer(event.printer_id) or config.get_printers()[0]

        await ha_service.call_service(
            domain=printer.pause_service.domain,
            service=printer.pause_service.service,
            target={"entity_id": printer.pause_service.target},
            service_data=printer.pause_service.data,
        )

        # Update event
        event.status = "paused"
        event.auto_paused = False
        event.add_action("pause", {"timestamp": datetime.utcnow().isoformat()})
        session.add(event)
        session.commit()

        logger.info(f"Print paused for event {event_id}")

        return ActionResponse(
            success=True,
            action="pause",
            event_id=event_id,
            message="Print paused successfully"
        )

    except Exception as e:
        logger.error(f"Failed to pause print: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to pause: {str(e)}")


@router.post("/ignore", response_model=ActionResponse)
def ignore_event(
    event_id: str = Query(...),
    token: str = Query(...),
    session: Session = Depends(get_session),
    config: AppConfig = Depends(get_app_config),
) -> ActionResponse:
    """Ignore a print issue."""
    if not verify_action_token(token, config):
        raise HTTPException(status_code=401, detail="Invalid token")

    event = session.exec(
        select(PrinterEvent).where(PrinterEvent.event_id == event_id)
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event.status = "ignored"
    event.auto_pause_deadline = None
    event.add_action("ignore", {"timestamp": datetime.utcnow().isoformat()})
    session.add(event)
    session.commit()

    logger.info(f"Event {event_id} marked as ignored")

    return ActionResponse(
        success=True,
        action="ignore",
        event_id=event_id,
        message="Event ignored"
    )


@router.post("/snooze", response_model=ActionResponse)
def snooze_event(
    event_id: str = Query(...),
    minutes: int = Query(15),
    token: str = Query(...),
    session: Session = Depends(get_session),
    config: AppConfig = Depends(get_app_config),
) -> ActionResponse:
    """Snooze notifications for an event."""
    if not verify_action_token(token, config):
        raise HTTPException(status_code=401, detail="Invalid token")

    event = session.exec(
        select(PrinterEvent).where(PrinterEvent.event_id == event_id)
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event.status = "snoozed"
    event.snoozed_until = datetime.utcnow() + timedelta(minutes=minutes)
    event.auto_pause_deadline = None
    event.add_action("snooze", {"minutes": minutes, "until": event.snoozed_until.isoformat()})
    session.add(event)
    session.commit()

    logger.info(f"Event {event_id} snoozed for {minutes} minutes")

    return ActionResponse(
        success=True,
        action="snooze",
        event_id=event_id,
        message=f"Event snoozed for {minutes} minutes"
    )


@router.post("/acknowledge", response_model=ActionResponse)
def acknowledge_event(
    event_id: str = Query(...),
    token: str = Query(...),
    session: Session = Depends(get_session),
    config: AppConfig = Depends(get_app_config),
) -> ActionResponse:
    """Acknowledge an event without ignoring it."""
    if not verify_action_token(token, config):
        raise HTTPException(status_code=401, detail="Invalid token")

    event = session.exec(
        select(PrinterEvent).where(PrinterEvent.event_id == event_id)
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event.status = "acknowledged"
    event.auto_pause_deadline = None
    event.add_action("acknowledge", {"timestamp": datetime.utcnow().isoformat()})
    session.add(event)
    session.commit()

    logger.info(f"Event {event_id} acknowledged")

    return ActionResponse(
        success=True,
        action="acknowledge",
        event_id=event_id,
        message="Event acknowledged"
    )
