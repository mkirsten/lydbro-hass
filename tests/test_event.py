"""Event-entity tests.

Three ``event.*`` entities are created per device:

  * ``event.test_lydbro_one_button`` — physical button presses
  * ``event.test_lydbro_one_menu``   — vendor-menu selections
  * ``event.test_lydbro_one_scene``  — four corner scene buttons

Each subscribes to the per-entry ``SIGNAL_EVENT`` dispatcher and
filters by ``frame.type`` so each entity only reacts to its own kind
of frame. Unknown button names and unknown scene positions are
silently dropped — HA's event platform doesn't reliably propagate
dynamic additions to ``event_types``, so firmware-side changes need
a matching update in ``const.KNOWN_BUTTONS``.
"""

from __future__ import annotations

import asyncio

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lydbro.const import DOMAIN

from .fake_server import FakeLydbroServer

BUTTON_ENTITY_ID = "event.test_lydbro_one_button"
MENU_ENTITY_ID = "event.test_lydbro_one_menu"
SCENE_ENTITY_ID = "event.test_lydbro_one_scene"


async def _setup(hass: HomeAssistant, fake_server: FakeLydbroServer) -> None:
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


async def _wait_for_state(
    hass: HomeAssistant,
    entity_id: str,
    predicate,
    timeout: float = 1.0,
) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        state = hass.states.get(entity_id)
        if state is not None and predicate(state):
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"timed out waiting for {entity_id} state")


# ---------------------------------------------------------------------------
# Button event entity
# ---------------------------------------------------------------------------


async def test_button_event_known_name_triggers_and_carries_attributes(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    await _setup(hass, fake_server)

    await fake_server.push_event("button_press", name="Play", kind="click", mode="MUSIC")
    await _wait_for_state(
        hass,
        BUTTON_ENTITY_ID,
        lambda s: s.attributes.get("event_type") == "Play",
    )

    state = hass.states.get(BUTTON_ENTITY_ID)
    assert state is not None
    # The kind/mode come through as extra attributes on the entity.
    assert state.attributes["name"] == "Play"
    assert state.attributes["kind"] == "click"
    assert state.attributes["mode"] == "MUSIC"


async def test_button_event_unknown_name_dropped(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Firmware names outside KNOWN_BUTTONS are dropped, not crashed on."""
    await _setup(hass, fake_server)

    initial = hass.states.get(BUTTON_ENTITY_ID)
    initial_state = initial.state if initial else None

    await fake_server.push_event("button_press", name="MadeUpKey", kind="click", mode="MUSIC")
    await asyncio.sleep(0.05)

    state = hass.states.get(BUTTON_ENTITY_ID)
    assert state is not None
    # No event fired — the entity state hasn't advanced past its
    # initial "no event yet" placeholder.
    assert state.state == initial_state


async def test_button_event_ignores_non_button_frames(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """menu_selection / scene_button frames don't touch the button entity."""
    await _setup(hass, fake_server)

    initial = hass.states.get(BUTTON_ENTITY_ID)
    initial_state = initial.state if initial else None

    await fake_server.push_event("menu_selection", name="Jazz", mode="MUSIC")
    await fake_server.push_event("scene_button", name="N", position="top_left", mode="MUSIC")
    await asyncio.sleep(0.05)

    state = hass.states.get(BUTTON_ENTITY_ID)
    assert state is not None
    assert state.state == initial_state


# ---------------------------------------------------------------------------
# Menu event entity
# ---------------------------------------------------------------------------


async def test_menu_event_single_menu_type(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    """Menu entity exposes one event_type "Menu"; frame data lands as attributes."""
    await _setup(hass, fake_server)

    await fake_server.push_event(
        "menu_selection", name="Jazz", source="spotify", id="pl_1", mode="MUSIC"
    )
    await _wait_for_state(
        hass,
        MENU_ENTITY_ID,
        lambda s: s.attributes.get("event_type") == "Menu",
    )

    state = hass.states.get(MENU_ENTITY_ID)
    assert state is not None
    assert state.attributes["name"] == "Jazz"
    assert state.attributes["source"] == "spotify"
    assert state.attributes["id"] == "pl_1"
    assert "Menu" in state.attributes["event_types"]


# ---------------------------------------------------------------------------
# Scene event entity
# ---------------------------------------------------------------------------


async def test_scene_event_known_position_triggers(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    await _setup(hass, fake_server)

    await fake_server.push_event("scene_button", name="Morning", position="top_left", mode="MUSIC")
    await _wait_for_state(
        hass,
        SCENE_ENTITY_ID,
        lambda s: s.attributes.get("event_type") == "top_left",
    )

    state = hass.states.get(SCENE_ENTITY_ID)
    assert state is not None
    assert state.attributes["name"] == "Morning"
    assert state.attributes["position"] == "top_left"
    assert state.attributes["mode"] == "MUSIC"
    assert set(state.attributes["event_types"]) == {
        "top_left",
        "top_right",
        "bottom_left",
        "bottom_right",
    }


async def test_scene_event_unknown_position_dropped(
    hass: HomeAssistant, fake_server: FakeLydbroServer
) -> None:
    await _setup(hass, fake_server)

    initial = hass.states.get(SCENE_ENTITY_ID)
    initial_state = initial.state if initial else None

    await fake_server.push_event("scene_button", name="Elsewhere", position="middle", mode="MUSIC")
    await asyncio.sleep(0.05)

    state = hass.states.get(SCENE_ENTITY_ID)
    assert state is not None
    assert state.state == initial_state
