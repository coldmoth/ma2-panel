"""Executor catalogue regressions using the isolated mock bridge."""
import json
import pytest

from test_bridge import FULL, ask, bridge_cfg  # noqa: F401
from commands import unrecognised_lines


@pytest.mark.parametrize("pages", [[1], [1, 2]])
def test_fixed_range_error_is_sent_once_without_learning_smaller_ceiling(bridge_cfg, pages):
    def edit(cfg):
        cfg["pages"] = [{"n": p, "label": str(p)} for p in pages]
    settings = {**FULL, "ma2": {"list_cmd": "List Executor {page}.1 Thru {page}.250"}}
    with bridge_cfg(edit, settings) as (ws, mock, path):
        original = mock._reply
        def reply(cmd):
            if cmd.startswith("List Executor"):
                return "Error #9: NUMBER TOO LARGE\r\n[Group]>"
            return original(cmd)
        mock._reply = reply
        before = path.read_bytes()
        result = ask(ws, {"a": "scenes_import"})
        assert not result["ok"]
        assert [c for c in mock.received if c.startswith("List Executor")] == ["List Executor 1.1 Thru 1.250"]
        assert "list_cmd" in result["err"]
        assert path.read_bytes() == before


def test_import_without_recognised_show_identity_is_cancelled(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        before = path.read_bytes()
        mock.list_garbage = True
        result = ask(ws, {"a": "scenes_import"})
        assert not result["ok"] and "имя шоу" in result["err"]
        assert path.read_bytes() == before
        assert not any(cmd.startswith("List Executor") for cmd in mock.received)


@pytest.mark.parametrize("action", ["scenes_import", "ma2_import"])
@pytest.mark.parametrize("failed_page", [1, 2])
def test_shortened_executor_range_refuses_import_without_changing_plan(bridge_cfg, action, failed_page):
    with bridge_cfg() as (ws, mock, path):
        original = mock._reply
        mock.rows["2.101"] = "Second page"
        def reply(cmd):
            if cmd == f"List Executor {failed_page}.1 Thru {failed_page}.250":
                return "Error #9: NUMBER TOO LARGE\r\n[Group]>"
            return original(cmd)
        mock._reply = reply
        before = path.read_bytes()
        ws.send_json({"a": action, "groups": [], "scenes": True})
        freshness = None
        while True:
            result = ws.receive_json()
            if "status" in result:
                freshness = result["status"]["read_freshness"]["scenes"]
            if result.get("a") == action and "ok" in result:
                break
        assert freshness is False
        assert not result["ok"] and "охват" in result["err"]
        assert [c for c in mock.received if c.startswith("List Executor")] == [
            *[f"List Executor 1.1 Thru 1.250"] * (failed_page == 2),
            f"List Executor {failed_page}.1 Thru {failed_page}.250",
            f"List Executor {failed_page}.1 Thru {failed_page}.200"]
        assert path.read_bytes() == before
        # The next explicit attempt starts from the requested range, not a cached
        # ceiling learned from a different failure/context.
        mock._reply = original
        mock.received.clear()
        assert ask(ws, {"a": action, "groups": [], "scenes": True})["ok"]
        assert [c for c in mock.received if c.startswith("List Executor")] == [
            "List Executor 1.1 Thru 1.250", "List Executor 2.1 Thru 2.250"]
        assert any(s["exec"] == "2.101" for s in json.loads(path.read_text())["scenes"])


@pytest.mark.parametrize("reply,unknown", [
    ("", 1), ("[Group]>", 1),
    ("Executing : List Executor 1.1 Thru 1.250\n[Group]>", 1),
    ("[Group]>List Executor 1.1 Thru 1.250\n[Group]>", 1),
    ("No. Name Info\n[Group]>", 1),
    ("No objects found\n[Group]>", 1),  # no verified empty catalogue format yet
    ("Error #9\n[Group]>", 1),
    ("Executor 1.101 Piano\n???\n[Group]>", 1),
    ("Executor 1.101 Piano\n[Group]>", 0),
])
def test_executor_catalogue_requires_data_evidence(reply, unknown):
    assert unrecognised_lines(reply) == unknown


@pytest.mark.parametrize("body", ["", "Executing : {cmd}\r\n", "{cmd}\r\n"])
def test_prompt_only_import_is_unknown_and_keeps_old_scenes(bridge_cfg, body):
    with bridge_cfg() as (ws, mock, path):
        original = mock._reply
        def reply(cmd):
            if cmd.startswith("List Executor"):
                return body.format(cmd=cmd) + "[Group]>"
            return original(cmd)
        # A bare prompt must still be a completed transport frame in this test.
        mock._reply = lambda cmd: "\r\n" + reply(cmd)
        before = path.read_bytes()
        ws.send_json({"a": "scenes_import"})
        freshness = None
        while True:
            message = ws.receive_json()
            if "status" in message:
                freshness = message["status"]["read_freshness"]["scenes"]
            if message.get("a") == "scenes_import" and "ok" in message:
                break
        assert message["ok"] and message["unrecognised"] > 0
        assert freshness is False
        assert path.read_bytes() == before
