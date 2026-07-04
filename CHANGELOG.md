# Changelog

All notable changes to this integration are documented here.

## [0.2.5] — 2026-07-04

First public release (HACS custom repository).

- Canonical BeoRemote One button-name cleanup across triggers,
  events, and services (`Select` confirmed as the wire name).
- New `tv_send_key` and `tv_launch_app` services; full BeoRemote
  button set exposed.
- Battery sensor hardened: no longer unavailable when the remote
  is disconnected, and null battery values no longer crash the
  sensor.
- Dropped the BLE-out-of-range repair issue (noise — BLE link
  binary sensor covers it).

## [0.2.0] — Unreleased

**Breaking**: wire protocol bumped to v2. Requires Lydbro One
firmware ≥ 0.13.0 — older firmware will be rejected on
`hello_ack` with `unsupported_version`.

- Dropped HA→bridge→Sonos/TV proxy services. The bridge still
  drives Sonos / TVs in response to BeoRemote button presses; HA
  controls them through its own integrations, not through Lydbro.
- Dropped the `rescan_discovery` service and button. Discovery
  runs on every boot, so the existing **Reboot** button covers it.
- Added **Reset BeoRemote pairing** admin button — clears all BLE
  bonds on the bridge and reboots, letting any BeoRemote pair
  fresh.

## [0.1.0] — Unreleased

Initial release.

- Native TCP v1 client with auto-reconnect
- Zeroconf discovery (`_lydbro._tcp`)
- Config flow (discovered + manual)
- Event entities: button, menu, scene
- Sensors: battery, boot_phase, firmware, IP
- Binary sensors: BLE link, ethernet, safe_mode
- Button entities: reboot, rescan, BLE disconnect
- Services: send_remote_key, rescan_discovery
