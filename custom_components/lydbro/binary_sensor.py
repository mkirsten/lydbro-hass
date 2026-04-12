"""Binary sensor platform for Lydbro."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LydbroConfigEntry
from .coordinator import LydbroCoordinator
from .entity import LydbroEntity

# Push-based integration — updates arrive over a persistent TCP connection,
# so there is no benefit to serialising entity refreshes.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LydbroBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[LydbroBinarySensorDescription, ...] = (
    LydbroBinarySensorDescription(
        key="ble_connected",
        translation_key="ble_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda s: bool(s.get("ble_connected")),
    ),
    LydbroBinarySensorDescription(
        key="ethernet",
        translation_key="ethernet",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: bool(s.get("eth_up")),
    ),
    LydbroBinarySensorDescription(
        key="safe_mode",
        translation_key="safe_mode",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: bool(s.get("safe_mode")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LydbroConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(LydbroBinarySensor(coordinator, desc) for desc in BINARY_SENSORS)


class LydbroBinarySensor(LydbroEntity, BinarySensorEntity):
    entity_description: LydbroBinarySensorDescription

    def __init__(
        self,
        coordinator: LydbroCoordinator,
        description: LydbroBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.state)
