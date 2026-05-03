"""Repair-issue monitor for Lydbro.

Surfaces three classes of problem to the HA Repairs dashboard so
users see them without having to trawl through logs:

* **safe_mode** — the bridge entered safe mode (crash loop). Severity
  ``error``. Clears when safe_mode drops back to False.
* **low_battery** — the BeoRemote One's battery is below
  :data:`LOW_BATTERY_THRESHOLD` percent. Severity ``warning``. Uses
  hysteresis (must recover past :data:`LOW_BATTERY_CLEAR`) so a
  remote bouncing around the threshold doesn't flap the issue on
  and off.
* **ble_disconnected** — the BLE link to the BeoRemote One has been
  down for more than :data:`BLE_DOWN_GRACE_SECONDS`. Severity
  ``warning``. A short drop is normal (the remote sleeps) so we
  deliberately wait before raising.

:class:`LydbroIssueMonitor` is owned by :class:`LydbroCoordinator`
and evaluated on every state update, plus on a timer for the BLE
grace period.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import LydbroCoordinator


# Tunable thresholds. Kept at module scope so tests can monkeypatch
# them without reaching into a class.
LOW_BATTERY_THRESHOLD = 10  # %  — raise at or below this
LOW_BATTERY_CLEAR = 15  # %  — clear once we recover past this
BLE_DOWN_GRACE_SECONDS = 300  # 5 min — ignore short wake-ups


def _issue_id(kind: str, device_id: str) -> str:
    """Issue-registry id that's stable per device and kind."""
    return f"{kind}_{device_id}"


class LydbroIssueMonitor:
    """Raises and clears HA repair issues based on coordinator state."""

    def __init__(self, hass: HomeAssistant, coordinator: LydbroCoordinator) -> None:
        self._hass = hass
        self._coordinator = coordinator

        # Hysteresis + grace-period bookkeeping.
        self._low_battery_active = False
        self._ble_down_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def evaluate(self) -> None:
        """Evaluate all three issue classes against the current state.

        Safe to call from the event loop on every state update — all
        interactions with the issue registry are idempotent, so
        repeating evaluations don't flap the UI.
        """
        state = self._coordinator.state
        self._check_safe_mode(state)
        self._check_low_battery(state)
        self._check_ble_link(state)

    def shutdown(self) -> None:
        """Cancel the pending BLE-down grace-period task on unload."""
        if self._ble_down_task is not None:
            self._ble_down_task.cancel()
            self._ble_down_task = None

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_safe_mode(self, state: dict[str, Any]) -> None:
        issue_id = _issue_id("safe_mode", self._coordinator.device_id)
        if state.get("safe_mode") is True:
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="safe_mode",
                translation_placeholders={
                    "name": self._coordinator.hello.get("name") or self._coordinator.entry.title,
                    "host": self._coordinator.host,
                },
                learn_more_url=f"http://{self._coordinator.host}/",
            )
        else:
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)

    def _check_low_battery(self, state: dict[str, Any]) -> None:
        issue_id = _issue_id("low_battery", self._coordinator.device_id)
        battery = state.get("battery")
        if not isinstance(battery, int | float) or battery < 0:
            return
        # Hysteresis: the issue can only become active below the
        # lower threshold, and can only clear above the higher one.
        # Between the two it keeps its current state.
        if battery <= LOW_BATTERY_THRESHOLD and not self._low_battery_active:
            self._low_battery_active = True
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="low_battery",
                translation_placeholders={"battery": str(int(battery))},
            )
        elif battery >= LOW_BATTERY_CLEAR and self._low_battery_active:
            self._low_battery_active = False
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)

    def _check_ble_link(self, state: dict[str, Any]) -> None:
        issue_id = _issue_id("ble_disconnected", self._coordinator.device_id)
        connected = bool(state.get("ble_connected"))

        if connected:
            # Cancel any pending grace-period timer and clear the issue.
            if self._ble_down_task is not None:
                self._ble_down_task.cancel()
                self._ble_down_task = None
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)
            return

        # Disconnected. If we're not already waiting, start the
        # grace-period timer that will raise the issue if the link
        # stays down for BLE_DOWN_GRACE_SECONDS.
        if self._ble_down_task is None or self._ble_down_task.done():
            self._ble_down_task = self._hass.async_create_task(self._ble_grace_period(issue_id))

    async def _ble_grace_period(self, issue_id: str) -> None:
        try:
            await asyncio.sleep(BLE_DOWN_GRACE_SECONDS)
        except asyncio.CancelledError:
            return
        # Still disconnected after the grace period? Raise.
        if not self._coordinator.state.get("ble_connected"):
            # Round up so the UI never says "0 minutes" — in prod
            # BLE_DOWN_GRACE_SECONDS is 300 (5 min); tests shrink it
            # to <60 which would otherwise integer-divide to 0.
            minutes = max(1, round(BLE_DOWN_GRACE_SECONDS / 60))
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="ble_disconnected",
                translation_placeholders={"minutes": str(minutes)},
            )
