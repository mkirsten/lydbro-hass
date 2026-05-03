"""Sensor platform for Lydbro."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
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
from .const import REMOTE_MODES
from .coordinator import LydbroCoordinator
from .entity import LydbroEntity

PARALLEL_UPDATES = 0


def _parse_last_press(state: dict[str, Any]) -> datetime | None:
    """Parse the coordinator's ISO-string last-press timestamp.

    Returns ``None`` before the first press so HA shows "Unknown"
    rather than a made-up datetime on a device that's just been set
    up. We store the value as ISO-8601 in the state dict (keeps the
    diagnostics dump JSON-safe) and reconstitute the datetime here.
    """
    raw = state.get("last_button_press")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


@dataclass(frozen=True, kw_only=True)
class LydbroSensorDescription(SensorEntityDescription):
    """Describes a Lydbro sensor entity."""

    value_fn: Callable[[dict[str, Any]], Any]
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    available_fn: Callable[[dict[str, Any]], bool] | None = None


SENSORS: tuple[LydbroSensorDescription, ...] = (
    LydbroSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        available_fn=lambda s: bool(s.get("ble_connected")),
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
    # Dashboard-oriented sensors — not diagnostic, but not on by
    # default either, because not every user wants them cluttering
    # the device page.
    LydbroSensorDescription(
        key="last_button_press",
        translation_key="last_button_press",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        value_fn=_parse_last_press,
        attributes_fn=lambda s: {
            "name": s.get("last_button_name"),
            "kind": s.get("last_button_kind"),
            "mode": s.get("last_button_mode"),
        },
    ),
    # Enum device-class state + translation keys are conventionally
    # lower-cased in HA, so we downcase the firmware's uppercase mode
    # ("MUSIC") to match the enum option list and translation keys.
    LydbroSensorDescription(
        key="current_mode",
        translation_key="current_mode",
        device_class=SensorDeviceClass.ENUM,
        options=[m.lower() for m in REMOTE_MODES],
        entity_registry_enabled_default=False,
        value_fn=lambda s: s["mode"].lower() if isinstance(s.get("mode"), str) else None,
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
    def available(self) -> bool:
        if self.entity_description.available_fn is not None:
            return super().available and self.entity_description.available_fn(self.coordinator.state)
        return super().available

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.state)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.state)
