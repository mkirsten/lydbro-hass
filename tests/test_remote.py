"""Remote-entity tests.

The ``remote.lab_beoremote_one_*`` entity wraps the paired BeoRemote
One as a HA remote:

* ``is_on`` tracks the BLE link state.
* ``remote.send_command`` forwards each string to the firmware as
  ``send_remote_key`` — one cmd per key.
* ``remote.turn_off`` issues ``ble_disconnect``; ``turn_on`` is a
  no-op (the bridge auto-reconnects when the remote wakes).
"""
from __future__ import annotations

from homeassistant.components.remote import (
    ATTR_COMMAND,
    DOMAIN as REMOTE_DOMAIN,
    SERVICE_SEND_COMMAND,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, CONF_PORT, STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lydbro.const import DOMAIN

from .fake_server import FakeLydbroServer


REMOTE_ENTITY_ID = "remote.test_lydbro_one_beoremote"


async def _setup(hass: HomeAssistant, fake_server: FakeLydbroServer) -> None:
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


async def test_remote_is_on_tracks_ble_connected(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """BLE up → state on. The default fake state has ble_connected=True."""
    await _setup(hass, fake_server)

    state = hass.states.get(REMOTE_ENTITY_ID)
    assert state is not None
    assert state.state == STATE_ON
    # extra_state_attributes carries the known commands list + battery.
    assert "known_commands" in state.attributes
    assert "Play" in state.attributes["known_commands"]
    assert state.attributes["battery"] == 87


async def test_remote_send_command_forwards_per_key(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Each string in ``command`` becomes one send_remote_key cmd."""
    await _setup(hass, fake_server)

    await hass.services.async_call(
        REMOTE_DOMAIN,
        SERVICE_SEND_COMMAND,
        {
            ATTR_ENTITY_ID: REMOTE_ENTITY_ID,
            ATTR_COMMAND: ["Play", "Volume Up", "Home"],
        },
        blocking=True,
    )

    cmds = fake_server.received_cmds
    assert len(cmds) == 3
    assert [c["cmd"] for c in cmds] == ["send_remote_key"] * 3
    assert [c["key"] for c in cmds] == ["Play", "Volume Up", "Home"]


async def test_remote_turn_off_issues_ble_disconnect(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    await _setup(hass, fake_server)

    await hass.services.async_call(
        REMOTE_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: REMOTE_ENTITY_ID},
        blocking=True,
    )

    assert len(fake_server.received_cmds) == 1
    assert fake_server.received_cmds[0]["cmd"] == "ble_disconnect"


async def test_remote_turn_on_is_no_op(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """turn_on has no firmware cmd — it's a user-facing hint, no-op under the hood."""
    await _setup(hass, fake_server)

    await hass.services.async_call(
        REMOTE_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: REMOTE_ENTITY_ID},
        blocking=True,
    )

    assert fake_server.received_cmds == []
