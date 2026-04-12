"""Service handlers for Lydbro.

All services take a ``device_id`` (HA device registry id) to identify
which Lydbro One they target. A single HA instance can manage several
Lydbro bridges, so we can't default to "the" device.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import DOMAIN
from .coordinator import LydbroCoordinator


SERVICE_SEND_REMOTE_KEY = "send_remote_key"
SERVICE_TV_SEND_KEY = "tv_send_key"
SERVICE_TV_LAUNCH_APP = "tv_launch_app"
SERVICE_SONOS_PLAY_URI = "sonos_play_uri"
SERVICE_SONOS_PLAY_SPOTIFY = "sonos_play_spotify"
SERVICE_SONOS_PLAY_FAVORITE = "sonos_play_favorite"
SERVICE_SONOS_SET_VOLUME = "sonos_set_volume"
SERVICE_SONOS_ADJUST_VOLUME = "sonos_adjust_volume"
SERVICE_SONOS_JOIN = "sonos_join"
SERVICE_RESCAN_DISCOVERY = "rescan_discovery"


_DEVICE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string}, extra=vol.ALLOW_EXTRA
)


def _coordinator_for(hass: HomeAssistant, call: ServiceCall) -> LydbroCoordinator:
    """Resolve a device_id from the call back to a coordinator instance."""
    device_id = call.data[ATTR_DEVICE_ID]
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise HomeAssistantError(f"Unknown device {device_id}")

    for ident_domain, ident_value in device.identifiers:
        if ident_domain != DOMAIN:
            continue
        for coordinator in hass.data.get(DOMAIN, {}).values():
            if coordinator.device_id == ident_value:
                return coordinator

    raise HomeAssistantError(f"Device {device_id} is not a Lydbro device")


def async_register_services(hass: HomeAssistant) -> None:
    """Register all Lydbro services. Called once per HA process."""

    async def send_remote_key(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call)
        await coord.async_send_cmd("send_remote_key", key=call.data["key"])

    async def tv_send_key(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call)
        await coord.async_send_cmd(
            "tv_send_key",
            key=call.data["key"],
            device_ip=call.data.get("device_ip", ""),
            device_type=call.data.get("device_type", ""),
        )

    async def tv_launch_app(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call)
        await coord.async_send_cmd(
            "tv_launch_app",
            param=call.data["app"],
            device_ip=call.data.get("device_ip", ""),
            device_type=call.data.get("device_type", ""),
        )

    async def sonos_play_uri(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call)
        await coord.async_send_cmd(
            "sonos_play_uri",
            param=call.data["uri"],
            device_ip=call.data.get("device_ip", ""),
        )

    async def sonos_play_spotify(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call)
        await coord.async_send_cmd(
            "sonos_play_spotify",
            param=call.data["uri"],
            device_ip=call.data.get("device_ip", ""),
        )

    async def sonos_play_favorite(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call)
        await coord.async_send_cmd(
            "sonos_play_favorite",
            param=call.data["favorite"],
            device_ip=call.data.get("device_ip", ""),
        )

    async def sonos_set_volume(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call)
        await coord.async_send_cmd(
            "sonos_set_volume",
            volume=call.data["volume"],
            device_ip=call.data.get("device_ip", ""),
        )

    async def sonos_adjust_volume(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call)
        await coord.async_send_cmd(
            "sonos_adjust_volume",
            delta=call.data["delta"],
            device_ip=call.data.get("device_ip", ""),
        )

    async def sonos_join(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call)
        await coord.async_send_cmd(
            "sonos_join",
            param=call.data["master_ip"],
            device_ip=call.data.get("device_ip", ""),
        )

    async def rescan_discovery(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call)
        await coord.async_send_cmd("rescan_discovery")

    def _schema(extra: dict) -> vol.Schema:
        return _DEVICE_SCHEMA.extend(extra)

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
        schema=_schema(
            {
                vol.Required("key"): cv.string,
                vol.Optional("device_ip"): cv.string,
                vol.Optional("device_type"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TV_LAUNCH_APP,
        tv_launch_app,
        schema=_schema(
            {
                vol.Required("app"): cv.string,
                vol.Optional("device_ip"): cv.string,
                vol.Optional("device_type"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SONOS_PLAY_URI,
        sonos_play_uri,
        schema=_schema(
            {vol.Required("uri"): cv.string, vol.Optional("device_ip"): cv.string}
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SONOS_PLAY_SPOTIFY,
        sonos_play_spotify,
        schema=_schema(
            {vol.Required("uri"): cv.string, vol.Optional("device_ip"): cv.string}
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SONOS_PLAY_FAVORITE,
        sonos_play_favorite,
        schema=_schema(
            {
                vol.Required("favorite"): cv.string,
                vol.Optional("device_ip"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SONOS_SET_VOLUME,
        sonos_set_volume,
        schema=_schema(
            {
                vol.Required("volume"): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=100)
                ),
                vol.Optional("device_ip"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SONOS_ADJUST_VOLUME,
        sonos_adjust_volume,
        schema=_schema(
            {
                vol.Required("delta"): vol.All(
                    vol.Coerce(int), vol.Range(min=-50, max=50)
                ),
                vol.Optional("device_ip"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SONOS_JOIN,
        sonos_join,
        schema=_schema(
            {
                vol.Required("master_ip"): cv.string,
                vol.Optional("device_ip"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESCAN_DISCOVERY,
        rescan_discovery,
        schema=_DEVICE_SCHEMA,
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_SEND_REMOTE_KEY,
        SERVICE_TV_SEND_KEY,
        SERVICE_TV_LAUNCH_APP,
        SERVICE_SONOS_PLAY_URI,
        SERVICE_SONOS_PLAY_SPOTIFY,
        SERVICE_SONOS_PLAY_FAVORITE,
        SERVICE_SONOS_SET_VOLUME,
        SERVICE_SONOS_ADJUST_VOLUME,
        SERVICE_SONOS_JOIN,
        SERVICE_RESCAN_DISCOVERY,
    ):
        hass.services.async_remove(DOMAIN, service)
