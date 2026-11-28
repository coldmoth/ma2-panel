"""MA2-003: failed discovery preserves the saved plan."""
import pytest

from ma2panel.link import MA2Link
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


def test_empty_show_list_page_returns_empty_scenes_without_error(bridge_cfg, monkeypatch):
    from test_bridge import ask
    with bridge_cfg(edit=lambda c: c.update(scenes=[])) as (ws, mock, path):
        mock.rows.clear()
        res = ask(ws, {"a": "scenes_import"})
        assert res["ok"] is True and res["total"] == 0 and res["added"] == 0


def test_prompt_prefixed_list_page_and_dict_pages_compatibility(bridge_cfg, monkeypatch):
    from ma2panel.show_plans import validate_auto_plan
    from test_bridge import ask
    original = MA2Link.send
    async def send(self, cmd, **kw):
        if cmd == "List Page":
            return True, "[Fixture]>        No.  Name  Info\r\n[Fixture]>Page  1 1    Page         (2)\r\n"
        return await original(self, cmd, **kw)
    monkeypatch.setattr(MA2Link, "send", send)
    with bridge_cfg(edit=lambda c: c.update(pages={"2": "Concert"})) as (ws, mock, path):
        res = ask(ws, {"a": "scenes_import"})
        assert res["ok"] is True and res["total"] >= 2
        # Both list and legacy dict formats pass validate_auto_plan
        base = {"fixtures": [], "groups": [], "scenes": [], "presets": [], "attrs": {}}
        validate_auto_plan({**base, "pages": [{"n": 1, "label": "Main"}]}, base)
        validate_auto_plan({**base, "pages": {"1": "Main"}}, base)


def test_new_scene_failure_before_store_cleans_up_scene_write_journal(bridge_cfg):
    from test_bridge import ask
    with bridge_cfg() as (ws, mock, path):
        assert ask(ws, {"a": "select_fixtures", "ids": [12]})["ok"]
        original = mock._reply
        def fail_select(text):
            if text == "Fixture 12":
                return "Error #72: COMMAND NOT EXECUTED\r\n[Channel]>"
            return original(text)
        mock._reply = fail_select
        res = ask(ws, {"a": "scene_create", "label": "Fresh", "page": 2, "exec": "2.150", "confirm": "2.150"})
        assert res["ok"] is False
        assert not (path.parent / "scene-write-2.150.json").exists()
        # Slot is not permanently locked: retrying after transient failure succeeds
        mock._reply = original
        res2 = ask(ws, {"a": "scene_create", "label": "Fresh", "page": 2, "exec": "2.150", "confirm": "2.150"})
        assert res2["ok"] is True
