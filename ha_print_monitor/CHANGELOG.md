# Changelog

## 0.3.14

- Added no-cache headers for the dashboard HTML so removed action buttons do not linger in Home Assistant or browser cache.
- Kept the dashboard action surface limited to Pause and Ignore.

## 0.3.13

- Removed Acknowledge and Snooze from dashboard and mobile notification actions.
- Kept Ignore as the operator dismissal action alongside Pause.
- Added optional per-printer `print_progress_entity` support and dashboard progress display.

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
- Switched Home Assistant API access to Supervisor-provided `SUPERVISOR_TOKEN`.
- Replaced `/data/config.yaml` loading with `/data/options.json` add-on options and schema validation.
- Updated dashboard URLs for Home Assistant ingress.
