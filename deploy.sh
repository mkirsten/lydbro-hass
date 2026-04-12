#!/usr/bin/env bash
# Deploy custom_components/lydbro/ to the lab HA instance and restart it.
#
# HA lives in a UTM VM on macmini, reachable as homeassistant.local
# with SSH user `markus` and config at /root/config/. Token in
# ~/.claude/CLAUDE.md (HA_TOKEN env var).
set -euo pipefail

HA_SSH="${HA_SSH:-markus@homeassistant.local}"
HA_URL="${HA_URL:-http://192.168.1.234:8123}"

if [[ -z "${HA_TOKEN:-}" ]]; then
  echo "HA_TOKEN not set — export it or source from ~/.claude/CLAUDE.md" >&2
  exit 1
fi

cd "$(dirname "$0")"

echo "→ scp custom_components/lydbro → $HA_SSH:/root/config/custom_components/"
scp -r -O custom_components/lydbro "$HA_SSH:/root/config/custom_components/"

echo "→ restart HA"
curl -sSf -X POST \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  "$HA_URL/api/services/homeassistant/restart" >/dev/null

echo "→ waiting for HA to come back…"
for i in {1..60}; do
  if curl -sSf -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/" >/dev/null 2>&1; then
    echo "✓ HA is up (took ${i}s)"
    exit 0
  fi
  sleep 1
done

echo "✗ HA did not come back within 60s" >&2
exit 1
