"""Repair-issue monitor tests.

Exercises the issue classes end-to-end against a live coordinator +
fake bridge:

* safe_mode raises an error-severity issue when state flips to True
  and clears it when it flips back;
* low_battery hysteresis — raise at ≤10, clear at ≥15, don't flap in
  the middle.
"""

from __future__ import annotations

import asyncio

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

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


async def test_legacy_ble_disconnected_issue_cleared_on_startup(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """A lingering ble_disconnected issue from an older version is cleared."""
    # Pre-seed the registry as if the previous version had raised it.
    ir.async_create_issue(
        hass,
        DOMAIN,
        "ble_disconnected_aa:bb:cc:dd:ee:ff",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="ble_disconnected",
    )
    assert _issue(hass, "ble_disconnected") is not None

    await _setup(hass, fake_server)
    await _wait_for(lambda: _issue(hass, "ble_disconnected") is None)
