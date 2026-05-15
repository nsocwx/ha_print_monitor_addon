# Changelog

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
