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
- Switched Home Assistant API access to Supervisor-provided `SUPERVISOR_TOKEN`.
- Replaced `/data/config.yaml` loading with `/data/options.json` add-on options and schema validation.
- Updated dashboard URLs for Home Assistant ingress.
