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


async def test_hello_with_error_field_is_rejected(
    fake_server: FakeLydbroServer,
) -> None:
    """Server can refuse the connection via ``hello.error`` (e.g. too_many_clients)."""
    fake_server.hello = dict(fake_server.hello, error="too_many_clients")

    recorder = _Recorder()
    client = LydbroClient(
        "127.0.0.1",
        fake_server.port,
        on_hello=recorder.on_hello,
        on_state=recorder.on_state,
        on_event=recorder.on_event,
        on_connection_change=recorder.on_connection,
    )
    await client.start()
    try:
        # Handshake must NOT complete — the client raises, the read
        # loop tears the socket down, and the reconnect loop backs off.
        assert await client.wait_connected(timeout=0.5) is False
        assert recorder.connection_changes == []
    finally:
        await client.stop()


async def test_hello_with_wrong_protocol_version_is_rejected(
    fake_server: FakeLydbroServer,
) -> None:
    """A server on a different wire version is refused before hello_ack."""
    fake_server.hello = dict(fake_server.hello, v=99)

    recorder = _Recorder()
    client = LydbroClient(
        "127.0.0.1",
        fake_server.port,
        on_hello=recorder.on_hello,
        on_state=recorder.on_state,
        on_event=recorder.on_event,
        on_connection_change=recorder.on_connection,
    )
    await client.start()
    try:
        assert await client.wait_connected(timeout=0.5) is False
        assert recorder.connection_changes == []
    finally:
        await client.stop()


async def test_hello_ack_state_handshake(fake_server: FakeLydbroServer) -> None:
    """Server hello → client ack → server state → client marked connected."""
    client, recorder = await _connected_client(fake_server)
    try:
        assert len(recorder.hellos) == 1
        assert recorder.hellos[0]["id"] == "aa:bb:cc:dd:ee:ff"
        assert recorder.hellos[0]["fw"] == "0.13.0"

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
        await fake_server.push_event("button_press", name="Play", kind="click", mode="MUSIC")
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
            await client.send_cmd("send_remote_key", key="Play")
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
            await client.send_cmd("reboot")
    finally:
        await client.stop()


async def test_cmd_ids_increment(fake_server: FakeLydbroServer) -> None:
    """Each send_cmd bumps the client-side id monotonically."""
    client, _ = await _connected_client(fake_server)
    try:
        await client.send_cmd("reboot")
        await client.send_cmd("reboot")
        await client.send_cmd("reboot")
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
            await client.send_cmd("reboot")
    finally:
        await client.stop()


# ---------------------------------------------------------------------------
# Small error and edge paths — exist to pin coverage and protect against
# silent regressions in the read loop's frame dispatcher.
# ---------------------------------------------------------------------------


async def test_start_called_twice_is_a_noop(fake_server: FakeLydbroServer) -> None:
    """Second start() while already running must not spawn a duplicate runner."""
    client, _ = await _connected_client(fake_server)
    try:
        runner_before = client._runner  # type: ignore[attr-defined]
        assert runner_before is not None
        await client.start()
        runner_after = client._runner  # type: ignore[attr-defined]
        assert runner_after is runner_before
    finally:
        await client.stop()


async def test_server_pong_is_silently_accepted(fake_server: FakeLydbroServer) -> None:
    """A pong from the server is a no-op, not a malformed-frame drop."""
    client, _ = await _connected_client(fake_server)
    try:
        # Push a raw pong — the client has no pending ping, so this
        # just exercises the "ignore" branch of _handle_frame.
        await fake_server.push_raw(b'{"t":"pong"}\n')
        await asyncio.sleep(0.05)
        assert client.connected is True
    finally:
        await client.stop()


async def test_server_error_frame_is_logged_not_fatal(
    fake_server: FakeLydbroServer, caplog
) -> None:
    """A server-side {t:"error", ...} frame logs a warning but doesn't disconnect."""
    client, recorder = await _connected_client(fake_server)
    try:
        with caplog.at_level("WARNING"):
            await fake_server.push_raw(b'{"t":"error","msg":"boom"}\n')
            # Push a real event behind the error to prove the read loop
            # is still alive.
            await fake_server.push_event("button_press", name="Play", kind="click")
            await asyncio.wait_for(recorder.event_event.wait(), 2.0)

        assert client.connected is True
        assert "lydbro server error" in caplog.text
    finally:
        await client.stop()


async def test_unknown_frame_type_is_dropped(fake_server: FakeLydbroServer) -> None:
    """Unrecognised frame types fall through to the debug-log tail."""
    client, recorder = await _connected_client(fake_server)
    try:
        await fake_server.push_raw(b'{"t":"banana","flavour":"yellow"}\n')
        # Prove the client still processes real frames after.
        await fake_server.push_event("button_press", name="Play", kind="click")
        await asyncio.wait_for(recorder.event_event.wait(), 2.0)
        assert client.connected is True
    finally:
        await client.stop()


async def test_read_timeout_disconnects_and_reconnects(
    fake_server: FakeLydbroServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A long silence on the socket trips READ_TIMEOUT → LydbroProtocolError.

    The resilient reconnect loop catches it and reconnects, so the
    client bounces `connected` false → true.
    """
    from custom_components.lydbro import client as client_mod

    monkeypatch.setattr(client_mod, "READ_TIMEOUT", 0.2)
    # Also shrink the backoff so the reconnect is observable in test time.
    monkeypatch.setattr(client_mod, "PING_INTERVAL", 10.0)

    client, recorder = await _connected_client(fake_server)
    try:
        # First handshake landed; wait out the READ_TIMEOUT with no
        # frames arriving.
        first_connects = sum(1 for v in recorder.connection_changes if v is True)
        assert first_connects == 1

        # Wait long enough for the read timeout to trip and the
        # reconnect loop to re-handshake.
        for _ in range(60):
            second_connects = sum(1 for v in recorder.connection_changes if v is True)
            if second_connects >= 2:
                break
            await asyncio.sleep(0.1)

        # At minimum we saw one disconnect and one reconnect.
        assert any(v is False for v in recorder.connection_changes)
        assert sum(1 for v in recorder.connection_changes if v is True) >= 2
    finally:
        await client.stop()


def test_fail_pending_sets_exceptions_on_pending_futures() -> None:
    """_fail_pending drains the pending dict and fails each live future."""
    client = LydbroClient(
        "127.0.0.1",
        1,
        on_hello=_Recorder().on_hello,
        on_state=_Recorder().on_state,
        on_event=_Recorder().on_event,
    )
    loop = asyncio.new_event_loop()
    try:
        fut1 = loop.create_future()
        fut2 = loop.create_future()
        client._pending[1] = fut1  # type: ignore[attr-defined]
        client._pending[2] = fut2  # type: ignore[attr-defined]

        client._fail_pending(LydbroProtocolError("boom"))  # type: ignore[attr-defined]

        assert fut1.done() and isinstance(fut1.exception(), LydbroProtocolError)
        assert fut2.done() and isinstance(fut2.exception(), LydbroProtocolError)
        assert client._pending == {}  # type: ignore[attr-defined]
    finally:
        loop.close()
