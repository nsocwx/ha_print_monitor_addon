#!/usr/bin/env bash
set -euo pipefail

if [ -z "${SUPERVISOR_TOKEN:-}" ]; then
  echo "SUPERVISOR_TOKEN is missing. This must run as a Home Assistant add-on with homeassistant_api enabled." >&2
  exit 1
fi

exec uvicorn main:app --host 0.0.0.0 --port 8080 --proxy-headers
