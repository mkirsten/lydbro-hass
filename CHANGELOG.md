# Changelog

All notable changes to this integration are documented here.

## [1.0.1] - 2026-09-12

- The logo at the top of the README now shows in the HACS repository
  page. No functional changes.

## [1.0.0] - 2026-09-12

First stable release. The integration has been running against the
1.0 firmware since its first customer unit shipped, and the version
now says so.

- Fix: the "Beoremote link" binary sensor (and the battery sensor's
  availability, which follows it) stayed on after the remote
  disconnected. Pushed state changes carry booleans as the strings
  "true" / "false", and the string "false" was being read as true.
  Only a full snapshot after an HA reconnect ever corrected it.
  Boolean state keys are now coerced the same way numeric ones are.
- Spelling: "Beoremote" everywhere (Bang & Olufsen's own styling,
  lowercase r). Display names of the link, battery, pairing and
  disconnect entities change accordingly; entity IDs are unaffected.

## [0.2.6] - 2026-07-04

Discoverability release for the HACS default-store submission.

- HACS display name now includes "Bang & Olufsen Beoremote One" so
  in-store search finds it by B&O terms.
- HACS validation runs the brands check for real (icons ship in the
  integration's own `brand/` directory, HA ≥ 2026.3.0 style).
- README/HACS info page copy fixes; no code changes.

## [0.2.5] - 2026-07-04

First public release (HACS custom repository).

- Canonical Beoremote One button-name cleanup across triggers,
  events, and services (`Select` confirmed as the wire name).
- New `tv_send_key` and `tv_launch_app` services; full Beoremote
  button set exposed.
- Battery sensor hardened: no longer unavailable when the remote
  is disconnected, and null battery values no longer crash the
  sensor.
- Dropped the BLE-out-of-range repair issue (noise - BLE link
  binary sensor covers it).

## [0.2.0] - Unreleased

**Breaking**: wire protocol bumped to v2. Requires Lydbro One
firmware ≥ 0.13.0 - older firmware will be rejected on
`hello_ack` with `unsupported_version`.

- Dropped HA→bridge→Sonos/TV proxy services. The bridge still
  drives Sonos / TVs in response to Beoremote button presses; HA
  controls them through its own integrations, not through Lydbro.
- Dropped the `rescan_discovery` service and button. Discovery
  runs on every boot, so the existing **Reboot** button covers it.
- Added **Reset Beoremote pairing** admin button - clears all BLE
  bonds on the bridge and reboots, letting any Beoremote pair
  fresh.

## [0.1.0] - Unreleased

Initial release.

- Native TCP v1 client with auto-reconnect
- Zeroconf discovery (`_lydbro._tcp`)
- Config flow (discovered + manual)
- Event entities: button, menu, scene
- Sensors: battery, boot_phase, firmware, IP
- Binary sensors: BLE link, ethernet, safe_mode
- Button entities: reboot, rescan, BLE disconnect
- Services: send_remote_key, rescan_discovery
