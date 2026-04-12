"""Device triggers — the point-and-click automation UX.

Without these, a user who wants "run my script when the BeoRemote Play
button is held" has to write YAML that matches an event entity by ID
and filters attributes by hand. With them, HA's automation editor shows
a dropdown per Lydbro device:

    Device: Lydbro One
    Trigger: Play button held

Each trigger type translates to an ``event`` platform trigger under the
hood, matching the HA bus events fired from :class:`LydbroCoordinator`
on ``button_press`` / ``menu_selection`` / ``scene_button`` frames.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    EVENT_BUS_BUTTON,
    EVENT_BUS_MENU,
    EVENT_BUS_SCENE,
    KNOWN_BUTTONS,
)

# Trigger-type string convention:
#   button_<name>_<kind>    e.g. button_Play_click, button_Home_hold
#   scene_<position>        e.g. scene_N
#   menu_select             (single trigger, filter on name in the action)
#
# Click is the default kind. Hold and double are rare-but-valuable,
# release is almost never what a user wants so we skip it — if someone
# needs it they can still use the raw event entity.
TRIGGER_KINDS = ("click", "hold", "double")


def _button_trigger_types() -> list[str]:
    out: list[str] = []
    for name in KNOWN_BUTTONS:
        for kind in TRIGGER_KINDS:
            out.append(f"button_{name}_{kind}")
    return out


def _scene_trigger_types() -> list[str]:
    return [f"scene_{pos}" for pos in ("top_left", "top_right", "bottom_left", "bottom_right")]


TRIGGER_TYPES: frozenset[str] = frozenset(
    _button_trigger_types() + _scene_trigger_types() + ["menu_select"]
)

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict[str, Any]]:
    """List the triggers available for this device."""
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in sorted(TRIGGER_TYPES)
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a device trigger.

    Translates the Lydbro-specific trigger type into an event-platform
    trigger that matches on the HA bus events fired by the coordinator.
    """
    trigger_type: str = config[CONF_TYPE]
    device_id: str = config[CONF_DEVICE_ID]

    if trigger_type.startswith("button_"):
        # button_<Name>_<kind>  — split from the right so button names
        # that contain underscores (e.g. "Play_Pause") still parse.
        body = trigger_type[len("button_") :]
        name, _, kind = body.rpartition("_")
        event_type = EVENT_BUS_BUTTON
        event_data = {"device_id": device_id, "name": name, "kind": kind}
    elif trigger_type.startswith("scene_"):
        position = trigger_type[len("scene_") :]
        event_type = EVENT_BUS_SCENE
        event_data = {"device_id": device_id, "position": position}
    elif trigger_type == "menu_select":
        event_type = EVENT_BUS_MENU
        event_data = {"device_id": device_id}
    else:
        # TRIGGER_SCHEMA already rejects anything outside TRIGGER_TYPES
        # via vol.In, so this branch is unreachable in practice — it
        # exists purely as a defensive backstop if the schema and the
        # type list ever drift apart.
        raise ValueError(  # pragma: no cover
            f"Unknown lydbro trigger type: {trigger_type}"
        )

    # Use plain string keys — the HA-internal event_trigger module
    # re-exports CONF_PLATFORM / CONF_EVENT_TYPE / CONF_EVENT_DATA but
    # they aren't in its public (py.typed) surface, so mypy strict
    # complains about attr-defined on them. The schema accepts the
    # string keys directly.
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            "platform": "event",
            "event_type": event_type,
            "event_data": event_data,
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )
