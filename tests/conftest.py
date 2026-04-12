"""Shared fixtures for the Lydbro test suite.

Two layers:

* :func:`fake_server` — starts :class:`FakeLydbroServer` on a random
  loopback port, yields it to the test, shuts it down on teardown.
  Pair with :func:`LydbroClient` for pure-client tests that don't
  need a Home Assistant runtime.

* :func:`enable_custom_integrations` — standard
  ``pytest-homeassistant-custom-component`` fixture that lets the test
  HA instance pick up ``custom_components/lydbro/``. Required for any
  test that uses :func:`hass` or sets up a config entry.

The HA-side fixtures (``hass``, ``mock_config_entry``, ...) are
provided by ``pytest-homeassistant-custom-component`` and don't need
re-exporting here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from .fake_server import FakeLydbroServer


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Auto-enable the lydbro custom component for every test.

    ``enable_custom_integrations`` is provided by
    pytest-homeassistant-custom-component; wrapping it in an autouse
    fixture means individual tests don't need to remember to request
    it.
    """
    yield


@pytest.fixture
async def fake_server(socket_enabled) -> AsyncIterator[FakeLydbroServer]:
    """Start a fresh fake Lydbro bridge for a single test.

    Depends on the ``socket_enabled`` fixture from ``pytest-socket``
    (pulled in via pytest-homeassistant-custom-component) because HA's
    test harness blocks raw sockets by default to catch accidental
    network calls. Our fake bridge listens on loopback, so we
    explicitly opt in for tests that need it.
    """
    server = FakeLydbroServer()
    await server.start()
    try:
        yield server
    finally:
        await server.stop()
