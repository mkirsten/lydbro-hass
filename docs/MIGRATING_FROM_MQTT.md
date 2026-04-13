# Migrating from the MQTT transport

If you used your Lydbro One with `ha_type=1` (MQTT) and a Home Assistant
automation subscribed to `lydbro-one/out`, here's how to move to the
native integration.

## Why bother?

- **No broker dependency.** The native TCP transport is direct
  device→HA over a single persistent TCP connection. Works even if
  Mosquitto is down.
- **Lower latency.** Events arrive in HA with no MQTT queueing.
- **First-class entities.** Battery, boot phase, BLE link state and
  firmware version all show up as HA entities — no template sensors to
  hand-maintain.
- **Device triggers.** The automation editor shows a per-button
  dropdown (*"BeoRemote → Play button held"*) instead of requiring you
  to hand-filter MQTT payloads.
- **Services.** `remote.send_command` and `lydbro.send_remote_key`
  are typed and discoverable in Developer Tools. (The bridge drives
  Sonos and TVs itself in response to remote presses — HA controls
  them through its own Sonos / TV integrations, not through
  Lydbro.)

## Field mapping

The MQTT payload on `lydbro-one/out` → the native HA bus events:

| MQTT field | Native event                 | Notes |
|---|---|---|
| `name`     | `name` (attribute)           | Remote label |
| `event`    | `name` (event_data field)    | Button name |
| `mode`     | `mode`                       | MUSIC / TV / ... |
| `type`     | `kind`                       | click / hold / double / release |
| `source`   | `source`                     | Menu category (for menu events) |
| `id`       | `id` (menu) / `position` (scene) | Menu id is int; scene position is string |

## Bus events

The integration fires three Home Assistant bus events — listen to
these from your automation triggers:

- **`lydbro_button`** — fired on every physical BeoRemote button
  press. `event_data`: `device_id`, `name`, `kind`, `mode`, `ts`.
- **`lydbro_menu`** — fired on vendor-menu selections. `event_data`:
  `device_id`, `name`, `source`, `id`, `mode`, `ts`.
- **`lydbro_scene`** — fired on the four physical corner scene
  buttons. `event_data`: `device_id`, `name`, `position`, `mode`, `ts`.
  `position` is one of `top_left`, `top_right`, `bottom_left`,
  `bottom_right`.

Every fired event carries `device_id` so you can filter on the bridge
if you run more than one.

## Template conversion

Old MQTT automation pattern:

```yaml
triggers:
  - platform: mqtt
    topic: lydbro-one/out
actions:
  - variables:
      p: '{{ trigger.payload_json }}'
      event: '{{ p.event }}'
      type: '{{ p.type | default("click") }}'
```

Equivalent native pattern:

```yaml
triggers:
  - platform: event
    event_type: lydbro_button
    event_data:
      device_id: <YOUR_LYDBRO_DEVICE_ID>
    id: button
actions:
  - variables:
      p: "{{ trigger.event.data }}"
      name: "{{ p.name }}"     # used to be `event`
      kind: "{{ p.kind | default('click') }}"  # used to be `type`
```

## Full example

See [`examples/automation-beoremote-control.yaml`](../examples/automation-beoremote-control.yaml)
for a complete port of a production MQTT automation that handled TV
menu dispatch, key mapping and scene corner buttons.

## Keeping both transports

The firmware only runs one HA transport at a time — when you select
`ha_type=3` (Native TCP), the MQTT adapter stops publishing. If you
need a smooth cut-over, build and test the new automation alongside
the old one (different `id`), flip `ha_type`, then delete the old
automation once you've verified every branch.
