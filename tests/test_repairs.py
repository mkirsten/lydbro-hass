"""Repair-issue monitor tests.

Exercises the three issue classes end-to-end against a live
coordinator + fake bridge:

* safe_mode raises an error-severity issue when state flips to True
  and clears it when it flips back;
* low_battery hysteresis — raise at ≤10, clear at ≥15, don't flap in
  the middle;
* ble_disconnected only fires after the grace period elapses; a
  reconnect before then cancels the timer silently.
"""

from __future__ import annotations

import asyncio

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lydbro import repairs as repairs_mod
from custom_components.lydbro.const import DOMAIN
from custom_components.lydbro.coordinator import LydbroCoordinator

from .fake_server import FakeLydbroServer


async def _setup(
    hass: HomeAssistant, fake_server: FakeLydbroServer, **state_overrides
) -> tuple[MockConfigEntry, LydbroCoordinator]:
    # Allow tests to customise the initial state snapshot the bridge
    # pushes on connect.
    for key, value in state_overrides.items():
        fake_server.state[key] = value

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
    return entry, entry.runtime_data


def _issue(hass: HomeAssistant, kind: str) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{kind}_aa:bb:cc:dd:ee:ff")


async def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out")


# ---------------------------------------------------------------------------
# safe_mode
# ---------------------------------------------------------------------------


async def test_safe_mode_issue_raised_and_cleared(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Entering safe mode raises an error issue; exiting clears it."""
    _, _ = await _setup(hass, fake_server, safe_mode=True)

    issue = _issue(hass, "safe_mode")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.ERROR
    assert issue.translation_key == "safe_mode"
    # Placeholders carry enough context for the UI.
    assert issue.translation_placeholders["host"] == "127.0.0.1"

    # Bridge recovers → clear the issue.
    await fake_server.push_event("state_change", name="safe_mode", value=False)
    await _wait_for(lambda: _issue(hass, "safe_mode") is None)


async def test_no_safe_mode_issue_when_healthy(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    await _setup(hass, fake_server)
    assert _issue(hass, "safe_mode") is None


# ---------------------------------------------------------------------------
# low_battery with hysteresis
# ---------------------------------------------------------------------------


async def test_low_battery_hysteresis(hass: HomeAssistant, fake_server: FakeLydbroServer) -> None:
    """The issue raises below 10, stays put between 10–15, clears above 15."""
    _, _ = await _setup(hass, fake_server, battery=50)
    assert _issue(hass, "low_battery") is None

    # Drop below threshold → issue raised.
    await fake_server.push_event("state_change", name="battery", value="8")
    await _wait_for(lambda: _issue(hass, "low_battery") is not None)
    issue = _issue(hass, "low_battery")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_placeholders["battery"] == "8"

    # Partial recovery (still under clear point) → still active.
    await fake_server.push_event("state_change", name="battery", value="12")
    await asyncio.sleep(0.05)
    assert _issue(hass, "low_battery") is not None

    # Full recovery → cleared.
    await fake_server.push_event("state_change", name="battery", value="50")
    await _wait_for(lambda: _issue(hass, "low_battery") is None)


async def test_low_battery_non_numeric_ignored(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """battery=None or missing shouldn't raise the issue or crash."""
    fake_server.state.pop("battery", None)
    await _setup(hass, fake_server)
    assert _issue(hass, "low_battery") is None


# ---------------------------------------------------------------------------
# ble_disconnected grace period
# ---------------------------------------------------------------------------


async def test_ble_disconnected_waits_for_grace_period(
    hass: HomeAssistant,
    fake_server: FakeLydbroServer,
    monkeypatch,
) -> None:
    """BLE down past the grace period raises a warning issue."""
    # Shrink the grace period so the test doesn't wait 5 real minutes.
    # Keep it long enough to be observably longer than "test setup".
    monkeypatch.setattr(repairs_mod, "BLE_DOWN_GRACE_SECONDS", 0.5)

    await _setup(hass, fake_server, ble_connected=False)

    # Wait past the grace period → issue raised.
    await _wait_for(lambda: _issue(hass, "ble_disconnected") is not None, timeout=2.0)
    issue = _issue(hass, "ble_disconnected")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_key == "ble_disconnected"

    # BLE comes back → issue cleared.
    await fake_server.push_event("state_change", name="ble_connected", value=True)
    await _wait_for(lambda: _issue(hass, "ble_disconnected") is None)


async def test_ble_reconnect_within_grace_cancels_timer(
    hass: HomeAssistant,
    fake_server: FakeLydbroServer,
    monkeypatch,
) -> None:
    """A reconnect before the grace period elapses must not raise the issue."""
    monkeypatch.setattr(repairs_mod, "BLE_DOWN_GRACE_SECONDS", 5.0)

    await _setup(hass, fake_server, ble_connected=False)

    # Quickly reconnect before the 5s timer can fire.
    await fake_server.push_event("state_change", name="ble_connected", value=True)
    await asyncio.sleep(0.1)

    assert _issue(hass, "ble_disconnected") is None
