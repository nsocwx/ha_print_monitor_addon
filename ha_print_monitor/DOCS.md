# HA Print Monitor Documentation

## Requirements

- Home Assistant OS or Home Assistant Supervised.
- A Home Assistant camera entity for the printer.
- A printer state entity whose state clearly identifies active printing.
- A pause service/entity, such as `button.press` on a safe pause button.
- A notify service, such as `notify.mobile_app_mobile_phone`.
- A model file under `/data/models` when using the `onnx` provider.

## Notifications

Notification action buttons do not require an external add-on URL. The add-on sends Home Assistant Companion action IDs and listens for `mobile_app_notification_action` events over the Supervisor websocket proxy, then consumes the signed one-time action token inside the add-on.

Notification images are published through Home Assistant local media. The add-on copies the event frame into `/media/ha_print_monitor` and sends the Companion app a relative `/media/local/ha_print_monitor/...` image URL. The `media:rw` map in `config.yaml` gives the add-on access to that location.

## Retention

Runtime captures live under `/data/captures`. Notification media copies live under `/media/ha_print_monitor`.

- Clear captures follow `retention.keep_clear_captures_hours`.
- Event capture files and their matching notification media copies follow `retention.keep_event_captures_days`.
- Event records follow `retention.keep_events_days`.
- Non-event captures are also limited by `retention.max_capture_storage_mb`.

## Safe Pause Testing

1. Configure one printer with the correct camera, printer state entity, pause service, and notify service.
2. Start with a safe/non-printing printer state and send a test notification from the dashboard.
3. Confirm that your pause service target is correct before printing.
4. Test pause behavior only when it is safe for the printer.

The add-on checks that the latest issue frame is recent, the printer is still in a configured printing state, and the event has not already been paused.

## Troubleshooting

- **HA API 401/403**: Confirm the add-on is running under Home Assistant Supervisor and `homeassistant_api: true` is present.
- **Camera capture fails**: Check that `camera_entity` exists, returns an image through Home Assistant, and responds before `capture_timeout_seconds`.
- **Notification image not showing**: Confirm Home Assistant local media is enabled and the add-on has the `media:rw` map.
- **Notification actions not firing**: Confirm the Home Assistant Companion app receives action buttons and check the add-on logs for the websocket listener.
- **Model load failure**: Confirm `model.provider`, `model_path`, and CPU/CUDA device settings.
