"""End-to-end setup/unload tests for the Lydbro integration.

These run the real ``async_setup_entry`` → coordinator → TCP client
against :class:`FakeLydbroServer` over loopback, so every link in the
entry-load chain is exercised for real:

  * config entry → ``LydbroCoordinator`` instance
  * coordinator → ``LydbroClient`` → fake server handshake
  * entry.runtime_data is populated with the coordinator
  * all five platforms forward and create their entities
  * global services are registered once and unregistered on the last unload
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lydbro.const import DOMAIN
from custom_components.lydbro.coordinator import LydbroCoordinator

from .fake_server import FakeLydbroServer


async def _setup_entry(hass: HomeAssistant, fake_server: FakeLydbroServer) -> MockConfigEntry:
    """Register and load a config entry pointed at the fake bridge."""
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


async def test_setup_loads_coordinator_and_entities(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Happy path: entry loads, coordinator connects, entities appear."""
    entry = await _setup_entry(hass, fake_server)

    assert entry.state is ConfigEntryState.LOADED

    # runtime_data holds the coordinator, not the old hass.data dict.
    coordinator = entry.runtime_data
    assert isinstance(coordinator, LydbroCoordinator)
    assert coordinator.available is True
    assert coordinator.hello["id"] == "aa:bb:cc:dd:ee:ff"
    assert coordinator.state["battery"] == 87
    assert coordinator.state["eth_up"] is True

    # Device registry should have the Lydbro One registered via DeviceInfo.
    device_reg = dr.async_get(hass)
    device = device_reg.async_get_device(identifiers={(DOMAIN, "aa:bb:cc:dd:ee:ff")})
    assert device is not None
    assert device.manufacturer == "Lydbro"

    # All five platforms created their entities.
    ent_reg = er.async_get(hass)
    entities = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    platforms = {e.entity_id.split(".", 1)[0] for e in entities}
    assert platforms == {"binary_sensor", "button", "event", "remote", "sensor"}

    # Spot-check a handful so we catch silent drops of a specific
    # entity under a renamed unique_id.
    unique_ids = {e.unique_id for e in entities}
    assert "aa:bb:cc:dd:ee:ff_battery" in unique_ids
    assert "aa:bb:cc:dd:ee:ff_ble_connected" in unique_ids
    assert "aa:bb:cc:dd:ee:ff_button" in unique_ids
    assert "aa:bb:cc:dd:ee:ff_remote" in unique_ids

    # Global services are registered after setup.
    assert hass.services.has_service(DOMAIN, "send_remote_key")
    assert hass.services.has_service(DOMAIN, "rescan_discovery")


async def test_unload_clears_runtime_data_and_services(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Unloading the last entry tears down coordinator and global services."""
    entry = await _setup_entry(hass, fake_server)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED

    # When the last entry unloads the global services go too.
    assert not hass.services.has_service(DOMAIN, "send_remote_key")
    assert not hass.services.has_service(DOMAIN, "rescan_discovery")


async def test_setup_survives_initial_handshake_failure(
    hass: HomeAssistant, socket_enabled, caplog
) -> None:
    """Entry still loads when the bridge is unreachable at setup time.

    The coordinator logs a warning and the client's reconnect loop
    keeps trying in the background. Entities come up as unavailable
    rather than the entry failing outright — blocking setup on
    network reachability would strand users whose bridge booted
    slower than HA.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="aa:bb:cc:dd:ee:ff",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: 1,  # nothing listening
            "device_id": "aa:bb:cc:dd:ee:ff",
            "fw_version": "0.11.9.3",
        },
        title="Test Lydbro One",
    )
    entry.add_to_hass(hass)

    # Shorten the handshake wait so the test doesn't hang on the
    # default CONNECT_TIMEOUT + 2s.
    from unittest.mock import patch

    from custom_components.lydbro import client as client_mod

    with patch.object(client_mod, "CONNECT_TIMEOUT", 0.2):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    coordinator: LydbroCoordinator = entry.runtime_data
    assert coordinator.available is False

    # Clean up — the coordinator's reconnect task is still running.
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
