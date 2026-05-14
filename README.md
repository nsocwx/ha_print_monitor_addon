# HA Print Monitor - Home Assistant 3D Print Monitoring

This is a containerized web application that monitors 3D print cameras via Home Assistant, uses image recognition to detect potential print failures, and can automatically pause the printer with user notification.

## Features

- **Real-time Camera Monitoring**: Captures frames from any Home Assistant camera
- **AI-Powered Detection**: Detects print failures like spaghetti failures, layer shifts, blobs, and more
- **Smart Notifications**: Sends actionable notifications via Home Assistant with pause/snooze/ignore options
- **Auto-Pause**: Automatically pauses printer after timeout if high-confidence issue detected
- **Event History**: Stores all detection events in SQLite database
- **Web Dashboard**: Simple real-time dashboard showing printer state and recent events
- **Modular ML**: Supports swapping between different analysis models (baseline, YOLO, ONNX, etc.)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│          Home Assistant Instance                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Printer     │  │  Camera      │  │  Notify      │  │
│  │  State       │  │  Feed        │  │  Services    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└────────────┬─────────────────────────────┬──────────────┘
             │ REST/WS API                 │
             │                             │
     ┌───────▼─────────────────────────────▼────────────┐
     │     HA Print Monitor Container                   │
     │  ┌────────────────────────────────────────────┐  │
     │  │  FastAPI Web Service                       │  │
     │  │  - REST API for status/events/actions      │  │
     │  │  - Web Dashboard (static HTML+JS)          │  │
     │  ├────────────────────────────────────────────┤  │
     │  │  Monitor Service                           │  │
     │  │  - Polls Home Assistant state              │  │
     │  │  - Captures camera frames                  │  │
     │  │  - Runs image analysis                     │  │
     │  │  - Manages event lifecycle                 │  │
     │  ├────────────────────────────────────────────┤  │
     │  │  Image Analyzer (Pluggable)                │  │
     │  │  - Baseline (heuristic)                    │  │
     │  │  - YOLO (real model)                       │  │
     │  │  - ONNX (future)                           │  │
     │  ├────────────────────────────────────────────┤  │
     │  │  SQLite Database & File Storage            │  │
     │  │  /data/app.db - Events                     │  │
     │  │  /data/captures/ - Images                  │  │
     │  └────────────────────────────────────────────┘  │
     └────────────────────────────────────────────────────┘
             │
             │ Docker Volume: /data
             │
         ┌───▼───┐
         │ /data │ (persistent storage)
         └───────┘
```

## Quick Start

### 1. Prerequisites

- Home Assistant instance running
- A configured printer camera entity
- A printer state entity (sensor or binary_sensor)
- Home Assistant long-lived access token
- Docker and Docker Compose

### 2. Get Long-Lived Token from Home Assistant

1. Go to Home Assistant > Settings > Users
2. Click your username at the bottom
3. Scroll to "Long-Lived Access Tokens" section
4. Click "Create Token"
5. Give it a name like "HA Print Monitor" and copy the token

### 3. Identify Your Entities

In Home Assistant developer tools (Developer Tools > States), find:

- **Camera entity**: Look for `camera.*` (e.g., `camera.prusa_camera`)
- **Printer state entity**: Look for `sensor.printer_*` (e.g., `sensor.prusa_print_status`)
- **Notify services**: Available at Developer Tools > Services (domain: `notify`)
- **Pause action**: Usually a `button.printer_pause` or call to `button.press` service

### 4. Configure the App

Create `data/config.yaml`:

```yaml
app_base_url: "http://192.168.1.100:8080"

home_assistant:
  url: "http://homeassistant.local:8123"
  token: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  camera_entity: "camera.prusa_camera"
  printer_state_entity: "sensor.prusa_print_status"
  printing_states:
    - "printing"
    - "paused"
  pause_service:
    domain: "button"
    service: "press"
    target: "button.prusa_pause_print"
    data: {}
  notify_services:
    - "notify.mobile_app_alex_phone"

monitoring:
  enabled: true
  frame_interval_seconds: 30
  confirmation_frames: 2
  certainty_threshold_notify: 0.70
  certainty_threshold_auto_pause: 0.85
  auto_pause_delay_minutes: 15
  snooze_minutes: 15

model:
  provider: "baseline"
  model_path: null
  options_path: null
  prototypes_path: null
  auto_download: true
  models_dir: "/data/models/printguard"
  device: "cpu"

security:
  action_token: "generate-a-long-random-string-here"

retention:
  keep_images_days: 7
  keep_events_days: 30
```

### 5. Start the Container

```bash
docker-compose up -d
```

Access the dashboard at: http://localhost:8080

### 6. Set Up Home Assistant Notifications

In Home Assistant `automations.yaml` or via UI automation editor:

```yaml
alias: "HA Print Monitor Alert"
trigger:
  platform: webhook
  webhook_id: "your-webhook-id"
action:
  service: notify.mobile_app_phone
  data:
    title: "Print Alert"
    message: "{{ trigger.json.message }}"
    data:
      actions:
        - action: URI
          title: "Pause"
          uri: "{{ trigger.json.pause_url }}"
```

Or use the app's built-in notifications which send directly to Home Assistant notify services.

## API Endpoints

### Status & Health

- **GET /health** - System health check
- **GET /api/status** - Current status
- **GET /api/config** - Current configuration

### Events

- **GET /api/events** - List all events (query: `limit`, `status`)
- **GET /api/events/{event_id}** - Get specific event
- **GET /api/events/active/current** - Get current active event

### Actions (require action_token)

- **POST /api/actions/pause** - Pause printer
  ```
  ?event_id=event_xxx&token=your-token
  ```
- **POST /api/actions/ignore** - Ignore issue
  ```
  ?event_id=event_xxx&token=your-token
  ```
- **POST /api/actions/snooze** - Snooze notifications
  ```
  ?event_id=event_xxx&token=your-token&minutes=15
  ```
- **POST /api/actions/acknowledge** - Acknowledge issue
  ```
  ?event_id=event_xxx&token=your-token
  ```

### Images

- **GET /captures/{filename}** - Download captured image
- **GET /** - Web dashboard

## Configuration Reference

### home_assistant

- `url`: Home Assistant URL (e.g., `http://homeassistant.local:8123`)
- `token`: Long-lived access token
- `camera_entity`: Camera entity ID (e.g., `camera.printer`)
- `printer_state_entity`: Printer state entity (e.g., `sensor.status`)
- `printing_states`: List of states that count as "printing"
- `pause_service`: Service call config for pausing
- `notify_services`: List of notify service names

### monitoring

- `enabled`: Enable/disable monitoring
- `frame_interval_seconds`: Capture interval (default: 30s)
- `confirmation_frames`: Require N detections before alerting
- `certainty_threshold_notify`: Certainty % to send notification (default: 70%)
- `certainty_threshold_auto_pause`: Certainty % for auto-pause (default: 85%)
- `auto_pause_delay_minutes`: Minutes to wait before auto-pause (default: 15)
- `snooze_minutes`: Default snooze duration (default: 15)

### model

- `provider`: `baseline` | `onnx` | `yolo` | etc.
- `model_path`: Path to model file. If `provider` is `onnx` and this is empty, the app downloads PrintGuard `model.onnx` from Hugging Face.
- `options_path`: Optional path to PrintGuard `opt.json`
- `prototypes_path`: Optional path to PrintGuard `prototypes.pkl`
- `auto_download`: Download missing PrintGuard ONNX artifacts automatically when using `provider: "onnx"`
- `models_dir`: Directory where downloaded PrintGuard artifacts are stored
- `device`: `cpu` | `cuda` | etc.

### PrintGuard ONNX

To use the PrintGuard model from Hugging Face, set:

```yaml
model:
  provider: "onnx"
  auto_download: true
  models_dir: "/data/models/printguard"
  device: "cpu"
```

On startup, the app downloads `model.onnx`, `opt.json`, and `prototypes.pkl` from `nsocwx/PrintGuard` if they are not already present. You can also mount the files manually and set `model_path`, `options_path`, and `prototypes_path` explicitly.

## Adding a Real ML Model

The app uses a pluggable analyzer architecture. To add a real model:

### 1. Create a New Analyzer Class

```python
# app/analysis/yolo.py
from .base import ImageAnalyzer, DetectionResult, AnalysisContext

class YOLOAnalyzer(ImageAnalyzer):
    def __init__(self, model_path: str, device: str):
        self.model_path = model_path
        self.device = device
        self.model = None

    def initialize(self) -> bool:
        # Load YOLO model
        return True

    async def analyze_frame(self, image_data: bytes, context: Optional[AnalysisContext]) -> DetectionResult:
        # Run YOLO inference
        # Return DetectionResult with issue_detected, certainty, etc.
        pass

    def cleanup(self):
        pass
```

### 2. Register in Factory

```python
# app/analysis/factory.py
elif provider == "yolo":
    return YOLOAnalyzer(model_path, device)
```

### 3. Update config.yaml

```yaml
model:
  provider: "yolo"
  model_path: "/data/models/print-failure-yolo.pt"
  device: "cuda"
```

## Security Notes

- **Change action_token** in production - use a long random string
- **Use HTTPS** in production - configure a reverse proxy (nginx, traefik)
- **Protect /api/actions** - consider adding IP whitelist or additional auth
- **Don't log tokens** - the app filters HA token from logs
- **Use environment variables** for sensitive config in production
- **Keep Home Assistant token secure** - only used server-side

## How Auto-Pause Works

1. **Detection**: Frame analysis detects potential issue
2. **Threshold Check**: Certainty > auto_pause threshold (85% default)?
3. **Severity Check**: Is severity high or critical?
4. **Notification**: User is notified immediately with action buttons
5. **Countdown**: 15-minute timer starts (configurable)
6. **User Action**: 
   - Click "Pause" → Immediately pauses
   - Click "Ignore" → No auto-pause
   - Click "Snooze" → Delay auto-pause 15 more minutes
   - Do nothing → Auto-pause triggers
7. **Confirmation**: Before pausing, re-check if issue still present
8. **Pause**: Call Home Assistant pause service
9. **Notification**: Send second notification that print was paused

## Troubleshooting

### Dashboard shows "Connection failed" for Home Assistant

- Check HA URL is correct and accessible
- Verify long-lived token is valid (hasn't expired)
- Check firewall between container and HA
- View logs: `docker-compose logs ha-print-monitor`

### No camera images captured

- Verify camera entity ID exists in HA
- Camera must be accessible via Home Assistant camera proxy
- Check HA user has permission to access camera
- Test in HA UI first: Development Tools > Call Service

### Events showing but no auto-pause

- Check `certainty_threshold_auto_pause` setting
- Verify issue severity is high/critical
- Check pause service configuration matches your setup
- Review logs for pause attempt errors

### High false positive rate

- Adjust `certainty_threshold_notify` higher
- Increase `confirmation_frames` requirement
- Switch to better model (replace baseline)
- Add more camera adjustments (lighting, angle)

### Database errors

- Check `/data` volume has write permissions
- Ensure sufficient disk space
- Check logs for SQLite errors
- May need to delete `/data/app.db` to reset

## Docker Compose Example

```yaml
version: '3.8'

services:
  ha-print-monitor:
    build: .
    container_name: ha-print-monitor
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
    environment:
      - DATA_DIR=/data
      - HA_URL=http://homeassistant:8123
      - HA_TOKEN=eyJhbGciOi...
      - HA_CAMERA_ENTITY=camera.printer
      - HA_PRINTER_STATE_ENTITY=sensor.printer_status
      - APP_BASE_URL=http://192.168.1.100:8080
      - ACTION_TOKEN=your-secure-random-token
    networks:
      - ha_network

networks:
  ha_network:
    external: true
```

## Model Architecture

The baseline analyzer uses:

- **Motion Detection**: Compares consecutive frames to detect unusual movement
- **Brightness Analysis**: Detects nozzle-related anomalies via lighting changes
- **Edge Detection**: Identifies blob and filament issues
- **Layer Shift Detection**: Analyzes edge alignment across frames

**Note**: The baseline is a proof-of-concept. For production, integrate a real model:
- **YOLO**: https://github.com/ultralytics/yolov5
- **TensorFlow Lite**: For edge deployment
- **OpenAI Vision**: For cloud-based analysis (future)

## Building from Source

```bash
git clone <repo>
cd ha-print-monitor

# Create data directory
mkdir -p data

# Copy example config
cp config.yaml.example data/config.yaml

# Edit configuration
nano data/config.yaml

# Build and run
docker-compose up --build
```

## Development

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Locally (without Docker)

```bash
export DATA_DIR=/tmp/ha-print-monitor
mkdir -p $DATA_DIR
cp config.yaml.example $DATA_DIR/config.yaml
python -m uvicorn main:app --reload --port 8080
```

### Run Tests

```bash
pytest tests/
```

## Logs

View logs with Docker:

```bash
docker-compose logs -f ha-print-monitor
```

Logs include:
- Startup configuration
- HA connection status
- Camera capture events
- Model analysis results
- Notifications sent
- User actions
- Pause events
- Errors and warnings

## Roadmap

- [ ] YOLO model integration
- [ ] Web UI for config management
- [ ] Historical graph of detections
- [ ] Telegram/Discord notifications
- [ ] Manual pause/resume button
- [ ] Print time/layer prediction
- [ ] Failure rate statistics
- [ ] Mobile app
- [ ] WebSocket live updates

## License

MIT

## Support

Report issues at: (repo)/issues

For Home Assistant help, see: https://www.home-assistant.io/

## Credits

Inspired by Obico (formerly Spaghetti Detective) and developed for Home Assistant integration.
