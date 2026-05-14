"""Quick Reference Guide - HA Print Monitor

This file is a quick lookup for developers and operators.
"""

# Quick Reference Guide

## Directory Structure

```
ha_print_monitor/
├── app/                          # Application package
│   ├── analysis/                 # Image analysis (pluggable)
│   ├── api/                      # REST API endpoints
│   ├── models/                   # Database models (SQLModel)
│   ├── services/                 # Business logic services
│   ├── core/                     # Core utilities (config, db)
│   ├── utils.py                  # Helper functions
│   ├── logging_config.py         # Logging setup
│   └── maintenance.py            # Data cleanup tasks
├── static/                       # Web UI files
├── tests/                        # Unit tests
├── main.py                       # FastAPI application
├── run.py                        # Entry point
├── requirements.txt              # Python dependencies
├── Dockerfile                    # Docker image
├── docker-compose.yml            # Docker Compose config
└── data/                         # Persistent volume
```

## Common Commands

### Development

```bash
# Install dependencies
pip install -r requirements.txt

# Configure application
mkdir -p data
cp config.yaml.example data/config.yaml
nano data/config.yaml

# Run locally
python -m uvicorn main:app --reload --port 8080

# Run tests
pytest tests/

# Run with specific test file
pytest tests/test_config.py -v
```

### Docker

```bash
# Build image
docker build -t ha-print-monitor .

# Run container
docker run -p 8080:8080 -v $(pwd)/data:/data ha-print-monitor

# Using Docker Compose
docker-compose up -d
docker-compose logs -f
docker-compose down
```

## Configuration Quick Reference

### Minimal config.yaml

```yaml
app_base_url: "http://localhost:8080"
home_assistant:
  url: "http://homeassistant.local:8123"
  token: "your-token"
  camera_entity: "camera.printer"
  printer_state_entity: "sensor.printer_status"
  pause_service:
    domain: "button"
    service: "press"
    target: "button.pause"
monitoring:
  enabled: true
security:
  action_token: "your-secret-token"
```

### Environment Variable Overrides

```bash
export HA_URL=http://homeassistant:8123
export HA_TOKEN=your-token
export HA_CAMERA_ENTITY=camera.printer
export HA_PRINTER_STATE_ENTITY=sensor.status
export APP_BASE_URL=http://localhost:8080
export ACTION_TOKEN=your-secret
export MONITORING_ENABLED=true
export FRAME_INTERVAL_SECONDS=30
```

## API Quick Reference

### Status Endpoints

```bash
# Health check
curl http://localhost:8080/health

# Application status
curl http://localhost:8080/api/status

# Configuration
curl http://localhost:8080/api/config
```

### Event Endpoints

```bash
# List events
curl http://localhost:8080/api/events?limit=10

# Get specific event
curl http://localhost:8080/api/events/event_xxx

# Get active event
curl http://localhost:8080/api/events/active/current
```

### Action Endpoints (require token)

```bash
# Pause printer
curl -X POST "http://localhost:8080/api/actions/pause?event_id=event_xxx&token=secret"

# Ignore event
curl -X POST "http://localhost:8080/api/actions/ignore?event_id=event_xxx&token=secret"

# Snooze (default 15 min)
curl -X POST "http://localhost:8080/api/actions/snooze?event_id=event_xxx&token=secret&minutes=15"

# Acknowledge
curl -X POST "http://localhost:8080/api/actions/acknowledge?event_id=event_xxx&token=secret"
```

### Image Endpoints

```bash
# Download captured image
curl http://localhost:8080/captures/capture_abc123.jpg > image.jpg
```

## Database

### Location
```
/data/app.db
```

### Tables

```sql
-- List all events
SELECT event_id, issue_type, certainty, severity, status FROM printer_events;

-- Get active events
SELECT * FROM printer_events WHERE status = 'active';

-- Get recent events
SELECT * FROM printer_events ORDER BY created_at DESC LIMIT 10;

-- Get auto-paused events
SELECT * FROM printer_events WHERE auto_paused = true;
```

### Connect to Database

```bash
sqlite3 /data/app.db

# In sqlite3:
.tables                    # List tables
.schema printer_events     # Show schema
SELECT COUNT(*) FROM printer_events;  # Count events
```

## File Locations

```
/data/app.db                    # SQLite database
/data/config.yaml               # Configuration file
/data/captures/                 # Captured images
/data/logs/                     # Application logs
```

## Logs

### View Logs

```bash
# Docker
docker-compose logs -f ha-print-monitor

# Local file
tail -f /data/logs/ha-print-monitor.log

# Following last 50 lines
tail -50 /data/logs/ha-print-monitor.log

# Search for errors
grep ERROR /data/logs/ha-print-monitor.log
```

## Troubleshooting

### Dashboard not loading

```bash
# Check if app is running
curl http://localhost:8080/health

# Check logs
docker-compose logs ha-print-monitor | grep error

# Restart container
docker-compose restart ha-print-monitor
```

### Home Assistant connection failed

```bash
# Check HA is reachable
curl -H "Authorization: Bearer YOUR_TOKEN" http://homeassistant:8123/api/

# Check token in config (don't log it!)
# Verify URL is correct in config.yaml
```

### No images being captured

```bash
# Check camera entity exists in HA
# Camera must be accessible via Home Assistant API
# Check entity ID matches config

# Verify in app logs
tail -f /data/logs/ha-print-monitor.log | grep camera
```

### Auto-pause not triggering

```bash
# Check certainty threshold
# Check event severity level
# Check pause service configuration
# Look for pause attempt errors in logs
```

## Code Organization

### Models (`app/models/`)
- `event.py` - PrinterEvent, CameraCapture, SystemLog

### Services (`app/services/`)
- `home_assistant.py` - HA API client
- `monitor.py` - Main monitoring service

### Analysis (`app/analysis/`)
- `base.py` - Abstract interfaces
- `baseline.py` - Baseline implementation
- `factory.py` - Analyzer factory

### API (`app/api/`)
- `schemas.py` - Pydantic schemas
- `events.py` - Event endpoints
- `actions.py` - Action endpoints

### Core (`app/core/`)
- `config.py` - Configuration management
- `database.py` - Database setup

## Adding a Real ML Model

1. Create class in `app/analysis/yourmodel.py`
2. Inherit from `ImageAnalyzer`
3. Implement `initialize()`, `analyze_frame()`, `cleanup()`
4. Register in `app/analysis/factory.py`
5. Update config.yaml with `provider: "yourmodel"`

Example:
```python
class YOLOAnalyzer(ImageAnalyzer):
    def __init__(self, model_path, device):
        # Initialize model
    
    async def analyze_frame(self, image_data, context):
        # Run inference
        # Return DetectionResult
```

## Performance Tuning

### Capture Interval
- Default: 30s
- Lower for faster response, higher for less CPU/network
- Setting: `monitoring.frame_interval_seconds`

### Confirmation Frames
- Default: 2 (require 2 consecutive detections)
- Increase to reduce false positives
- Setting: `monitoring.confirmation_frames`

### Thresholds
- `certainty_threshold_notify`: 0.70 (70%)
- `certainty_threshold_auto_pause`: 0.85 (85%)
- Increase to reduce alerts
- Settings under `monitoring`

### Data Retention
- Images: 7 days default
- Events: 30 days default
- Logs: 7 days
- Settings under `retention`

## Deployment Checklist

- [ ] Generate secure action_token (use `secrets.token_urlsafe(32)`)
- [ ] Create config.yaml with all settings
- [ ] Test HA connection before deploying
- [ ] Set proper file permissions on /data
- [ ] Use HTTPS in production (reverse proxy)
- [ ] Configure firewall to only allow needed access
- [ ] Set up monitoring/alerting for the monitor itself
- [ ] Document your entity IDs and service setup
- [ ] Test pause action works before relying on auto-pause
- [ ] Set up log rotation/cleanup

## Support Resources

- README.md - Full documentation
- ARCHITECTURE.md - System design
- HOME_ASSISTANT_SETUP.md - HA integration examples
- API endpoints have built-in /docs (Swagger UI) when app runs

## Key URLs

- Dashboard: http://localhost:8080
- API Docs: http://localhost:8080/docs
- Health: http://localhost:8080/health
- Status: http://localhost:8080/api/status
