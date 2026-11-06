import pytest

from ma2panel import api
from ma2panel import bridge
from ma2panel import link
from ma2panel.safety import DEFAULT_MA2


@pytest.fixture(autouse=True)
def short_waits(monkeypatch):
    """The mock answers in milliseconds: the hall's waits (3 s reconnect, 2 s reply, 2 s show poll, 3 s bare connect, 5 s export) only slow the suite.
    A test that needs the real value sets it itself."""
    monkeypatch.setattr(link, "RECONNECT_S", 0.2)
    monkeypatch.setattr(link, "REPLY_S", 0.5)
    monkeypatch.setattr(bridge, "SHOW_POLL_S", 0.2)
    monkeypatch.setattr(api, "BARE_CONNECT_S", 0.5)
    monkeypatch.setitem(DEFAULT_MA2, "timeout", 0.5)
    monkeypatch.setitem(DEFAULT_MA2, "export_wait", 0.3)
