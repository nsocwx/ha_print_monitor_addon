"""API routes for events."""
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, desc
from app.models.event import PrinterEvent
from app.core.database import get_session
from app.api.schemas import EventResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


class ClearEventsResponse(BaseModel):
    """Response for clearing event history."""
    deleted: int
    printer_id: Optional[str] = None


@router.get("", response_model=List[EventResponse])
def list_events(
    session: Session = Depends(get_session),
    limit: int = Query(50, ge=1, le=500),
    status: Optional[str] = None,
    printer_id: Optional[str] = None,
) -> List[EventResponse]:
    """Get list of events."""
    query = select(PrinterEvent).order_by(desc(PrinterEvent.created_at))

    if status:
        query = query.where(PrinterEvent.status == status)
    if printer_id:
        query = query.where(PrinterEvent.printer_id == printer_id)

    query = query.limit(limit)
    events = session.exec(query).all()

    return [EventResponse(**event.dict()) for event in events]


@router.post("/clear", response_model=ClearEventsResponse)
def clear_events(
    session: Session = Depends(get_session),
    printer_id: Optional[str] = None,
) -> ClearEventsResponse:
    """Clear event history, optionally for one printer."""
    query = select(PrinterEvent)
    if printer_id:
        query = query.where(PrinterEvent.printer_id == printer_id)

    events_to_delete = session.exec(query).all()
    for event in events_to_delete:
        session.delete(event)
    session.commit()

    return ClearEventsResponse(deleted=len(events_to_delete), printer_id=printer_id)


@router.get("/active/current", response_model=Optional[EventResponse])
def get_active_event(
    session: Session = Depends(get_session),
    printer_id: Optional[str] = None,
) -> Optional[EventResponse]:
    """Get current active event."""
    query = select(PrinterEvent).where(PrinterEvent.status == "active")
    if printer_id:
        query = query.where(PrinterEvent.printer_id == printer_id)
    event = session.exec(query.order_by(desc(PrinterEvent.created_at))).first()

    if not event:
        return None

    return EventResponse(**event.dict())


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: str, session: Session = Depends(get_session)) -> EventResponse:
    """Get a specific event."""
    event = session.exec(
        select(PrinterEvent).where(PrinterEvent.event_id == event_id)
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return EventResponse(**event.dict())
