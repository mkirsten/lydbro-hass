"""Remote platform — a HA-native view of the BeoRemote One.

Exposes the paired BeoRemote as ``remote.lydbro_one``:

  * ``is_on`` tracks the BLE link state — you know from HA whether the
    remote is currently paired and reachable.
  * ``remote.send_command`` fires a virtual BeoRemote key press at the
    bridge. Useful for automations that want to simulate a button
    without the physical remote (e.g. "on sunset, trigger Play").

Commands map one-to-one to :data:`const.KNOWN_BUTTONS`. Unknown command
names are passed through to the firmware — it will reject them if they
aren't valid, and the service call will raise.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import RemoteEntity, RemoteEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LydbroConfigEntry
from .const import KNOWN_BUTTONS
from .coordinator import LydbroCoordinator
from .entity import LydbroEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LydbroConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([LydbroRemote(coordinator)])


class LydbroRemote(LydbroEntity, RemoteEntity):
    """Virtual BeoRemote One exposed as a HA remote entity."""

    _attr_translation_key = "remote"
    _attr_supported_features = RemoteEntityFeature(0)

    def __init__(self, coordinator: LydbroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_remote"

    @property
    def is_on(self) -> bool:
        """On when the BeoRemote is paired and the BLE link is up."""
        return bool(self.coordinator.state.get("ble_connected"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "known_commands": list(KNOWN_BUTTONS),
            "battery": self.coordinator.state.get("battery"),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn-on means "reconnect the BLE link".

        There's no firmware cmd for "force BLE scan/connect" — the
        bridge auto-reconnects on advertisement. Best we can do is
        nudge the user's mental model: if is_on is False, pressing any
        button on the physical remote wakes it.
        """

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn-off drops the current BLE link."""
        await self.coordinator.async_send_cmd("ble_disconnect")

    async def async_send_command(
        self, command: Iterable[str], **kwargs: Any
    ) -> None:
        """Inject virtual remote key presses.

        Each string in ``command`` is forwarded to the firmware as
        ``send_remote_key`` with the button name as ``key``. This
        lets automations fire e.g. ``Play`` or ``Home`` without a
        physical press, which the rest of the bridge (bus → adapters)
        then treats identically.
        """
        for cmd in command:
            await self.coordinator.async_send_cmd("send_remote_key", key=cmd)
