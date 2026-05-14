"""Main FastAPI application."""
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import load_config, save_config, AppConfig
from app.core.database import SessionLocal, init_db, get_session
from app.api import events, actions
from app.api.schemas import (
    ConfigResponse,
    EventResponse,
    HealthResponse,
    PrinterStatusResponse,
    StatusResponse,
)
from app.services.monitor import PrintMonitorService

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global config, monitor_services, monitoring_task

    # Startup
    logger.info("Starting HA Print Monitor")

    # Load configuration
    try:
        config = load_config()
        logger.info("Configuration loaded successfully")
        logger.info(f"Home Assistant URL: {config.home_assistant.url}")
        logger.info(f"Configured printers: {[printer.id for printer in config.get_printers()]}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise

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
        }
        for service in monitor_services.values():
            await service.start()
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
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)

    monitoring_task = asyncio.create_task(run_monitoring())

    yield

    # Shutdown
    logger.info("Shutting down HA Print Monitor")
    if monitoring_task:
        monitoring_task.cancel()
        try:
            await monitoring_task
        except asyncio.CancelledError:
            pass

    for service in monitor_services.values():
        await service.stop()

    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="HA Print Monitor",
    description="Home Assistant 3D Print Monitoring",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(events.router)
app.include_router(actions.router)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    try:
        # Check database
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    # Check Home Assistant
    try:
        first_service = next(iter(monitor_services.values()))
        await first_service.ha_service.test_connection()
        ha_status = "healthy"
    except Exception as e:
        logger.error(f"HA health check failed: {e}")
        ha_status = "unhealthy"

    # Check analyzer
    analyzer_status = (
        "healthy"
        if monitor_services and all(service.analyzer.initialized for service in monitor_services.values())
        else "unhealthy"
    )

    # Determine overall status
    statuses = [db_status, ha_status, analyzer_status]
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
        uptime_seconds=uptime,
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
        printer_printing=(
            service.printer_state in service.printer.printing_states
            if service.printer_state
            else False
        ),
        last_capture_time=service.last_capture_time,
        last_capture_image_url=(
            f"/captures/{service.last_capture_path.name}"
            if service.last_capture_path
            else None
        ),
        last_analysis_time=service.last_analysis_time,
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
        app_version="0.1.0",
        running=printer_status.running,
        monitoring_enabled=config.monitoring.enabled,
        printer_state=printer_status.printer_state,
        printer_printing=printer_status.printer_printing,
        last_capture_time=printer_status.last_capture_time,
        last_capture_image_url=printer_status.last_capture_image_url,
        last_analysis_time=printer_status.last_analysis_time,
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
        home_assistant_url=config.home_assistant.url,
        camera_entity=config.home_assistant.camera_entity,
        printer_state_entity=config.home_assistant.printer_state_entity,
        selected_printer={
            "id": service.printer.id,
            "name": service.printer.name,
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
        certainty_threshold_notify=config.monitoring.certainty_threshold_notify,
        certainty_threshold_auto_pause=config.monitoring.certainty_threshold_auto_pause,
        auto_pause_delay_minutes=config.monitoring.auto_pause_delay_minutes,
        printers=[
            {
                "id": printer.id,
                "name": printer.name,
                "camera_entity": printer.camera_entity,
                "printer_state_entity": printer.printer_state_entity,
            }
            for printer in config.get_printers()
        ],
    )


@app.get("/captures/{filename}")
async def get_capture(filename: str):
    """Get a capture image."""
    capture_path = Path("/data/captures") / filename

    if not capture_path.exists():
        raise HTTPException(status_code=404, detail="Capture not found")

    if not str(capture_path).startswith(str(Path("/data/captures").resolve())):
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(capture_path, media_type="image/jpeg")


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
