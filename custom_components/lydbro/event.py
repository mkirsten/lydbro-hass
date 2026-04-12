"""Event platform — exposes BeoRemote One button, menu, and scene events.

Event entities are the modern HA pattern for remote controls: each press
arrives as a first-class trigger source, not a hidden `bus.fire`. Three
event entities are created per device:

  * ``event.<device>_button``  — every physical button press (click/hold/
    release/double). The ``event_type`` is the button name ("Play",
    "Next", ...); ``kind`` and ``mode`` come through as attributes.
  * ``event.<device>_menu``    — vendor-menu selections from the remote's
    custom UI. ``event_type`` is the menu item name.
  * ``event.<device>_scene``   — the four corner "scene" buttons that the
    remote can be assigned to. ``event_type`` is the scene label.
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

    _frame_type: str = ""

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
    _attr_event_types = list(KNOWN_BUTTONS)

    def __init__(self, coordinator: LydbroCoordinator) -> None:
        super().__init__(coordinator, "button")

    @callback
    def _handle_frame(self, frame: dict[str, Any]) -> None:
        if frame.get("type") != "button_press":
            return
        name = frame.get("name")
        if not isinstance(name, str) or not name:
            return
        # HA's event platform rejects event_types that weren't declared
        # up-front. Unknown buttons (user-defined scenes, new firmware
        # additions) get folded into the catch-all "Unknown" slot so they
        # still trigger automations via the attributes.
        event_type = name if name in KNOWN_BUTTONS else "Unknown"
        if event_type == "Unknown" and "Unknown" not in self._attr_event_types:
            self._attr_event_types = [*self._attr_event_types, "Unknown"]
        self._trigger_event(
            event_type,
            {
                "name": name,
                "kind": frame.get("kind"),
                "mode": frame.get("mode"),
            },
        )
        self.async_write_ha_state()


class LydbroMenuEvent(_LydbroEventBase):
    """Vendor-menu selections from the remote's custom UI."""

    _attr_event_types: list[str] = []

    def __init__(self, coordinator: LydbroCoordinator) -> None:
        super().__init__(coordinator, "menu")
        # Menu labels are user-configured, so we learn them at runtime
        # rather than declaring them up-front.
        self._attr_event_types = ["Menu"]

    @callback
    def _handle_frame(self, frame: dict[str, Any]) -> None:
        if frame.get("type") != "menu_selection":
            return
        name = frame.get("name") or "Menu"
        if name not in self._attr_event_types:
            self._attr_event_types = [*self._attr_event_types, name]
        self._trigger_event(
            name,
            {
                "name": name,
                "source": frame.get("source"),
                "id": frame.get("id"),
                "mode": frame.get("mode"),
            },
        )
        self.async_write_ha_state()


class LydbroSceneEvent(_LydbroEventBase):
    """The four corner scene buttons (N/E/S/W)."""

    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = ["N", "E", "S", "W"]

    def __init__(self, coordinator: LydbroCoordinator) -> None:
        super().__init__(coordinator, "scene")

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
