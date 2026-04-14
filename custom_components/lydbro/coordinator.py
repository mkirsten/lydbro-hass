"""Coordinator — owns the TCP client and fans out state/events to entities."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .client import CONNECT_TIMEOUT, LydbroClient, LydbroProtocolError
from .const import (
    DOMAIN,
    EVENT_BUS_BUTTON,
    EVENT_BUS_MENU,
    EVENT_BUS_SCENE,
    NUMERIC_STATE_KEYS,
    SIGNAL_CONNECTION,
    SIGNAL_EVENT,
    SIGNAL_STATE_UPDATED,
)
from .repairs import LydbroIssueMonitor

_LOGGER = logging.getLogger(__name__)


def _coerce_numeric(key: str, value: Any) -> Any:
    """Normalize state values so sensors don't see int/str drift.

    The firmware encodes numeric fields as ints in full ``state``
    snapshots but as strings in ``state_change`` events (every value
    field in a state_change frame is a string). Without this coercion
    the battery sensor flips between ``50`` and ``"50"`` across the
    reconnect/poll boundary, and HA's numeric device_class machinery
    complains.
    """
    if key not in NUMERIC_STATE_KEYS or value is None:
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return None
    return value


def _normalize_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {k: _coerce_numeric(k, v) for k, v in snapshot.items()}


class LydbroCoordinator:
    """Owns one persistent TCP connection for one config entry.

    HA's DataUpdateCoordinator is built around polling; this device is
    push-based, so we implement a thinner equivalent directly on top of
    :class:`LydbroClient`. Entities subscribe via ``async_dispatcher_connect``
    using the per-entry signals in :mod:`.const`.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry[Any]) -> None:
        self.hass = hass
        self.entry = entry
        self.host: str = entry.data["host"]
        self.port: int = entry.data.get("port", 6204)
        self.device_id: str = entry.data["device_id"]

        # Latest state snapshot, merged from every `state` frame and
        # `state_change` event the server sends. Entities read it directly.
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
        self._issue_monitor = LydbroIssueMonitor(hass, self)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_start(self) -> None:
        """Connect and block until the first state snapshot arrives."""
        await self._client.start()
        ok = await self._client.wait_connected(CONNECT_TIMEOUT + 2.0)
        if not ok:
            # Don't fail setup — reconnect loop keeps trying in the
            # background. Entities come up as unavailable until the
            # first snapshot lands.
            _LOGGER.warning(
                "lydbro %s:%d did not complete handshake in time; will retry",
                self.host,
                self.port,
            )

    async def async_stop(self) -> None:
        self._issue_monitor.shutdown()
        await self._client.stop()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def async_send_cmd(self, cmd: str, **args: Any) -> dict[str, Any]:
        """Forward a command to the bridge.

        Protocol errors are translated into :class:`HomeAssistantError`
        with a localised ``cmd_failed`` translation key so entity
        actions and service calls surface a readable message in the
        HA notification area instead of a raw exception.
        """
        try:
            return await self._client.send_cmd(cmd, **args)
        except LydbroProtocolError as err:
            _LOGGER.error("lydbro cmd %s failed: %s", cmd, err)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cmd_failed",
                translation_placeholders={"cmd": cmd, "error": str(err)},
            ) from err

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ha_device_id(self) -> str | None:
        """Look up the HA device-registry id for this bridge.

        Device triggers need the registry id, not the lydbro MAC-based
        ``device_id``. The device is registered when the first entity
        platform adds entities, so this returns None until then — we
        look up lazily on every button press rather than caching.
        """
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={(DOMAIN, self.device_id)})
        return device.id if device else None

    # ------------------------------------------------------------------
    # Client callbacks
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
        name = frame.get("name")
        if isinstance(name, str) and name and name != self.entry.title:
            self.hass.config_entries.async_update_entry(self.entry, title=name)

    async def _handle_state(self, frame: dict[str, Any]) -> None:
        snapshot = {k: v for k, v in frame.items() if k != "t"}
        self.state = _normalize_state(snapshot)
        self.available = True
        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED.format(self.entry.entry_id))
        self._issue_monitor.evaluate()

    async def _handle_event(self, frame: dict[str, Any]) -> None:
        etype = frame.get("type")
        state_touched = False

        # state_change events are the device's way of pushing a delta
        # without re-sending the whole snapshot. Merge into local state,
        # coercing numeric fields so the sensor layer sees consistent
        # types across snapshot + delta paths.
        if etype == "state_change":
            name = frame.get("name")
            value = frame.get("value")
            if isinstance(name, str):
                self.state[name] = _coerce_numeric(name, value)
                state_touched = True
                self._issue_monitor.evaluate()

        if etype == "boot_phase":
            phase = frame.get("phase")
            if isinstance(phase, str):
                self.state["boot_phase"] = phase
                state_touched = True

        # Every event frame that carries a ``mode`` field is a truthful
        # report of the remote's current mode — use the most recent one
        # as the device's "current mode". This is how the mode sensor
        # tracks MUSIC / TV / RADIO / … since the firmware doesn't
        # publish mode in the state snapshot.
        mode = frame.get("mode")
        if isinstance(mode, str) and mode and self.state.get("mode") != mode:
            self.state["mode"] = mode
            state_touched = True

        # Record "last button press" so a sensor can surface it for
        # dashboards. We store the timestamp as an ISO-8601 string so
        # the state dict stays JSON-serialisable (diagnostics dump it
        # raw), plus the name/kind/mode so the sensor can expose them
        # as attributes.
        if etype == "button_press":
            self.state["last_button_press"] = datetime.now(UTC).isoformat()
            self.state["last_button_name"] = frame.get("name")
            self.state["last_button_kind"] = frame.get("kind")
            self.state["last_button_mode"] = frame.get("mode")
            state_touched = True

        if state_touched:
            async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED.format(self.entry.entry_id))

        # Fan out to dispatcher listeners (event entities).
        async_dispatcher_send(self.hass, SIGNAL_EVENT.format(self.entry.entry_id), frame)

        # Fire HA bus events for button / menu / scene presses. This is
        # how device triggers attach — they register an "event" trigger
        # filtered by event_data.device_id + name + kind, so the bus
        # event is the load-bearing thing (not just the dispatcher).
        if etype in ("button_press", "menu_selection", "scene_button"):
            ha_device_id = self._ha_device_id()
            if ha_device_id is None:
                return
            bus_event = {
                "button_press": EVENT_BUS_BUTTON,
                "menu_selection": EVENT_BUS_MENU,
                "scene_button": EVENT_BUS_SCENE,
            }[etype]
            data = {"device_id": ha_device_id, **{k: v for k, v in frame.items() if k != "t"}}
            self.hass.bus.async_fire(bus_event, data)

    async def _handle_connection(self, connected: bool) -> None:
        self.available = connected
        if not connected:
            _LOGGER.info("lydbro %s disconnected, will reconnect", self.host)
        async_dispatcher_send(self.hass, SIGNAL_CONNECTION.format(self.entry.entry_id), connected)
        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED.format(self.entry.entry_id))
