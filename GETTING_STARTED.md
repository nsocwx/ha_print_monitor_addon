"""HA Print Monitor - Getting Started Guide

Follow this guide to get your print monitor up and running in 10 minutes.
"""

# Getting Started - 10 Minute Setup

## Step 1: Prerequisites (1 minute)

You need:
- Docker and Docker Compose installed
- Home Assistant instance running
- Access to your Home Assistant
- Your printer camera entity ID
- Your printer state entity ID

## Step 2: Get Home Assistant Token (2 minutes)

1. Go to Home Assistant > Settings > Users
2. Click your username (bottom of list)
3. Scroll to "Long-Lived Access Tokens" section
4. Click "Create Token"
5. Name it "HA Print Monitor"
6. Copy the entire token (save it securely)

## Step 3: Find Your Entity IDs (2 minutes)

In Home Assistant, go to Developer Tools > States and find:

**Camera Entity**: Look for `camera.*`
- Example: `camera.prusa_camera`

**Printer State Entity**: Look for `sensor.*` with printer status
- Example: `sensor.prusa_print_status`
- Or `binary_sensor.printer_printing`

**Pause Action**: Usually a button
- Example: `button.prusa_pause_print`
- Or can be a service like `button.press`

**Notify Service**: Look under Developer Tools > Services > domain: notify
- Example: `notify.mobile_app_alex_phone`

## Step 4: Create Configuration (2 minutes)

In the project directory:

```bash
mkdir -p data
cp config.yaml.example data/config.yaml
nano data/config.yaml  # or your preferred editor
```

Edit these sections:

```yaml
app_base_url: "http://192.168.1.YOUR_DOCKER_HOST:8080"

home_assistant:
  url: "http://homeassistant.local:8123"  # Your HA URL
  token: "eyJhbGciOi..."  # Your long-lived token
  camera_entity: "camera.your_camera"  # Your camera
  printer_state_entity: "sensor.your_printer_status"  # Your printer state
  pause_service:
    target: "button.your_pause"  # Your pause button
  notify_services:
    - "notify.mobile_app_your_phone"  # Your notify service

security:
  action_token: "GenerateARandomSecureTokenHere123!@#"
```

## Step 5: Start the Application (1 minute)

```bash
# Make sure you're in the project directory
cd ha_print_monitor

# Start with Docker Compose
docker-compose up -d

# Check that it's running
docker-compose logs
```

You should see: "Uvicorn running on 0.0.0.0:8080"

## Step 6: Access the Dashboard (1 minute)

Open your browser and go to:

```
http://192.168.1.YOUR_DOCKER_HOST:8080
```

You should see:
- Current printer status
- Health checks (all should be green)
- No active issues yet
- Configuration summary

## Step 7: Test It (1 minute)

### Test Camera Connection

1. Start a print on your 3D printer
2. Wait for the first monitor cycle (default 30s)
3. You should see:
   - "Printing" status
   - Last capture time updated
   - Last analysis time updated

### Test Notification (optional)

If you want to trigger a test:
1. Artificially lower certainty thresholds temporarily
2. Or check the logs for analysis results
3. When an issue is detected, you'll get a notification

## What's Next?

### Configure Auto-Pause (optional)

Edit these in `data/config.yaml`:

```yaml
monitoring:
  auto_pause_delay_minutes: 15    # Wait 15 min before pausing
  certainty_threshold_auto_pause: 0.85  # 85% confidence required
```

### Adjust Monitoring Frequency

```yaml
monitoring:
  frame_interval_seconds: 30  # Check every 30 seconds
```

(Lower = more responsive but higher CPU/bandwidth)

### View Events

Access the API directly:

```bash
# Recent events
curl http://localhost:8080/api/events

# Active event
curl http://localhost:8080/api/events/active/current

# System health
curl http://localhost:8080/health
```

### View Database

```bash
# Connect to database
sqlite3 data/app.db

# List events
.tables
SELECT * FROM printer_events LIMIT 5;
```

## Troubleshooting

### Dashboard shows "Connection failed"

**Solution**: Check logs
```bash
docker-compose logs -f
```

Look for error messages about Home Assistant connection.

Verify:
- HA_URL is correct
- HA_TOKEN is valid (tokens can expire)
- Your firewall allows connection

### No camera images captured

**Solution**: Verify entity

In Home Assistant Developer Tools > States, check your camera_entity exists and shows a state.

Test in Home Assistant UI > Media > Photos to ensure camera works.

### Container won't start

**Solution**: Check Docker

```bash
docker-compose up  # Without -d to see errors
```

Ensure no port 8080 conflicts:
```bash
# Linux/Mac
lsof -i :8080

# Windows
netstat -ano | findstr :8080
```

### High false positive rate

**Solution**: Adjust thresholds

Edit `data/config.yaml`:
```yaml
monitoring:
  certainty_threshold_notify: 0.85  # Increase from 0.70
```

Or add more confirmation frames:
```yaml
monitoring:
  confirmation_frames: 3  # Require 3 detections instead of 2
```

## Common Configuration Patterns

### Basic Prusa Setup

```yaml
home_assistant:
  camera_entity: "camera.prusa_camera"
  printer_state_entity: "sensor.prusa_print_status"
  printing_states: ["printing", "paused"]
  pause_service:
    domain: "button"
    service: "press"
    target: "button.prusa_pause_print"
  notify_services:
    - "notify.mobile_app_phone"
```

### Multiple Notify Services

```yaml
home_assistant:
  notify_services:
    - "notify.mobile_app_alex_phone"
    - "notify.mobile_app_family_phone"
    - "notify.telegram"
```

### Conservative Auto-Pause (less aggressive)

```yaml
monitoring:
  certainty_threshold_auto_pause: 0.95
  auto_pause_delay_minutes: 30
  confirmation_frames: 3
```

### Aggressive Monitoring (more responsive)

```yaml
monitoring:
  certainty_threshold_notify: 0.60
  frame_interval_seconds: 15
  confirmation_frames: 1
```

## Important Security Notes

### Production Deployment

1. **Change action_token**
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Use HTTPS**
   - Put behind nginx/traefik with SSL
   - Never expose without HTTPS in production

3. **Protect /data volume**
   - Use proper file permissions
   - Don't expose to untrusted networks

4. **Manage HA token**
   - Store securely
   - Use environment variables in production
   - Rotate regularly

5. **Database backup**
   - Regularly backup `/data/app.db`
   - Keep configuration backed up

## Monitor Your Monitor

### Check Health Regularly

```bash
curl http://localhost:8080/health | python -m json.tool
```

Should show all components as "healthy".

### Monitor Logs

```bash
docker-compose logs --tail 50 -f
```

Watch for:
- HA connection errors
- Camera capture failures
- Model errors
- Notification send failures

## Performance Tips

### Reduce CPU Usage

- Increase `frame_interval_seconds` (e.g., 60s)
- Increase `confirmation_frames`
- Increase certainty thresholds

### Reduce Storage Usage

- Decrease `keep_images_days` (e.g., 3 days)
- Run cleanup task regularly (daily)

### Improve Responsiveness

- Decrease `frame_interval_seconds` (e.g., 15s)
- Decrease `certainty_threshold_notify`
- Use smaller captured images if possible

## Next Steps

1. **Test thoroughly**: Run several prints and verify detection works
2. **Tune thresholds**: Adjust certainty levels based on results
3. **Enable auto-pause**: Only after testing manual pause
4. **Monitor logs**: Watch for errors or issues
5. **Add real model**: Replace baseline with YOLO when ready

## Support

- **README.md** - Full documentation
- **ARCHITECTURE.md** - System design
- **QUICK_REFERENCE.md** - Command reference
- **HOME_ASSISTANT_SETUP.md** - HA examples

## Quick Reference

```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# Logs
docker-compose logs -f

# Restart
docker-compose restart ha-print-monitor

# Reset (careful!)
docker-compose down -v  # Deletes database!

# Rebuild
docker-compose up --build
```

---

**You're all set!** Your print monitor should be running and ready to protect your prints. 🖨️✅
