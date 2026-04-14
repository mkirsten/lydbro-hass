"""Service handlers for Lydbro.

The Lydbro One is a bridge from the BeoRemote One to Sonos / TVs / HA —
it talks outbound to those targets when the remote triggers it. There
is intentionally no HA→bridge→Sonos or HA→bridge→TV path: HA already
controls Sonos and TVs directly, so routing through the ESP32 would
just be a detour.

The only service we expose is ``send_remote_key`` — injecting a
virtual BeoRemote key press so automations can reuse the bridge's
dispatch logic. Bridge-level admin actions (reboot, reset pairing,
disconnect BeoRemote) live on the device page as button entities
rather than services; they're one-off actions, not automation inputs.

All services take a ``device_id`` (HA device registry id) to identify
which Lydbro One they target. A single HA instance can manage several
Lydbro bridges, so we can't default to "the" device.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import LydbroCoordinator

SERVICE_SEND_REMOTE_KEY = "send_remote_key"
SERVICE_TV_SEND_KEY = "tv_send_key"
SERVICE_TV_LAUNCH_APP = "tv_launch_app"


_DEVICE_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.string}, extra=vol.ALLOW_EXTRA)


def _coordinator_for(hass: HomeAssistant, call: ServiceCall) -> LydbroCoordinator:
    """Resolve a device_id from the call back to a coordinator instance."""
    device_id = call.data[ATTR_DEVICE_ID]
    device = dr.async_get(hass).async_get(device_id)
    if device is not None:
        lydbro_idents = {v for d, v in device.identifiers if d == DOMAIN}
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator: LydbroCoordinator | None = getattr(entry, "runtime_data", None)
            if coordinator is not None and coordinator.device_id in lydbro_idents:
                return coordinator

    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="device_not_found",
        translation_placeholders={"device_id": device_id},
    )


def async_register_services(hass: HomeAssistant) -> None:
    """Register all Lydbro services. Idempotent across config entries."""

    if hass.services.has_service(DOMAIN, SERVICE_SEND_REMOTE_KEY):
        return

    def _schema(extra: dict[Any, Any]) -> vol.Schema:
        return _DEVICE_SCHEMA.extend(extra)

    async def send_remote_key(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call)
        await coord.async_send_cmd("send_remote_key", key=call.data["key"])

    async def tv_send_key(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call)
        await coord.async_send_cmd("tv_send_key", key=call.data["key"])

    async def tv_launch_app(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call)
        # Wire field is "name" — adapter_tv_dispatch looks up args.param
        # against the configured TV source table by user-visible name.
        await coord.async_send_cmd("tv_launch_app", name=call.data["app"])

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_REMOTE_KEY,
        send_remote_key,
        schema=_schema({vol.Required("key"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TV_SEND_KEY,
        tv_send_key,
        schema=_schema({vol.Required("key"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TV_LAUNCH_APP,
        tv_launch_app,
        schema=_schema({vol.Required("app"): cv.string}),
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    for svc in (SERVICE_SEND_REMOTE_KEY, SERVICE_TV_SEND_KEY, SERVICE_TV_LAUNCH_APP):
        hass.services.async_remove(DOMAIN, svc)
