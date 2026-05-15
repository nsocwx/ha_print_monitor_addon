# Changelog

## 0.3.0

- Repackaged the app as a Home Assistant add-on with `config.yaml`, `build.yaml`, ingress on internal port `8080`, and `/data` persistence.
- Switched Home Assistant API access to Supervisor-provided `SUPERVISOR_TOKEN`; long-lived tokens are no longer configured or documented for the add-on.
- Replaced `/data/config.yaml` loading with `/data/options.json` add-on options and schema validation.
- Updated dashboard URLs for Home Assistant ingress and removed hardcoded localhost browser calls.
- Added `external_base_url` for mobile push image/action links when a phone-reachable URL is needed.
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
