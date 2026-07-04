# lydbro-hass — Project Instructions

Home Assistant custom integration for the Lydbro One bridge. Speaks the **Native TCP v2** protocol on port 6204, push-based — no polling, no MQTT broker. Firmware lives in the separate `~/Development/lydbro-code/` repo under `products/lydbro-one-esp32/`; the **canonical wire-format spec is `docs/native_tcp_protocol.md` in this repo** (moved here so third-party clients can read it without firmware-source access — the firmware repo's copy is a one-line pointer).

## Native TCP protocol + firmware compatibility

This integration is hard-gated on the Native TCP wire version. `PROTOCOL_VERSION` in `custom_components/lydbro/client.py` must match `NTCP_PROTO_VERSION` in the firmware's `adapters/adapter_native_tcp.h`, otherwise the bridge rejects `hello_ack` with `unsupported_version` and the client refuses the connection. The two constants MUST move together across repos.

**Additive changes** (new cmd, new event type, new state field) — do NOT bump `PROTOCOL_VERSION`. Just handle the new field/event in `coordinator.py` or the relevant entity platform. Unknown fields from the server are ignored by design — that's how additive evolution works.

**Breaking changes** (rename or remove a field, change framing) — MUST:
1. Bump `PROTOCOL_VERSION` here AND `NTCP_PROTO_VERSION` in `lydbro-code`.
2. Update `docs/native_tcp_protocol.md` **in this repo** (it's the canonical spec — the other repo copy is a pointer).
3. Add a new row to the compatibility table in BOTH `README.md` (this repo, "Compatibility" subsection under Requirements) AND other repo's `README.md` ("Home Assistant integration compatibility" section).
4. Bump `manifest.json` version here (and tag a HACS release) alongside the firmware release.

**Every HA integration release** that touches `client.py`, `coordinator.py`, or frame-shape assumptions should also update the HA row in both compat tables — even if `v` didn't bump — so the "known-tested-together" pair advances with reality. Otherwise the tables rot.

## Deploying to HA

Before every deploy, bump the patch version in `custom_components/lydbro/manifest.json` by 0.0.1 (e.g. `0.2.1` → `0.2.2`). Then run the deploy script:

```bash
cd ~/Development/lydbro-hass
HA_SSH=<HA USER>@<HA IP> HA_TOKEN=<HA TOKEN> ./deploy.sh
```

## After editing `client.py` or `coordinator.py`

Run the test suite before committing — the tests under `tests/` mock the firmware's wire protocol, so they catch frame-shape drift that HA itself wouldn't:

```bash
cd lydbro-hass
source .venv/bin/activate && python -m pytest tests/ -x --cov=custom_components/lydbro --cov-report=term-missing --cov-fail-under=100
```

End-to-end verification against a real bridge happens on the firmware side test_device.sh script in other repo_ — that script's headless-browser step only validates the bridge's own web UI, not this integration, so a manual HA reload + "entities appear, button press fires trigger" check is the real smoke test for changes here.
