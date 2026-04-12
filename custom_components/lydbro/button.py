"""Button platform — admin-style buttons for reboot and rescan."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LydbroConfigEntry
from .coordinator import LydbroCoordinator
from .entity import LydbroEntity

PARALLEL_UPDATES = 0


BUTTONS: tuple[tuple[ButtonEntityDescription, str], ...] = (
    (
        ButtonEntityDescription(
            key="reboot",
            translation_key="reboot",
            entity_category=EntityCategory.CONFIG,
        ),
        "reboot",
    ),
    (
        ButtonEntityDescription(
            key="rescan_discovery",
            translation_key="rescan_discovery",
            entity_category=EntityCategory.CONFIG,
        ),
        "rescan_discovery",
    ),
    (
        ButtonEntityDescription(
            key="ble_disconnect",
            translation_key="ble_disconnect",
            entity_category=EntityCategory.CONFIG,
        ),
        "ble_disconnect",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LydbroConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(LydbroButton(coordinator, desc, cmd) for desc, cmd in BUTTONS)


class LydbroButton(LydbroEntity, ButtonEntity):
    def __init__(
        self,
        coordinator: LydbroCoordinator,
        description: ButtonEntityDescription,
        cmd: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._cmd = cmd
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"

    async def async_press(self) -> None:
        await self.coordinator.async_send_cmd(self._cmd)
