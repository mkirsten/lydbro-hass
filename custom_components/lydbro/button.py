"""Button platform — admin buttons plus per-key virtual BeoRemote buttons.

Two flavours of button entity are created per device:

* **Admin** — Reboot / Rescan discovery / Disconnect BeoRemote. These
  sit under ``EntityCategory.CONFIG`` on the device page and fire
  bridge-level commands.
* **Virtual remote key** — one per entry in
  :data:`const.COMMON_REMOTE_BUTTONS` (Play, Pause, Volume Up, …).
  Each calls :meth:`LydbroCoordinator.async_send_cmd` with
  ``send_remote_key`` so an automation or Lovelace card can inject a
  button press without the physical remote. They are disabled by
  default — enable the ones you need from the HA device page so the
  entity registry isn't swamped with 12 new entries per bridge.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LydbroConfigEntry
from .const import COMMON_REMOTE_BUTTONS
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


def _virtual_key_entity_key(button_name: str) -> str:
    """Slugify a BeoRemote button name for use in an entity unique_id.

    ``"Volume Up"`` → ``"volume_up"``. The slugified form is stable
    across renames so users don't lose entity customisations if the
    human-readable name ever changes in the firmware.
    """
    return button_name.lower().replace(" ", "_").replace("/", "_")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LydbroConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data

    entities: list[Entity] = [LydbroButton(coordinator, desc, cmd) for desc, cmd in BUTTONS]
    entities.extend(LydbroVirtualRemoteButton(coordinator, name) for name in COMMON_REMOTE_BUTTONS)
    async_add_entities(entities)


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


class LydbroVirtualRemoteButton(LydbroEntity, ButtonEntity):
    """A single BeoRemote key exposed as a HA button entity.

    Pressing it fires the same ``send_remote_key`` cmd an automation
    would invoke through ``remote.send_command`` — the value is
    discoverability and the ability to drag one onto a Lovelace card
    without scripting.
    """

    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: LydbroCoordinator, button_name: str) -> None:
        super().__init__(coordinator)
        self._button_name = button_name
        key = _virtual_key_entity_key(button_name)
        self.entity_description = ButtonEntityDescription(
            key=f"remote_key_{key}",
            translation_key=f"remote_key_{key}",
            # Human name falls back to the firmware's button label when
            # no translation is found (so users always see *something*
            # reasonable even if we miss a translation).
            name=button_name,
        )
        self._attr_unique_id = f"{coordinator.device_id}_remote_key_{key}"

    async def async_press(self) -> None:
        await self.coordinator.async_send_cmd("send_remote_key", key=self._button_name)
