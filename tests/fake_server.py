"""A fake Lydbro bridge speaking the Native TCP v1 protocol.

Used by the test suite instead of mocking :class:`LydbroClient`. Tests
run the real client code end-to-end against this server, which means
frame parsing, handshake ordering, and timeout behaviour are all
exercised for real. If you're tempted to mock the client instead, that
coverage disappears.

Protocol (line-delimited JSON, one frame per line, UTF-8):

    S -> C  {"t":"hello", "fw":..., "id":..., "name":..., ...}
    C -> S  {"t":"hello_ack"}
    S -> C  {"t":"state", "battery":..., "eth_up":..., ...}
    S -> C  {"t":"event", "type":"button_press", "name":"Play", ...}
    S -> C  {"t":"ping"}
    C -> S  {"t":"pong"}
    C -> S  {"t":"cmd", "id":N, "cmd":"foo", ...}
    S -> C  {"t":"result", "id":N, "ok":true,  "value":...}
       or   {"t":"result", "id":N, "ok":false, "error":"..."}

See ``custom_components/lydbro/client.py`` for the reference client.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

DEFAULT_HELLO: dict[str, Any] = {
    "t": "hello",
    "v": 2,
    "fw": "0.13.0",
    "branch": "test",
    "id": "aa:bb:cc:dd:ee:ff",
    "name": "Test Lydbro One",
    "caps": ["cmd", "event", "state"],
}

DEFAULT_STATE: dict[str, Any] = {
    "t": "state",
    "battery": 87,
    "eth_up": True,
    "ble_connected": True,
    "safe_mode": False,
    "fw": "0.11.9.3",
    "ip": "127.0.0.1",
    "boot_phase": "Ready",
    "boot_complete": True,
}


CmdHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class FakeLydbroServer:
    """Asyncio TCP server emulating the Lydbro Native TCP protocol.

    Configure per-test via :attr:`hello`, :attr:`state`, and a
    :attr:`cmd_handler`. The server accepts a single client at a time
    (which matches the real firmware's one-slot behaviour closely
    enough for the integration's needs) but stores every connection's
    lifecycle for assertions.
    """

    def __init__(self) -> None:
        self.hello: dict[str, Any] = dict(DEFAULT_HELLO)
        self.state: dict[str, Any] = dict(DEFAULT_STATE)
        # Called with the incoming cmd frame; must return the result
        # frame the server should send back. If None, every cmd is
        # answered with ``{ok: true}``.
        self.cmd_handler: CmdHandler | None = None

        # Assertion-friendly history:
        self.acked = asyncio.Event()  # set when client sends hello_ack
        self.received_cmds: list[dict[str, Any]] = []
        self.received_pongs = 0

        # Writer for the currently-connected client, so tests can push
        # events/pings at will.
        self._writer: asyncio.StreamWriter | None = None
        self._server: asyncio.base_events.Server | None = None
        self._client_closed = asyncio.Event()
        # Tracks the task for the currently-connected client handler
        # plus any in-flight cmd handler coroutines, so teardown can
        # cancel them cleanly and avoid "lingering task" failures from
        # HA's test harness.
        self._client_task: asyncio.Task[None] | None = None
        self._cmd_tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def port(self) -> int:
        assert self._server is not None, "server not started"
        sock = self._server.sockets[0]
        return sock.getsockname()[1]

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, host="127.0.0.1", port=0)

    async def stop(self) -> None:
        # Cancel any in-flight cmd handlers first — they may be
        # awaiting sleeps or events and would otherwise hang the
        # client connection task we're about to cancel.
        for task in list(self._cmd_tasks):
            task.cancel()
        for task in list(self._cmd_tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._cmd_tasks.clear()

        if self._client_task is not None:
            self._client_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._client_task
            self._client_task = None

        if self._writer is not None:
            with contextlib.suppress(Exception):
                self._writer.close()
                await self._writer.wait_closed()
            self._writer = None

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # ------------------------------------------------------------------
    # Server-side push helpers (tests call these)
    # ------------------------------------------------------------------

    async def push_state(self, **overrides: Any) -> None:
        """Send a state snapshot, optionally overriding fields."""
        frame = dict(self.state)
        frame.update(overrides)
        frame["t"] = "state"
        await self._send(frame)

    async def push_event(self, event_type: str, **fields: Any) -> None:
        """Send an event frame."""
        frame = {"t": "event", "type": event_type, **fields}
        await self._send(frame)

    async def push_ping(self) -> None:
        await self._send({"t": "ping"})

    async def push_raw(self, payload: bytes) -> None:
        """Send raw bytes (for malformed-frame tests)."""
        assert self._writer is not None
        self._writer.write(payload)
        await self._writer.drain()

    async def drop_client(self) -> None:
        """Close the current client connection, simulating network drop."""
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None

    async def wait_client_closed(self, timeout: float = 5.0) -> None:
        await asyncio.wait_for(self._client_closed.wait(), timeout)

    # ------------------------------------------------------------------
    # Client connection handler
    # ------------------------------------------------------------------

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._writer = writer
        self._client_task = asyncio.current_task()
        self._client_closed.clear()
        try:
            # Send the hello frame immediately on connect.
            await self._send(self.hello)

            while not reader.at_eof():
                raw = await reader.readline()
                if not raw:
                    break
                try:
                    frame = json.loads(raw.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue

                ftype = frame.get("t")
                if ftype == "hello_ack":
                    self.acked.set()
                    # Push the initial state snapshot right after ack,
                    # same as the real firmware does.
                    await self._send(self.state)
                elif ftype == "pong":
                    self.received_pongs += 1
                elif ftype == "ping":
                    await self._send({"t": "pong"})
                elif ftype == "cmd":
                    if frame.get("cmd") == "24601":
                        # Easter egg — mirror firmware, don't pollute
                        # received_cmds (tests that count cmds would
                        # otherwise break whenever the integration
                        # whispers on connect).
                        await self._send(
                            {
                                "t": "result",
                                "id": frame.get("id"),
                                "ok": True,
                                "name": "jean-valjean",
                                "line": "Who am I? 2-4-6-0-1!",
                            }
                        )
                        continue
                    self.received_cmds.append(frame)
                    result = await self._answer_cmd(frame)
                    await self._send(result)
                # Silently ignore anything else — the real server does too.
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        finally:
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()
            self._writer = None
            self._client_closed.set()

    async def _answer_cmd(self, frame: dict[str, Any]) -> dict[str, Any]:
        if self.cmd_handler is not None:
            return await self.cmd_handler(frame)
        return {"t": "result", "id": frame.get("id"), "ok": True}

    async def _send(self, frame: dict[str, Any]) -> None:
        if self._writer is None:
            return
        data = (json.dumps(frame, separators=(",", ":")) + "\n").encode("utf-8")
        self._writer.write(data)
        await self._writer.drain()
