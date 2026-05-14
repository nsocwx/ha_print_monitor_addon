"""Main FastAPI application."""
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import load_config, save_config, AppConfig
from app.core.database import init_db, get_session
from app.api import events, actions
from app.api.schemas import StatusResponse, HealthResponse, ConfigResponse
from app.services.monitor import PrintMonitorService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global state
config: AppConfig = None
monitor_service: PrintMonitorService = None
app_start_time: datetime = datetime.utcnow()
monitoring_task: asyncio.Task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global config, monitor_service, monitoring_task

    # Startup
    logger.info("Starting HA Print Monitor")

    # Load configuration
    try:
        config = load_config()
        logger.info("Configuration loaded successfully")
        logger.info(f"Home Assistant URL: {config.home_assistant.url}")
        logger.info(f"Camera entity: {config.home_assistant.camera_entity}")
        logger.info(f"Printer state entity: {config.home_assistant.printer_state_entity}")
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
        monitor_service = PrintMonitorService(config)
        await monitor_service.start()
    except Exception as e:
        logger.error(f"Failed to initialize monitor service: {e}")
        raise

    # Start monitoring task
    async def run_monitoring():
        while True:
            try:
                await monitor_service.monitor_cycle()
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

    if monitor_service:
        await monitor_service.stop()

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
        session = next(get_session())
        session.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    # Check Home Assistant
    try:
        await monitor_service.ha_service.test_connection()
        ha_status = "healthy"
    except Exception as e:
        logger.error(f"HA health check failed: {e}")
        ha_status = "unhealthy"

    # Check analyzer
    analyzer_status = "healthy" if monitor_service.analyzer.initialized else "unhealthy"

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


@app.get("/api/status", response_model=StatusResponse)
async def get_status(session: Session = Depends(get_session)) -> StatusResponse:
    """Get current application status."""
    active_event = None
    if monitor_service.active_event_id:
        from sqlmodel import select
        from app.models.event import PrinterEvent

        event = session.exec(
            select(PrinterEvent).where(
                PrinterEvent.event_id == monitor_service.active_event_id
            )
        ).first()

        if event:
            from app.api.schemas import EventResponse

            active_event = EventResponse(**event.dict())

    return StatusResponse(
        app_version="0.1.0",
        running=monitor_service.running,
        monitoring_enabled=config.monitoring.enabled,
        printer_state=monitor_service.printer_state,
        printer_printing=monitor_service.printer_state
        in config.home_assistant.printing_states
        if monitor_service.printer_state
        else False,
        last_capture_time=monitor_service.last_capture_time,
        last_analysis_time=monitor_service.last_analysis_time,
        active_event=active_event,
        health_status="healthy",
    )


@app.get("/api/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Get current configuration."""
    return ConfigResponse(
        app_base_url=config.app_base_url,
        home_assistant_url=config.home_assistant.url,
        camera_entity=config.home_assistant.camera_entity,
        printer_state_entity=config.home_assistant.printer_state_entity,
        analyzer_provider=config.model.provider,
        analyzer_device=config.model.device,
        detection_threshold=config.monitoring.detection_threshold,
        frame_interval_seconds=config.monitoring.frame_interval_seconds,
        certainty_threshold_notify=config.monitoring.certainty_threshold_notify,
        certainty_threshold_auto_pause=config.monitoring.certainty_threshold_auto_pause,
        auto_pause_delay_minutes=config.monitoring.auto_pause_delay_minutes,
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
