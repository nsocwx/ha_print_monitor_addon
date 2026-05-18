# HA Print Monitor

HA Print Monitor watches a 3D printer camera while Home Assistant says the printer is actively printing. It captures frames, runs model analysis, records events, sends Home Assistant Companion notifications with images and actions, and can pause a print through a configured Home Assistant service when safety checks allow it.

## Highlights

- Uses Home Assistant ingress for the dashboard.
- Uses the Supervisor-provided Home Assistant API token.
- Supports multiple printer configurations.
- Sends notification images through Home Assistant local media.
- Handles Pause, Ignore, and Snooze notification buttons through Home Assistant mobile app action events.
- Stores runtime data under `/data`, including captures, logs, backups, database, and model files.

## Setup

Configure the add-on options, start the add-on, then open the dashboard with **Open Web UI**. Use a safe test state first and send a test notification before relying on auto-pause.

For full setup notes and troubleshooting, open the documentation tab or visit the project repository.
