#!/usr/bin/env bash
# Seed $DSH_HOME on first boot, then hand off to dsh. Existing files on the
# /data volume win, so operator edits (in the web UI or by hand) survive a
# redeploy; we only ever fill in what's missing.
set -euo pipefail

DSH_HOME="${DSH_HOME:-/data/dsh}"
mkdir -p "$DSH_HOME"

if [ ! -f "$DSH_HOME/settings.yaml" ]; then
  echo "[dsh] seeding $DSH_HOME/settings.yaml (redacted-proxy provider)"
  cp /app/seed/settings.yaml "$DSH_HOME/settings.yaml"
fi

if [ -z "${PROXY_TOKEN:-}" ]; then
  echo "[dsh] WARNING: PROXY_TOKEN is unset — redacted-proxy calls will 401" >&2
fi

# The web profile auto-initialises from dsh's shipped templates on first run.
# Pick "redacted-proxy / auto" once in Settings -> Models; the choice persists
# to $DSH_HOME/settings.yaml on the volume.
exec dsh "$@"
