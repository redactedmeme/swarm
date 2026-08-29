#!/bin/bash
# Auto-start custom stacks after umbreOS update/reboot.
# Idempotent - safe to run multiple times.
# Invoked at boot by the `autostart-bootstrap` container (restart: always), NOT by cron:
# umbreOS updates remove the cron binary entirely and reset /etc, but /var/lib/docker survives.

LOG=/home/umbrel/autostart.log
exec >> "$LOG" 2>&1
echo "===== autostart-stacks.sh starting $(date -Is) ====="

# --- self-heal: kernel limits that umbreOS resets on /etc wipe ---
# ~50 containers exhaust the default fs.inotify.max_user_instances=256, which makes
# homelab-cadvisor crash-loop with "inotify_add_watch /sys/fs/cgroup: no space left on device".
docker run --rm --privileged --pid=host alpine nsenter -t 1 -m -u -i -n -p -- sh -c '
  sysctl -w fs.inotify.max_user_instances=1024
  sysctl -w fs.inotify.max_user_watches=524288
  printf "fs.inotify.max_user_instances = 1024\nfs.inotify.max_user_watches = 524288\n" > /etc/sysctl.d/98-inotify-cadvisor.conf
' || echo "WARN: inotify sysctl self-heal failed"

# --- self-heal: restore umbrel's docker group membership (umbreOS updates wipe /etc/group members) ---
docker run --rm -v /etc/group:/etc/group -v /etc/passwd:/etc/passwd:ro docker:27-cli addgroup umbrel docker 2>/dev/null || true

# --- custom stacks ---
# NOTE: errors are logged, not swallowed. A silent `2>/dev/null` here hid three dead
# stacks during the 2026-08-29 outage recovery.
for stack in homelab-platform swarm-infra glance open-webui nextcloud-ts redacted-chan; do
  if [ -d "/home/umbrel/$stack" ]; then
    echo "--- up: $stack"
    ( cd "/home/umbrel/$stack" && docker compose up -d ) || echo "ERROR: $stack failed to start"
  else
    echo "WARN: /home/umbrel/$stack missing, skipping"
  fi
done

# --- Tailscale serve persistence (webchat :8090, swarm-runtime :3000) ---
# Re-apply declarative serve config in case the tailscaled state did not reload.
for i in $(seq 1 30); do
  if docker exec tailscale_web_1 tailscale status >/dev/null 2>&1; then
    docker exec tailscale_web_1 tailscale serve --bg --https=8090 8090 >/dev/null 2>&1
    docker exec tailscale_web_1 tailscale serve --bg --https=3000 3000 >/dev/null 2>&1
    echo "tailscale serve re-applied"
    break
  fi
  sleep 5
done

echo "===== autostart-stacks.sh done $(date -Is) ====="
