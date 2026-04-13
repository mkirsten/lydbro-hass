"""Asyncio client for the Lydbro Native TCP v1 protocol.

Wire format: line-delimited JSON on TCP port 6204. The server sends a
`hello` frame on connect; we reply with `hello_ack` and it pushes an
initial `state` snapshot followed by event frames. Commands travel in
the other direction as `cmd` frames with a client-chosen `id`; the
server replies with a `result` frame carrying the same id.

See docs/native_tcp_protocol.md in this repo for the full spec.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Keepalive timings — match adapter_native_tcp.h:
#   NTCP_PING_MS = 10000  (server pings when idle 10s in both directions)
#   NTCP_IDLE_MS = 30000  (server drops clients silent for 30s)
# We ping at 8s so we always beat the server's idle clock.
# Wire-format version this integration speaks. The firmware announces
# its own `v` in the hello frame; a mismatch means the wire format
# itself differs and neither side can recover, so we refuse the
# connection and let the reconnect loop surface the reason. See
# docs/native_tcp_protocol.md § Versioning in this repo.
PROTOCOL_VERSION = 2

PING_INTERVAL = 8.0
READ_TIMEOUT = 25.0
CONNECT_TIMEOUT = 5.0
CMD_TIMEOUT = 5.0


class LydbroProtocolError(Exception):
    """Raised when the server sends an invalid or unexpected frame."""


class LydbroClient:
    """Persistent TCP client with auto-reconnect and push event dispatch.

    Callers supply three async callbacks:
      * ``on_hello``  — fired once per connection after the server hello.
                        Receives the hello dict (fw, id, name, caps, ...).
      * ``on_state``  — fired for every ``state`` snapshot frame.
      * ``on_event``  — fired for every ``event`` frame.

    Commands are sent with :meth:`send_cmd`, which returns the ``result``
    payload or raises on error / timeout.
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        on_hello: Callable[[dict[str, Any]], Awaitable[None]],
        on_state: Callable[[dict[str, Any]], Awaitable[None]],
        on_event: Callable[[dict[str, Any]], Awaitable[None]],
        on_connection_change: Callable[[bool], Awaitable[None]] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._on_hello = on_hello
        self._on_state = on_state
        self._on_event = on_event
        self._on_connection_change = on_connection_change

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._runner: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._connected = asyncio.Event()

        self._cmd_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._write_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    async def start(self) -> None:
        """Begin the connect/reconnect loop. Returns immediately."""
        if self._runner is not None:
            return
        self._stop.clear()
        self._runner = asyncio.create_task(self._run(), name=f"lydbro-{self._host}")

    async def stop(self) -> None:
        """Stop the client and close the socket."""
        self._stop.set()
        if self._writer is not None:
            with contextlib.suppress(Exception):
                self._writer.close()
                await self._writer.wait_closed()
        if self._runner is not None:
            with contextlib.suppress(asyncio.CancelledError):
                self._runner.cancel()
                await self._runner
            self._runner = None
        self._fail_pending(LydbroProtocolError("client stopped"))

    async def wait_connected(self, timeout: float) -> bool:
        """Block until the initial hello+state completes, or timeout."""
        try:
            await asyncio.wait_for(self._connected.wait(), timeout)
            return True
        except TimeoutError:
            return False

    # ------------------------------------------------------------------
    # Command send path
    # ------------------------------------------------------------------

    async def send_cmd(self, cmd: str, **args: Any) -> dict[str, Any]:
        """Send a command and await its ``result`` frame.

        Raises :class:`LydbroProtocolError` on timeout, disconnection, or
        a server-side error response.
        """
        if self._writer is None or not self._connected.is_set():
            raise LydbroProtocolError("not connected")

        self._cmd_id += 1
        cmd_id = self._cmd_id
        payload: dict[str, Any] = {"t": "cmd", "id": cmd_id, "cmd": cmd}
        payload.update(args)

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[cmd_id] = fut

        try:
            await self._write_json(payload)
            return await asyncio.wait_for(fut, CMD_TIMEOUT)
        except TimeoutError as err:
            raise LydbroProtocolError(f"cmd {cmd} timed out") from err
        finally:
            self._pending.pop(cmd_id, None)

    # ------------------------------------------------------------------
    # Internal: connect loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self._connect_and_serve()
                # clean disconnect — reset backoff. Only hit if
                # _connect_and_serve ever returns without raising,
                # which the current read-loop design never does (peer
                # close raises LydbroProtocolError). Kept as defensive
                # bookkeeping for a future refactor.
                backoff = 1.0  # pragma: no cover
            except asyncio.CancelledError:  # pragma: no cover
                # The runner task was cancelled from outside — let
                # cancellation propagate so the coroutine shuts down
                # cleanly instead of being swallowed by the generic
                # Exception handler below.
                raise
            except Exception as err:  # noqa: BLE001 — resilient loop
                _LOGGER.debug("lydbro %s:%d connection error: %s", self._host, self._port, err)
            finally:
                await self._mark_disconnected()

            if self._stop.is_set():
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    async def _connect_and_serve(self) -> None:
        _LOGGER.debug("lydbro connecting to %s:%d", self._host, self._port)
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port), CONNECT_TIMEOUT
        )

        ping_task = asyncio.create_task(self._ping_loop(), name="lydbro-ping")
        try:
            await self._read_loop()
        finally:
            ping_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ping_task

    async def _read_loop(self) -> None:
        assert self._reader is not None
        while not self._stop.is_set():
            try:
                raw = await asyncio.wait_for(self._reader.readline(), READ_TIMEOUT)
            except TimeoutError as err:
                raise LydbroProtocolError("read timeout") from err

            if not raw:
                raise LydbroProtocolError("peer closed")

            try:
                frame = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                _LOGGER.warning("lydbro dropping malformed frame: %r", raw[:120])
                continue

            await self._handle_frame(frame)

    async def _handle_frame(self, frame: dict[str, Any]) -> None:
        ftype = frame.get("t")

        if ftype == "hello":
            # The server uses a hello frame with an `error` field to
            # reject the connection (e.g. too_many_clients — more than
            # 4 concurrent clients). Don't send hello_ack; surface the
            # reason and let the read loop observe the peer close.
            err = frame.get("error")
            if err:
                raise LydbroProtocolError(f"server rejected hello: {err}")
            server_v = frame.get("v")
            if server_v != PROTOCOL_VERSION:
                raise LydbroProtocolError(
                    f"unsupported protocol version: server v={server_v}, "
                    f"client v={PROTOCOL_VERSION}"
                )
            await self._on_hello(frame)
            await self._write_json(
                {"t": "hello_ack", "v": PROTOCOL_VERSION, "client": "home-assistant"}
            )
            # Server pushes initial state snapshot right after hello_ack.
            return

        if ftype == "state":
            await self._on_state(frame)
            if not self._connected.is_set():
                self._connected.set()
                if self._on_connection_change is not None:
                    await self._on_connection_change(True)
            return

        if ftype == "event":
            await self._on_event(frame)
            return

        if ftype == "ping":
            await self._write_json({"t": "pong"})
            return

        if ftype == "pong":
            return

        if ftype == "result":
            cmd_id = frame.get("id")
            fut = self._pending.get(cmd_id) if isinstance(cmd_id, int) else None
            if fut is not None and not fut.done():
                if frame.get("ok"):
                    fut.set_result(frame)
                else:
                    fut.set_exception(LydbroProtocolError(frame.get("error") or "cmd failed"))
            return

        if ftype == "error":
            _LOGGER.warning("lydbro server error: %s", frame)
            return

        _LOGGER.debug("lydbro unknown frame type: %s", frame)

    async def _ping_loop(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(PING_INTERVAL)
            # The writer-gone and write-failure branches are
            # defensive bookkeeping — in normal operation the
            # ping loop is cancelled by _connect_and_serve before
            # either condition can occur.
            if self._writer is None:  # pragma: no cover
                return
            try:
                await self._write_json({"t": "ping"})
            except Exception:  # noqa: BLE001  # pragma: no cover
                return

    # ------------------------------------------------------------------
    # Internal: writes + disconnect bookkeeping
    # ------------------------------------------------------------------

    async def _write_json(self, payload: dict[str, Any]) -> None:
        if self._writer is None:  # pragma: no cover
            # Defensive: send_cmd guards against writer=None earlier
            # in its own flow, so this branch is only reachable if a
            # future caller forgets to and passes through directly.
            raise LydbroProtocolError("not connected")
        data = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        async with self._write_lock:
            self._writer.write(data)
            await self._writer.drain()

    async def _mark_disconnected(self) -> None:
        was_connected = self._connected.is_set()
        self._connected.clear()
        if self._writer is not None:
            with contextlib.suppress(Exception):
                self._writer.close()
            self._writer = None
        self._reader = None
        self._fail_pending(LydbroProtocolError("disconnected"))
        if was_connected and self._on_connection_change is not None:
            with contextlib.suppress(Exception):
                await self._on_connection_change(False)

    def _fail_pending(self, err: Exception) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(err)
        self._pending.clear()
