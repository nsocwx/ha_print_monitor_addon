# HA Print Monitor Home Assistant Add-on

HA Print Monitor watches a 3D printer camera while Home Assistant says the printer is actively printing. It captures frames, runs model analysis, records events, sends notifications, and can pause a print through a configured Home Assistant service when safety checks allow it.

This fork is packaged for Home Assistant OS or Home Assistant Supervised. It uses Home Assistant ingress for the dashboard and the Supervisor-provided API token for Home Assistant API access.

## Requirements

- Home Assistant OS or Home Assistant Supervised
- A Home Assistant camera entity for the printer
- A printer state entity whose state clearly identifies active printing
- A pause service/entity, such as `button.press` on a safe pause button
- A notify service, such as `notify.mobile_app_mobile_phone`
- A model file under `/data/models` when using the `onnx` provider

## Installation

1. Copy this repository folder into your Home Assistant add-ons directory, or add it as a local/custom add-on repository.
2. In Home Assistant, go to Settings -> Add-ons -> Add-on Store.
3. Refresh the store if needed, open **HA Print Monitor**, and install it.
4. Configure the add-on options.
5. Start the add-on and open the dashboard with **Open Web UI**.

The dashboard is served internally on port `8080` for ingress. The add-on does not publish a host port by default.

## Authentication

The add-on uses `SUPERVISOR_TOKEN`, which Home Assistant injects automatically because `homeassistant_api: true` is enabled in `config.yaml`.

No Home Assistant long-lived access token is required for this add-on version. Do not paste a token into the options. The Supervisor token is not shown in diagnostics, UI responses, errors, or normal logs.

Long-lived access tokens are only relevant for the standalone Docker version, not this add-on fork.

## Options

Configure options in the Home Assistant add-on Configuration tab. Example:

```yaml
external_base_url: null
printers:
  - printer_id: mk4s
    name: MK4s
    camera_entity: camera.example_camera
    printer_state_entity: sensor.example_printer_state
    printing_states:
      - printing
      - Printing
      - running
    pause_service:
      domain: button
      service: press
      target: button.example_pause_print
      data: {}
    notify_services:
      - notify.mobile_app_mobile_phone
monitoring:
  enabled: true
  frame_interval_seconds: 30
  confirmation_frames: 3
  certainty_threshold_notify: 0.70
  certainty_threshold_auto_pause: 0.85
  auto_pause_delay_minutes: 15
  snooze_minutes: 15
  cooldown_minutes: 10
model:
  provider: onnx
  model_path: /data/models/model.onnx
  device: cpu
camera:
  stale_after_seconds: 120
  capture_timeout_seconds: 15
  retry_count: 2
  retry_backoff_seconds: 3
retention:
  keep_clear_captures_hours: 24
  keep_event_captures_days: 30
  keep_events_days: 90
  max_capture_storage_mb: 2048
security:
  action_token_expiration_hours: 24
advanced:
  log_level: info
  json_logs: false
```

Runtime data is stored under `/data`, including the SQLite database, captures, logs, backups, and model files.

## Ingress And Mobile Links

Ingress is excellent for using the dashboard inside Home Assistant. Browser API calls, static assets, and capture images use relative URLs so they work when Home Assistant mounts the add-on under an ingress path.

Mobile push notification images and action URLs are different: phones may need a URL reachable from the phone's network. Set `external_base_url` to an externally reachable trusted URL if you want notification images and action links. This could be Home Assistant Cloud/Nabu Casa, a reverse proxy, or another trusted route to the add-on.

If `external_base_url` is not configured, notifications can still be sent, but image previews and action links may be omitted or may not work outside the Home Assistant UI.

## Safe Pause Testing

1. Configure one printer with the correct camera, printer state entity, pause service, and notify service.
2. Start with a safe/non-printing printer state and send a test notification from the dashboard.
3. Confirm that your pause service target is correct before printing.
4. Test pause behavior only when it is safe for the printer. The add-on checks that the latest issue frame is recent, the printer is still in a configured printing state, and the event has not already been paused.

## Troubleshooting

- **HA API 401/403**: Confirm the add-on is running under Home Assistant Supervisor and `homeassistant_api: true` is present. Restart the add-on so Home Assistant injects `SUPERVISOR_TOKEN`.
- **Camera capture fails**: Check that `camera_entity` exists, returns an image through Home Assistant, and responds before `capture_timeout_seconds`.
- **Entity not found**: Verify the exact entity IDs in Developer Tools -> States.
- **Notification image not showing**: Configure `external_base_url` with a phone-reachable URL. Ingress-only URLs often are not usable by push notification clients.
- **Ingress path issues**: Refresh the dashboard and confirm you opened it via **Open Web UI**. The UI uses relative fetch and image URLs.
- **Model load failure**: Confirm `model.provider`, `model_path`, and CPU/CUDA device settings. Put ONNX models under `/data/models`.

## Backup

Back up `/data`. It contains `options.json`, the database, captures, logs, backups, and model files. Home Assistant add-on backups should include this data.

## Updating

Update the add-on from Home Assistant after pulling or replacing the local/custom repository. Review release notes, then rebuild/restart the add-on. Keep a backup of `/data` before major updates.

## Development Only

A Docker Compose file is kept at `docs/dev/docker-compose.yml` for local testing. It is not the recommended installation path and still expects a development `SUPERVISOR_TOKEN` or mock token.
