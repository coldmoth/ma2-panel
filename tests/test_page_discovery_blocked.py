"""MA2-003: failed discovery preserves the saved plan."""
import pytest

from link import MA2Link
from test_bridge import bridge_cfg  # noqa: F401


@pytest.mark.parametrize("ok, reason", [(False, "Error: List Page failed"), (False, "результат неизвестен"), (True, "Executing : List Page\n[Group]>")])
def test_failed_page_discovery_never_confirms_complete_read(bridge_cfg, monkeypatch, ok, reason):
    original = MA2Link.send
    async def send(self, cmd, **kw):
        if cmd == "List Page":
            return ok, reason
        return await original(self, cmd, **kw)
    monkeypatch.setattr(MA2Link, "send", send)
    with bridge_cfg() as (ws, mock, path):
        mock.rows["2.101"] = "Not in the plan"
        before = path.read_bytes()
        ws.send_json({"a": "scenes_import"})
        freshness = None
        while True:
            message = ws.receive_json()
            if "status" in message:
                freshness = message["status"]["read_freshness"]["scenes"]
            if message.get("a") == "scenes_import" and "ok" in message:
                break
        assert freshness is not True
        assert message["ok"] is False
        assert "List Page" in message["err"]
        assert path.read_bytes() == before
