"""Test retention cleanup behavior."""
import asyncio
from datetime import datetime, timedelta

from sqlmodel import SQLModel, Session, create_engine, select

from app.core.config import AppConfig
from app.models.event import CameraCapture, PrinterEvent
from app import maintenance


def make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_event_capture_retention_removes_media_copy(tmp_path, monkeypatch):
    config = AppConfig()
    config.retention.keep_event_captures_days = 1
    config.retention.keep_events_days = 90
    session = make_session()
    media_dir = tmp_path / "media"
    monkeypatch.setattr(maintenance, "MEDIA_NOTIFICATION_DIR", media_dir)

    capture_path = tmp_path / "event_1.jpg"
    media_path = media_dir / "event_1.jpg"
    capture_path.write_bytes(b"capture")
    media_dir.mkdir()
    media_path.write_bytes(b"media")
    old = datetime.utcnow() - timedelta(days=2)

    event = PrinterEvent(
        event_id="event_1",
        printer_id="printer_1",
        printer_name="Printer 1",
        printer_state="printing",
        printer_state_at=old,
        issue_type="spaghetti_failure",
        certainty=0.9,
        severity="high",
        explanation="Old event image",
        image_path=str(capture_path),
        recommended_action="notify",
        created_at=old,
    )
    capture = CameraCapture(
        capture_id="capture_1",
        printer_id="printer_1",
        printer_name="Printer 1",
        captured_at=old,
        file_path=str(capture_path),
        file_size=len(b"capture"),
        event_id="event_1",
    )
    session.add(event)
    session.add(capture)
    session.commit()

    asyncio.run(maintenance.cleanup_old_data(config, session))

    updated_event = session.exec(
        select(PrinterEvent).where(PrinterEvent.event_id == "event_1")
    ).one()
    remaining_capture = session.exec(select(CameraCapture)).first()
    assert updated_event.image_path is None
    assert remaining_capture is None
    assert not capture_path.exists()
    assert not media_path.exists()
