# Lydbro for Home Assistant

Native integration for [Lydbro](https://lydbro.com) devices — control and
automate your BeoRemote One via a Lydbro One bridge.

## Features

- **Zero-config discovery** via mDNS (`_lydbro._tcp`)
- **Local push** — persistent TCP connection, button presses arrive in HA
  with <50ms latency
- **Event entities** for every BeoRemote One button, mode, and scene
- **Sensors** for battery, BLE link state, and boot phase
- **Services** to inject virtual remote key presses and drive the bridge's
  configured TV directly (send key, launch app)
- **No cloud, no polling, no YAML required**

See the [README](https://github.com/mkirsten/lydbro-hass) for full setup
and automation examples.
