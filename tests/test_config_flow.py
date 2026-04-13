"""Config-flow tests for the Lydbro integration.

Covers every entry point into the flow:

* ``async_step_user``     — manual host/port entry.
* ``async_step_zeroconf`` — mDNS discovery of ``_lydbro._tcp``.
* ``async_step_discovery_confirm`` — user-facing confirm of a zeroconf hit.
* ``async_step_reconfigure`` — in-place host/port update on an existing entry.

Tests run the real flow code against :class:`FakeLydbroServer` over a
loopback socket, so ``_probe`` is exercised end-to-end. The only thing
mocked is mDNS discovery info, because that comes from ``hass``'s
zeroconf helper and never touches our code path.
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lydbro.const import DOMAIN

from .fake_server import FakeLydbroServer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _zeroconf_info(host: str, port: int, device_id: str, name: str) -> ZeroconfServiceInfo:
    """Build a fake ZeroconfServiceInfo matching the device's _lydbro._tcp record."""
    return ZeroconfServiceInfo(
        ip_address=host,  # phacc accepts a plain string here
        ip_addresses=[host],
        port=port,
        hostname=f"{name}.local.",
        type="_lydbro._tcp.local.",
        name=f"{name}._lydbro._tcp.local.",
        properties={"id": device_id, "name": name},
    )


async def _existing_entry(
    hass: HomeAssistant,
    *,
    host: str,
    port: int,
    device_id: str = "aa:bb:cc:dd:ee:ff",
) -> MockConfigEntry:
    """Register a config entry directly, as if a previous setup succeeded."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=device_id,
        data={
            CONF_HOST: host,
            CONF_PORT: port,
            "device_id": device_id,
            "fw_version": "0.11.9.3",
        },
        title="Test Lydbro One",
    )
    entry.add_to_hass(hass)
    return entry


# ---------------------------------------------------------------------------
# async_step_user
# ---------------------------------------------------------------------------


async def test_user_flow_happy_path(hass: HomeAssistant, fake_server: FakeLydbroServer) -> None:
    """User types a valid host → flow probes → entry is created."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: fake_server.port},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Lydbro One"
    assert result["data"][CONF_HOST] == "127.0.0.1"
    assert result["data"][CONF_PORT] == fake_server.port
    assert result["data"]["device_id"] == "aa:bb:cc:dd:ee:ff"
    assert result["data"]["fw_version"] == "0.13.0"

    # Unique id keyed on the MAC-ish id from the hello frame.
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == "aa:bb:cc:dd:ee:ff"


async def test_user_flow_cannot_connect(hass: HomeAssistant, socket_enabled) -> None:
    """No server listening → flow shows cannot_connect, stays on user step."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    # Point at a port that will refuse the connection. Port 1 is
    # reserved and tcpmux is never running in CI, so the probe fails
    # inside CONNECT_TIMEOUT without actually hanging.
    with patch("custom_components.lydbro.config_flow.CONNECT_TIMEOUT", 0.3):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "127.0.0.1", CONF_PORT: 1},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Adding a device that's already configured aborts and updates host/port."""
    await _existing_entry(hass, host="10.0.0.1", port=9999)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: fake_server.port},
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data[CONF_HOST] == "127.0.0.1"
    assert entry.data[CONF_PORT] == fake_server.port


# ---------------------------------------------------------------------------
# async_step_zeroconf
# ---------------------------------------------------------------------------


async def test_zeroconf_flow_happy_path(hass: HomeAssistant, fake_server: FakeLydbroServer) -> None:
    """Zeroconf hit → discovery_confirm form → user confirms → entry created."""
    discovery = _zeroconf_info(
        host="127.0.0.1",
        port=fake_server.port,
        device_id="aa:bb:cc:dd:ee:ff",
        name="Lab Lydbro One",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"]["name"] == "Lab Lydbro One"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Lab Lydbro One"
    assert result["data"][CONF_HOST] == "127.0.0.1"
    assert result["data"]["device_id"] == "aa:bb:cc:dd:ee:ff"


async def test_zeroconf_flow_already_configured_updates_host(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Zeroconf of an already-configured device updates its host/port and aborts."""
    await _existing_entry(hass, host="10.0.0.1", port=9999)

    discovery = _zeroconf_info(
        host="127.0.0.1",
        port=fake_server.port,
        device_id="aa:bb:cc:dd:ee:ff",
        name="Lab Lydbro One",
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data[CONF_HOST] == "127.0.0.1"
    assert entry.data[CONF_PORT] == fake_server.port


async def test_zeroconf_confirm_cannot_connect(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Server disappears between discovery and confirm → cannot_connect error."""
    discovery = _zeroconf_info(
        host="127.0.0.1",
        port=fake_server.port,
        device_id="aa:bb:cc:dd:ee:ff",
        name="Lab Lydbro One",
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery
    )
    assert result["step_id"] == "discovery_confirm"

    # Kill the bridge before the user confirms.
    await fake_server.stop()

    with patch("custom_components.lydbro.config_flow.CONNECT_TIMEOUT", 0.3):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["errors"] == {"base": "cannot_connect"}


# ---------------------------------------------------------------------------
# async_step_reconfigure
# ---------------------------------------------------------------------------


async def test_reconfigure_happy_path(hass: HomeAssistant, fake_server: FakeLydbroServer) -> None:
    """Reconfigure updates host/port on an existing entry when id matches."""
    entry = await _existing_entry(hass, host="10.0.0.99", port=1234)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: fake_server.port},
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    refreshed = hass.config_entries.async_get_entry(entry.entry_id)
    assert refreshed is not None
    assert refreshed.data[CONF_HOST] == "127.0.0.1"
    assert refreshed.data[CONF_PORT] == fake_server.port


async def test_reconfigure_cannot_connect(hass: HomeAssistant, socket_enabled) -> None:
    """Reconfigure probe failure keeps the user on the reconfigure step."""
    entry = await _existing_entry(hass, host="10.0.0.99", port=1234)

    result = await entry.start_reconfigure_flow(hass)
    with patch("custom_components.lydbro.config_flow.CONNECT_TIMEOUT", 0.3):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "127.0.0.1", CONF_PORT: 1},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "cannot_connect"}

    # Entry data unchanged.
    refreshed = hass.config_entries.async_get_entry(entry.entry_id)
    assert refreshed is not None
    assert refreshed.data[CONF_HOST] == "10.0.0.99"
    assert refreshed.data[CONF_PORT] == 1234


async def test_reconfigure_wrong_device(hass: HomeAssistant, fake_server: FakeLydbroServer) -> None:
    """Pointing at a different physical device is refused, not silently accepted."""
    entry = await _existing_entry(hass, host="10.0.0.99", port=1234, device_id="de:ad:be:ef:00:01")

    result = await entry.start_reconfigure_flow(hass)
    # The fake server's hello id is aa:bb:... — a different device.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: fake_server.port},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "wrong_device"}

    # Entry untouched — we refuse to repoint it at a different unit.
    refreshed = hass.config_entries.async_get_entry(entry.entry_id)
    assert refreshed is not None
    assert refreshed.data[CONF_HOST] == "10.0.0.99"
    assert refreshed.data["device_id"] == "de:ad:be:ef:00:01"
