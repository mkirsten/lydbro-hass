# Lydbro Native TCP Protocol — v2

Canonical wire-format spec for the bidirectional channel between the
Lydbro One bridge and any client (the Home Assistant custom
integration is one; others are welcome). Runs on
**TCP port 6204**, advertised via mDNS as `_lydbro._tcp.local.`.

## Design goals

- **Push-based event stream** for BLE button presses, state changes,
  and boot lifecycle — no polling, no SSE, no HTTP upgrade.
- **Bidirectional** over the same socket: commands flow client→server
  while events flow server→client, interleaved.
- **Low latency** — persistent connection, ~5–15 ms round-trip on LAN.
- **No broker dependency** — unlike MQTT, the integration works on
  every HA install type without extra setup.
- **Simple** — newline-delimited JSON, readable on the wire. A
  client can be written from scratch in an afternoon.
- **Survives reconnects** — the client resyncs by reading the
  `state` snapshot the server pushes after every successful
  handshake. Bus events are transient; the snapshot is authoritative.

## Wire format

- **Framing:** newline-delimited UTF-8 JSON. One frame per line.
- **Max inbound frame size:** 4096 bytes. Longer frames are dropped
  with `{"t":"error","code":"frame_too_large","max":4096}`.
- **Encoding:** compact JSON, `"t"` (not `"type"`) at the message
  level to save bandwidth.
- **No handshake gymnastics** — connect, read the first line
  (`hello` from server), reply with `hello_ack`, start exchanging.

Every frame has a `"t"` field naming its type:

| `t`         | Direction | Purpose |
|-------------|-----------|---------|
| `hello`     | S → C (unsolicited, first frame) | Capabilities + device identity + `v` |
| `hello_ack` | C → S     | Client identification + `v` negotiation |
| `state`     | S → C     | Full state snapshot (after `hello_ack`, also on `get_state`) |
| `event`     | S → C     | Push — bus event from the device |
| `cmd`       | C → S     | Command request with optional correlation `id` |
| `result`    | S → C     | Command result paired with `cmd.id` |
| `ping`      | either    | Keep-alive; peer replies with `pong` |
| `pong`      | either    | Keep-alive reply |
| `error`     | S → C     | Asynchronous, unsolicited error (not tied to a `cmd`) |

## Connect flow

```
client → connect tcp://<device-ip>:6204
server → {"t":"hello","v":2,"fw":"0.13.0","branch":"master","id":"a1b2c3d4e5f6","name":"Lab Beoremote One","caps":["events","cmds","state"]}
client → {"t":"hello_ack","v":2,"client":"home-assistant"}
server → {"t":"state", ...initial snapshot...}
server → {"t":"event", ...}   # push as events happen
client → {"t":"cmd","id":1,"cmd":"reboot"}
server → {"t":"result","id":1,"ok":true}
```

- `v` is the protocol major version. **v2 is current.** Server and
  client MUST match exactly; mismatches are rejected at handshake
  time (see Versioning).
- `id` in the hello is the device's MAC address (hex, lowercase, no
  separators). Stable unique id for config-flow deduplication.
- `branch` names the firmware git branch the build came from —
  useful when running lab branches in parallel.
- `caps` is a string array of optional features. v2 always includes
  `["events","cmds","state"]`; future additive caps can be added
  without bumping `v`.

A server can refuse the connection by sending a hello with an
`error` field instead — the canonical case is
`{"t":"hello","error":"too_many_clients"}`. The client MUST NOT
send `hello_ack` in that case; the server will close right after.

## Event frames (server → client)

```jsonc
{"t":"event","type":"button_press","ts":12345678,"name":"Play","kind":"click","mode":"MUSIC"}
{"t":"event","type":"button_release","ts":12345680,"name":"Play","kind":"click","mode":"MUSIC"}
{"t":"event","type":"menu_selection","ts":12345690,"name":"Netflix","source":"tv","id":2,"mode":"TV"}
{"t":"event","type":"scene_button","ts":12345700,"name":"Good Night","position":"top_left","mode":"MUSIC"}
{"t":"event","type":"state_change","ts":12345710,"name":"battery","value":"87"}
{"t":"event","type":"boot_phase","ts":12345720,"phase":"Ready"}
```

- `type` names the bus event. One frame per event, no batching.
- `ts` is the device's `millis()` at publish time (uint32, wraps
  every ~49 days). Treat it as monotonic **within a connection
  only** — do not compare across reconnects.
- Per-type fields:
  - `button_press` / `button_release`: `name`, `kind`
    (`click` | `hold` | `double_click`), `mode`
  - `menu_selection`: `name`, `source`
    (`tv` | `music` | `sub_1` | `sub_2` | `scene` | `join` | `sound` | `nowplaying`),
    `id`, `mode`
  - `scene_button`: `name`, `position`
    (`top_left` | `top_right` | `bottom_left` | `bottom_right`), `mode`
  - `state_change`: `name` (key), `value` (stringified — numeric fields
    arrive as strings in deltas but as ints in the full `state` snapshot)
  - `boot_phase`: `phase` (human-readable string)

Unknown `type` values MUST be ignored — that's how additive
evolution works without bumping `v`.

## State frames (server → client)

```jsonc
{"t":"state","fw":"0.13.0","ip":"192.168.0.195","eth_up":true,"safe_mode":false,"boot_phase":"Ready","ble_connected":true,"battery":87,"source":"sonos_kitchen","remote_name":"Lab Beoremote One"}
```

Sent automatically once after `hello_ack` (initial snapshot), and on
request via `get_state`. Fields mirror the device's `/api/status`
for convenience. Clients build their initial entity state from this
and apply subsequent `state_change` event deltas on top.

## Command frames (client → server)

v2 intentionally exposes a tiny surface. HA drives Sonos and TVs
through its own integrations, so the bridge never needs to proxy
those — the only commands on the wire are the ones that only the
bridge itself can execute.

```jsonc
{"t":"cmd","id":42,"cmd":"reboot"}
{"t":"cmd","id":43,"cmd":"reset_pairing"}
{"t":"cmd","id":44,"cmd":"ble_disconnect"}
{"t":"cmd","id":45,"cmd":"send_remote_key","args":{"key":"Volume Up"}}
{"t":"cmd","id":46,"cmd":"get_state"}
```

- `id` is any non-negative integer chosen by the client. The server
  echoes it in the matching `result`. May be omitted for
  fire-and-forget.
- `cmd` is one of the names in the table below. Unknown commands
  produce `{"t":"result","ok":false,"error":"unknown cmd"}`.
- `args` is an optional object. Unknown arg fields are ignored;
  missing required fields produce `result.ok=false`.

| `cmd` | args | Effect |
|---|---|---|
| `reboot` | — | `ESP.restart()` after `result` is sent. Discovery rescans automatically on the way back up. |
| `reset_pairing` | — | Clear all BLE bonds + NVS pairing state + crash-loop boot counter, then reboot. The next boot comes up unpaired so any BeoRemote can pair fresh. |
| `ble_disconnect` | — | Force the remote to drop and reconnect with a fresh GATT session. **Does not** clear bonds. |
| `send_remote_key` | `key` (required, string) | Publish a synthetic `button_press` on the internal event bus with the given BeoRemote key name. Reuses the full mode-aware remote-dispatch pipeline — the bridge routes it to Sonos/TV/HA exactly as if the physical remote had been pressed. |
| `get_state` | — | Server replies with a fresh `state` frame, then `{"t":"result","id":<id>,"ok":true}`. |

### Deliberately not in v2

- **No `sonos_*` / `tv_*` commands.** HA controls those targets
  directly through `media_player.*` / `webostv` / Samsung TV
  integrations. Routing through the bridge was a detour with no
  upside. The bridge's remote-press → Sonos/TV dispatch path still
  lives on the device, it just isn't reachable from the wire.
- **No `rescan_discovery`.** Discovery runs on every boot, so a
  `reboot` gets you a fresh device list for free.
- **No `config_set` / `config_get`.** Configuration still lives on
  the device's HTTP `/api/config` endpoint served by the local
  web UI — out of scope for the wire protocol.

If you find yourself wanting any of these, use HA's own
integration for the target, or POST to the device's `/api/*`
surface. Don't expand this table.

## Result frames (server → client)

```jsonc
{"t":"result","id":42,"ok":true}
{"t":"result","id":45,"ok":false,"error":"missing key"}
```

- `ok` is always a boolean.
- `error` is a short human-readable string when `ok=false`.
  Optional on success.
- Results arrive **interleaved** with events. A client MUST NOT
  block the read loop waiting for one specific `result` — match on
  `id` instead.
- For `reboot` and `reset_pairing` the server sends the `result`
  **before** calling `ESP.restart()`, so clients see `ok:true` just
  before the connection drops.

## Ping / pong

- Either side MAY send `{"t":"ping"}` at any time; peer replies with
  `{"t":"pong"}`.
- Server pings every **10 seconds** if no inbound frame was seen.
- Server closes the connection after **30 seconds** of inbound
  silence (nothing, not even pongs).
- Clients SHOULD ping at ~8 s and treat 25 s silence from the
  server as a drop → reconnect.

## Error frames

Unsolicited server-side errors use:

```jsonc
{"t":"error","code":"frame_too_large","max":4096}
{"t":"error","code":"unsupported_version","server_v":2}
{"t":"error","code":"event_dropped"}
```

These do NOT close the connection on their own, *except* for
`unsupported_version`, which is a handshake failure — the server
closes immediately after sending it.

## Reconnect semantics

On disconnect the client reconnects with exponential backoff (1 s,
2 s, 4 s, … capped at 30 s). On reconnect:

1. The client receives a fresh `hello`.
2. After `hello_ack`, the server pushes a `state` snapshot.
3. The client replaces any cached state with that snapshot. Events
   delivered after the snapshot apply on top.

There is **no replay** of missed events — bus events are transient,
and the state snapshot is authoritative for "what the world looks
like now." Same model as ESPHome's native API.

## Versioning

- **Additive** changes (new event type, new cmd, new state field,
  new caps entry) do NOT bump `v`. Clients MUST ignore unknown
  type/cmd/field values so additive evolution works without a
  flag day.
- **Breaking** changes (renaming or removing a field, changing
  semantics, changing framing, **removing a command from the
  wire**) bump `v`. Both sides hard-check `v` at `hello` /
  `hello_ack` time and refuse the connection on mismatch —
  a client with the wrong version gets `unsupported_version` and
  the socket closes. There is deliberately no "negotiate down to a
  lower version" path; the failure mode is explicit rather than
  silently garbled.

### Changelog

- **v2** (firmware 0.13.0+, lydbro-hass 0.2.0+) — Hard `v` gate on
  `hello` / `hello_ack`. Wire command surface trimmed to
  `reboot` / `reset_pairing` / `ble_disconnect` /
  `send_remote_key` / `get_state`. All `sonos_*`, `tv_*`, and
  `rescan_discovery` commands removed — HA controls those targets
  directly. New `reset_pairing` command added. `hello` gains a
  `branch` field.
- **v1** (firmware 0.11.4.0 – 0.12.4, lydbro-hass 0.1.x) — Initial
  release. Soft version check; wide command surface including
  TV/Sonos proxy commands.

## Client cap + backpressure

- Server accepts up to **4 simultaneous clients**. Additional
  connects get `{"t":"hello","error":"too_many_clients"}` and are
  closed.
- Each client has a small outbound queue (8 frames). If it fills
  (slow client), the **oldest** frame is dropped and an
  `event_dropped` error frame is injected. A dropped `state_change`
  is harmless because full snapshots via `get_state` are the
  authoritative resync.
- Inbound command rate is not limited. Clients should self-throttle.

## Security

- **No authentication.** Protected by LAN reachability only, same
  as the device's existing HTTP admin UI. Suitable for home
  networks where the device is trusted.
- Plain TCP, no TLS
- A future version may add optional bearer tokens provisioned via
  the device's config UI. Not in v2.

## mDNS advertisement

The device publishes `_lydbro._tcp.local.` with these TXT records:

| key | value |
|---|---|
| `id` | device MAC (lowercase hex, no separators) |
| `model` | `lydbro-one` |
| `version` | firmware version (e.g. `0.13.0`) |
| `name` | configured remote name |

The HA integration uses this for zeroconf discovery → config flow
auto-population. Any client can do the same.
