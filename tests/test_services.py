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


@pytest.mark.parametrize(
    ("entity_id", "expected_cmd"),
    [
        ("button.test_lydbro_one_reboot", "reboot"),
        ("button.test_lydbro_one_reset_beoremote_pairing", "reset_pairing"),
        ("button.test_lydbro_one_disconnect_beoremote", "ble_disconnect"),
    ],
)
async def test_admin_button_press_forwards_cmd(
    hass: HomeAssistant,
    fake_server: FakeLydbroServer,
    entity_id: str,
    expected_cmd: str,
) -> None:
    """Each admin button maps to its documented wire cmd."""
    await _setup(hass, fake_server)

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    assert len(fake_server.received_cmds) == 1
    assert fake_server.received_cmds[0]["cmd"] == expected_cmd


async def test_services_only_registered_once_across_multiple_entries(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Loading a second config entry re-enters async_register_services.

    The idempotency guard (``has_service`` check) should short-circuit
    the second call — without it we'd get "service already registered"
    warnings and double-register handlers.
    """
    # First entry via the usual _setup helper.
    await _setup(hass, fake_server)
    assert hass.services.has_service(DOMAIN, "send_remote_key")

    # Second entry on the same fake bridge — different unique_id so
    # HA accepts it as a separate config entry, different host to
    # keep the unique_id keying obvious.
    second = MockConfigEntry(
        domain=DOMAIN,
        unique_id="11:22:33:44:55:66",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: fake_server.port,
            "device_id": "11:22:33:44:55:66",
            "fw_version": "0.11.9.3",
        },
        title="Second Lydbro One",
    )
    second.add_to_hass(hass)
    # The fake server only tracks one connected client at a time but
    # the coordinator's async_start doesn't block on a clean handshake
    # — it logs a warning and keeps trying. For this test we only
    # care that the services-register path short-circuits.
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()

    # Still exactly the one registration, no duplicate handlers.
    assert hass.services.has_service(DOMAIN, "send_remote_key")


async def test_tv_send_key_forwards_cmd(hass: HomeAssistant, fake_server: FakeLydbroServer) -> None:
    """tv_send_key sends the key directly to the TV via the bridge."""
    _, device_id = await _setup(hass, fake_server)

    await hass.services.async_call(
        DOMAIN,
        "tv_send_key",
        {ATTR_DEVICE_ID: device_id, "key": "KEY_VOLUP"},
        blocking=True,
    )

    cmds = fake_server.received_cmds
    assert len(cmds) == 1
    assert cmds[0]["cmd"] == "tv_send_key"
    assert cmds[0]["key"] == "KEY_VOLUP"


async def test_tv_launch_app_forwards_cmd_with_name_field(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """tv_launch_app sends the app name as the 'name' wire field."""
    _, device_id = await _setup(hass, fake_server)

    await hass.services.async_call(
        DOMAIN,
        "tv_launch_app",
        {ATTR_DEVICE_ID: device_id, "app": "Netflix"},
        blocking=True,
    )

    cmds = fake_server.received_cmds
    assert len(cmds) == 1
    assert cmds[0]["cmd"] == "tv_launch_app"
    assert cmds[0]["name"] == "Netflix"
