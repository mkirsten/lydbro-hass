"""Coordinator tests — state merge, numeric coercion, bus-event fan-out.

These verify the pieces :class:`LydbroCoordinator` layers on top of
:class:`LydbroClient`:

* full ``state`` snapshots are stored verbatim;
* ``state_change`` events merge into the snapshot as deltas;
* numeric fields like ``battery`` are coerced to int even when the
  firmware sends them as strings in delta frames;
* ``boot_phase`` events update the state dict;
* ``button_press`` / ``menu_selection`` / ``scene_button`` events fire
  the corresponding HA bus events (``lydbro_button`` etc.) carrying
  the HA device_id — this is the load-bearing hook for device triggers.
"""

from __future__ import annotations

import asyncio

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import Event, HomeAssistant, callback
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lydbro.const import (
    DOMAIN,
    EVENT_BUS_BUTTON,
    EVENT_BUS_MENU,
    EVENT_BUS_SCENE,
)
from custom_components.lydbro.coordinator import LydbroCoordinator

from .fake_server import FakeLydbroServer


async def _setup(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> tuple[MockConfigEntry, LydbroCoordinator]:
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
    return entry, entry.runtime_data


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    """Spin until ``predicate()`` is truthy or timeout. Keeps tests short."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out waiting for condition")


# ---------------------------------------------------------------------------
# Snapshot + delta merge
# ---------------------------------------------------------------------------


async def test_initial_state_snapshot_populated(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """First state frame after handshake lands verbatim in coordinator.state."""
    _, coordinator = await _setup(hass, fake_server)

    assert coordinator.state["battery"] == 87
    assert coordinator.state["eth_up"] is True
    assert coordinator.state["ble_connected"] is True
    assert coordinator.state["boot_phase"] == "Ready"


async def test_state_change_event_merges_delta(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """A state_change event overwrites a single key without dropping others."""
    _, coordinator = await _setup(hass, fake_server)

    await fake_server.push_event("state_change", name="ble_connected", value=False)
    await _wait_for(lambda: coordinator.state["ble_connected"] is False)

    # Battery survived — the delta only touched ble_connected.
    assert coordinator.state["battery"] == 87
    assert coordinator.state["eth_up"] is True


async def test_battery_string_delta_coerced_to_int(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Firmware delta frames send numeric fields as strings — coordinator fixes it.

    Without this coercion the battery sensor flips between 87 and "42"
    across the snapshot/delta boundary and HA's numeric device_class
    machinery complains.
    """
    _, coordinator = await _setup(hass, fake_server)

    await fake_server.push_event("state_change", name="battery", value="42")
    await _wait_for(lambda: coordinator.state["battery"] == 42)

    assert isinstance(coordinator.state["battery"], int)


async def test_boot_phase_event_updates_state(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """boot_phase events are recorded so the diagnostic sensor can track them."""
    _, coordinator = await _setup(hass, fake_server)

    await fake_server.push_event("boot_phase", phase="Discovering devices")
    await _wait_for(lambda: coordinator.state.get("boot_phase") == "Discovering devices")


# ---------------------------------------------------------------------------
# Bus-event fan-out (load-bearing for device triggers)
# ---------------------------------------------------------------------------


async def test_button_press_fires_lydbro_button_bus_event(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """button_press frame → lydbro_button HA event carrying the HA device_id."""
    await _setup(hass, fake_server)

    # Look up the HA registry id for the device — that's what the
    # coordinator stamps into event data.
    from homeassistant.helpers import device_registry as dr

    ha_device_id = (
        dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "aa:bb:cc:dd:ee:ff")}).id
    )

    captured: list[Event] = []

    @callback
    def _listener(event: Event) -> None:
        captured.append(event)

    hass.bus.async_listen(EVENT_BUS_BUTTON, _listener)

    await fake_server.push_event("button_press", name="Play", kind="click", mode="MUSIC")
    await _wait_for(lambda: len(captured) == 1)

    event = captured[0]
    assert event.event_type == EVENT_BUS_BUTTON
    assert event.data["device_id"] == ha_device_id
    assert event.data["name"] == "Play"
    assert event.data["kind"] == "click"
    assert event.data["mode"] == "MUSIC"


async def test_menu_selection_fires_lydbro_menu_bus_event(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    await _setup(hass, fake_server)
    captured: list[Event] = []
    hass.bus.async_listen(EVENT_BUS_MENU, lambda e: captured.append(e))

    await fake_server.push_event(
        "menu_selection", name="Jazz", source="spotify", id="pl_1", mode="MUSIC"
    )
    await _wait_for(lambda: len(captured) == 1)

    assert captured[0].data["name"] == "Jazz"
    assert captured[0].data["source"] == "spotify"


async def test_scene_button_fires_lydbro_scene_bus_event(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    await _setup(hass, fake_server)
    captured: list[Event] = []
    hass.bus.async_listen(EVENT_BUS_SCENE, lambda e: captured.append(e))

    await fake_server.push_event("scene_button", name="TopLeft", position="top_left", mode="MUSIC")
    await _wait_for(lambda: len(captured) == 1)

    assert captured[0].data["position"] == "top_left"
    assert captured[0].data["name"] == "TopLeft"


async def test_non_device_trigger_events_do_not_fire_bus(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """state_change / boot_phase events should not land on the device-trigger buses."""
    await _setup(hass, fake_server)
    bus_hits: list[Event] = []
    for etype in (EVENT_BUS_BUTTON, EVENT_BUS_MENU, EVENT_BUS_SCENE):
        hass.bus.async_listen(etype, lambda e: bus_hits.append(e))

    await fake_server.push_event("state_change", name="battery", value="55")
    await fake_server.push_event("boot_phase", phase="Ready")
    # Give the event loop a few ticks to deliver anything it was going to.
    await asyncio.sleep(0.05)

    assert bus_hits == []


# ---------------------------------------------------------------------------
# Availability on disconnect
# ---------------------------------------------------------------------------


async def test_available_flips_false_on_server_drop(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    _, coordinator = await _setup(hass, fake_server)
    assert coordinator.available is True

    await fake_server.drop_client()
    await _wait_for(lambda: coordinator.available is False, timeout=3.0)


# ---------------------------------------------------------------------------
# Dashboard-oriented state: last_button_press + current mode
# ---------------------------------------------------------------------------


async def test_button_press_records_last_button_fields(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Every button_press frame updates last_button_* keys in state."""
    from datetime import datetime

    _, coordinator = await _setup(hass, fake_server)
    assert "last_button_press" not in coordinator.state

    await fake_server.push_event("button_press", name="Play", kind="click", mode="MUSIC")
    await _wait_for(lambda: "last_button_press" in coordinator.state)

    assert coordinator.state["last_button_name"] == "Play"
    assert coordinator.state["last_button_kind"] == "click"
    assert coordinator.state["last_button_mode"] == "MUSIC"

    # Timestamp parses as a datetime.
    ts = coordinator.state["last_button_press"]
    assert isinstance(ts, str)
    parsed = datetime.fromisoformat(ts)
    assert parsed is not None


async def test_mode_tracked_from_any_event_with_mode(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Any event frame carrying a mode field updates state['mode']."""
    _, coordinator = await _setup(hass, fake_server)
    assert "mode" not in coordinator.state

    await fake_server.push_event("button_press", name="Play", kind="click", mode="MUSIC")
    await _wait_for(lambda: coordinator.state.get("mode") == "MUSIC")

    # Switching mode via any event (menu_selection here) should
    # update the cached mode.
    await fake_server.push_event("menu_selection", name="Samsung Frame", mode="TV")
    await _wait_for(lambda: coordinator.state.get("mode") == "TV")


async def test_mode_untouched_by_frame_without_mode(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """A state_change delta without a mode field must not clear the cached mode."""
    _, coordinator = await _setup(hass, fake_server)

    # Prime the mode.
    await fake_server.push_event("button_press", name="Play", kind="click", mode="MUSIC")
    await _wait_for(lambda: coordinator.state.get("mode") == "MUSIC")

    # A later delta that has no mode field should leave MUSIC in place.
    await fake_server.push_event("state_change", name="battery", value="42")
    await _wait_for(lambda: coordinator.state.get("battery") == 42)
    assert coordinator.state["mode"] == "MUSIC"
