#!/usr/bin/env bash
# Deploy custom_components/lydbro/ to a development HA instance and restart it.
#
# Assumes SSH access to the HA host with config at /root/config/,
# and a long-lived access token for the restart API call.
#
# Usage: HA_SSH=<user>@<ha-host> HA_URL=http://<ha-host>:8123 HA_TOKEN=<token> ./deploy.sh
set -euo pipefail

if [[ -z "${HA_SSH:-}" || -z "${HA_URL:-}" || -z "${HA_TOKEN:-}" ]]; then
  echo "HA_SSH, HA_URL and HA_TOKEN must all be set — see usage in the header" >&2
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
