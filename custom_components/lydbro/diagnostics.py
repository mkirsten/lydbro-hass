"""Diagnostics support for Lydbro.

Downloadable from the device page in the HA UI. Dumps the full hello
frame, current state snapshot, and connection status so a user can
attach it to a bug report without copy-pasting JSON from logs.

Nothing on this device is sensitive (no credentials, no tokens, no
personal data — just local IPs of Sonos/TVs on the same LAN), so we
don't redact anything. If that ever changes, redact here.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import LydbroConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LydbroConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "connection": {
            "host": coordinator.host,
            "port": coordinator.port,
            "available": coordinator.available,
            "device_id": coordinator.device_id,
        },
        "hello": coordinator.hello,
        "state": coordinator.state,
    }
