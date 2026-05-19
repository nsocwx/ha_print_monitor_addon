"""Monitoring service for print analysis."""
import logging
import asyncio
import uuid
import json
import time
import httpx
import shutil
from io import BytesIO
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from PIL import Image, UnidentifiedImageError
from sqlmodel import Session, select
from app.models.event import AnalysisResult, PrinterEvent, CameraCapture
from app.core.config import AppConfig, PrinterConfig
from app.services.home_assistant import HAService
from app.analysis.factory import AnalyzerFactory
from app.analysis.base import AnalysisContext, RecommendedAction, Severity
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

DATA_DIR = Path("/data")
CAPTURES_DIR = DATA_DIR / "captures"
FALLBACK_CAPTURES_DIR = Path("/tmp/ha-print-monitor/captures")
MEDIA_NOTIFICATION_DIR = Path("/media/ha_print_monitor")
MEDIA_NOTIFICATION_URL_PREFIX = "/media/local/ha_print_monitor"


class PrintMonitorService:
    """Service for monitoring 3D prints."""

    ACTIVE_PRINTING_STATE_PREFIXES = ("printing",)

    def __init__(self, config: AppConfig, printer: Optional[PrinterConfig] = None):
        self.config = config
        self.printer = printer or config.get_printers()[0]
        self.printer_id = self.printer.id
        self.printer_name = self.printer.name
        self.ha_service = HAService(
            config.home_assistant.url,
            config.home_assistant.token,
            timeout_seconds=config.camera.capture_timeout_seconds,
            retry_count=config.camera.retry_count,
            retry_backoff_seconds=config.camera.retry_backoff_seconds,
        )
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
        self.last_capture_status: str = "no_capture"
        self.last_capture_error: Optional[str] = None
        self.capture_success_count = 0
        self.capture_failure_count = 0
        self.last_successful_capture_time: Optional[datetime] = None
        self.last_analysis_time: Optional[datetime] = None
        self.last_analysis_result: Optional[dict] = None
        self.last_analysis_error: Optional[str] = None
        self.last_inference_duration_ms: Optional[float] = None
        self.model_status = "initialized" if self.analyzer.initialized else "uninitialized"
        self.printer_state: Optional[str] = None
        self.active_event_id: Optional[str] = None
        self.pending_detection_count = 0
        self.pending_issue_type: Optional[str] = None

        self.captures_dir = self._prepare_captures_dir()

    def _prepare_captures_dir(self) -> Path:
        try:
            CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
            return CAPTURES_DIR
        except OSError as exc:
            logger.warning(
                "Cannot write captures to %s; using temporary storage at %s: %s",
                CAPTURES_DIR,
                FALLBACK_CAPTURES_DIR,
                exc,
            )
            FALLBACK_CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
            return FALLBACK_CAPTURES_DIR

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
        if not self.printer.enabled:
            return

        try:
            if self._analysis_interval_active():
                return

            # Get printer state
            state_entity = self.printer.printer_state_entity
            state_response = await self.ha_service.get_state(state_entity)
            current_state = state_response.get("state", "unknown")
            self.printer_state = current_state

            # Only capture/analyze while the printer is actively printing.
            is_printing = self.is_printer_printing(current_state)

            if not is_printing:
                # Not printing, skip camera capture and analysis.
                if self.active_event_id:
                    logger.info("Printer stopped, resolving active event")
                    await self._resolve_event(self.active_event_id)
                    self.active_event_id = None
                return

            # Get camera image
            try:
                camera_image = await self.ha_service.get_camera_image(
                    self.printer.camera_entity
                )
                image_data = self._validate_camera_image(camera_image)
            except Exception as e:
                if self.config.camera.fallback_snapshot_url:
                    try:
                        image_data = await self._capture_fallback_snapshot()
                    except Exception as fallback_error:
                        self._record_capture_failure(
                            f"{e}; fallback failed: {fallback_error}"
                        )
                        logger.error(
                            "Failed to capture image for %s: %s; fallback failed: %s",
                            self.printer_name,
                            e,
                            fallback_error,
                        )
                        return
                else:
                    self._record_capture_failure(str(e))
                    logger.error(f"Failed to capture image for {self.printer_name}: {e}")
                    return

            # Save capture
            capture_id = f"capture_{self.printer_id}_{uuid.uuid4().hex[:8]}"
            capture_path = self.captures_dir / f"{capture_id}.jpg"
            try:
                capture_path.write_bytes(image_data)
            except OSError as e:
                self._record_capture_failure(f"failed to save capture: {e}")
                logger.error("Failed to save capture for %s: %s", self.printer_name, e)
                return
            self.last_capture_time = datetime.utcnow()
            self.last_capture_path = capture_path
            self.last_capture_status = "ok"
            self.last_capture_error = None
            self.last_successful_capture_time = self.last_capture_time
            self.capture_success_count += 1
            self._store_camera_capture(capture_id, capture_path)

            # Analyze frame
            context = AnalysisContext(
                printer_state=current_state,
                printer_attributes=state_response.get("attributes", {}),
            )

            try:
                start = time.perf_counter()
                result = await asyncio.wait_for(
                    self.analyzer.analyze_frame(image_data, context),
                    timeout=max(1, self.config.model.max_inference_timeout_seconds),
                )
                self.last_inference_duration_ms = (time.perf_counter() - start) * 1000
                self.last_analysis_error = None
                self.model_status = "healthy"
            except Exception as e:
                self.last_analysis_error = str(e)
                self.model_status = "degraded"
                logger.error("Analysis failed for %s: %s", self.printer_name, e)
                return
            self.last_analysis_time = datetime.utcnow()
            self.last_analysis_result = result.to_dict()
            self.last_analysis_result["inference_duration_ms"] = self.last_inference_duration_ms
            self._store_analysis_result(result, capture_path)

            logger.debug(f"Analysis result: {result.to_dict()}")

            # Handle result
            if result.issue_detected:
                if self._confirm_detection(result):
                    await self._handle_detection(result, capture_id, capture_path, current_state)
                else:
                    logger.info(
                        f"Pending detection for {self.printer_name}: "
                        f"{self.pending_detection_count}/"
                        f"{self.config.monitoring.confirmation_frames} "
                        f"frames confirmed"
                    )
            else:
                self._reset_detection_confirmation()

        except Exception as e:
            logger.error(f"Error in monitoring cycle: {e}")

    def _analysis_interval_active(self) -> bool:
        minimum = max(0, self.config.monitoring.min_analysis_interval_seconds)
        if not minimum or not self.last_analysis_time:
            return False
        return (datetime.utcnow() - self.last_analysis_time).total_seconds() < minimum

    def is_printer_printing(self, state: Optional[str] = None) -> bool:
        """Return true only for configured states that represent active printing."""
        normalized_state = self._normalize_printer_state(
            self.printer_state if state is None else state
        )
        if not normalized_state:
            return False

        configured_states = {
            self._normalize_printer_state(configured_state)
            for configured_state in self.printer.printing_states
        }
        if normalized_state not in configured_states:
            return False

        return normalized_state.startswith(self.ACTIVE_PRINTING_STATE_PREFIXES)

    @staticmethod
    def _normalize_printer_state(state: Optional[str]) -> str:
        """Normalize Home Assistant printer states for conservative comparisons."""
        return (state or "").strip().lower()

    def _confirm_detection(self, result) -> bool:
        """Track consecutive matching detections before acting."""
        required_frames = max(1, self.config.monitoring.confirmation_frames)
        issue_type = result.issue_type or "unknown"

        if self.pending_issue_type == issue_type:
            self.pending_detection_count += 1
        else:
            self.pending_issue_type = issue_type
            self.pending_detection_count = 1

        return self.pending_detection_count >= required_frames

    def _reset_detection_confirmation(self):
        """Reset pending detection confirmation state."""
        if self.pending_detection_count:
            logger.info(f"Detection confirmation reset for {self.printer_name}")
        self.pending_detection_count = 0
        self.pending_issue_type = None

    def _validate_camera_image(self, camera_image) -> bytes:
        """Validate Home Assistant returned a complete decodable image."""
        content = camera_image.content
        content_type = camera_image.content_type or "unknown"

        if not content:
            raise ValueError(
                f"empty camera response from {self.printer.camera_entity} "
                f"(content-type: {content_type})"
            )

        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            preview = content[:80].decode("utf-8", errors="replace").replace("\n", " ")
            raise ValueError(
                f"invalid camera image from {self.printer.camera_entity}: "
                f"{len(content)} bytes, content-type {content_type}, "
                f"preview {preview!r}"
            ) from exc

        return content

    def _record_capture_failure(self, message: str):
        """Track capture failure without clearing the last valid snapshot."""
        self.last_capture_status = "error"
        self.last_capture_error = message
        self.capture_failure_count += 1

    async def _capture_fallback_snapshot(self) -> bytes:
        """Fetch a fallback snapshot URL when HA camera proxy fails."""
        async with httpx.AsyncClient(timeout=self.config.camera.capture_timeout_seconds) as client:
            response = await client.get(self.config.camera.fallback_snapshot_url)
            response.raise_for_status()

        class FallbackImage:
            content = response.content
            content_type = response.headers.get("content-type", "")

        return self._validate_camera_image(FallbackImage())

    def camera_is_stale(self) -> bool:
        """Return true when no recent valid camera image has been captured."""
        if not self.last_successful_capture_time:
            return True
        age = (datetime.utcnow() - self.last_successful_capture_time).total_seconds()
        return age > self.config.camera.stale_after_seconds

    def _store_camera_capture(self, capture_id: str, capture_path: Path):
        """Persist capture metadata for retention and diagnostics."""
        session = SessionLocal()
        try:
            capture = CameraCapture(
                capture_id=capture_id,
                printer_id=self.printer_id,
                printer_name=self.printer_name,
                file_path=str(capture_path),
                file_size=capture_path.stat().st_size,
            )
            session.add(capture)
            session.commit()
        except Exception as e:
            logger.warning("Failed to store camera capture metadata: %s", e)
        finally:
            session.close()

    def _store_analysis_result(self, result, capture_path: Path):
        """Persist one analyzer result for dashboard history."""
        session = SessionLocal()
        try:
            analysis = AnalysisResult(
                printer_id=self.printer_id,
                printer_name=self.printer_name,
                result="issue" if result.issue_detected else "clear",
                issue_type=result.issue_type,
                certainty=result.certainty,
                severity=result.severity.value,
                explanation=result.explanation,
                image_path=str(capture_path),
                annotated_image_path=result.annotated_image_path,
                raw_model_output_json=json.dumps(result.raw_model_output, default=str),
                inference_duration_ms=self.last_inference_duration_ms,
            )
            session.add(analysis)
            session.commit()
        except Exception as e:
            logger.warning(f"Failed to store analysis result: {e}")
        finally:
            session.close()

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

                if event and event.status in ("active", "acknowledged", "pending_pause"):
                    # Same or similar issue - update event
                    event.certainty = max(event.certainty, result.certainty)
                    event.updated_at = datetime.utcnow()
                    event.last_seen_at = datetime.utcnow()
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
                self.config.monitoring.auto_pause_enabled
                and
                result.certainty >= self.config.monitoring.certainty_threshold_auto_pause
                and result.severity in (Severity.HIGH, Severity.CRITICAL)
            ):
                auto_pause_deadline = datetime.utcnow() + timedelta(
                    minutes=self.config.monitoring.auto_pause_delay_minutes
                )
                event.auto_pause_deadline = auto_pause_deadline
                event.status = "pending_pause"
                session.add(event)
                session.commit()

                logger.info(
                    f"Auto-pause scheduled for {event_id} at {auto_pause_deadline}"
                )

        finally:
            session.close()

    async def _send_notification_if_needed(self, event: PrinterEvent, session: Session):
        """Send a notification once certainty reaches the configured threshold."""
        if not self.config.notifications.enabled:
            return
        if not self._notification_allowed_for_severity(event.severity):
            logger.info("Notification suppressed for %s severity %s", event.event_id, event.severity)
            return
        if self._notification_already_sent(event):
            return

        notify_threshold = (
            self.printer.certainty_threshold_notify
            if self.printer.certainty_threshold_notify is not None
            else self.config.monitoring.certainty_threshold_notify
        )
        if event.certainty < notify_threshold:
            logger.info(
                f"Detection {event.event_id} recorded below notification threshold "
                f"({event.certainty:.0%} < {notify_threshold:.0%})"
            )
            return

        await self._send_notification(event, session)
        event.notification_sent_at = datetime.utcnow()
        event.add_action("notification_sent", {"certainty": event.certainty})
        session.add(event)
        session.commit()

    def _notification_already_sent(self, event: PrinterEvent) -> bool:
        """Return true if this event has already produced a notification."""
        return any(
            action.get("action") == "notification_sent"
            for action in event.action_history
        )

    def _notification_allowed_for_severity(self, severity: str) -> bool:
        """Return true when notification config allows this severity."""
        severity_key = f"notify_on_{(severity or '').lower()}"
        return bool(getattr(self.config.notifications, severity_key, False))

    async def _check_auto_pause(self, event: PrinterEvent, result, session: Session):
        """Check if auto-pause should be triggered."""
        if (
            event.auto_pause_deadline
            and self.config.monitoring.auto_pause_enabled
            and datetime.utcnow() >= event.auto_pause_deadline
            and not event.auto_paused
            and event.status in ("active", "pending_pause")
        ):
            logger.warning(f"Auto-pausing print for event {event.event_id}")

            try:
                from app.api.actions import _pause_event

                response = await _pause_event(event, self.config, session, auto_pause=True)
                if response.success:
                    await self._send_auto_pause_notification(event, session)
                else:
                    await self._send_auto_pause_skipped_notification(event, response.message)

            except Exception as e:
                logger.error(f"Failed to auto-pause print: {e}")

    async def _send_notification(self, event: PrinterEvent, session: Session):
        """Send notification for event."""
        try:
            notify_services = self.printer.notify_services or self.config.home_assistant.notify_services
            for notify_service in notify_services:
                from app.security import create_action_token
                from app.services.notification_actions import build_notification_action

                # Mobile action taps are delivered back to Home Assistant as events.
                # The add-on websocket listener consumes these signed one-time tokens.
                pause_token = create_action_token(self.config, event.event_id, "pause", event.printer_id)
                ignore_token = create_action_token(self.config, event.event_id, "ignore", event.printer_id)
                snooze_token = create_action_token(self.config, event.event_id, "snooze", event.printer_id)
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
                    "actions": [
                        {
                            "action": build_notification_action("pause", pause_token),
                            "title": "Pause Print",
                            "destructive": True,
                        },
                        {
                            "action": build_notification_action("ignore", ignore_token),
                            "title": "Ignore",
                        },
                        {
                            "action": build_notification_action("snooze", snooze_token),
                            "title": f"Snooze {self.config.monitoring.snooze_minutes}m",
                        },
                    ],
                }
                image_url = self._prepare_notification_image(event)
                if image_url:
                    data["image"] = image_url

                await self.ha_service.send_notification(
                    service=notify_service,
                    title=title,
                    message=message,
                    data=data,
                )

                logger.info("Notification sent via %s for event %s", notify_service, event.event_id)

        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    def _prepare_notification_image(self, event: PrinterEvent) -> Optional[str]:
        """Copy an event image into HA local media and return its media_source URL."""
        if not event.image_path:
            return None

        source_path = Path(event.image_path)
        if not source_path.is_file():
            logger.warning(
                "Notification image for event %s is missing: %s",
                event.event_id,
                source_path,
            )
            return None

        try:
            MEDIA_NOTIFICATION_DIR.mkdir(parents=True, exist_ok=True)
            destination = MEDIA_NOTIFICATION_DIR / source_path.name
            shutil.copy2(source_path, destination)
            return f"{MEDIA_NOTIFICATION_URL_PREFIX}/{destination.name}"
        except Exception as exc:
            logger.warning(
                "Could not publish notification image for event %s to Home Assistant media: %s",
                event.event_id,
                exc,
            )
            return None

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

    async def _send_auto_pause_skipped_notification(self, event: PrinterEvent, reason: str):
        """Send notification that auto-pause was skipped by safety interlocks."""
        try:
            notify_services = self.printer.notify_services or self.config.home_assistant.notify_services
            for notify_service in notify_services:
                await self.ha_service.send_notification(
                    service=notify_service,
                    title=f"Auto-Pause Skipped: {self.printer_name}",
                    message=f"Auto-pause was skipped for {event.issue_type}: {reason}",
                )
        except Exception as e:
            logger.error("Failed to send auto-pause skipped notification: %s", e)

    async def _resolve_event(self, event_id: str):
        """Mark event as resolved."""
        session = SessionLocal()
        try:
            event = session.exec(
                select(PrinterEvent).where(PrinterEvent.event_id == event_id)
            ).first()

            if event and event.status not in ("resolved", "paused", "ignored", "snoozed"):
                event.status = "resolved"
                event.resolved_at = datetime.utcnow()
                event.add_action("auto_resolved", {})
                session.add(event)
                session.commit()
                logger.info(f"Event {event_id} auto-resolved")

        finally:
            session.close()
