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
- [x] **runtime-data** — switched from `hass.data[DOMAIN][entry_id]` to typed `entry.runtime_data: LydbroCoordinator`; services now resolve coordinators via `config_entries.async_entries(DOMAIN)`.
- [x] **action-exceptions** — `coordinator.async_send_cmd` now translates `LydbroProtocolError` into `HomeAssistantError` with the `cmd_failed` translation key; services and entity actions both benefit
- [x] **config-flow-test-coverage** — `tests/test_config_flow.py` covers user, zeroconf, discovery_confirm, and reconfigure steps against `FakeLydbroServer`
- [x] **docs-removal-instructions** — README has a "Removing the integration" section under Installation

## Silver — reliability and production-ready

- [x] **log-when-unavailable** — coordinator logs disconnect + reconnect attempts
- [x] **config-entry-unloading** — `async_unload_entry` closes the TCP client and unregisters services
- [x] **entity-unavailable** — entities read `coordinator.available` which flips false on disconnect
- [x] **integration-owner** — `CODEOWNERS` + `codeowners` key in manifest
- [x] **reauthentication-flow** — N/A, no authentication
- [x] **docs-configuration-parameters** — N/A, no YAML config
- [x] **docs-installation-parameters** — README
- [x] **parallel-updates** — `PARALLEL_UPDATES = 0` set in every platform file (push-based, no serialisation needed)
- [x] **test-coverage-above-95%** — 49 tests, 95% branch coverage over `custom_components/lydbro`; enforced in CI via `--cov-fail-under=95`

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
- [x] **diagnostics** — `diagnostics.py` exports entry/connection/hello/state via the HA diagnostics download flow; nothing sensitive so no redaction
- [x] **reconfiguration-flow** — `async_step_reconfigure` lets the user update host/port in place; refuses to point an entry at a different physical device (id mismatch)
- [x] **repair-issues** — `repairs.py` raises HA repair issues for `safe_mode=true` (severity error, learn_more link to the bridge web UI), low battery ≤10% with 15% clear hysteresis, and BLE link down >5 min. Auto-clear when the condition recovers. `tests/test_repairs.py` covers each, including hysteresis and grace-period cancellation. Firmware-version "older than known-good" warning deliberately not implemented — no "known-good minimum" exists yet; add once there's a real floor to enforce.
- [x] **exception-translations** — `cmd_failed` and `device_not_found` errors use `translation_domain` + `translation_key` + `translation_placeholders`; English strings in `strings.json` and `translations/en.json`
- [x] **icon-translations** — `custom_components/lydbro/icons.json` overrides entity and service icons without hard-coding `_attr_icon` strings; covers all five entity platforms plus every service
- [x] **stale-devices** — N/A. One config entry = one physical bridge = one device. There is no "pool of devices" to mark stale; if the bridge is gone, the user removes the entry. Scale decision: document and move on.
- [x] **dynamic-devices** — N/A. Same reasoning — devices aren't created or destroyed at runtime; they're created by the config flow.
- [x] **docs-data-update** — README "How data arrives" subsection explains the push model: persistent TCP, no polling, no scan_interval, auto-reconnect with unavailable during gaps.
- [x] **docs-known-limitations** — README "Known limitations" section covers 8-frame out-queue drop, 30-s idle timeout, zeroconf LAN-scoped, single-remote BLE, English-only translations.
- [x] **docs-supported-devices** — README "Supported devices" section lists Lydbro One ≥ 0.11.9.3 and explicitly flags that legacy Pi/BlueZ builds are not supported (migration guide linked).
- [x] **docs-use-cases** — README "Common use cases" subsection walks through BeoRemote → Sonos, BeoRemote → Samsung Frame, corner-scene lighting, and ambient diagnostics.

## Platinum — the gold standard, plus typing and async purity

- [x] **async-dependency** — the only dependency is stdlib asyncio; no blocking deps
- [x] **inject-websession** — N/A, we use raw TCP
- [x] **strict-typing** — `[tool.mypy] strict = true` in `pyproject.toml` over `custom_components/lydbro`; clean on every file. Enforced in CI via a `mypy` step alongside the pytest job.

---

## Tests — Silver foundation (done)

Bronze/Silver both hinged on a real test suite. As of commit `248908e`:

- [x] **Bootstrap** `pyproject.toml` + `requirements-dev.txt` + `tests/` with `pytest-homeassistant-custom-component` (needs Python 3.13 venv)
- [x] **`tests/conftest.py`** — autouses the custom integration, yields a fresh fake bridge per test (gated on `socket_enabled`)
- [x] **`tests/fake_server.py`** — `FakeLydbroServer` speaks Native TCP v1 on a loopback port so every test runs against the real `LydbroClient` — no transport mocking
- [x] **`tests/test_client.py`** — 11 tests: hello/ack/state handshake, event fan-out, state delta, ping/pong, cmd round-trip (ok + server error + timeout), id monotonicity, drop → on_connection(False), malformed-frame recovery, send-while-disconnected rejection
- [x] **`tests/test_config_flow.py`** — 9 tests: user / zeroconf / discovery_confirm / reconfigure with happy, cannot_connect, already_configured, wrong_device branches
- [x] **`tests/test_init.py`** — 3 tests: setup/unload lifecycle, `entry.runtime_data` plumbing, setup survives unreachable bridge (entities come up unavailable)
- [x] **`tests/test_coordinator.py`** — 9 tests: snapshot + delta merge, numeric coercion, `boot_phase` updates, HA bus-event fan-out for button/menu/scene (load-bearing for device triggers), available-flag on drop
- [x] **`tests/test_services.py`** — 12 tests: every registered service maps to the correct cmd + args, device_not_found and cmd_failed translation keys both wired
- [x] **`tests/test_device_trigger.py`** — 4 tests: async_get_triggers lists button/scene/menu types, attach + fire runs an automation end-to-end for button/scene/menu
- [x] **`tests/test_diagnostics.py`** — 1 test: download payload has the 4 top-level keys populated from a live coordinator
- [x] **Coverage target 95%+** — actual 95% across `custom_components/lydbro`
- [x] **CI job** — `.github/workflows/validate.yml` runs `pytest --cov --cov-fail-under=95` on every push/PR

**Notable real bug caught by tests:** `LydbroEntity._handle_update`
called `async_write_ha_state` off the event-loop thread because it
wasn't decorated `@callback`; HA 2024.x+ raises `RuntimeError` in that
case. Fix is one decorator, caught by `test_services` the first time
an entity tried to refresh.

**Remaining tests that would push coverage past 95% but aren't
gating:** `test_remote.py` (async_send_command forwarding, async_turn_off),
`test_event.py` (per-frame-type event entity filtering, unknown-name drops).

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
- [x] **Battery low repair issue** — shipped in `repairs.py`, raises at ≤10% with 15% clear hysteresis (implemented alongside the Gold `repair-issues` item)
- [ ] **Discovery of multiple Lydbro devices on one LAN** — mostly works now via the unique_id, but test with two bridges

---

## Quality-of-life items outside the scale

- [x] **`pyproject.toml`** with pytest + ruff configs (mypy config still pending under Platinum strict-typing)
- [x] **Pre-commit hooks** — `.pre-commit-config.yaml` runs ruff lint + ruff-format, mypy (via the project venv, not an isolated one, so the HA version matches CI), and file-hygiene hooks (trailing whitespace, EOF, check-yaml/json, merge conflicts, large files, line endings). Install with `pre-commit install` after `pip install -r requirements-dev.txt`.
- [ ] **Screenshot in README** of the integration card + device page
- [ ] **Translations beyond English** — Swedish, Danish (the Lydbro home turf)
- [ ] **README badges** for quality scale tier once we hit one
