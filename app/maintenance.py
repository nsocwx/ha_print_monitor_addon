"""Maintenance tasks for data retention."""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from sqlmodel import Session, select
from app.models.event import AnalysisResult, PrinterEvent, CameraCapture, SystemLog
from app.core.config import AppConfig

logger = logging.getLogger(__name__)


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
                Path(event.image_path).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to delete image {event.image_path}: {e}")

        if event.annotated_image_path:
            try:
                Path(event.annotated_image_path).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to delete annotated image: {e}")

        session.delete(event)
        deleted_count += 1

    if deleted_count > 0:
        session.commit()
        logger.info(f"Deleted {deleted_count} old events")

    old_results = session.exec(
        select(AnalysisResult).where(AnalysisResult.created_at < cutoff_events)
    ).all()
    deleted_results = 0
    for result in old_results:
        session.delete(result)
        deleted_results += 1

    if deleted_results > 0:
        session.commit()
        logger.info(f"Deleted {deleted_results} old analysis results")

    # Cleanup old images
    cutoff_images = now - timedelta(days=retention_config.keep_images_days)
    old_captures = session.exec(
        select(CameraCapture).where(CameraCapture.captured_at < cutoff_images)
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
