"""Sensor entity tests — last-button-press + current-mode.

The existing battery / ip / firmware / boot_phase sensors are covered
by test_init (they're all created at setup) and test_coordinator
(they read from state). These two sensors are new and have their own
moving parts worth testing directly:

* ``sensor.*_last_button_press`` — timestamp device class, parsed
  from the ISO string the coordinator stores in state; carries
  name/kind/mode as extra attributes.
* ``sensor.*_current_mode`` — enum device class, reads
  ``state['mode']`` and lowercases to match the translation keys.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_HOST, CONF_PORT, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lydbro.const import DOMAIN

from .fake_server import FakeLydbroServer

LAST_PRESS_ENTITY = "sensor.test_lydbro_one_last_button_press"
CURRENT_MODE_ENTITY = "sensor.test_lydbro_one_current_mode"


async def _setup(hass: HomeAssistant, fake_server: FakeLydbroServer) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="aa:bb:cc:dd:ee:ff",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: fake_server.port,
            "device_id": "aa:bb:cc:dd:ee:ff",
            "fw_version": "0.11.9.3",
        },
        title="Test Lydbro One",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _enable_entity(hass: HomeAssistant, entity_id: str) -> None:
    """Re-enable a disabled-by-default entity and reload its entry."""
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(entity_id)
    assert entry is not None, f"{entity_id} not registered"
    assert entry.disabled_by is not None, f"{entity_id} should be disabled by default"
    ent_reg.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.config_entry_id)
    await hass.async_block_till_done()


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("timed out")


# ---------------------------------------------------------------------------
# last_button_press
# ---------------------------------------------------------------------------


async def test_last_button_press_disabled_by_default(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    await _setup(hass, fake_server)
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(LAST_PRESS_ENTITY)
    assert entry is not None
    assert entry.disabled_by is not None


async def test_last_button_press_updates_on_press(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    await _setup(hass, fake_server)
    await _enable_entity(hass, LAST_PRESS_ENTITY)

    # Pre-press: unknown, since no button has been pressed yet.
    state = hass.states.get(LAST_PRESS_ENTITY)
    assert state is not None
    assert state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)
    # Device class is timestamp regardless of value.
    assert state.attributes["device_class"] == SensorDeviceClass.TIMESTAMP

    await fake_server.push_event("button_press", name="Play", kind="click", mode="MUSIC")
    await _wait_for(
        lambda: hass.states.get(LAST_PRESS_ENTITY).state  # type: ignore[union-attr]
        not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
    )

    state = hass.states.get(LAST_PRESS_ENTITY)
    assert state is not None
    # State parses back to a datetime.
    datetime.fromisoformat(state.state)
    assert state.attributes["name"] == "Play"
    assert state.attributes["kind"] == "click"
    assert state.attributes["mode"] == "MUSIC"


# ---------------------------------------------------------------------------
# current_mode
# ---------------------------------------------------------------------------


async def test_current_mode_enum_lowercased(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Firmware sends 'MUSIC', sensor state + options are lowercase."""
    await _setup(hass, fake_server)
    await _enable_entity(hass, CURRENT_MODE_ENTITY)

    # Options list is lowercase so the enum device_class + translation
    # keys line up.
    state = hass.states.get(CURRENT_MODE_ENTITY)
    assert state is not None
    assert "music" in state.attributes["options"]
    assert "MUSIC" not in state.attributes["options"]

    await fake_server.push_event("button_press", name="Play", kind="click", mode="MUSIC")
    await _wait_for(
        lambda: hass.states.get(CURRENT_MODE_ENTITY).state == "music"  # type: ignore[union-attr]
    )

    await fake_server.push_event("button_press", name="Home", kind="click", mode="TV")
    await _wait_for(
        lambda: hass.states.get(CURRENT_MODE_ENTITY).state == "tv"  # type: ignore[union-attr]
    )


# ---------------------------------------------------------------------------
# _parse_last_press fallback
# ---------------------------------------------------------------------------


def test_parse_last_press_bad_iso_returns_none() -> None:
    """A corrupted ISO timestamp in state parses back to None, not a crash."""
    from custom_components.lydbro.sensor import _parse_last_press

    assert _parse_last_press({"last_button_press": "definitely not iso"}) is None
    assert _parse_last_press({}) is None
    assert _parse_last_press({"last_button_press": 12345}) is None
    assert _parse_last_press({"last_button_press": "2026-04-12T20:30:00+00:00"}) is not None


# ---------------------------------------------------------------------------
# battery value_fn
# ---------------------------------------------------------------------------


def test_battery_value_fn_handles_null() -> None:
    """A null/missing battery resolves to None, not a TypeError.

    The firmware sends ``battery: null`` while the remote is disconnected.
    The key is present, so ``dict.get('battery', -1)`` returns None (not the
    -1 default) and a naive ``None >= 0`` comparison raises. Guard for None.
    """
    from custom_components.lydbro.sensor import SENSORS

    value_fn = next(s for s in SENSORS if s.key == "battery").value_fn

    assert value_fn({"battery": None}) is None  # disconnected: present-but-null
    assert value_fn({}) is None  # absent
    assert value_fn({"battery": -1}) is None  # sentinel negative
    assert value_fn({"battery": 0}) == 0  # falsy-but-valid
    assert value_fn({"battery": 87}) == 87
