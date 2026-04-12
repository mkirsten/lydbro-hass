<p align="center">
  <img src="logo.svg" alt="Lydbro" width="96" height="96">
</p>

<h1 align="center">Lydbro for Home Assistant</h1>

<p align="center">
  <a href="https://github.com/hacs/integration"><img alt="HACS" src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg"></a>
  <a href="https://github.com/mkirsten/lydbro-hass/actions/workflows/validate.yml"><img alt="Validate" src="https://github.com/mkirsten/lydbro-hass/actions/workflows/validate.yml/badge.svg"></a>
  <a href="https://github.com/mkirsten/lydbro-hass/releases"><img alt="Release" src="https://img.shields.io/github/v/release/mkirsten/lydbro-hass?include_prereleases"></a>
</p>

Native Home Assistant integration for [Lydbro](https://lydbro.com) devices —
control and automate your Bang & Olufsen BeoRemote One through a **Lydbro One**
bridge.

Local, push-based, no cloud, no polling, no YAML required.

---

## What this integration gives you

The moment you press a button on your BeoRemote One, Home Assistant knows
about it. Latency is on the order of the TCP round-trip on your LAN —
typically under 50 ms. Events arrive over a single persistent TCP
connection; commands flow back through the same socket.

### Entities (per Lydbro One device)

| Platform | Entity | Notes |
|---|---|---|
| `event` | **Button** | Fires on every physical press. `event_type` is the button name (`Play`, `Next`, `Home`…); `kind` (`click` / `hold` / `release` / `double`) and `mode` (`MUSIC` / `TV` / …) come through as attributes. |
| `event` | **Menu** | Fires when the user picks an item from the remote's vendor menu. `name` and `source` identify the menu and item. |
| `event` | **Scene** | Fires when one of the four corner scene buttons is pressed. `event_type` is the physical position: `top_left`, `top_right`, `bottom_left`, `bottom_right`. |
| `sensor` | BeoRemote battery | Battery % of the paired BeoRemote One (device class `battery`). |
| `sensor` | Boot phase | Diagnostic — what the bridge is doing during startup. |
| `sensor` | Firmware | Reported firmware version of the bridge. |
| `binary_sensor` | BeoRemote link | `connectivity` — is a BeoRemote currently paired over BLE. |
| `binary_sensor` | Ethernet | Diagnostic. |
| `binary_sensor` | Safe mode | `problem` — fires if the bridge has entered crash-loop safe mode. |
| `button` | Reboot | Reboot the bridge. |
| `button` | Rescan discovery | Trigger an mDNS rescan for Sonos / TVs / HA on the LAN. |
| `button` | Disconnect BeoRemote | Drop the BLE link and re-pair. |
| `remote` | BeoRemote | Virtual remote — `remote.send_command` fires a BeoRemote key press without needing the physical remote. `is_on` tracks the BLE link. |

### Device triggers

Every button × kind combination and every scene position is registered
as a Home Assistant **device trigger**, so the automation editor shows a
point-and-click dropdown for each bridge:

> Device: *Lab Beoremote One* → Trigger type: *Play button (held)*

No YAML required for the common cases. Under the hood each device
trigger wraps a `lydbro_button` / `lydbro_scene` / `lydbro_menu` bus
event with the right filters.

### Services

For the things that benefit from structured arguments, the integration
also registers a set of services. All of them take a `device_id` so you
can target a specific bridge when you run more than one:

- `lydbro.send_remote_key` — inject a virtual BeoRemote key press
- `lydbro.tv_send_key` / `lydbro.tv_launch_app` — Samsung Tizen or LG webOS
- `lydbro.sonos_play_uri` / `lydbro.sonos_play_spotify` / `lydbro.sonos_play_favorite`
- `lydbro.sonos_set_volume` / `lydbro.sonos_adjust_volume` / `lydbro.sonos_join`
- `lydbro.rescan_discovery`

---

## Installation

### Via HACS (recommended)

1. In HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/mkirsten/lydbro-hass` as category **Integration**
3. Install **Lydbro**
4. Restart Home Assistant
5. Your Lydbro One should pop up under **Settings → Devices & Services →
   Discovered**. If it doesn't, add it manually via **+ Add Integration →
   Lydbro** and enter its IP.

### Manually

1. Copy `custom_components/lydbro/` into your HA `config/custom_components/`
2. Restart Home Assistant
3. Add the integration from **Settings → Devices & Services**

---

## Requirements

- Home Assistant **2024.10** or newer
- A **Lydbro One** bridge running a firmware release that supports the
  Native TCP v1 transport (the bridge's config UI at `http://<bridge-ip>/`
  must have *HA integration → Native TCP* selected)

---

## Automation examples

### "Play" button on the BeoRemote → resume Sonos

Simple event-entity trigger. No kind filter, so this fires on clicks,
holds and doubles alike:

```yaml
automation:
  - alias: BeoRemote Play resumes Sonos
    triggers:
      - trigger: state
        entity_id: event.lab_beoremote_one_button
        attribute: event_type
        to: "Play"
    actions:
      - action: media_player.media_play
        target:
          entity_id: media_player.living_room
```

### Hold the Red button → "good night" script

For kind-sensitive triggers, listen to the `lydbro_button` bus event
directly so you can filter on `kind` in `event_data`:

```yaml
automation:
  - alias: BeoRemote Red hold → good night
    triggers:
      - trigger: event
        event_type: lydbro_button
        event_data:
          name: Red
          kind: hold
    actions:
      - action: script.good_night
```

### Scene corner button → scene activation

Four positions: `top_left`, `top_right`, `bottom_left`, `bottom_right`.
You can trigger on the event entity's attribute, or — for a nicer
editor experience — pick the device trigger *Scene: top_left* from the
Automations UI:

```yaml
automation:
  - alias: BeoRemote top-left scene → movie mode
    triggers:
      - trigger: state
        entity_id: event.lab_beoremote_one_scene
        attribute: event_type
        to: "top_left"
    actions:
      - action: scene.turn_on
        target:
          entity_id: scene.movie_mode
```

A full worked example — porting a real MQTT automation to the native
transport, including TV menu dispatch, Samsung key mapping and corner
scenes — lives in [`examples/automation-beoremote-control.yaml`](examples/automation-beoremote-control.yaml).

---

## Troubleshooting

- **Integration loads but stays "unavailable"** — verify the bridge has
  the **Native TCP** transport selected in its config UI at
  `http://<bridge-ip>/`. If it's set to MQTT or Webhook, the native TCP
  server is torn down and this integration can't connect.
- **No buttons triggering** — check the `event.lab_beoremote_one_button`
  entity in **Developer Tools → States**. Press a button on the remote;
  the state (last-fired timestamp) and `event_type` attribute should
  update within a second. If they don't, the bridge isn't receiving BLE
  events — debug on the device itself.
- **Duplicate devices after reconfiguring** — each bridge is keyed by
  its MAC address, so re-running the config flow on the same device
  just updates the host.
- **Enabling debug logs** — add to `configuration.yaml`:
  ```yaml
  logger:
    logs:
      custom_components.lydbro: debug
  ```

---

## Protocol reference

The integration speaks **Lydbro Native TCP v1**: persistent line-delimited
JSON over TCP port 6204.

- Server sends a `hello` frame on connect (`{t, v, fw, branch, id, name, caps}`)
- Client replies with `hello_ack`
- Server pushes an initial `state` snapshot, then streams `event` frames
- Commands travel client → server as `cmd` frames with a client-chosen `id`;
  server replies with a matching `result` frame
- Keepalive: `ping` / `pong` every 10 s while idle, 30 s silent drop

Event types emitted: `button_press`, `button_release`, `menu_selection`,
`scene_button`, `state_change`, `boot_phase`.

Discovery: mDNS `_lydbro._tcp` with TXT records `id`, `model`, `version`,
`name`, `proto_v`.

---

## Migrating from MQTT

If you previously drove Home Assistant automations off the
`lydbro-one/out` MQTT topic, see
[`docs/MIGRATING_FROM_MQTT.md`](docs/MIGRATING_FROM_MQTT.md) for the
field-by-field mapping and a template conversion guide.

---

## License

MIT — see [LICENSE](LICENSE).
