"""Repair-issue monitor for Lydbro.

Surfaces two classes of problem to the HA Repairs dashboard so
users see them without having to trawl through logs:

* **safe_mode** — the bridge entered safe mode (crash loop). Severity
  ``error``. Clears when safe_mode drops back to False.
* **low_battery** — the BeoRemote One's battery is below
  :data:`LOW_BATTERY_THRESHOLD` percent. Severity ``warning``. Uses
  hysteresis (must recover past :data:`LOW_BATTERY_CLEAR`) so a
  remote bouncing around the threshold doesn't flap the issue on
  and off.

:class:`LydbroIssueMonitor` is owned by :class:`LydbroCoordinator`
and evaluated on every state update.
"""

from __future__ import annotations

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


def _issue_id(kind: str, device_id: str) -> str:
    """Issue-registry id that's stable per device and kind."""
    return f"{kind}_{device_id}"


class LydbroIssueMonitor:
    """Raises and clears HA repair issues based on coordinator state."""

    def __init__(self, hass: HomeAssistant, coordinator: LydbroCoordinator) -> None:
        self._hass = hass
        self._coordinator = coordinator

        # Hysteresis bookkeeping.
        self._low_battery_active = False

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def evaluate(self) -> None:
        """Evaluate the issue classes against the current state.

        Safe to call from the event loop on every state update — all
        interactions with the issue registry are idempotent, so
        repeating evaluations don't flap the UI.
        """
        state = self._coordinator.state
        self._check_safe_mode(state)
        self._check_low_battery(state)
        # Clear any lingering issue from older versions that raised a
        # repair when the BLE link stayed down. The BeoRemote One
        # normally disconnects when idle so that notification was noise.
        ir.async_delete_issue(
            self._hass,
            DOMAIN,
            _issue_id("ble_disconnected", self._coordinator.device_id),
        )

    def shutdown(self) -> None:
        """Hook for unload-time cleanup. Currently nothing to cancel."""
        return

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
