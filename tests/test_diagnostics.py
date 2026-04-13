"""Diagnostics tests.

Downloadable diagnostics is a ``diagnostics.py`` hook HA calls from
the device page's "Download Diagnostics" button. The test asserts the
payload is a dict with the four expected top-level keys and that each
carries the data we promised: the config entry, the live connection
state, the hello frame, and the latest state snapshot.
"""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lydbro.const import DOMAIN
from custom_components.lydbro.diagnostics import async_get_config_entry_diagnostics

from .fake_server import FakeLydbroServer


async def test_diagnostics_dump_shape(hass: HomeAssistant, fake_server: FakeLydbroServer) -> None:
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

    data = await async_get_config_entry_diagnostics(hass, entry)

    assert set(data) == {"entry", "connection", "hello", "state"}

    assert data["entry"]["entry_id"] == entry.entry_id
    assert data["entry"]["data"][CONF_HOST] == "127.0.0.1"
    assert data["entry"]["data"][CONF_PORT] == fake_server.port

    assert data["connection"]["host"] == "127.0.0.1"
    assert data["connection"]["port"] == fake_server.port
    assert data["connection"]["available"] is True
    assert data["connection"]["device_id"] == "aa:bb:cc:dd:ee:ff"

    assert data["hello"]["id"] == "aa:bb:cc:dd:ee:ff"
    assert data["hello"]["fw"] == "0.13.0"

    assert data["state"]["battery"] == 87
    assert data["state"]["eth_up"] is True
