"""Monitoring service for print analysis."""
import logging
import asyncio
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from sqlmodel import Session, select
from app.models.event import PrinterEvent, CameraCapture
from app.core.config import AppConfig, PrinterConfig
from app.services.home_assistant import HAService
from app.analysis.factory import AnalyzerFactory
from app.analysis.base import AnalysisContext, RecommendedAction, Severity
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

DATA_DIR = Path("/data")
CAPTURES_DIR = DATA_DIR / "captures"


class PrintMonitorService:
    """Service for monitoring 3D prints."""

    def __init__(self, config: AppConfig, printer: Optional[PrinterConfig] = None):
        self.config = config
        self.printer = printer or config.get_printers()[0]
        self.printer_id = self.printer.id
        self.printer_name = self.printer.name
        self.ha_service = HAService(config.home_assistant.url, config.home_assistant.token)
        self.analyzer = AnalyzerFactory.create_analyzer(
            config.model.provider,
            config.model.model_path,
            config.model.device,
            options_path=config.model.options_path,
            prototypes_path=config.model.prototypes_path,
            auto_download=config.model.auto_download,
            models_dir=config.model.models_dir,
        )
        self.analyzer.initialize()

        self.running = False
        self.last_capture_time: Optional[datetime] = None
        self.last_capture_path: Optional[Path] = None
        self.last_analysis_time: Optional[datetime] = None
        self.printer_state: Optional[str] = None
        self.active_event_id: Optional[str] = None

        CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

    async def start(self):
        """Start monitoring."""
        self.running = True
        logger.info(f"PrintMonitorService started for {self.printer_name}")

        # Test HA connection
        try:
            await self.ha_service.test_connection()
        except Exception as e:
            logger.error(f"Failed to connect to Home Assistant: {e}")

    async def stop(self):
        """Stop monitoring."""
        self.running = False
        self.analyzer.cleanup()
        logger.info(f"PrintMonitorService stopped for {self.printer_name}")

    async def monitor_cycle(self):
        """Run one monitoring cycle."""
        if not self.config.monitoring.enabled or not self.running:
            return

        try:
            # Get printer state
            state_entity = self.printer.printer_state_entity
            state_response = await self.ha_service.get_state(state_entity)
            current_state = state_response.get("state", "unknown")
            self.printer_state = current_state

            # Check if printer is printing
            is_printing = current_state in self.printer.printing_states

            if not is_printing:
                # Not printing, skip analysis
                if self.active_event_id:
                    logger.info("Printer stopped, resolving active event")
                    await self._resolve_event(self.active_event_id)
                    self.active_event_id = None
                return

            # Get camera image
            try:
                image_data = await self.ha_service.get_camera_image(
                    self.printer.camera_entity
                )
                self.last_capture_time = datetime.utcnow()
            except Exception as e:
                logger.error(f"Failed to capture image: {e}")
                return

            # Save capture
            capture_id = f"capture_{self.printer_id}_{uuid.uuid4().hex[:8]}"
            capture_path = CAPTURES_DIR / f"{capture_id}.jpg"
            capture_path.write_bytes(image_data)
            self.last_capture_path = capture_path

            # Analyze frame
            context = AnalysisContext(
                printer_state=current_state,
                printer_attributes=state_response.get("attributes", {}),
            )

            result = await self.analyzer.analyze_frame(image_data, context)
            self.last_analysis_time = datetime.utcnow()

            logger.debug(f"Analysis result: {result.to_dict()}")

            # Handle result
            if result.issue_detected:
                await self._handle_detection(result, capture_id, capture_path, current_state)

        except Exception as e:
            logger.error(f"Error in monitoring cycle: {e}")

    async def _handle_detection(
        self,
        result,
        capture_id: str,
        capture_path: Path,
        printer_state: str,
    ):
        """Handle a detection result."""
        session = SessionLocal()

        try:
            # Check if this is a continuation of an existing event
            if self.active_event_id:
                event = session.exec(
                    select(PrinterEvent).where(PrinterEvent.event_id == self.active_event_id)
                ).first()

                if event and event.status in ("active", "acknowledged"):
                    # Same or similar issue - update event
                    event.certainty = max(event.certainty, result.certainty)
                    event.updated_at = datetime.utcnow()
                    event.add_action(
                        "detection",
                        {
                            "capture_id": capture_id,
                            "certainty": result.certainty,
                        },
                    )
                    session.add(event)
                    session.commit()

                    logger.info(f"Updated event {self.active_event_id} with new detection")

                    await self._send_notification_if_needed(event, session)

                    # Check for auto-pause
                    await self._check_auto_pause(event, result, session)
                    return

            # New event
            event_id = f"event_{uuid.uuid4().hex[:8]}"
            event = PrinterEvent(
                event_id=event_id,
                printer_id=self.printer_id,
                printer_name=self.printer_name,
                printer_state=printer_state,
                printer_state_at=datetime.utcnow(),
                issue_type=result.issue_type,
                certainty=result.certainty,
                severity=result.severity.value,
                explanation=result.explanation,
                image_path=str(capture_path),
                status="active",
                recommended_action=result.recommended_action.value,
            )

            session.add(event)
            session.commit()

            self.active_event_id = event_id
            logger.info(f"Created new event {event_id}: {result.issue_type}")

            await self._send_notification_if_needed(event, session)

            # Set up auto-pause if needed
            if (
                result.certainty >= self.config.monitoring.certainty_threshold_auto_pause
                and result.severity in (Severity.HIGH, Severity.CRITICAL)
            ):
                auto_pause_deadline = datetime.utcnow() + timedelta(
                    minutes=self.config.monitoring.auto_pause_delay_minutes
                )
                event.auto_pause_deadline = auto_pause_deadline
                session.add(event)
                session.commit()

                logger.info(
                    f"Auto-pause scheduled for {event_id} at {auto_pause_deadline}"
                )

        finally:
            session.close()

    async def _send_notification_if_needed(self, event: PrinterEvent, session: Session):
        """Send a notification once certainty reaches the configured threshold."""
        if self._notification_already_sent(event):
            return

        notify_threshold = self.config.monitoring.certainty_threshold_notify
        if event.certainty < notify_threshold:
            logger.info(
                f"Detection {event.event_id} recorded below notification threshold "
                f"({event.certainty:.0%} < {notify_threshold:.0%})"
            )
            return

        await self._send_notification(event, session)
        event.add_action("notification_sent", {"certainty": event.certainty})
        session.add(event)
        session.commit()

    def _notification_already_sent(self, event: PrinterEvent) -> bool:
        """Return true if this event has already produced a notification."""
        return any(
            action.get("action") == "notification_sent"
            for action in event.action_history
        )

    async def _check_auto_pause(self, event: PrinterEvent, result, session: Session):
        """Check if auto-pause should be triggered."""
        if (
            event.auto_pause_deadline
            and datetime.utcnow() >= event.auto_pause_deadline
            and not event.auto_paused
            and event.status == "active"
        ):
            logger.warning(f"Auto-pausing print for event {event.event_id}")

            try:
                await self.ha_service.call_service(
                    domain=self.printer.pause_service.domain,
                    service=self.printer.pause_service.service,
                    target={"entity_id": self.printer.pause_service.target},
                    service_data=self.printer.pause_service.data,
                )

                event.auto_paused = True
                event.auto_pause_at = datetime.utcnow()
                event.add_action("auto_paused", {})
                session.add(event)
                session.commit()

                # Send notification
                await self._send_auto_pause_notification(event, session)

            except Exception as e:
                logger.error(f"Failed to auto-pause print: {e}")

    async def _send_notification(self, event: PrinterEvent, session: Session):
        """Send notification for event."""
        try:
            notify_services = self.printer.notify_services or self.config.home_assistant.notify_services
            for notify_service in notify_services:
                action_token = self.config.security.action_token

                # Construct action URLs
                pause_url = (
                    f"{self.config.app_base_url}/api/actions/pause"
                    f"?event_id={event.event_id}&token={action_token}"
                )
                ignore_url = (
                    f"{self.config.app_base_url}/api/actions/ignore"
                    f"?event_id={event.event_id}&token={action_token}"
                )
                snooze_url = (
                    f"{self.config.app_base_url}/api/actions/snooze"
                    f"?event_id={event.event_id}&token={action_token}&minutes={self.config.monitoring.snooze_minutes}"
                )

                # Build notification data
                title = f"Possible Print Issue Detected: {self.printer_name}"
                message = (
                    f"{event.issue_type.replace('_', ' ').title()}\n"
                    f"Certainty: {event.certainty:.0%}\n"
                    f"Severity: {event.severity}\n"
                    f"{event.explanation}"
                )

                if event.auto_pause_deadline:
                    deadline = event.auto_pause_deadline
                    time_remaining = (deadline - datetime.utcnow()).total_seconds() / 60
                    message += (
                        f"\n\nAuto-pause in {time_remaining:.0f} minutes unless ignored."
                    )

                data = {
                    "image": f"{self.config.app_base_url}/captures/{Path(event.image_path).name}",
                    "actions": [
                        {"action": "URI", "title": "Pause Print", "uri": pause_url},
                        {"action": "URI", "title": "Ignore", "uri": ignore_url},
                        {"action": "URI", "title": f"Snooze {self.config.monitoring.snooze_minutes}m", "uri": snooze_url},
                    ],
                }

                await self.ha_service.send_notification(
                    service=notify_service,
                    title=title,
                    message=message,
                    data=data,
                )

                logger.info(f"Notification sent via {notify_service}")

        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    async def _send_auto_pause_notification(self, event: PrinterEvent, session: Session):
        """Send notification that print was auto-paused."""
        try:
            notify_services = self.printer.notify_services or self.config.home_assistant.notify_services
            for notify_service in notify_services:
                title = f"Print Auto-Paused: {self.printer_name}"
                message = (
                    f"Print was automatically paused due to detected issue:\n"
                    f"{event.issue_type.replace('_', ' ').title()}\n"
                    f"Certainty: {event.certainty:.0%}\n"
                    f"{event.explanation}"
                )

                await self.ha_service.send_notification(
                    service=notify_service,
                    title=title,
                    message=message,
                )

        except Exception as e:
            logger.error(f"Failed to send auto-pause notification: {e}")

    async def _resolve_event(self, event_id: str):
        """Mark event as resolved."""
        session = SessionLocal()
        try:
            event = session.exec(
                select(PrinterEvent).where(PrinterEvent.event_id == event_id)
            ).first()

            if event and event.status not in ("resolved", "paused"):
                event.status = "resolved"
                event.add_action("auto_resolved", {})
                session.add(event)
                session.commit()
                logger.info(f"Event {event_id} auto-resolved")

        finally:
            session.close()
