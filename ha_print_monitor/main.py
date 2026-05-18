"""Main FastAPI application."""
import logging
import asyncio
import os
import shutil
import zipfile
import re
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import CONFIG_FILE, DATA_DIR, load_config, AppConfig, redact_sensitive
from app.core.database import DATABASE_URL, SessionLocal, init_db, get_session
from app.api import actions, analysis, events
from app.api.schemas import (
    ConfigResponse,
    EventResponse,
    HealthResponse,
    PrinterStatusResponse,
    StatusResponse,
)
from app.services.monitor import PrintMonitorService
from app.services.home_assistant import HAService
from app.services.notification_actions import HomeAssistantNotificationActionListener
from app.version import APP_VERSION, BUILD_DATE, GIT_COMMIT
from app.logging_config import setup_logging
from app.maintenance import cleanup_old_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global state
config: AppConfig = None
monitor_services: dict[str, PrintMonitorService] = {}
app_start_time: datetime = datetime.utcnow()
monitoring_task: asyncio.Task = None
maintenance_task: asyncio.Task = None
notification_action_listener: HomeAssistantNotificationActionListener = None
notification_action_task: asyncio.Task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global config, monitor_services, monitoring_task, maintenance_task
    global notification_action_listener, notification_action_task

    # Startup
    logger.info("Starting HA Print Monitor")

    # Load configuration
    try:
        config = load_config()
        setup_logging(json_output=config.logging.json_logs, log_level=config.logging.log_level)
        logger.info("Configuration loaded successfully")
        logger.info("Home Assistant API: Supervisor Core API")
        logger.info(f"Configured printers: {[printer.id for printer in config.get_printers()]}")
        if config.security.action_signing_secret.startswith("change-me"):
            logger.warning(
                "ACTION_SIGNING_SECRET is using the default value; set a long random "
                "secret before relying on notification action links"
            )
    except Exception as e:
        logger.error("Failed to load configuration: %s", redact_sensitive(str(e)))
        raise

    if not config.timezone:
        try:
            ha_service = HAService(config.home_assistant.url, config.home_assistant.token)
            ha_config = await ha_service.get_home_assistant_config()
            await ha_service.close()
            config.timezone = ha_config.get("time_zone") or "UTC"
            logger.info("Timezone loaded from Home Assistant: %s", config.timezone)
        except Exception as e:
            config.timezone = "UTC"
            logger.warning(
                "Could not load Home Assistant timezone; falling back to UTC: %s",
                redact_sensitive(str(e)),
            )

    # Initialize database
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # Initialize monitor service
    try:
        monitor_services = {
            printer.id: PrintMonitorService(config, printer)
            for printer in config.get_printers()
            if printer.enabled
        }
        if not monitor_services:
            raise RuntimeError("No enabled printers configured")
        for service in monitor_services.values():
            await service.start()
            try:
                await service.ha_service.get_state(service.printer.printer_state_entity)
                await service.ha_service.get_state(service.printer.camera_entity)
            except Exception as e:
                logger.warning(
                    "Configured Home Assistant entity validation failed for %s: %s",
                    service.printer_name,
                    redact_sensitive(str(e)),
                )
    except Exception as e:
        logger.error(f"Failed to initialize monitor service: {e}")
        raise

    # Start monitoring task
    async def run_monitoring():
        while True:
            try:
                await asyncio.gather(
                    *(service.monitor_cycle() for service in monitor_services.values())
                )
                await asyncio.sleep(config.monitoring.frame_interval_seconds)
            except Exception as e:
                logger.error("Error in monitoring loop: %s", redact_sensitive(str(e)))
                await asyncio.sleep(5)

    monitoring_task = asyncio.create_task(run_monitoring())

    notification_action_listener = HomeAssistantNotificationActionListener(config)
    notification_action_task = asyncio.create_task(notification_action_listener.run_forever())

    async def run_maintenance():
        while True:
            try:
                with SessionLocal() as session:
                    await cleanup_old_data(config, session)
                await asyncio.sleep(3600)
            except Exception as e:
                logger.error("Maintenance loop failed: %s", e)
                await asyncio.sleep(300)

    maintenance_task = asyncio.create_task(run_maintenance())

    yield

    # Shutdown
    logger.info("Shutting down HA Print Monitor")
    if monitoring_task:
        monitoring_task.cancel()
        try:
            await monitoring_task
        except asyncio.CancelledError:
            pass
    if maintenance_task:
        maintenance_task.cancel()
        try:
            await maintenance_task
        except asyncio.CancelledError:
            pass
    if notification_action_listener:
        await notification_action_listener.stop()
    if notification_action_task:
        notification_action_task.cancel()
        try:
            await notification_action_task
        except asyncio.CancelledError:
            pass

    for service in monitor_services.values():
        await service.stop()

    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="HA Print Monitor",
    description="Home Assistant 3D Print Monitoring",
    version=APP_VERSION,
    lifespan=lifespan,
)

if os.getenv("FORWARDED_HEADERS", "").lower() in ("1", "true", "yes"):
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Include routers
app.include_router(events.router)
app.include_router(actions.router)
app.include_router(analysis.router)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    try:
        # Check database
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.error("Database health check failed: %s", redact_sensitive(str(e)))
        db_status = "unhealthy"

    # Check Home Assistant
    try:
        first_service = next(iter(monitor_services.values()))
        await first_service.ha_service.test_connection()
        ha_status = "healthy"
    except Exception as e:
        logger.error("HA health check failed: %s", redact_sensitive(str(e)))
        ha_status = "unhealthy"

    # Check analyzer
    analyzer_status = (
        "healthy"
        if monitor_services and all(service.analyzer.initialized for service in monitor_services.values())
        else "unhealthy"
    )

    addon_checks = [
        bool(os.getenv("SUPERVISOR_TOKEN")),
        DATA_DIR.exists(),
        config is not None and config.home_assistant.url == "http://supervisor/core",
    ]
    addon_status = "healthy" if all(addon_checks) else "unhealthy"

    # Determine overall status
    statuses = [db_status, ha_status, analyzer_status, addon_status]
    if all(s == "healthy" for s in statuses):
        overall = "healthy"
    elif any(s == "healthy" for s in statuses):
        overall = "degraded"
    else:
        overall = "unhealthy"

    uptime = (datetime.utcnow() - app_start_time).total_seconds()

    return HealthResponse(
        status=overall,
        database=db_status,
        home_assistant=ha_status,
        analyzer=analyzer_status,
        addon=addon_status,
        uptime_seconds=uptime,
        app_version=APP_VERSION,
        build_date=BUILD_DATE,
        git_commit=GIT_COMMIT,
    )


def _get_monitor_service(printer_id: Optional[str] = None) -> PrintMonitorService:
    """Get a monitor service by ID or return the first configured printer."""
    if not monitor_services:
        raise HTTPException(status_code=503, detail="Monitor service is not initialized")

    if printer_id:
        service = monitor_services.get(printer_id)
        if service:
            return service
        raise HTTPException(status_code=404, detail="Printer not found")

    return next(iter(monitor_services.values()))


def _active_event_response(
    service: PrintMonitorService,
    session: Session,
) -> Optional[EventResponse]:
    """Get active event response for one monitor service."""
    """Get current application status."""
    if service.active_event_id:
        from sqlmodel import select
        from app.models.event import PrinterEvent

        event = session.exec(
            select(PrinterEvent).where(
                PrinterEvent.event_id == service.active_event_id
            )
        ).first()

        if event:
            return EventResponse(**event.dict())

    return None


def _printer_status_response(
    service: PrintMonitorService,
    session: Session,
) -> PrinterStatusResponse:
    """Build a status response for one printer."""
    return PrinterStatusResponse(
        printer_id=service.printer_id,
        printer_name=service.printer_name,
        camera_entity=service.printer.camera_entity,
        printer_state_entity=service.printer.printer_state_entity,
        running=service.running,
        monitoring_enabled=config.monitoring.enabled,
        printer_state=service.printer_state,
        printer_printing=service.is_printer_printing(),
        last_capture_time=service.last_capture_time,
        last_capture_image_url=(
            f"/captures/{service.last_capture_path.name}"
            if service.last_capture_path
            else None
        ),
        last_capture_status=service.last_capture_status,
        last_capture_error=service.last_capture_error,
        last_successful_capture_time=service.last_successful_capture_time,
        capture_success_count=service.capture_success_count,
        capture_failure_count=service.capture_failure_count,
        camera_stale=service.camera_is_stale(),
        last_analysis_time=service.last_analysis_time,
        latest_analysis_result=service.last_analysis_result,
        last_analysis_error=service.last_analysis_error,
        last_inference_duration_ms=service.last_inference_duration_ms,
        model_status=service.model_status,
        active_event=_active_event_response(service, session),
    )


@app.get("/api/printers", response_model=list[PrinterStatusResponse])
async def list_printers(session: Session = Depends(get_session)) -> list[PrinterStatusResponse]:
    """Get status for every configured printer."""
    return [
        _printer_status_response(service, session)
        for service in monitor_services.values()
    ]


@app.get("/api/status", response_model=StatusResponse)
async def get_status(
    printer_id: Optional[str] = None,
    session: Session = Depends(get_session),
) -> StatusResponse:
    """Get current application status."""
    service = _get_monitor_service(printer_id)
    printer_status = _printer_status_response(service, session)

    return StatusResponse(
        app_version=APP_VERSION,
        printer_id=service.printer_id,
        printer_name=service.printer_name,
        running=printer_status.running,
        monitoring_enabled=config.monitoring.enabled,
        printer_state=printer_status.printer_state,
        printer_printing=printer_status.printer_printing,
        last_capture_time=printer_status.last_capture_time,
        last_capture_image_url=printer_status.last_capture_image_url,
        last_capture_status=printer_status.last_capture_status,
        last_capture_error=printer_status.last_capture_error,
        last_successful_capture_time=printer_status.last_successful_capture_time,
        capture_success_count=printer_status.capture_success_count,
        capture_failure_count=printer_status.capture_failure_count,
        camera_stale=printer_status.camera_stale,
        last_analysis_time=printer_status.last_analysis_time,
        latest_analysis_result=printer_status.latest_analysis_result,
        last_analysis_error=printer_status.last_analysis_error,
        last_inference_duration_ms=printer_status.last_inference_duration_ms,
        model_status=printer_status.model_status,
        active_event=printer_status.active_event,
        health_status="healthy",
    )


@app.get("/api/config", response_model=ConfigResponse)
async def get_config(printer_id: Optional[str] = None) -> ConfigResponse:
    """Get current configuration."""
    service = _get_monitor_service(printer_id)
    return ConfigResponse(
        app_base_url=config.app_base_url,
        timezone=config.timezone,
        home_assistant_url="Supervisor Core API",
        camera_entity=config.home_assistant.camera_entity,
        printer_state_entity=config.home_assistant.printer_state_entity,
        selected_printer={
                "id": service.printer.id,
                "name": service.printer.name,
                "enabled": service.printer.enabled,
            "camera_entity": service.printer.camera_entity,
            "printer_state_entity": service.printer.printer_state_entity,
            "printing_states": service.printer.printing_states,
            "pause_service": {
                "domain": service.printer.pause_service.domain,
                "service": service.printer.pause_service.service,
                "target": service.printer.pause_service.target,
                "data": service.printer.pause_service.data,
            },
            "notify_services": service.printer.notify_services
            or config.home_assistant.notify_services,
        },
        analyzer_provider=config.model.provider,
        analyzer_device=config.model.device,
        frame_interval_seconds=config.monitoring.frame_interval_seconds,
        confirmation_frames=config.monitoring.confirmation_frames,
        certainty_threshold_notify=config.monitoring.certainty_threshold_notify,
        auto_pause_enabled=config.monitoring.auto_pause_enabled,
        certainty_threshold_auto_pause=config.monitoring.certainty_threshold_auto_pause,
        auto_pause_delay_minutes=config.monitoring.auto_pause_delay_minutes,
        cooldown_minutes=config.monitoring.cooldown_minutes,
        printers=[
            {
                "id": printer.id,
                "name": printer.name,
                "enabled": printer.enabled,
                "camera_entity": printer.camera_entity,
                "printer_state_entity": printer.printer_state_entity,
            }
            for printer in config.get_printers()
        ],
        safety=config.safety.model_dump(),
        camera=config.camera.model_dump(),
        notifications=config.notifications.model_dump(),
        retention=config.retention.model_dump(),
    )


@app.get("/api/diagnostics")
async def diagnostics() -> dict:
    """Return redacted diagnostics for troubleshooting."""
    data_dir_usage = shutil.disk_usage(DATA_DIR)
    capture_dir = DATA_DIR / "captures"
    capture_bytes = sum(path.stat().st_size for path in capture_dir.glob("*") if path.is_file()) if capture_dir.exists() else 0
    return {
        "version": {
            "app_version": APP_VERSION,
            "build_date": BUILD_DATE,
            "git_commit": GIT_COMMIT,
        },
        "paths": {
            "options_file": str(CONFIG_FILE),
            "database_url": DATABASE_URL.replace(str(DATA_DIR), "/data"),
            "data_dir": str(DATA_DIR),
        },
        "disk": {
            "data_total_bytes": data_dir_usage.total,
            "data_used_bytes": data_dir_usage.used,
            "data_free_bytes": data_dir_usage.free,
            "captures_bytes": capture_bytes,
        },
        "config": {
            "app_base_url": config.app_base_url,
            "timezone": config.timezone,
            "home_assistant_url": "Supervisor Core API",
            "monitoring": config.monitoring.model_dump(),
            "safety": config.safety.model_dump(),
            "camera": config.camera.model_dump(),
            "notifications": config.notifications.model_dump(),
            "retention": config.retention.model_dump(),
            "model": {
                "provider": config.model.provider,
                "device": config.model.device,
                "auto_download": config.model.auto_download,
            },
        },
        "printers": {
            printer_id: {
                "printer_name": service.printer_name,
                "running": service.running,
                "printer_state": service.printer_state,
                "printer_printing": service.is_printer_printing(),
                "camera_stale": service.camera_is_stale(),
                "last_capture_status": service.last_capture_status,
                "last_capture_error": redact_sensitive(service.last_capture_error or ""),
                "capture_success_count": service.capture_success_count,
                "capture_failure_count": service.capture_failure_count,
                "model_status": service.model_status,
                "last_analysis_error": redact_sensitive(service.last_analysis_error or ""),
            }
            for printer_id, service in monitor_services.items()
        },
    }


@app.get("/api/backup")
async def backup() -> FileResponse:
    """Create a simple backup archive with add-on options and SQLite database."""
    backup_dir = DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    archive_path = backup_dir / f"ha-print-monitor-backup-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if CONFIG_FILE.exists():
            archive.write(CONFIG_FILE, "options.json")
        db_path = DATA_DIR / "app.db"
        if db_path.exists():
            archive.write(db_path, "app.db")
    return FileResponse(archive_path, media_type="application/zip", filename=archive_path.name)


@app.get("/captures/{filename}")
async def get_capture(filename: str):
    """Get a capture image."""
    captures_dir = (DATA_DIR / "captures").resolve()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.(?:jpg|jpeg|png|webp)", filename):
        raise HTTPException(status_code=400, detail="Invalid capture filename")

    capture_path = (captures_dir / filename).resolve()

    if captures_dir not in capture_path.parents:
        raise HTTPException(status_code=403, detail="Access denied")
    if not capture_path.exists() or not capture_path.is_file():
        raise HTTPException(status_code=404, detail="Capture not found")

    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(capture_path.suffix.lower(), "application/octet-stream")
    return FileResponse(capture_path, media_type=media_type)


@app.get("/favicon.ico")
async def favicon() -> Response:
    """Return a no-content favicon response to avoid 404 noise."""
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve dashboard HTML."""
    static_dir = Path(__file__).parent / "static"
    dashboard_file = static_dir / "dashboard.html"

    if not dashboard_file.exists():
        return "<h1>HA Print Monitor</h1><p>Dashboard coming soon...</p>"

    return FileResponse(dashboard_file)
