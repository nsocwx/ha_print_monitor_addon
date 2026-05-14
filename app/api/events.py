"""API routes for events."""
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, desc
from app.models.event import PrinterEvent
from app.core.database import get_session
from app.api.schemas import EventResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=List[EventResponse])
def list_events(
    session: Session = Depends(get_session),
    limit: int = Query(50, ge=1, le=500),
    status: Optional[str] = None,
) -> List[EventResponse]:
    """Get list of events."""
    query = select(PrinterEvent).order_by(desc(PrinterEvent.created_at))

    if status:
        query = query.where(PrinterEvent.status == status)

    query = query.limit(limit)
    events = session.exec(query).all()

    return [EventResponse(**event.dict()) for event in events]


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: str, session: Session = Depends(get_session)) -> EventResponse:
    """Get a specific event."""
    event = session.exec(
        select(PrinterEvent).where(PrinterEvent.event_id == event_id)
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return EventResponse(**event.dict())


@router.get("/active/current", response_model=Optional[EventResponse])
def get_active_event(session: Session = Depends(get_session)) -> Optional[EventResponse]:
    """Get current active event."""
    event = session.exec(
        select(PrinterEvent)
        .where(PrinterEvent.status == "active")
        .order_by(desc(PrinterEvent.created_at))
    ).first()

    if not event:
        return None

    return EventResponse(**event.dict())
