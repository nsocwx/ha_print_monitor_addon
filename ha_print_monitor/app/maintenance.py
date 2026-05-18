"""Maintenance tasks for data retention."""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from sqlmodel import Session, select
from app.models.event import AnalysisResult, PrinterEvent, CameraCapture, SystemLog
from app.core.config import AppConfig

logger = logging.getLogger(__name__)

MEDIA_NOTIFICATION_DIR = Path("/media/ha_print_monitor")


async def cleanup_old_data(config: AppConfig, session: Session):
    """Clean up old events and images based on retention policy.

    Args:
        config: Application configuration
        session: Database session
    """
    now = datetime.utcnow()
    retention_config = config.retention

    # Cleanup old events
    cutoff_events = now - timedelta(days=retention_config.keep_events_days)
    old_events = session.exec(
        select(PrinterEvent).where(PrinterEvent.created_at < cutoff_events)
    ).all()

    deleted_count = 0
    for event in old_events:
        # Clean up associated images
        if event.image_path:
            try:
                _delete_capture_file_and_notification_media(event.image_path)
            except Exception as e:
                logger.warning(f"Failed to delete image {event.image_path}: {e}")

        if event.annotated_image_path:
            try:
                _delete_capture_file_and_notification_media(event.annotated_image_path)
            except Exception as e:
                logger.warning(f"Failed to delete annotated image: {e}")

        session.delete(event)
        deleted_count += 1

    if deleted_count > 0:
        session.commit()
        logger.info(f"Deleted {deleted_count} old events")

    cutoff_event_images = now - timedelta(days=retention_config.keep_event_captures_days)
    old_event_image_captures = session.exec(
        select(CameraCapture).where(
            CameraCapture.event_id != None,  # noqa: E711
            CameraCapture.captured_at < cutoff_event_images,
        )
    ).all()

    deleted_event_images = 0
    for capture in old_event_image_captures:
        try:
            _delete_capture_file_and_notification_media(capture.file_path)
            event = session.exec(
                select(PrinterEvent).where(PrinterEvent.event_id == capture.event_id)
            ).first()
            if event and event.image_path == capture.file_path:
                event.image_path = None
                session.add(event)
            session.delete(capture)
            deleted_event_images += 1
        except Exception as e:
            logger.warning("Failed to delete event capture %s: %s", capture.capture_id, e)

    old_events_with_images = session.exec(
        select(PrinterEvent).where(
            PrinterEvent.created_at < cutoff_event_images,
            PrinterEvent.image_path != None,  # noqa: E711
        )
    ).all()
    for event in old_events_with_images:
        try:
            _delete_capture_file_and_notification_media(event.image_path)
            event.image_path = None
            if event.annotated_image_path:
                _delete_capture_file_and_notification_media(event.annotated_image_path)
                event.annotated_image_path = None
            session.add(event)
        except Exception as e:
            logger.warning("Failed to clear old event images for %s: %s", event.event_id, e)

    if deleted_event_images or old_events_with_images:
        session.commit()
        logger.info(
            "Deleted %s old event capture records and cleared images from %s events",
            deleted_event_images,
            len(old_events_with_images),
        )

    cutoff_clear_results = now - timedelta(hours=retention_config.keep_clear_captures_hours)
    old_results = session.exec(
        select(AnalysisResult).where(AnalysisResult.created_at < cutoff_clear_results)
    ).all()
    deleted_results = 0
    for result in old_results:
        session.delete(result)
        deleted_results += 1

    if deleted_results > 0:
        session.commit()
        logger.info(f"Deleted {deleted_results} old analysis results")

    # Cleanup old clear images sooner than event images.
    cutoff_images = now - timedelta(hours=retention_config.keep_clear_captures_hours)
    old_captures = session.exec(
        select(CameraCapture).where(
            CameraCapture.captured_at < cutoff_images,
            CameraCapture.event_id == None,  # noqa: E711
        )
    ).all()

    deleted_images = 0
    for capture in old_captures:
        try:
            Path(capture.file_path).unlink(missing_ok=True)
            session.delete(capture)
            deleted_images += 1
        except Exception as e:
            logger.warning(f"Failed to delete capture {capture.capture_id}: {e}")

    if deleted_images > 0:
        session.commit()
        logger.info(f"Deleted {deleted_images} old capture images")

    await cleanup_notification_media(config)
    await enforce_capture_storage_limit(config, session)

    # Cleanup old logs
    cutoff_logs = now - timedelta(days=7)  # Keep logs for 7 days
    old_logs = session.exec(
        select(SystemLog).where(SystemLog.timestamp < cutoff_logs)
    ).all()

    deleted_logs = 0
    for log in old_logs:
        session.delete(log)
        deleted_logs += 1

    if deleted_logs > 0:
        session.commit()
        logger.info(f"Deleted {deleted_logs} old system logs")


async def enforce_capture_storage_limit(config: AppConfig, session: Session):
    """Delete oldest non-event captures when capture storage exceeds max size."""
    max_bytes = config.retention.max_capture_storage_mb * 1024 * 1024
    captures_dir = Path("/data/captures")
    if not captures_dir.exists():
        return

    total = sum(path.stat().st_size for path in captures_dir.glob("*") if path.is_file())
    if total <= max_bytes:
        return

    captures = session.exec(
        select(CameraCapture)
        .where(CameraCapture.event_id == None)  # noqa: E711
        .order_by(CameraCapture.captured_at)
    ).all()

    deleted = 0
    for capture in captures:
        if total <= max_bytes:
            break
        path = Path(capture.file_path)
        size = path.stat().st_size if path.exists() else 0
        path.unlink(missing_ok=True)
        total -= size
        session.delete(capture)
        deleted += 1

    if deleted:
        session.commit()
        logger.warning("Deleted %s old non-event captures to enforce disk limit", deleted)


async def cleanup_notification_media(config: AppConfig):
    """Delete old Home Assistant media copies used for notification images."""
    if not MEDIA_NOTIFICATION_DIR.exists():
        return

    cutoff = datetime.utcnow() - timedelta(days=config.retention.keep_event_captures_days)
    deleted = 0
    for path in MEDIA_NOTIFICATION_DIR.glob("*"):
        if not path.is_file():
            continue
        modified_at = datetime.utcfromtimestamp(path.stat().st_mtime)
        if modified_at >= cutoff:
            continue
        try:
            path.unlink()
            deleted += 1
        except Exception as exc:
            logger.warning("Failed to delete notification media %s: %s", path, exc)

    if deleted:
        logger.info("Deleted %s old notification media files", deleted)


def _delete_capture_file_and_notification_media(image_path: str):
    """Delete a capture and the matching Home Assistant media notification copy."""
    path = Path(image_path)
    path.unlink(missing_ok=True)
    _notification_media_path_for_image(image_path).unlink(missing_ok=True)


def _notification_media_path_for_image(image_path: str) -> Path:
    """Return the media copy path used for a capture image."""
    return MEDIA_NOTIFICATION_DIR / Path(image_path).name
