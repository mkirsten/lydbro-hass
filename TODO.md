# Roadmap to Home Assistant Gold Standard

The HA Integration Quality Scale has four tiers — **Bronze → Silver →
Gold → Platinum** — each building on the previous. This file tracks
where Lydbro stands and what's left. Checked items are done; unchecked
items are what needs work to hit the next tier.

Reference: <https://developers.home-assistant.io/docs/core/integration-quality-scale>

---

## Bronze — the minimum for a published integration

- [x] **config-flow** — UI setup, no YAML
- [x] **test-before-configure** — probe the device in the config flow, fail fast on unreachable
- [x] **unique-config-entry** — keyed by device MAC from the `hello` frame, prevents duplicates
- [x] **entity-unique-id** — every entity sets `_attr_unique_id = f"{device_id}_{key}"`
- [x] **has-entity-name** — base class sets `_attr_has_entity_name = True`
- [x] **entity-event-setup** — dispatcher subscriptions registered in `async_added_to_hass` and torn down via `async_on_remove`
- [x] **appropriate-polling** — N/A, this is a push integration
- [x] **action-setup** — services registered once per HA process
- [x] **brands** — `custom_components/lydbro/brand/` ships icon + logo, served locally by HA 2026.3+
- [x] **dependency-transparency** — empty `requirements` in manifest, no hidden deps
- [x] **docs-actions** — `services.yaml` documents every service
- [x] **docs-high-level-description** — README top
- [x] **docs-installation-instructions** — README Installation section
- [x] **runtime-data** — switch from `hass.data[DOMAIN][entry_id]` to typed `entry.runtime_data: LydbroCoordinator` (HA 2024.4+ pattern). One-line change per file but touches most platforms.
- [ ] **action-exceptions** — services should raise `HomeAssistantError` / `ServiceValidationError` with translation keys when the command fails, not bubble the raw `LydbroProtocolError`
- [ ] **config-flow-test-coverage** — need a test suite. This is the single biggest item; see *Tests* section below
- [ ] **docs-removal-instructions** — add a "Removing the integration" section to README

## Silver — reliability and production-ready

- [x] **log-when-unavailable** — coordinator logs disconnect + reconnect attempts
- [x] **config-entry-unloading** — `async_unload_entry` closes the TCP client and unregisters services
- [x] **entity-unavailable** — entities read `coordinator.available` which flips false on disconnect
- [x] **integration-owner** — `CODEOWNERS` + `codeowners` key in manifest
- [x] **reauthentication-flow** — N/A, no authentication
- [x] **docs-configuration-parameters** — N/A, no YAML config
- [x] **docs-installation-parameters** — README
- [ ] **parallel-updates** — set `PARALLEL_UPDATES = 0` in each platform file since we're push-based; default (1) serialises updates unnecessarily
- [ ] **test-coverage-above-95%** — blocked on the test suite bootstrap

## Gold — polished UX and full HA citizen

- [x] **devices** — every entity populates `DeviceInfo` with manufacturer, model, sw_version, configuration_url
- [x] **discovery** — zeroconf `_lydbro._tcp`, manual fallback
- [x] **docs-examples** — `examples/automation-beoremote-control.yaml` ports a real-world automation; `blueprints/beoremote_media_player.yaml` as a one-click template
- [x] **docs-supported-functions** — README entity and service tables
- [x] **docs-troubleshooting** — README Troubleshooting section
- [x] **entity-category** — diagnostic entities tagged (`EntityCategory.DIAGNOSTIC`), admin buttons tagged (`EntityCategory.CONFIG`)
- [x] **entity-device-class** — battery, connectivity, problem, button
- [x] **entity-disabled-by-default** — `ip_address` sensor disabled by default as an example; more candidates in the binary sensors
- [x] **entity-translations** — `strings.json` + `translations/en.json`
- [ ] **diagnostics** — add `diagnostics.py` so users can one-click download a redacted state dump for bug reports. Should include: hello dict, state dict, ntcp counters, last ~50 log lines. Redact nothing sensitive (there's nothing sensitive in this device).
- [ ] **reconfiguration-flow** — add an options flow that lets the user change host/port without removing and re-adding the entry. Useful when DHCP moves the device. Gold requires this in addition to the initial config_flow.
- [ ] **repair-issues** — raise `homeassistant.helpers.issue_registry.async_create_issue` when:
  - device reports `safe_mode=true` → severity `error`, action: link to the config UI
  - firmware version is older than a known-good minimum → severity `warning`
  - BLE link has been down for more than N minutes → severity `warning`
- [ ] **exception-translations** — translate `HomeAssistantError` messages via `translation_key` + `translation_placeholders` so non-English users see localised errors in notifications
- [ ] **icon-translations** — ship `icons.json` to override entity icons without hard-coding `_attr_icon` strings (e.g. mdi:remote for the remote entity, mdi:remote-tv for the Button event)
- [ ] **stale-devices** — N/A (single device per entry), document the N/A decision
- [ ] **dynamic-devices** — N/A (single device per entry)
- [ ] **docs-data-update** — short docs section explaining the push model: "events arrive over a persistent TCP connection; there is no polling, and no `scan_interval` to tune"
- [ ] **docs-known-limitations** — a README section listing: events dropped if the TCP out-queue overflows (8 frames), 30-second server-side idle timeout, zeroconf only within a /24
- [ ] **docs-supported-devices** — README section listing "Lydbro One" + firmware range
- [ ] **docs-use-cases** — short README section "What people build with this": BeoRemote → Sonos, BeoRemote → Samsung Frame, scene-corner → light scenes

## Platinum — the gold standard, plus typing and async purity

- [x] **async-dependency** — the only dependency is stdlib asyncio; no blocking deps
- [x] **inject-websession** — N/A, we use raw TCP
- [ ] **strict-typing** — add a `mypy.ini` or pyproject mypy config with `strict = True`, annotate every function that currently elides return types or uses `Any` loosely. The client/coordinator are mostly typed; sensors/events/triggers need passes.

---

## Tests — the missing load-bearing foundation

The tier system keeps tripping on test coverage. To unblock Silver:

- [ ] **Bootstrap `tests/`** with `pytest-homeassistant-custom-component` as the fixture provider
- [ ] **conftest.py**: autouse fixture that enables the lydbro integration, plus a fixture that returns a fake `LydbroClient` the coordinator can use
- [ ] **Fake server** for integration tests: a simple asyncio TCP server that speaks the v1 protocol so the real client code is exercised end-to-end without mocks
- [ ] **test_config_flow.py**: cover manual entry (happy path + cannot_connect), zeroconf path, already_configured abort, reconfigure flow (once added)
- [ ] **test_init.py**: setup_entry, unload_entry, coordinator lifecycle, reconnect backoff
- [ ] **test_client.py**: hello/hello_ack/state/event/ping/pong/cmd/result round-trips, frame parsing, bad JSON handling, timeout behavior
- [ ] **test_coordinator.py**: state merging, numeric coercion, dispatcher fan-out, bus event firing
- [ ] **test_event.py**: each event entity class handles its frame types and ignores the others
- [ ] **test_device_trigger.py**: trigger attach translates correctly to event-platform triggers
- [ ] **test_services.py**: every service resolves `device_id`, calls the right cmd, rejects unknown device
- [ ] **test_remote.py**: send_command forwards to `send_remote_key`; turn_off → `ble_disconnect`
- [ ] **Coverage target**: 95%+ on everything except the BLE/HID specific paths (those aren't in this repo)
- [ ] **CI job** in `validate.yml` that runs `pytest --cov` and fails the build if coverage drops below the threshold

---

## Publishing (when the repo goes public)

- [ ] **Flip repo visibility to public**: `gh repo edit mkirsten/lydbro-hass --visibility public`
- [ ] **Re-enable HACS validation** in `.github/workflows/validate.yml` (currently commented out)
- [ ] **Tag `v0.1.0`** — triggers `release.yml` which syncs `manifest.version` and uploads `lydbro.zip` to the release
- [ ] **Add to HACS default**: PR to `hacs/default` under `integration` with the repo URL
- [ ] **Submit to home-assistant/brands**: optional, our local `brand/` already covers HA UI — but upstreaming means HACS dashboard shows the icon too
- [ ] **Submit the integration to HA core**: very optional, requires extensive tests and docs on developers.home-assistant.io. Not on the critical path — a high-quality custom integration is fine.

---

## Beyond Gold — product-level things worth considering

- [ ] **Firmware update entity** — `update.lydbro_one_firmware` backed by the bridge's `/api/status` + `/ota` endpoints so users flash firmware from HA's Updates panel
- [ ] **Per-button `button` entities** — in addition to the `event` entity, expose each common button as an HA `button` that calls `remote.send_command` internally. Useful for Lovelace dashboards without scripting.
- [ ] **Sensor for last button press** with timestamp — for dashboards
- [ ] **Current mode sensor** (MUSIC / TV / RADIO) — for dashboard conditionals
- [ ] **Sonos media_player wrapping** — a media_player entity per discovered Sonos speaker, letting automations call `media_player.play_media` directly instead of the `lydbro.sonos_*` services
- [ ] **Battery low repair issue** at <10% — complements the diagnostic sensor
- [ ] **Discovery of multiple Lydbro devices on one LAN** — mostly works now via the unique_id, but test with two bridges

---

## Quality-of-life items outside the scale

- [ ] **`pyproject.toml`** with ruff, mypy and pytest configs so `pip install -e ".[dev]"` in a dev shell sets everything up
- [ ] **Pre-commit hooks** — ruff, mypy, black/ruff-format, yaml-lint
- [ ] **Screenshot in README** of the integration card + device page
- [ ] **Translations beyond English** — Swedish, Danish (the Lydbro home turf)
- [ ] **README badges** for quality scale tier once we hit one
