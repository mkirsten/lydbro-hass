"""Constants for the Lydbro integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "lydbro"
MANUFACTURER: Final = "Lydbro"
MODEL_DEFAULT: Final = "Lydbro One"

DEFAULT_PORT: Final = 6204
PROTOCOL_VERSION: Final = 2

CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_DEVICE_ID: Final = "device_id"
CONF_NAME: Final = "name"

# Dispatcher signals — per-entry, formatted with the config entry id
SIGNAL_STATE_UPDATED: Final = "lydbro_state_updated_{}"
SIGNAL_EVENT: Final = "lydbro_event_{}"
SIGNAL_CONNECTION: Final = "lydbro_connection_{}"

# Home Assistant bus events — the load-bearing hook for device triggers.
# Device triggers register an "event" platform trigger filtered on
# event_data.device_id + name + kind; the coordinator fires these.
EVENT_BUS_BUTTON: Final = "lydbro_button"
EVENT_BUS_MENU: Final = "lydbro_menu"
EVENT_BUS_SCENE: Final = "lydbro_scene"

# Keys in the state dict whose values must be numeric. Coordinator
# coerces these on ingest so sensors don't see int/str drift between
# full snapshots (ints) and state_change deltas (strings).
NUMERIC_STATE_KEYS: Final = ("battery",)

# BeoRemote One button names — canonical set matching hid_client.h output.
# Firmware publishes exactly these names; unknown names from the server are
# handled gracefully by the event entity (ignored, not an error).
KNOWN_BUTTONS: Final = (
    # Playback
    "Play",
    "Pause",
    "Next",
    "Fast Forward",
    "Rewind",
    # Volume
    "Volume Up",
    "Volume Down",
    "Mute",
    # Power
    "Power",
    # Navigation
    "Up",
    "Down",
    "Left",
    "Right",
    "Select",
    "Menu",
    "Back",
    "Home",
    # Info / Guide
    "Info",
    "Guide",
    # Source / Mode
    "Music",
    "TV",
    "List",
    # Channel
    "Channel Up",
    "Channel Down",
    # Colors
    "Red",
    "Green",
    "Yellow",
    "Blue",
    # Digits
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
)

# Remote button press kinds published by the firmware
BUTTON_KINDS: Final = ("click", "hold", "release", "double")

# Remote modes published in the "mode" field
REMOTE_MODES: Final = ("MUSIC", "TV", "RADIO", "HOMEMEDIA", "GAMES", "CONTROL")

# All BeoRemote buttons exposed as individual HA `button` entities.
# Disabled by default — enable the ones you want from the HA device
# page and drag them onto a Lovelace card. Mirrors KNOWN_BUTTONS exactly.
COMMON_REMOTE_BUTTONS: Final = KNOWN_BUTTONS
