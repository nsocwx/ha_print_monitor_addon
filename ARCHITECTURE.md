"""Architecture Documentation for HA Print Monitor"""

# HA Print Monitor - Architecture

## Overview

HA Print Monitor is a containerized web service that monitors 3D printers via Home Assistant. It captures camera feeds, analyzes frames for print failures using configurable image recognition models, sends actionable notifications, and can automatically pause the printer.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Home Assistant Instance                         │
│                                                                       │
│  ┌────────────────────┐  ┌─────────────────┐  ┌──────────────────┐ │
│  │ Camera Entity      │  │ Printer State   │  │ Notify Services  │ │
│  │ (Video Feed)       │  │ (Sensor)        │  │ (Mobile App)     │ │
│  └────────┬───────────┘  └────────┬────────┘  └────────┬─────────┘ │
│           │                      │                    │             │
└───────────┼──────────────────────┼────────────────────┼─────────────┘
            │ REST API             │                    │
            │ /api/camera_proxy    │ /api/states        │ /api/services
            │                      │                    │
        ┌───┴──────────────────────┴────────────────────┴──────────────┐
        │                                                               │
        │         HA Print Monitor Container                           │
        │                                                               │
        │  ┌──────────────────────────────────────────────────────┐   │
        │  │  FastAPI Web Service (Uvicorn)                       │   │
        │  │  - Listens on :8080/                                 │   │
        │  │  - REST API endpoints (/api/*)                       │   │
        │  │  - Static web dashboard (/)                          │   │
        │  │  - Image serving (/captures/*)                       │   │
        │  └──────────────────────────────────────────────────────┘   │
        │           ▲                                   ▲              │
        │           │                                   │              │
        │  ┌────────┴──────────────────────────────────┴────────────┐ │
        │  │  Monitoring Service (Background Task)                  │ │
        │  │                                                        │ │
        │  │  1. Poll printer state (every 5s)                     │ │
        │  │  2. If printing:                                      │ │
        │  │     - Capture frame (every 30s configurable)          │ │
        │  │     - Analyze frame                                   │ │
        │  │     - Detect issues                                   │ │
        │  │     - Manage auto-pause countdown                     │ │
        │  │     - Send notifications                              │ │
        │  │     - Track event lifecycle                           │ │
        │  │  3. If not printing:                                  │ │
        │  │     - Auto-resolve active event                       │ │
        │  └────────────────────────────────────────────────────────┘ │
        │           ▲                 ▲                                │
        │           │                 │                                │
        │  ┌────────┴──────┐  ┌───────┴──────────────────────────┐   │
        │  │ Image Analyzer│  │ Home Assistant Service          │   │
        │  │ (Pluggable)   │  │                                  │   │
        │  │               │  │ - get_state()                   │   │
        │  │ BaselineAnalyzer  - get_camera_image()            │   │
        │  │ - Motion detect   - call_service()                │   │
        │  │ - Edge detection  - send_notification()           │   │
        │  │ - Heuristics      - test_connection()             │   │
        │  │                   │                                 │   │
        │  │ (Future)          │ (via httpx AsyncClient)        │   │
        │  │ - YOLOAnalyzer    │                                 │   │
        │  │ - ONNXAnalyzer    │                                 │   │
        │  │ - TFLiteAnalyzer  │                                 │   │
        │  └─────────────────┘ └──────────────────────────────────┘   │
        │           ▲                                                  │
        │           │                                                  │
        │  ┌────────┴────────────────────────────────────────────┐   │
        │  │  SQLite Database & File Storage                    │   │
        │  │                                                     │   │
        │  │  /data/app.db                                      │   │
        │  │  ├─ printer_events (detection events)             │   │
        │  │  ├─ camera_captures (image metadata)              │   │
        │  │  └─ system_logs (application logs)                │   │
        │  │                                                     │   │
        │  │  /data/captures/ (captured images)                │   │
        │  │  /data/logs/ (application logs)                   │   │
        │  │  /data/config.yaml (configuration)                │   │
        │  └────────────────────────────────────────────────────┘   │
        │                                                               │
        └───────────────────────────────────────────────────────────────┘
                                    │
                                    │ Docker Volume
                                    ▼
                            ┌──────────────┐
                            │ /data/       │ (Persistent Storage)
                            │              │
                            │ - app.db     │
                            │ - captures/  │
                            │ - logs/      │
                            │ - config.yaml│
                            └──────────────┘
```

## Component Breakdown

### 1. FastAPI Web Service

**File**: `main.py`

- Entry point for the application
- Defines all REST API endpoints
- Manages application lifecycle (startup/shutdown)
- Serves static web dashboard
- Handles CORS and security

**Key Routes**:
- `GET /` - Dashboard HTML
- `GET /health` - Health check
- `GET /api/status` - Current status
- `GET /api/config` - Configuration
- `GET /api/events` - Event list
- `POST /api/actions/*` - User actions

### 2. Monitoring Service

**File**: `app/services/monitor.py`

The core service responsible for:
- Polling Home Assistant for printer state
- Capturing camera frames when printing
- Running image analysis
- Managing the event lifecycle
- Handling auto-pause logic
- Sending notifications

**Key Methods**:
- `monitor_cycle()` - Main monitoring loop (runs every 30s)
- `_handle_detection()` - Process detection results
- `_check_auto_pause()` - Check if auto-pause should trigger
- `_send_notification()` - Send Home Assistant notification

### 3. Home Assistant Integration

**File**: `app/services/home_assistant.py`

Async HTTP client for interacting with Home Assistant:
- `get_state()` - Retrieve entity state
- `get_camera_image()` - Get camera snapshot
- `call_service()` - Call Home Assistant service
- `send_notification()` - Send notification
- `test_connection()` - Verify connectivity

### 4. Image Analysis Framework

**Directory**: `app/analysis/`

**Base Classes** (`base.py`):
- `ImageAnalyzer` - Abstract interface
- `DetectionResult` - Result dataclass
- `AnalysisContext` - Analysis context with history

**Implementations**:
- `BaselineAnalyzer` (`baseline.py`) - Proof-of-concept heuristic analyzer
  - Motion detection (frame differencing)
  - Brightness anomaly detection
  - Edge density analysis
  - Layer shift detection
  
- `AnalyzerFactory` (`factory.py`) - Factory for creating analyzers
  - Extensible for YOLO, ONNX, TensorFlow Lite, etc.

### 5. Database Models

**File**: `app/models/event.py`

**Tables**:
- `printer_events` - Detection events with full lifecycle tracking
- `camera_captures` - Image metadata
- `system_logs` - Application logs

**Event Lifecycle States**:
- `active` - Issue detected, awaiting user action
- `acknowledged` - User acknowledged but didn't pause/ignore
- `ignored` - User ignored this issue
- `snoozed` - User snoozed for N minutes
- `paused` - Printer was paused (manually or auto)
- `resolved` - Printer stopped printing

### 6. Configuration Management

**File**: `app/core/config.py`

Uses Pydantic Settings for:
- Loading from `config.yaml`
- Environment variable overrides
- Type validation
- Nested configuration objects

**Config Structure**:
```yaml
app_base_url: string
home_assistant:
  url, token, camera_entity, printer_state_entity, printing_states,
  pause_service (domain, service, target, data),
  notify_services
monitoring:
  enabled, frame_interval_seconds, confirmation_frames,
  certainty_threshold_notify, certainty_threshold_auto_pause,
  auto_pause_delay_minutes, snooze_minutes
model:
  provider (baseline|yolo|onnx), model_path, device
security:
  action_token
retention:
  keep_images_days, keep_events_days
```

### 7. Database Setup

**File**: `app/core/database.py`

- SQLModel for ORM (SQLAlchemy + Pydantic)
- SQLite database at `/data/app.db`
- Session management for API endpoints
- `init_db()` creates tables on startup

### 8. API Endpoints

**File**: `app/api/*.py`

**events.py**:
- `GET /api/events` - List events
- `GET /api/events/{id}` - Get event
- `GET /api/events/active/current` - Get active event

**actions.py**:
- `POST /api/actions/pause` - Pause printer
- `POST /api/actions/ignore` - Ignore issue
- `POST /api/actions/snooze` - Snooze notifications
- `POST /api/actions/acknowledge` - Acknowledge issue

All actions require valid `action_token` query parameter.

### 9. Web Dashboard

**File**: `static/dashboard.html`

Single-page static HTML application that:
- Refreshes every 5 seconds
- Shows current printer status
- Displays active issue with countdown
- Lists recent events
- Shows system health
- Polls `/api/status`, `/api/health`, `/api/config`, `/api/events`

## Workflow: Detection to Auto-Pause

```
1. Monitor Loop Runs
   ↓
2. Get Printer State from HA
   ├─ Not Printing? → Skip analysis, resolve active event, exit
   └─ Printing? → Continue
     ↓
3. Capture Image from HA Camera
   ↓
4. Save Capture to /data/captures/
   ↓
5. Run Image Analysis
   ├─ No Issue Detected? → Log result, exit
   └─ Issue Detected? → Continue with detection_score
     ↓
6. Check Thresholds
   ├─ certainty < notify_threshold? → Log only, exit
   └─ certainty >= notify_threshold? → Continue
     ↓
7. Is This a New Issue?
   ├─ No (continuing existing event) → Update event, go to 10
   └─ Yes (first detection) → Create event, continue
     ↓
8. Send Notification to User
   ├─ Include image, issue type, certainty
   ├─ Include action buttons (Pause, Ignore, Snooze)
   └─ Include auto-pause countdown
     ↓
9. Check Auto-Pause Eligibility
   ├─ certainty < auto_pause_threshold? → Exit (no auto-pause)
   ├─ severity not high/critical? → Exit
   └─ Eligible? → Set auto_pause_deadline (now + 15 min)
     ↓
10. Wait for User Action or Deadline
    ├─ User clicks Pause → Immediately call pause service
    ├─ User clicks Ignore → Stop auto-pause
    ├─ User clicks Snooze → Delay auto-pause
    ├─ Deadline reached? → Continue to 11
    └─ Printer stops printing? → Resolve event, exit
      ↓
11. Re-Check Issue (Optional Confirmation)
    ├─ Issue still detected? → Continue to 12
    └─ Issue gone? → Resolve event, exit
      ↓
12. Auto-Pause
    ├─ Call Home Assistant pause service
    ├─ Mark event as auto_paused
    ├─ Send "Print Auto-Paused" notification
    └─ Log action
```

## Safety Mechanisms

1. **Confirmation Frames**: Require detection across N frames
2. **Threshold Validation**: Certainty must meet thresholds
3. **Severity Checking**: Only high/critical issues auto-pause
4. **State Verification**: Check printer still printing before pause
5. **Re-Verification**: Optional re-check before auto-pause
6. **User Override**: Any user action cancels auto-pause
7. **Cooldown**: Don't repeatedly notify for same event
8. **False Positive Prevention**: Combine multiple heuristics

## Data Flow: Configuration

```
1. Application Start
   ↓
2. Load config.yaml from /data/config.yaml
   ↓
3. Override with environment variables
   (HA_URL, HA_TOKEN, APP_BASE_URL, etc.)
   ↓
4. Validate configuration with Pydantic
   ↓
5. Pass to services (HA, Monitor, Analyzer)
   ↓
6. Web API exposes current config at GET /api/config
```

## Extensibility

### Adding a New Image Analyzer

1. Create new class inheriting `ImageAnalyzer`:
   ```python
   class YOLOAnalyzer(ImageAnalyzer):
       async def analyze_frame(image_data, context) -> DetectionResult:
           # Load model, run inference, return result
   ```

2. Update factory in `app/analysis/factory.py`:
   ```python
   elif provider == "yolo":
       return YOLOAnalyzer(model_path, device)
   ```

3. Configure in `config.yaml`:
   ```yaml
   model:
     provider: "yolo"
     model_path: "/data/models/print-failure.pt"
   ```

### Adding New Notification Channels

1. Extend notification sending in `app/services/monitor.py`
2. Add to `notify_services` config list
3. Home Assistant already supports: Telegram, Discord, Slack, etc.

### Adding New User Actions

1. Add endpoint in `app/api/actions.py`
2. Implement business logic
3. Add to notification data payload
4. Document action_token requirement

## Performance Considerations

- **Frame Capture**: ~1-5 seconds per capture (network dependent)
- **Analysis**: ~100-500ms for baseline, varies for real models
- **Database**: SQLite suitable for <1M events, consider PostgreSQL for scale
- **Storage**: ~100-500KB per image, configurable retention (7 days default)
- **Memory**: ~100-300MB baseline usage, varies with frame history size
- **Network**: ~1-2MB per capture + notifications

## Testing

- `tests/test_config.py` - Configuration loading
- `tests/test_event.py` - Event models and state transitions
- `tests/test_analysis.py` - Analyzer functionality

Run with: `pytest tests/`

## Deployment

### Docker Compose
- Single-command deployment
- Volume mounts for persistence
- Environment variables for configuration
- Health checks enabled

### Kubernetes (Future)
- StatefulSet for persistence
- ConfigMap for configuration
- PersistentVolume for data
- Service for networking

## Logging

- Structured logging to `/data/logs/ha-print-monitor.log`
- Log rotation (5 backups, 10MB each)
- JSON format option for aggregation
- Rotation and cleanup of old logs (7-day retention)

## Security

- Action tokens prevent unauthorized pause/ignore/snooze
- Safe file path handling prevents directory traversal
- HA tokens filtered from logs
- HTTPS recommended in production
- IP whitelisting possible with reverse proxy
