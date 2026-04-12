"""Coordinator — owns the TCP client and fans out state/events to entities."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .client import CONNECT_TIMEOUT, LydbroClient, LydbroProtocolError
from .const import (
    DOMAIN,
    SIGNAL_CONNECTION,
    SIGNAL_EVENT,
    SIGNAL_STATE_UPDATED,
)

_LOGGER = logging.getLogger(__name__)


class LydbroCoordinator:
    """Owns one persistent TCP connection for one config entry.

    HA's DataUpdateCoordinator is built around polling; this device is
    push-based, so we implement a thinner equivalent directly on top of
    :class:`LydbroClient`. Entities subscribe via ``async_dispatcher_connect``
    using the per-entry signals in :mod:`.const`.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.host: str = entry.data["host"]
        self.port: int = entry.data.get("port", 6204)
        self.device_id: str = entry.data["device_id"]

        # Latest state snapshot, merged from every `state` and `state_change`
        # event the server sends. Entities read from this dict directly.
        self.state: dict[str, Any] = {}
        self.hello: dict[str, Any] = {}
        self.available = False

        self._client = LydbroClient(
            self.host,
            self.port,
            on_hello=self._handle_hello,
            on_state=self._handle_state,
            on_event=self._handle_event,
            on_connection_change=self._handle_connection,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_start(self) -> None:
        """Connect and block until the first state snapshot arrives."""
        await self._client.start()
        ok = await self._client.wait_connected(CONNECT_TIMEOUT + 2.0)
        if not ok:
            # Don't fail setup — reconnect loop keeps trying in the
            # background. Entities come up as unavailable until the first
            # snapshot lands.
            _LOGGER.warning(
                "lydbro %s:%d did not complete handshake in time; will retry",
                self.host,
                self.port,
            )

    async def async_stop(self) -> None:
        await self._client.stop()

    # ------------------------------------------------------------------
    # Commands — thin wrappers so services/entities don't need to know
    # about the client class directly.
    # ------------------------------------------------------------------

    async def async_send_cmd(self, cmd: str, **args: Any) -> dict[str, Any]:
        try:
            return await self._client.send_cmd(cmd, **args)
        except LydbroProtocolError as err:
            _LOGGER.error("lydbro cmd %s failed: %s", cmd, err)
            raise

    # ------------------------------------------------------------------
    # Client callbacks — merge state, dispatch to entities
    # ------------------------------------------------------------------

    async def _handle_hello(self, frame: dict[str, Any]) -> None:
        self.hello = frame
        _LOGGER.debug(
            "lydbro hello from %s: fw=%s branch=%s id=%s",
            self.host,
            frame.get("fw"),
            frame.get("branch"),
            frame.get("id"),
        )

    async def _handle_state(self, frame: dict[str, Any]) -> None:
        # Full snapshot — replace, don't merge, so removed keys disappear.
        snapshot = {k: v for k, v in frame.items() if k != "t"}
        self.state = snapshot
        self.available = True
        async_dispatcher_send(
            self.hass, SIGNAL_STATE_UPDATED.format(self.entry.entry_id)
        )

    async def _handle_event(self, frame: dict[str, Any]) -> None:
        etype = frame.get("type")

        # state_change events are the device's way of pushing a delta
        # without re-sending the whole snapshot. Merge into local state.
        if etype == "state_change":
            name = frame.get("name")
            value = frame.get("value")
            if isinstance(name, str):
                self.state[name] = value
                async_dispatcher_send(
                    self.hass, SIGNAL_STATE_UPDATED.format(self.entry.entry_id)
                )

        # boot_phase events also update the state dict so sensors stay
        # in sync during the startup splash.
        if etype == "boot_phase":
            phase = frame.get("phase")
            if isinstance(phase, str):
                self.state["boot_phase"] = phase
                async_dispatcher_send(
                    self.hass, SIGNAL_STATE_UPDATED.format(self.entry.entry_id)
                )

        # Fan out every event to event entities / automations. Even the
        # state_change / boot_phase ones are forwarded — some users want
        # to trigger on them directly.
        async_dispatcher_send(
            self.hass, SIGNAL_EVENT.format(self.entry.entry_id), frame
        )

    async def _handle_connection(self, connected: bool) -> None:
        self.available = connected
        if not connected:
            _LOGGER.info("lydbro %s disconnected, will reconnect", self.host)
        async_dispatcher_send(
            self.hass, SIGNAL_CONNECTION.format(self.entry.entry_id), connected
        )
        async_dispatcher_send(
            self.hass, SIGNAL_STATE_UPDATED.format(self.entry.entry_id)
        )
