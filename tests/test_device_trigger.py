"""Device-trigger tests.

The trigger layer translates "Lydbro One: Play button clicked" from
the HA automation editor into an event-platform trigger that listens
for the bus events :class:`LydbroCoordinator` fires. These tests
verify that mapping end-to-end — register a trigger, fire the
matching bus event from the fake bridge, and assert the automation
action runs.
"""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.components import automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_get_device_automations,
    async_mock_service,
)

from custom_components.lydbro.const import DOMAIN

from .fake_server import FakeLydbroServer


async def _setup_and_device_id(hass: HomeAssistant, fake_server: FakeLydbroServer) -> str:
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
    return device.id


async def _wait_for_calls(calls: list[ServiceCall], expected: int, timeout: float = 2.0) -> None:
    """Wait until ``calls`` has ``expected`` entries or timeout.

    The chain push_event → socket → read loop → coordinator → bus →
    automation → action script → service call is multi-step async,
    so assertions need a brief spin rather than a single
    ``async_block_till_done``.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if len(calls) >= expected:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"expected {expected} service calls, got {len(calls)}")


@pytest.fixture
def service_calls(hass: HomeAssistant) -> list[ServiceCall]:
    """Register a ``test.trigger_fired`` service and collect its calls.

    ``async_mock_service`` returns the list that HA appends each
    ServiceCall to — using it instead of a manual async_register
    avoids a subtle caching quirk where HA doesn't call the handler
    if the service wasn't set up through the proper helper.
    """
    return async_mock_service(hass, "test", "trigger_fired")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


async def test_get_triggers_lists_button_scene_and_menu(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """async_get_triggers exposes button+scene+menu triggers for the device."""
    ha_device_id = await _setup_and_device_id(hass, fake_server)

    all_triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, ha_device_id
    )
    # The helper aggregates triggers from every device-automation
    # source — HA's built-in button/event entity triggers plus our
    # lydbro ones. Filter to the Lydbro-domain subset before asserting
    # on trigger types.
    lydbro_triggers = [t for t in all_triggers if t["domain"] == DOMAIN]
    assert lydbro_triggers, "no lydbro triggers returned"

    types = {t["type"] for t in lydbro_triggers}
    # A handful of button+kind combos must be present.
    assert "button_Play_click" in types
    assert "button_Home_hold" in types
    assert "button_Play_double" in types
    # All four scene corners.
    assert {"scene_top_left", "scene_top_right", "scene_bottom_left", "scene_bottom_right"} <= types
    # Single menu trigger.
    assert "menu_select" in types
    for t in lydbro_triggers:
        assert t["device_id"] == ha_device_id


# ---------------------------------------------------------------------------
# Attach + fire
# ---------------------------------------------------------------------------


async def test_button_trigger_fires_automation(
    hass: HomeAssistant,
    fake_server: FakeLydbroServer,
    service_calls: list[ServiceCall],
) -> None:
    """Automation with a button trigger runs when the matching bus event fires."""
    ha_device_id = await _setup_and_device_id(hass, fake_server)

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "alias": "play click",
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": ha_device_id,
                        "type": "button_Play_click",
                    },
                    "action": {"service": "test.trigger_fired"},
                },
            ]
        },
    )
    await hass.async_block_till_done()

    # Wrong kind — should not fire.
    await fake_server.push_event("button_press", name="Play", kind="hold", mode="MUSIC")
    await asyncio.sleep(0.05)
    assert service_calls == []

    # Wrong name — should not fire.
    await fake_server.push_event("button_press", name="Next", kind="click", mode="MUSIC")
    await asyncio.sleep(0.05)
    assert service_calls == []

    # Matching frame — should fire exactly once.
    await fake_server.push_event("button_press", name="Play", kind="click", mode="MUSIC")
    await _wait_for_calls(service_calls, 1)


async def test_scene_trigger_fires_automation(
    hass: HomeAssistant,
    fake_server: FakeLydbroServer,
    service_calls: list[ServiceCall],
) -> None:
    ha_device_id = await _setup_and_device_id(hass, fake_server)

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "alias": "top left scene",
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": ha_device_id,
                        "type": "scene_top_left",
                    },
                    "action": {"service": "test.trigger_fired"},
                },
            ]
        },
    )
    await hass.async_block_till_done()

    await fake_server.push_event("scene_button", name="Morning", position="top_right", mode="MUSIC")
    await asyncio.sleep(0.05)
    assert service_calls == []

    await fake_server.push_event("scene_button", name="Morning", position="top_left", mode="MUSIC")
    await _wait_for_calls(service_calls, 1)


async def test_menu_trigger_fires_on_any_menu_event(
    hass: HomeAssistant,
    fake_server: FakeLydbroServer,
    service_calls: list[ServiceCall],
) -> None:
    """menu_select is a single catch-all trigger — name filtering is in the action."""
    ha_device_id = await _setup_and_device_id(hass, fake_server)

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "alias": "any menu",
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": ha_device_id,
                        "type": "menu_select",
                    },
                    "action": {"service": "test.trigger_fired"},
                },
            ]
        },
    )
    await hass.async_block_till_done()

    await fake_server.push_event(
        "menu_selection", name="Jazz", source="spotify", id="pl_1", mode="MUSIC"
    )
    await _wait_for_calls(service_calls, 1)
