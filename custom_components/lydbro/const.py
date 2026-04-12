"""Constants for the Lydbro integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "lydbro"
MANUFACTURER: Final = "Lydbro"
MODEL_DEFAULT: Final = "Lydbro One"

DEFAULT_PORT: Final = 6204
PROTOCOL_VERSION: Final = 1

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

# BeoRemote One button names — matches hid_client.h EVENT_NAMES table.
# The firmware may also send numeric "1".."9" (digit presets) and any
# user-defined scene label — the event entity handles unknown names
# gracefully, these are just the ones we declare up-front.
KNOWN_BUTTONS: Final = (
    "Mute",
    "Power",
    "Play",
    "Play/Pause",
    "Fast Forward",
    "Rewind",
    "Next",
    "Previous",
    "Stop",
    "Home",
    "Back",
    "Menu",
    "Up",
    "Down",
    "Left",
    "Right",
    "Select",
    "Red",
    "Green",
    "Yellow",
    "Blue",
    "Volume Up",
    "Volume Down",
    "Pause",
    "Info",
    "Channel Up",
    "Channel Down",
    "TV",
    "Radio",
    "Record",
    "Recall",
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
