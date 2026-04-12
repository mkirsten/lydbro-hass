"""Config flow for Lydbro."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .client import CONNECT_TIMEOUT, LydbroClient, LydbroProtocolError
from .const import DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def _probe(host: str, port: int) -> dict[str, Any]:
    """Open a connection and wait for the hello frame.

    Returns the hello dict on success or raises :class:`LydbroProtocolError`.
    """
    hello: dict[str, Any] = {}
    done = asyncio.Event()

    async def on_hello(frame: dict[str, Any]) -> None:
        hello.update(frame)
        done.set()

    # The probe only needs ``on_hello`` — the client's callback
    # interface requires all three, but state and event frames that
    # arrive after hello are discarded. Whether they fire at all
    # depends on a race between ``client.stop()`` and the next
    # server frame, which makes these branches untestable in any
    # meaningful way.
    async def on_state(_frame: dict[str, Any]) -> None:  # pragma: no cover
        pass

    async def on_event(_frame: dict[str, Any]) -> None:  # pragma: no cover
        pass

    client = LydbroClient(
        host,
        port,
        on_hello=on_hello,
        on_state=on_state,
        on_event=on_event,
    )
    await client.start()
    try:
        try:
            await asyncio.wait_for(done.wait(), CONNECT_TIMEOUT + 2.0)
        except TimeoutError as err:
            raise LydbroProtocolError("no hello") from err
    finally:
        await client.stop()
    return hello


class LydbroConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lydbro."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._device_id: str | None = None
        self._name: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manual entry: user types the device IP or hostname."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            try:
                hello = await _probe(host, port)
            except LydbroProtocolError as err:
                _LOGGER.debug("lydbro probe failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                device_id = hello.get("id") or host
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
                return self.async_create_entry(
                    title=hello.get("name") or "Lydbro One",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        "device_id": device_id,
                        "fw_version": hello.get("fw"),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user change host/port without removing the entry.

        DHCP can move the device between reboots. Rather than forcing a
        delete-and-re-add (which would orphan automations keyed to the
        device registry id), this flow re-probes the supplied address
        and updates the existing entry in place. The probed hello must
        carry the same ``id`` as the configured entry — we refuse to
        point an existing entry at a different physical device, because
        that would silently break unique_id invariants and entity links.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            try:
                hello = await _probe(host, port)
            except LydbroProtocolError as err:
                _LOGGER.debug("lydbro reconfigure probe failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                probed_id = hello.get("id") or host
                if probed_id != entry.data.get("device_id"):
                    errors["base"] = "wrong_device"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={
                            CONF_HOST: host,
                            CONF_PORT: port,
                            "fw_version": hello.get("fw"),
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST, "")): str,
                vol.Optional(CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)): int,
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """Handle zeroconf discovery of _lydbro._tcp."""
        host = discovery_info.host
        port = discovery_info.port or DEFAULT_PORT
        props = discovery_info.properties or {}
        device_id = props.get("id") or discovery_info.name
        name = props.get("name") or "Lydbro One"

        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})

        self._host = host
        self._port = port
        self._device_id = device_id
        self._name = name
        self.context["title_placeholders"] = {"name": name, "host": host}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to confirm an auto-discovered device."""
        assert self._host is not None and self._device_id is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                hello = await _probe(self._host, self._port)
            except LydbroProtocolError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=self._name or "Lydbro One",
                    data={
                        CONF_HOST: self._host,
                        CONF_PORT: self._port,
                        "device_id": self._device_id,
                        "fw_version": hello.get("fw"),
                    },
                )

        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "name": self._name or "Lydbro One",
                "host": self._host,
            },
            errors=errors,
        )
