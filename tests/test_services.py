"""Service tests — every registered service round-trips through the fake bridge.

Instead of checking "did HA register 10 services" (which test_init
already covers), these tests call each service and verify the exact
``cmd`` frame that hit the fake server. If a future refactor renames a
cmd string on either side, this catches it.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lydbro.const import DOMAIN

from .fake_server import FakeLydbroServer


async def _setup(hass: HomeAssistant, fake_server: FakeLydbroServer) -> tuple[MockConfigEntry, str]:
    """Set up an entry and return (entry, ha_device_id)."""
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

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "aa:bb:cc:dd:ee:ff")})
    assert device is not None
    return entry, device.id


# ---------------------------------------------------------------------------
# Happy-path round-trips
# ---------------------------------------------------------------------------


async def test_send_remote_key_forwards_cmd(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    _, device_id = await _setup(hass, fake_server)

    await hass.services.async_call(
        DOMAIN,
        "send_remote_key",
        {ATTR_DEVICE_ID: device_id, "key": "Play"},
        blocking=True,
    )

    # Filter out the handshake noise — just the cmd frames.
    cmds = fake_server.received_cmds
    assert len(cmds) == 1
    assert cmds[0]["cmd"] == "send_remote_key"
    assert cmds[0]["key"] == "Play"


@pytest.mark.parametrize(
    ("service", "data", "expected_cmd", "expected_args"),
    [
        (
            "tv_send_key",
            {"key": "HOME", "device_ip": "192.168.0.10", "device_type": "samsung"},
            "tv_send_key",
            {"key": "HOME", "device_ip": "192.168.0.10", "device_type": "samsung"},
        ),
        (
            "tv_launch_app",
            {"app": "Netflix", "device_ip": "192.168.0.10"},
            "tv_launch_app",
            {"param": "Netflix", "device_ip": "192.168.0.10", "device_type": ""},
        ),
        (
            "sonos_play_uri",
            {"uri": "x-sonos-http:foo", "device_ip": "192.168.0.20"},
            "sonos_play_uri",
            {"param": "x-sonos-http:foo", "device_ip": "192.168.0.20"},
        ),
        (
            "sonos_play_spotify",
            {"uri": "spotify:track:abc"},
            "sonos_play_spotify",
            {"param": "spotify:track:abc", "device_ip": ""},
        ),
        (
            "sonos_play_favorite",
            {"favorite": "Morning Jazz"},
            "sonos_play_favorite",
            {"param": "Morning Jazz", "device_ip": ""},
        ),
        (
            "sonos_set_volume",
            {"volume": 35, "device_ip": "192.168.0.20"},
            "sonos_set_volume",
            {"volume": 35, "device_ip": "192.168.0.20"},
        ),
        (
            "sonos_adjust_volume",
            {"delta": -3},
            "sonos_adjust_volume",
            {"delta": -3, "device_ip": ""},
        ),
        (
            "sonos_join",
            {"master_ip": "192.168.0.20"},
            "sonos_join",
            {"param": "192.168.0.20", "device_ip": ""},
        ),
        ("rescan_discovery", {}, "rescan_discovery", {}),
    ],
)
async def test_service_cmd_mapping(
    hass: HomeAssistant,
    fake_server: FakeLydbroServer,
    service: str,
    data: dict[str, Any],
    expected_cmd: str,
    expected_args: dict[str, Any],
) -> None:
    """Each service forwards to the documented cmd with the documented args."""
    _, device_id = await _setup(hass, fake_server)

    await hass.services.async_call(
        DOMAIN,
        service,
        {ATTR_DEVICE_ID: device_id, **data},
        blocking=True,
    )

    assert len(fake_server.received_cmds) == 1
    frame = fake_server.received_cmds[0]
    assert frame["cmd"] == expected_cmd
    for key, value in expected_args.items():
        assert frame[key] == value, f"{service}: {key}={frame.get(key)!r} != {value!r}"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


async def test_service_unknown_device_raises(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Service call against a non-Lydbro device id raises device_not_found."""
    await _setup(hass, fake_server)

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            "send_remote_key",
            {ATTR_DEVICE_ID: "not-a-real-device-id", "key": "Play"},
            blocking=True,
        )

    err = exc_info.value
    assert err.translation_domain == DOMAIN
    assert err.translation_key == "device_not_found"


async def test_service_protocol_error_translated(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """A server-side ``ok=false`` result surfaces as a translated HA error."""
    _, device_id = await _setup(hass, fake_server)

    async def handler(frame: dict[str, Any]) -> dict[str, Any]:
        return {
            "t": "result",
            "id": frame["id"],
            "ok": False,
            "error": "no such device",
        }

    fake_server.cmd_handler = handler

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            "send_remote_key",
            {ATTR_DEVICE_ID: device_id, "key": "Play"},
            blocking=True,
        )

    err = exc_info.value
    assert err.translation_domain == DOMAIN
    assert err.translation_key == "cmd_failed"
    # Placeholders surface both the failing cmd name and the server error.
    assert err.translation_placeholders == {
        "cmd": "send_remote_key",
        "error": "no such device",
    }


# ---------------------------------------------------------------------------
# Virtual remote-key buttons
# ---------------------------------------------------------------------------


async def test_virtual_remote_button_press_forwards_send_remote_key(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Pressing the virtual Play button fires send_remote_key key=Play.

    The entity is disabled by default so we re-enable it explicitly
    — that's the real-world flow: user enables the buttons they
    care about from the device page, then drags them onto a card.
    """
    await _setup(hass, fake_server)

    ent_reg = er.async_get(hass)
    entity_id = "button.test_lydbro_one_play"
    entry = ent_reg.async_get(entity_id)
    assert entry is not None, "expected virtual Play button entity to exist"
    assert entry.disabled_by is not None, "virtual buttons should be disabled by default"

    # Re-enable and force a reload so the platform picks it up.
    ent_reg.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.config_entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    # The press → send_remote_key(key="Play") round-trip should have
    # produced exactly one cmd on the fake bridge.
    cmds = [c for c in fake_server.received_cmds if c["cmd"] == "send_remote_key"]
    assert len(cmds) == 1
    assert cmds[0]["key"] == "Play"
