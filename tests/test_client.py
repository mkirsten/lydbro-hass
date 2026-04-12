"""End-to-end tests for :class:`LydbroClient` against the fake server.

These run the real client code over a real loopback socket — no
mocking of the transport. If any of these break, the bridge-side
protocol or the client's frame handling has regressed.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.lydbro.client import LydbroClient, LydbroProtocolError

from .fake_server import FakeLydbroServer


# ---------------------------------------------------------------------------
# Test-side plumbing
# ---------------------------------------------------------------------------


class _Recorder:
    """Collects hello/state/event frames and connection transitions.

    Tests read from this instead of registering their own callbacks
    each time. Every callback is async to match the real coordinator's
    surface area.
    """

    def __init__(self) -> None:
        self.hellos: list[dict[str, Any]] = []
        self.states: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.connection_changes: list[bool] = []
        self.state_event = asyncio.Event()
        self.event_event = asyncio.Event()

    async def on_hello(self, frame: dict[str, Any]) -> None:
        self.hellos.append(frame)

    async def on_state(self, frame: dict[str, Any]) -> None:
        self.states.append(frame)
        self.state_event.set()

    async def on_event(self, frame: dict[str, Any]) -> None:
        self.events.append(frame)
        self.event_event.set()

    async def on_connection(self, connected: bool) -> None:
        self.connection_changes.append(connected)


async def _connected_client(
    server: FakeLydbroServer,
) -> tuple[LydbroClient, _Recorder]:
    """Start a client pointed at ``server`` and wait for full handshake."""
    recorder = _Recorder()
    client = LydbroClient(
        "127.0.0.1",
        server.port,
        on_hello=recorder.on_hello,
        on_state=recorder.on_state,
        on_event=recorder.on_event,
        on_connection_change=recorder.on_connection,
    )
    await client.start()
    ok = await client.wait_connected(timeout=2.0)
    assert ok, "client did not complete handshake"
    return client, recorder


# ---------------------------------------------------------------------------
# Handshake
# ---------------------------------------------------------------------------


async def test_hello_ack_state_handshake(fake_server: FakeLydbroServer) -> None:
    """Server hello → client ack → server state → client marked connected."""
    client, recorder = await _connected_client(fake_server)
    try:
        assert len(recorder.hellos) == 1
        assert recorder.hellos[0]["id"] == "aa:bb:cc:dd:ee:ff"
        assert recorder.hellos[0]["fw"] == "0.11.9.3"

        assert len(recorder.states) == 1
        assert recorder.states[0]["battery"] == 87
        assert recorder.states[0]["eth_up"] is True

        # The client reports "connected" once the first state arrives.
        assert recorder.connection_changes == [True]
        assert client.connected is True

        # The server recorded that the client sent hello_ack.
        assert fake_server.acked.is_set()
    finally:
        await client.stop()


# ---------------------------------------------------------------------------
# Event fan-out
# ---------------------------------------------------------------------------


async def test_server_pushed_event_reaches_on_event(
    fake_server: FakeLydbroServer,
) -> None:
    client, recorder = await _connected_client(fake_server)
    try:
        await fake_server.push_event(
            "button_press", name="Play", kind="click", mode="MUSIC"
        )
        await asyncio.wait_for(recorder.event_event.wait(), 2.0)

        assert len(recorder.events) == 1
        frame = recorder.events[0]
        assert frame["type"] == "button_press"
        assert frame["name"] == "Play"
        assert frame["kind"] == "click"
        assert frame["mode"] == "MUSIC"
    finally:
        await client.stop()


async def test_state_frame_after_handshake_merges(
    fake_server: FakeLydbroServer,
) -> None:
    """A second state frame from the server lands as another on_state call."""
    client, recorder = await _connected_client(fake_server)
    try:
        recorder.state_event.clear()
        await fake_server.push_state(battery=42)
        await asyncio.wait_for(recorder.state_event.wait(), 2.0)

        assert len(recorder.states) == 2
        assert recorder.states[-1]["battery"] == 42
        # Connection-change callback is only fired on the first
        # connect, not on subsequent state frames.
        assert recorder.connection_changes == [True]
    finally:
        await client.stop()


# ---------------------------------------------------------------------------
# Ping / pong
# ---------------------------------------------------------------------------


async def test_server_ping_gets_client_pong(fake_server: FakeLydbroServer) -> None:
    client, _ = await _connected_client(fake_server)
    try:
        await fake_server.push_ping()
        # Client replies to pings inside its read loop; give it a
        # tick. Assert via the fake server's pong counter.
        for _ in range(20):
            if fake_server.received_pongs >= 1:
                break
            await asyncio.sleep(0.05)
        assert fake_server.received_pongs == 1
    finally:
        await client.stop()


# ---------------------------------------------------------------------------
# Command round-trip
# ---------------------------------------------------------------------------


async def test_cmd_round_trip_success(fake_server: FakeLydbroServer) -> None:
    """send_cmd resolves with the result frame on ok=true."""

    async def handler(frame: dict[str, Any]) -> dict[str, Any]:
        assert frame["cmd"] == "send_remote_key"
        assert frame["key"] == "Play"
        return {"t": "result", "id": frame["id"], "ok": True, "echo": "Play"}

    fake_server.cmd_handler = handler

    client, _ = await _connected_client(fake_server)
    try:
        result = await client.send_cmd("send_remote_key", key="Play")
        assert result["ok"] is True
        assert result["echo"] == "Play"
        assert len(fake_server.received_cmds) == 1
        assert fake_server.received_cmds[0]["id"] == 1
    finally:
        await client.stop()


async def test_cmd_server_error_raises(fake_server: FakeLydbroServer) -> None:
    """A result frame with ok=false becomes a LydbroProtocolError."""

    async def handler(frame: dict[str, Any]) -> dict[str, Any]:
        return {
            "t": "result",
            "id": frame["id"],
            "ok": False,
            "error": "no such device",
        }

    fake_server.cmd_handler = handler

    client, _ = await _connected_client(fake_server)
    try:
        with pytest.raises(LydbroProtocolError, match="no such device"):
            await client.send_cmd("tv_send_key", key="HOME")
    finally:
        await client.stop()


async def test_cmd_timeout_when_server_never_replies(
    fake_server: FakeLydbroServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_cmd raises LydbroProtocolError on CMD_TIMEOUT."""
    # Shrink the timeout so the test runs fast. Monkeypatch the
    # module constant rather than sleeping for the real 5s default.
    from custom_components.lydbro import client as client_mod

    monkeypatch.setattr(client_mod, "CMD_TIMEOUT", 0.3)

    async def handler(frame: dict[str, Any]) -> dict[str, Any]:
        # Never reply.
        await asyncio.sleep(10)
        return {"t": "result", "id": frame["id"], "ok": True}

    fake_server.cmd_handler = handler

    client, _ = await _connected_client(fake_server)
    try:
        with pytest.raises(LydbroProtocolError, match="timed out"):
            await client.send_cmd("rescan_discovery")
    finally:
        await client.stop()


async def test_cmd_ids_increment(fake_server: FakeLydbroServer) -> None:
    """Each send_cmd bumps the client-side id monotonically."""
    client, _ = await _connected_client(fake_server)
    try:
        await client.send_cmd("rescan_discovery")
        await client.send_cmd("rescan_discovery")
        await client.send_cmd("rescan_discovery")
        ids = [f["id"] for f in fake_server.received_cmds]
        assert ids == [1, 2, 3]
    finally:
        await client.stop()


# ---------------------------------------------------------------------------
# Reconnect + disconnect bookkeeping
# ---------------------------------------------------------------------------


async def test_drop_triggers_on_connection_false(
    fake_server: FakeLydbroServer,
) -> None:
    """When the server drops the client, on_connection_change(False) fires."""
    client, recorder = await _connected_client(fake_server)
    try:
        await fake_server.drop_client()

        # The client's read loop should see EOF and flip to disconnected.
        for _ in range(50):
            if recorder.connection_changes[-1] is False:
                break
            await asyncio.sleep(0.05)

        assert recorder.connection_changes[0] is True
        assert recorder.connection_changes[-1] is False
        assert client.connected is False
    finally:
        await client.stop()


async def test_malformed_frame_is_dropped_not_fatal(
    fake_server: FakeLydbroServer,
) -> None:
    """Garbage line between valid frames is ignored and the client survives."""
    client, recorder = await _connected_client(fake_server)
    try:
        # Send a broken JSON line followed by a real event. The client
        # should drop the first and deliver the second without
        # disconnecting.
        await fake_server.push_raw(b"{not json\n")
        await fake_server.push_event("button_press", name="Next", kind="click")
        await asyncio.wait_for(recorder.event_event.wait(), 2.0)

        assert client.connected is True
        assert recorder.events[-1]["name"] == "Next"
    finally:
        await client.stop()


async def test_send_cmd_while_disconnected_raises(
    fake_server: FakeLydbroServer,
) -> None:
    client, recorder = await _connected_client(fake_server)
    try:
        await fake_server.drop_client()
        for _ in range(50):
            if not client.connected:
                break
            await asyncio.sleep(0.05)

        with pytest.raises(LydbroProtocolError, match="not connected"):
            await client.send_cmd("rescan_discovery")
    finally:
        await client.stop()
