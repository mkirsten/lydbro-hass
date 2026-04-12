"""Sensor platform for Lydbro."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LydbroConfigEntry
from .coordinator import LydbroCoordinator
from .entity import LydbroEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LydbroSensorDescription(SensorEntityDescription):
    """Describes a Lydbro sensor entity."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[LydbroSensorDescription, ...] = (
    LydbroSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda s: s.get("battery") if s.get("battery", -1) >= 0 else None,
    ),
    LydbroSensorDescription(
        key="boot_phase",
        translation_key="boot_phase",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.get("boot_phase"),
    ),
    LydbroSensorDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.get("fw"),
    ),
    LydbroSensorDescription(
        key="ip_address",
        translation_key="ip_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.get("ip"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LydbroConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(LydbroSensor(coordinator, desc) for desc in SENSORS)


class LydbroSensor(LydbroEntity, SensorEntity):
    """A Lydbro state-backed sensor."""

    entity_description: LydbroSensorDescription

    def __init__(
        self,
        coordinator: LydbroCoordinator,
        description: LydbroSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.state)
