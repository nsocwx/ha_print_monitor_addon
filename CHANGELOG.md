# Changelog

## 0.3.12

- Fixed Home Assistant pause service calls to send `entity_id` as service data for `button.press`.
- Fixed flattened add-on pause options so `pause_service_target` maps to the selected printer pause service.
- Fixed ignored, snoozed, paused, and resolved events continuing to appear as active issues with action buttons.

## 0.3.11

- Removed the external notification URL setting entirely.
- Added Home Assistant local media publishing for notification image previews.
- Added Home Assistant Companion native notification action handling through `mobile_app_notification_action` websocket events.
- Applied existing event-capture retention to `/media/ha_print_monitor` notification image copies.
- Added add-on package README, DOCS, and CHANGELOG files so Home Assistant can render the Info and Changelog views.

## 0.3.0

- Repackaged the app as a Home Assistant add-on with `config.yaml`, `build.yaml`, ingress on internal port `8080`, and `/data` persistence.
- Switched Home Assistant API access to Supervisor-provided `SUPERVISOR_TOKEN`; long-lived tokens are no longer configured or documented for the add-on.
- Replaced `/data/config.yaml` loading with `/data/options.json` add-on options and schema validation.
- Updated dashboard URLs for Home Assistant ingress and removed hardcoded localhost browser calls.
- Added native Home Assistant Companion notification actions handled through `mobile_app_notification_action` websocket events.
- Added Home Assistant local media publishing for notification image previews and removed the external notification URL requirement.
- Hardened capture serving, diagnostics redaction, notification URL logging, and add-on startup validation.
- Moved Docker Compose into `docs/dev` as a development-only path.

## 0.2.0

- Added production Docker defaults: non-root container, healthcheck, restart policy, persistent `/data`, and log limits.
- Added version metadata in `/health` and dashboard health.
- Added signed one-time notification action tokens with replay prevention.
- Added pause safety interlocks for stale frames, printer state changes, duplicate pause calls, severity, and confidence.
- Added Home Assistant retries, timeout configuration, auth/network error separation, and startup entity validation warnings.
- Added camera health counters, stale detection, fallback snapshot URL support, and malformed image protection.
- Added model inference duration and model error/status tracking.
- Added diagnostics and backup endpoints.
- Expanded retention settings and disk protection for capture storage.
- Documented reverse proxy, Home Assistant token setup, backups, troubleshooting, and safe pause testing.
