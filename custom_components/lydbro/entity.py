"""Base entity for Lydbro — shared device_info + dispatcher plumbing."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER, MODEL_DEFAULT, SIGNAL_STATE_UPDATED
from .coordinator import LydbroCoordinator


class LydbroEntity(Entity):
    """Base class with device_info and state-dispatcher wiring."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: LydbroCoordinator) -> None:
        self.coordinator = coordinator
        hello = coordinator.hello
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer=MANUFACTURER,
            model=hello.get("model") or MODEL_DEFAULT,
            name=hello.get("name") or coordinator.entry.title,
            sw_version=hello.get("fw"),
            configuration_url=f"http://{coordinator.host}/",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATE_UPDATED.format(self.coordinator.entry.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        # @callback marks this as event-loop-safe so the dispatcher
        # runs it inline instead of scheduling it on a worker thread,
        # which would violate async_write_ha_state's thread-safety
        # check and crash HA at runtime.
        self.async_write_ha_state()
