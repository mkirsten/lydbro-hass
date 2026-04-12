# Lydbro for Home Assistant

[![hacs][hacs-badge]][hacs]
[![HA Validate][validate-badge]][validate]
[![Release][release-badge]][release]

Native Home Assistant integration for [Lydbro](https://lydbro.com) devices —
control and automate your Bang & Olufsen BeoRemote One through a **Lydbro One**
bridge.

Built on top of the Lydbro One's Native TCP v1 protocol. Local, push-based,
no cloud, no polling, no YAML.

---

## What this integration gives you

The moment you press a button on your BeoRemote One, Home Assistant knows
about it. Latency is on the order of the TCP round-trip on your LAN —
typically under 50 ms.

### Entities (per Lydbro One device)

| Platform | Entity | Notes |
|---|---|---|
| `event` | **Button** | Fires on every physical press. `event_type` is the button name (`Play`, `Next`, `Home`…), with `kind` (`click` / `hold` / `release` / `double`) and `mode` (`MUSIC` / `TV` / …) as attributes. |
| `event` | **Menu** | Fires when the user picks an item from the remote's vendor menu. |
| `event` | **Scene** | Fires when one of the four corner scene buttons (N/E/S/W) is pressed. |
| `sensor` | BeoRemote battery | Battery % of the paired BeoRemote One. |
| `sensor` | Boot phase | Diagnostic — what the device is doing during startup. |
| `sensor` | Firmware | Reported firmware version from the bridge. |
| `binary_sensor` | BeoRemote link | `connectivity` — is a BeoRemote currently paired over BLE. |
| `binary_sensor` | Ethernet | Diagnostic. |
| `binary_sensor` | Safe mode | `problem` — fires if the bridge has entered crash-loop safe mode. |
| `button` | Reboot | Reboot the bridge. |
| `button` | Rescan discovery | Trigger an mDNS rescan for Sonos / TVs / HA on the LAN. |
| `button` | Disconnect BeoRemote | Drop the BLE link and re-pair. |

### Services

Use these from automations to drive music, TVs, and other devices through
the bridge (rather than running them via HA's own integrations):

- `lydbro.send_remote_key` — inject a virtual BeoRemote key press
- `lydbro.tv_send_key` / `lydbro.tv_launch_app` — Samsung Tizen or LG webOS
- `lydbro.sonos_play_uri` / `lydbro.sonos_play_spotify` / `lydbro.sonos_play_favorite`
- `lydbro.sonos_set_volume` / `lydbro.sonos_adjust_volume` / `lydbro.sonos_join`
- `lydbro.rescan_discovery`

All services take a `device_id` so you can target a specific bridge when
you run more than one.

---

## Installation

### Via HACS (recommended)

1. In HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/mkirsten/lydbro-hass` as category **Integration**
3. Install **Lydbro**
4. Restart Home Assistant
5. Your Lydbro One should pop up under **Settings → Devices & Services →
   Discovered**. If it doesn't, add it manually via **+ Add Integration →
   Lydbro** and type its IP.

### Manually

1. Copy `custom_components/lydbro/` into your HA `config/custom_components/`
2. Restart Home Assistant
3. Add the integration from **Settings → Devices & Services**

---

## Requirements

- Home Assistant **2024.10** or newer
- A **Lydbro One** bridge running firmware **0.11.9** or newer, with its
  HA transport set to **Native TCP** (the default). MQTT and Webhook
  transports are not used by this integration — they're kept around for
  users who prefer plain MQTT.

---

## Automation examples

### "Play" button on the BeoRemote → resume Sonos

```yaml
automation:
  - alias: BeoRemote Play resumes Sonos
    triggers:
      - trigger: state
        entity_id: event.lydbro_one_button
        attribute: event_type
        to: "Play"
    actions:
      - action: media_player.media_play
        target:
          entity_id: media_player.living_room
```

### Hold the Red button → "good night" script

```yaml
automation:
  - alias: BeoRemote Red hold → good night
    triggers:
      - trigger: event
        event_type: state_changed
        event_data:
          entity_id: event.lydbro_one_button
    conditions:
      - "{{ trigger.event.data.new_state.attributes.event_type == 'Red' }}"
      - "{{ trigger.event.data.new_state.attributes.kind == 'hold' }}"
    actions:
      - action: script.good_night
```

### Scene button → scene activation

```yaml
automation:
  - alias: BeoRemote scene N → movie mode
    triggers:
      - trigger: state
        entity_id: event.lydbro_one_scene
        attribute: event_type
        to: "N"
    actions:
      - action: scene.turn_on
        target:
          entity_id: scene.movie_mode
```

---

## Troubleshooting

- **Integration loads but stays "unavailable"** — verify the bridge has
  the **Native TCP** transport selected (not MQTT) in its config UI at
  `http://<bridge-ip>/`. Native TCP is the default on firmware ≥0.11.x.
- **No buttons triggering** — check the `event.lydbro_one_button` entity
  in **Developer Tools → States**. Press a button on the remote; the
  `last_event_type` attribute should update within a second. If it
  doesn't, the bridge isn't receiving BLE events — debug on the device
  itself.
- **Duplicate devices after reconfiguring** — each bridge is keyed by
  its MAC address, so re-running the config flow on the same device
  just updates the host.

---

## Protocol reference

The integration speaks Lydbro Native TCP v1. The spec lives in the
firmware repo: [`products/lydbro-one-esp32/adapters/adapter_native_tcp.h`][protocol-src].

Short summary: persistent TCP on port 6204, line-delimited JSON, server
pushes `hello` → client replies `hello_ack` → server sends `state`
snapshot and then streams `event` frames. Commands travel as `cmd`
frames with a client id, server replies with matching `result`.

---

## License

MIT — see [LICENSE](LICENSE).

[hacs]: https://github.com/hacs/integration
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[validate]: https://github.com/mkirsten/lydbro-hass/actions/workflows/validate.yml
[validate-badge]: https://github.com/mkirsten/lydbro-hass/actions/workflows/validate.yml/badge.svg
[release]: https://github.com/mkirsten/lydbro-hass/releases
[release-badge]: https://img.shields.io/github/v/release/mkirsten/lydbro-hass?include_prereleases
[protocol-src]: https://github.com/mkirsten/lydbro-code/blob/master/products/lydbro-one-esp32/adapters/adapter_native_tcp.h
