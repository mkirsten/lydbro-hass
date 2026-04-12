"""Event platform — BeoRemote One button, menu, and scene events.

Three event entities are created per device:
  * ``event.<device>_button``  — every physical button press. The
    ``event_type`` is the button name ("Play", "Next", ...); ``kind``
    (click / hold / double / release) and ``mode`` (MUSIC / TV / ...)
    come through as attributes.
  * ``event.<device>_menu``    — vendor-menu selections from the
    remote's custom UI. ``event_type`` is the menu item name.
  * ``event.<device>_scene``   — the four corner "scene" buttons
    (N/E/S/W).

Device triggers in :mod:`.device_trigger` build a nicer automation-
editor UX on top of these entities.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, KNOWN_BUTTONS, SIGNAL_EVENT
from .coordinator import LydbroCoordinator
from .entity import LydbroEntity

_LOGGER_NAME = __name__


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LydbroCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            LydbroButtonEvent(coordinator),
            LydbroMenuEvent(coordinator),
            LydbroSceneEvent(coordinator),
        ]
    )


class _LydbroEventBase(LydbroEntity, EventEntity):
    """Shared wiring — subscribes to the event dispatcher and filters."""

    def __init__(self, coordinator: LydbroCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_{key}"
        self._attr_translation_key = key

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_EVENT.format(self.coordinator.entry.entry_id),
                self._handle_frame,
            )
        )

    @callback
    def _handle_frame(self, frame: dict[str, Any]) -> None:
        raise NotImplementedError


class LydbroButtonEvent(_LydbroEventBase):
    """Physical BeoRemote One button presses."""

    _attr_device_class = EventDeviceClass.BUTTON

    def __init__(self, coordinator: LydbroCoordinator) -> None:
        super().__init__(coordinator, "button")
        # Per-instance list — never mutate a class-level list, that would
        # leak state across devices on a multi-bridge install.
        self._attr_event_types = list(KNOWN_BUTTONS)

    @callback
    def _handle_frame(self, frame: dict[str, Any]) -> None:
        if frame.get("type") != "button_press":
            return
        name = frame.get("name")
        if not isinstance(name, str) or name not in self._attr_event_types:
            # Drop rather than mutate event_types at runtime — HA's
            # event platform doesn't reliably propagate dynamic
            # additions to the frontend picker. If firmware starts
            # emitting a new button, add it to KNOWN_BUTTONS in const.py.
            return
        self._trigger_event(
            name,
            {
                "name": name,
                "kind": frame.get("kind"),
                "mode": frame.get("mode"),
            },
        )
        self.async_write_ha_state()


class LydbroMenuEvent(_LydbroEventBase):
    """Vendor-menu selections from the remote's custom UI.

    Menu labels are user-configured on the bridge, so we declare a
    generic "Menu" event_type up-front and rely on the ``name``
    attribute for automation filtering. Users who want per-menu-item
    triggers can match on ``trigger.event.data.name``.
    """

    def __init__(self, coordinator: LydbroCoordinator) -> None:
        super().__init__(coordinator, "menu")
        self._attr_event_types = ["Menu"]

    @callback
    def _handle_frame(self, frame: dict[str, Any]) -> None:
        if frame.get("type") != "menu_selection":
            return
        self._trigger_event(
            "Menu",
            {
                "name": frame.get("name"),
                "source": frame.get("source"),
                "id": frame.get("id"),
                "mode": frame.get("mode"),
            },
        )
        self.async_write_ha_state()


class LydbroSceneEvent(_LydbroEventBase):
    """The four corner scene buttons on the BeoRemote One.

    Positions match the physical layout and the strings the firmware
    publishes in ``scene.position``: top_left / top_right / bottom_left /
    bottom_right.
    """

    _attr_device_class = EventDeviceClass.BUTTON

    def __init__(self, coordinator: LydbroCoordinator) -> None:
        super().__init__(coordinator, "scene")
        self._attr_event_types = [
            "top_left",
            "top_right",
            "bottom_left",
            "bottom_right",
        ]

    @callback
    def _handle_frame(self, frame: dict[str, Any]) -> None:
        if frame.get("type") != "scene_button":
            return
        position = frame.get("position")
        if position not in self._attr_event_types:
            return
        self._trigger_event(
            position,
            {
                "name": frame.get("name"),
                "position": position,
                "mode": frame.get("mode"),
            },
        )
        self.async_write_ha_state()
