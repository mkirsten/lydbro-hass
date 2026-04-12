# Changelog

All notable changes to this integration are documented here.

## [0.1.0] — Unreleased

Initial release.

- Native TCP v1 client with auto-reconnect
- Zeroconf discovery (`_lydbro._tcp`)
- Config flow (discovered + manual)
- Event entities: button, menu, scene
- Sensors: battery, boot_phase, firmware, IP
- Binary sensors: BLE link, ethernet, safe_mode
- Button entities: reboot, rescan, BLE disconnect
- Services: send_remote_key, tv_send_key / tv_launch_app,
  sonos_play_uri / sonos_play_spotify / sonos_play_favorite /
  sonos_set_volume / sonos_adjust_volume / sonos_join, rescan_discovery
