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

### How data arrives

This is a **push integration**. Events arrive over a persistent TCP
connection that the integration holds open to the bridge — there is
no polling, no `scan_interval` to tune, and no "update every N
seconds" knob anywhere. When you press a button, the bridge pushes a
frame, the coordinator forwards it to the right entity, and your
automation runs. Round-trip is bounded by your LAN latency.

If the TCP link drops (device reboot, Ethernet flap, power cycle) the
client reconnects automatically with exponential backoff. Entities
drop to `unavailable` until the first state snapshot arrives on the
new connection.

### Common use cases

What people actually build with this:

- **BeoRemote One → Sonos**. Play / Pause / Next / Previous / Vol
  Up / Vol Down mapped to the currently-selected Sonos zone. The
  bundled [`blueprints/beoremote_media_player.yaml`](blueprints/beoremote_media_player.yaml)
  wires this up in one click.
- **BeoRemote One → Samsung Frame TV**. Mode-aware dispatch: in
  `TV` mode the remote directly controls the Frame via
  `lydbro.tv_send_key`; in `MUSIC` mode the same buttons drive
  Sonos instead.
- **Corner scene buttons → light scenes**. The four corner
  "scene" buttons on the BeoRemote trigger four different Home
  Assistant scenes, good for "movie mode" / "reading" / "party" /
  "off".
- **Ambient automation triggers**. Low battery, BLE disconnect,
  safe mode — all surface as device diagnostics + repair
  notifications, so you get a heads-up without watching logs.

See [`examples/automation-beoremote-control.yaml`](examples/automation-beoremote-control.yaml)
for a worked end-to-end example that's driving a real setup in the
wild.

---

## Supported devices

| Device | Firmware | Status |
|---|---|---|
| **Lydbro One** | ≥ `0.11.9.3` | Fully supported (active development target) |

The Lydbro One is the ESP32-based bridge with PoE Ethernet + BLE
that pairs with a Bang & Olufsen BeoRemote One. Earlier Raspberry Pi
/ BlueZ builds (pre-ESP32) are not supported by this integration —
they predate the Native TCP transport. If you're on one of those,
the legacy MQTT path still works and there's a migration guide
linked below.

Only the **Native TCP v1** transport is wired up. If the bridge's
config UI has *HA integration* set to MQTT or Webhook, flip it to
Native TCP before adding the integration. Native TCP must be enabled
on the device for the integration to connect at all.

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

### Removing the integration

1. **Settings → Devices & Services → Lydbro**, click the three-dot
   menu on your bridge entry and choose **Delete**. This removes the
   config entry, tears down the TCP connection, and unregisters all
   entities, services, and device triggers for that bridge.
2. If you installed via HACS and want to remove the integration
   entirely, go to **HACS → Integrations → Lydbro → ⋮ → Remove** and
   restart Home Assistant.
3. Any automations that referenced the deleted entities or device
   triggers will show up in **Settings → Automations** as
   *Unavailable* — update or delete them.

The integration doesn't write anything outside HA's own config
directory, so removing the entry leaves no stray state behind.

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

## Known limitations

- **Events drop under extreme burst load.** The bridge's Native TCP
  server keeps an 8-frame outbound queue per client. If the client
  can't drain it fast enough (e.g. HA is pegged), the oldest frames
  are dropped rather than growing the queue unbounded. In normal
  use this is never hit — button presses are orders of magnitude
  slower than the drain rate — but if you are generating synthetic
  floods for testing, expect losses beyond 8 in-flight frames.
- **Idle timeout is 30 seconds.** The server drops clients that go
  silent for more than 30 s in both directions. The client pings
  every 8 s to stay ahead of it, so in practice this only shows up
  if the network itself stalls for that long — in which case the
  auto-reconnect loop picks it back up on the next attempt.
- **Zeroconf discovery is LAN-scoped.** The bridge advertises
  `_lydbro._tcp.local.`, which only propagates within a broadcast
  domain. If Home Assistant and the bridge live on different VLANs
  / subnets, auto-discovery won't find the bridge — add it
  manually by IP via **+ Add Integration → Lydbro** and the flow
  will probe it the same way.
- **BLE is single-remote.** The Lydbro One pairs with exactly one
  BeoRemote One at a time. Running two remotes into one bridge
  isn't a software limitation this integration can fix — it's a
  bridge-side constraint.
- **No translation beyond English yet.** The entity, error and
  repair-issue strings ship in English. Swedish / Danish
  translations are on the roadmap (the Lydbro home turf).

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
