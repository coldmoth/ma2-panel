"""P0.4 regressions. Raw frames retain the revision of the originating view."""
import asyncio
import json
from contextlib import ExitStack, contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ma2panel.bridge import create_app
from ma2panel.fixtures import save_config
from ma2panel.mock import MockMA2
from ma2panel import scene_recovery
from ma2panel.scenes import merge_scenes, new_scene
from test_bridge import CONFIG, FULL, until
from test_release33_regressions import context  # noqa: F401
from test_stage4_integration import client as session, desk_link


@contextmanager
def mock_bridge(path, settings=FULL):
    if not path.exists():
        cfg = json.loads(Path(CONFIG).read_text())
        cfg["scenes"] = [{"id": f"s{i}", "label": f"Scene {i}", "exec": f"1.{100+i}"} for i in range(1, 7)]
        cfg["ma2"]["export_dir"] = str(path.parent)
        cfg["scene_fade"] = 1.5
        path.write_text(json.dumps(cfg), encoding="utf-8")
    cfg = json.loads(path.read_text())
    app = create_app(cfg, True, str(path), {"poll_seconds": 0, **settings})
    app.mount("/simple-test", app.state.simple_app)
    app.router.routes.insert(0, app.router.routes.pop())
    with TestClient(app) as client:
        yield client, app.state.mock


class Panel:
    def __init__(self, ws):
        self.ws = ws
        self.config = None
        self.status = {}
        self.history = []
        self.serial = 0
        while not self.config or self.status.get("ma2") != "logged_in" or self.status.get("recovering"):
            self.receive()

    def receive(self):
        frame = self.ws.receive_json()
        self.config = frame.get("config", self.config)
        self.status = frame.get("status", self.status)
        self.history = frame.get("history", self.history)
        return frame

    def action(self, action):
        self.serial += 1
        rid = f"p04-{self.serial}"
        payload = {"request_id": rid, "config_revision": self.config["revision"],
                   "blackout_epoch": self.status["blackout_epoch"], **action}
        self.ws.send_json(payload)
        while True:
            reply = self.receive()
            if reply.get("request_id") == rid and "ok" in reply:
                print("request", json.dumps(payload, ensure_ascii=False))
                print("response", json.dumps(reply, ensure_ascii=False))
                return reply

    def scene(self, sid):
        return next(scene for scene in self.config["scenes"] if scene["id"] == sid)


def intent(name, scene, revision):
    return {"a": name, "id": scene["id"], "scene_identity": scene["identity"], "config_revision": revision}


def assert_refused(panel, mock, action, code):
    before = len(mock.received)
    result = panel.action(action)
    assert not result["ok"] and result["code"] == code
    assert result["outcome"] == "failed" and result["command_evidence"] == []
    assert mock.received[before:] == []
    print("mock", mock.received[before:])


def test_two_clients_delete_create_and_stale_go_off(tmp_path):
    with mock_bridge(tmp_path / "config.json") as (client, mock), ExitStack() as stack:
        a, b = [Panel(stack.enter_context(client.websocket_connect("/ws"))) for _ in range(2)]
        previous, revision = a.scene("s6"), a.config["revision"]
        assert previous["exec"] == "1.106"
        assert b.action({"a": "scene_delete", "id": "s6"})["ok"]
        assert b.action({"a": "select_fixtures", "ids": [12]})["ok"]
        assert b.action({"a": "scene_create", "exec": "1.107", "confirm": "1.107", "page": 1, "label": "Replacement"})["ok"]
        new = b.config["scenes"][-1]
        assert new["exec"] == "1.107" and new["id"] != previous["id"] and new["identity"] != previous["identity"]
        for name in ("scene_go", "scene_off"):
            assert_refused(a, mock, intent(name, previous, revision), "scene_context_changed")
            assert_refused(a, mock, intent(name, previous, a.config["revision"]), "scene_target_changed")

        before = len(mock.received)
        assert a.action(intent("scene_go", new, a.config["revision"]))["ok"]
        writes = [line for line in mock.received[before:] if line.startswith(("Goto", "Off", "Masterfade", "ClearAll"))]
        assert writes == ["Goto Cue 1 Executor 1.107 Fade 1.5"]
        print("mock", json.dumps(mock.received[before:]))

        old_revision = a.config["revision"]
        assert b.action({"a": "group_save", "label": "Local", "ids": [12]})["ok"]
        assert_refused(a, mock, intent("scene_off", new, old_revision), "scene_context_changed")
        assert a.scene(new["id"])["identity"] == new["identity"]
        before = len(mock.received)
        assert a.action(intent("scene_off", new, a.config["revision"]))["ok"]
        assert mock.received[before:] == ["ListVar", "Masterfade 1.5 Executor 1.107", "Off Executor 1.107"]
        print("mock", mock.received[before:])


@pytest.mark.parametrize("path", ["/ws", "/simple-test/ws"])
def test_missing_context_has_no_legacy_bypass(tmp_path, path):
    with mock_bridge(tmp_path / "config.json") as (client, mock), client.websocket_connect(path) as ws:
        panel = Panel(ws)
        for action in ("scene_go", "scene_off"):
            for payload in ({"a": action, "id": "s1"}, {"a": action, "id": "s1", "config_revision": None}):
                assert_refused(panel, mock, payload, "scene_context_required")
            before = len(mock.received)
            ws.send_json({"a": action, "id": "s1"})
            assert until(ws, lambda frame: "ok" in frame)["code"] == "scene_context_required"
            assert mock.received[before:] == []
        for action in ("scene_go", "scene_off"):
            assert panel.action(intent(action, panel.scene("s1"), panel.config["revision"]))["ok"]


def test_switch_return_and_restart_keep_identity_but_refuse_old_revision(tmp_path):
    path = tmp_path / "config.json"
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        original = panel.scene("s1")
        old = intent("scene_go", original, panel.config["revision"])
        show = panel.config["show"]
        assert panel.action({"a": "show_open_plan", "name": "Other"})["ok"]
        assert panel.action({"a": "show_open_plan", "name": show})["ok"]
        assert panel.scene("s1") == original
        assert_refused(panel, mock, old, "scene_context_changed")
        current = intent("scene_off", original, panel.config["revision"])
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        assert panel.scene("s1") == original
        assert_refused(panel, mock, current, "scene_context_changed")


def test_replace_and_undo_delete_never_restore_an_old_assignment(tmp_path):
    with mock_bridge(tmp_path / "config.json") as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        original = panel.scene("s1")
        assert panel.action({"a": "select_fixtures", "ids": [12]})["ok"]
        assert panel.action({"a": "scene_create", "exec": original["exec"], "confirm": original["exec"],
                             "page": 1, "label": "Replaced Cue", "replace": True})["ok"]
        replacement = panel.config["scenes"][0]
        assert replacement["exec"] == original["exec"]
        assert replacement["identity"] != original["identity"] and replacement["id"] == original["id"]
        assert any(line.endswith("/CueOnly /Overwrite") for line in mock.received)
        assert_refused(panel, mock, intent("scene_go", original, panel.config["revision"]), "scene_target_changed")

        assert panel.action({"a": "scene_delete", "id": replacement["id"]})["ok"]
        while not any(entry["a"] == "scene_delete" for entry in panel.history):
            panel.receive()
        delete = next(entry for entry in reversed(panel.history) if entry["a"] == "scene_delete")
        assert panel.action({"a": "undo", "n": delete["n"]})["ok"]
        restored = panel.config["scenes"][0]
        assert restored["exec"] == original["exec"]
        assert restored["identity"] not in {original["identity"], replacement["identity"]}
        assert_refused(panel, mock, intent("scene_off", replacement, panel.config["revision"]), "scene_target_changed")


def test_import_keeps_existing_identity_in_any_order(tmp_path):
    with mock_bridge(tmp_path / "config.json") as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        original = panel.config["scenes"]
        merged, added = merge_scenes(list(reversed(original)), [("1.109", "New"), ("1.101", "Renamed")])
        assert added == 1
        assert [row["identity"] for row in merged[:-1]] == [row["identity"] for row in reversed(original)]
        assert merged[-2]["label"] == "Renamed"
        assert merged[-1]["id"] not in {row["id"] for row in original}
        mock.rows["1.109"] = "New"
        assert panel.action({"a": "scenes_import"})["ok"]
        current = panel.config["scenes"]
        assert [(row["id"], row["identity"]) for row in current[:len(original)]] == [
            (row["id"], row["identity"]) for row in original
        ]
        assert current[-1]["exec"] == "1.109"


@pytest.mark.parametrize("action", ["scene_go", "scene_off"])
def test_catalog_change_during_preparation_refuses_before_light(context, action):
    c = context
    _, calls = desk_link(c)
    original_send = c.link.send
    async def replace_after_confirm(line, **kwargs):
        reply = await original_send(line, **kwargs)
        if line == "ListVar":
            c.cfg["scenes"][0] = {**c.cfg["scenes"][0], "exec": "1.107"}
        return reply

    async def run():
        ws = session(c)
        c.link.send = replace_after_confirm
        scene = c.cfg["scenes"][0]
        response = await c.handle(ws, json.dumps(intent(action, scene, c.revision_token())))
        assert response["code"] == "scene_context_changed"
        assert calls == ["ListVar"]
    asyncio.run(run())


OVERWRITE = "Copy Cue 1 Executor 1.1 At Cue 1 Executor 1.101 /CueOnly /Overwrite"
REPLACE = {"a": "scene_create", "exec": "1.101", "confirm": "1.101",
           "page": 1, "label": "Replaced Cue", "replace": True}


def playback_lines(mock, start):
    return [line for line in mock.received[start:]
            if line.startswith(("Go ", "Goto ", "Off ", "Masterfade ", "ClearAll"))]


def test_failed_overwrite_readback_blocks_old_go_off(tmp_path, monkeypatch):
    reply = MockMA2._reply

    def fail_after_copy(mock, line):
        if (line == "List Executor 1.101" and OVERWRITE in mock.received
                and line not in mock.received[mock.received.index(OVERWRITE) + 1:-1]):
            return "Error #72: COMMAND NOT EXECUTED\r\n[Channel]>"
        return reply(mock, line)

    monkeypatch.setattr(MockMA2, "_reply", fail_after_copy)
    path = tmp_path / "config.json"
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        old = panel.scene("s1")
        assert panel.action(intent("scene_go", old, panel.config["revision"]))["ok"]
        mock.cues["1.101"][1] = {12: {"dim": 70}}
        mock.programmer = {12: {"dim": 25}}
        assert panel.action({"a": "select_fixtures", "ids": [12]})["ok"]
        assert not panel.action(REPLACE)["ok"]
        assert mock.cues["1.101"][1] == {12: {"dim": 25}}
        assert mock.cues["1.1"][2] == {12: {"dim": 70}}
        assert mock.received.count(OVERWRITE) == 1
        with client.websocket_connect("/ws") as fresh_ws:
            fresh = Panel(fresh_ws)
            for name in ("scene_off", "scene_go"):
                before = len(mock.received)
                result = fresh.action(intent(name, old, fresh.config["revision"]))
                assert mock.received[before:] == []
                assert not result["ok"] and "не подтверждена" in result["err"]
            before = len(mock.received)
            assert fresh.action(intent("scene_go", fresh.scene("s2"), fresh.config["revision"]))["ok"]
            assert playback_lines(mock, before) == ["Goto Cue 1 Executor 1.102 Fade 1.5"]

    journal = tmp_path / "scene-write-1.101.json"
    record = json.loads(journal.read_text())
    assert record["phase"] == "committing"
    assert record["previous_identity"] == old["identity"]

    # Reconnect/startup sees an occupied Executor again. The old UUID is still blocked.
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        for name in ("scene_go", "scene_off"):
            assert_refused(panel, mock, intent(name, old, panel.config["revision"]), "action_failed")

    # Reproduce the old incomplete procedure: remove the error and archive the journal.
    plan = json.loads(path.read_text())
    scene = next(row for row in plan["scenes"] if row["id"] == old["id"])
    del scene["write_error"]
    save_config(path, plan)
    journal.rename(journal.with_suffix(".json.verified"))
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        for name in ("scene_go", "scene_off"):
            assert_refused(panel, mock, intent(name, old, panel.config["revision"]), "action_failed")

    # Operator has independently verified the target Cue against spare Cue 1.
    saved_plan = tmp_path / "shows" / "historical-plan.json"
    saved_plan.parent.mkdir(exist_ok=True)
    saved_plan.write_bytes(path.read_bytes())
    previous = saved_plan.read_bytes()
    identity = scene_recovery.recover_scene(path, record["show"], "1.101",
                                           verified_label="Verified Cue", fixtures=record["fixtures"])
    recovered = json.loads(path.read_bytes())
    scene = recovered["scenes"][0]
    assert scene["id"] == old["id"] and scene["identity"] == identity != old["identity"]
    assert scene["label"] == "Verified Cue" and scene["backup_exec"] == record["spare"]
    assert recovered["scenes"][1:] == plan["scenes"][1:]
    assert saved_plan.read_bytes() == previous
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        for name in ("scene_go", "scene_off"):
            assert_refused(panel, mock, intent(name, old, panel.config["revision"]), "scene_target_changed")
        before = len(mock.received)
        for name in ("scene_go", "scene_off"):
            assert panel.action(intent(name, scene, panel.config["revision"]))["ok"]
        assert playback_lines(mock, before) == ["Goto Cue 1 Executor 1.101 Fade 1.5",
                                                "Masterfade 1.5 Executor 1.101",
                                                "Off Executor 1.101"]
        print("mock recovered UUID", playback_lines(mock, before))

    # Reopening an older copy can't re-authorize its old row.
    path.write_bytes(previous)
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        for name in ("scene_go", "scene_off"):
            assert_refused(panel, mock, intent(name, old, panel.config["revision"]), "action_failed")


def test_replaced_cue_running_on_desk_is_excluded_from_panel_transition(tmp_path):
    with mock_bridge(tmp_path / "config.json") as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        old = panel.scene("s1")
        before = len(mock.received)
        assert panel.action(intent("scene_go", old, panel.config["revision"]))["ok"]
        assert playback_lines(mock, before) == ["Goto Cue 1 Executor 1.101 Fade 1.5"]
        assert panel.action({"a": "select_fixtures", "ids": [12]})["ok"]
        assert panel.action(REPLACE)["ok"]
        assert panel.scene("s1")["identity"] != old["identity"]
        mock.running.discard("1.101")
        mock._reply("Go Executor 1.101")  # independent desk operator
        before = len(mock.received)
        ack = panel.action(intent("scene_go", panel.scene("s2"), panel.config["revision"]))
        assert ack["ok"] and ack["outcome"] == "completed"
        assert ack["command_evidence"] == ["sent"]
        assert ack["skipped_off"] == [{"executor": "1.101", "reason": "scene_identity_changed"}]
        assert playback_lines(mock, before) == ["Goto Cue 1 Executor 1.102 Fade 1.5"]
        print("mock skipped Off", playback_lines(mock, before))
        assert "1.101" in mock.running
        mock.rows["1.103"], mock.cues["1.103"] = "Third Scene", {1: {}}
        before = len(mock.received)
        assert panel.action(intent("scene_go", panel.scene("s3"), panel.config["revision"]))["ok"]
        assert playback_lines(mock, before) == ["Masterfade 1.5 Executor 1.102",
                                                "Goto Cue 1 Executor 1.103 Fade 1.5",
                                                "Off Executor 1.102"]
        assert "1.101" in mock.running
        print("mock unchanged transition", playback_lines(mock, before))


@pytest.mark.parametrize("action", ["scene_go", "scene_off"])
def test_playback_queued_during_replacement_never_touches_replaced_cue(context, action):
    c = context
    desk, calls = desk_link(c)
    send = c.link.send

    async def run():
        reading, resume = asyncio.Event(), asyncio.Event()

        async def delayed(line, **kwargs):
            if line == "List Executor 1.101" and not reading.is_set():
                reading.set()
                await resume.wait()
            return await send(line, **kwargs)

        c.link.send = delayed
        writer, operator = session(c), session(c)
        old = c.cfg["scenes"][0]
        previous = intent(action, old, c.revision_token())
        replace = asyncio.create_task(c.handle(writer, json.dumps(REPLACE)))
        await asyncio.wait_for(reading.wait(), 1)
        playback = asyncio.create_task(c.handle(operator, json.dumps(previous)))
        await asyncio.sleep(0)
        assert not playback.done()
        resume.set()
        assert (await replace)["ok"]
        refusal = await playback
        assert not refusal["ok"] and refusal["code"] == "scene_context_changed"
        assert calls.count(OVERWRITE) == 1
        assert not any(line.startswith(("Goto ", "Off ", "Masterfade ", "ClearAll")) for line in calls)
        assert "1.101" not in desk.running

    asyncio.run(run())


def test_go_reply_before_queued_replacement_cannot_restore_old_ownership(context):
    c = context
    desk, calls = desk_link(c)
    send = c.link.send

    async def run():
        sent, resume = asyncio.Event(), asyncio.Event()

        async def delayed(line, **kwargs):
            result = await send(line, **kwargs)
            if line == "Goto Cue 1 Executor 1.101 Fade 1.5":
                sent.set()
                await resume.wait()
            return result

        c.cfg["scene_fade"] = 1.5
        c.link.send = delayed
        writer, operator = session(c), session(c)
        old = c.cfg["scenes"][0]
        other = new_scene("1.102", "Rehearsal")
        c.cfg["scenes"].append(other)
        go = asyncio.create_task(c.handle(operator, json.dumps(intent("scene_go", old, c.revision_token()))))
        await asyncio.wait_for(sent.wait(), 1)
        replace = asyncio.create_task(c.handle(writer, json.dumps(REPLACE)))
        await asyncio.sleep(0)
        assert not replace.done()
        resume.set()
        assert (await go)["ok"] and (await replace)["ok"]
        desk._reply("Go Executor 1.101")
        before = len(calls)
        assert (await c.handle(operator, json.dumps(intent("scene_go", other, c.revision_token()))))["ok"]
        assert [line for line in calls[before:] if line.startswith(("Goto ", "Off ", "Masterfade ", "ClearAll"))] == [
            "Goto Cue 1 Executor 1.102 Fade 1.5"]
        assert "1.101" in desk.running

    asyncio.run(run())


@pytest.mark.parametrize(("stage", "apply"), [
    ("Store Executor 1.1 Cue 1 /Source=Output /Use=Allforselected", False),
    ("Copy Cue 1 Executor 1.101 At Cue 2 Executor 1.1 /CueOnly", False),
    (OVERWRITE, False),
    (OVERWRITE, True),
    ("List Executor 1.101", True),
])
def test_replacement_timeout_at_each_write_boundary(context, stage, apply):
    c = context
    desk, calls = desk_link(c)
    send = c.link.send

    async def run():
        async def timeout(line, **kwargs):
            if line == stage and (line != "List Executor 1.101" or OVERWRITE in calls):
                if apply:
                    await send(line, **kwargs)
                else:
                    if before_write := kwargs.get("before_write"):
                        before_write()
                    calls.append(line)
                return False, "таймаут: результат неизвестен"
            return await send(line, **kwargs)

        c.cfg["scene_fade"] = 1.5
        desk.cues["1.101"][1] = {12: {"dim": 70}}
        desk.programmer = {12: {"dim": 25}}
        ws = session(c)
        old = c.cfg["scenes"][0]
        c.link.send = timeout
        result = await c.handle(ws, json.dumps(REPLACE))
        assert not result["ok"]
        assert calls[-1] == stage
        mutations = [
            "Fixture 12",
            "Store Executor 1.1 Cue 1 /Source=Output /Use=Allforselected",
            "Assign Cue 1 Executor 1.1 /Trig=Go",
            'Label Executor 1.1 "Replaced Cue"',
            "Copy Cue 1 Executor 1.101 At Cue 2 Executor 1.1 /CueOnly",
            OVERWRITE,
        ]
        final_write = OVERWRITE if stage == "List Executor 1.101" else stage
        sent = [line for line in calls if not line.startswith(("List", "Lua"))]
        assert sent == mutations[:mutations.index(final_write) + 1]
        print("mock write boundary", stage, apply, sent)
        assert desk.cues["1.101"][1] == {12: {"dim": 25 if apply else 70}}
        journal = Path(c.config_path).with_name("scene-write-1.101.json")
        committing = OVERWRITE in calls
        if committing:
            assert json.loads(journal.read_text())["phase"] == "committing"
        else:
            assert not journal.exists()

        c.link.send = send
        for name in ("scene_go", "scene_off"):
            before = len(calls)
            result = await c.handle(ws, json.dumps(intent(name, old, c.revision_token())))
            if committing:
                assert not result["ok"] and calls[before:] == []
            else:
                assert result["ok"]

    asyncio.run(run())


@pytest.mark.parametrize("crash_at", ["fence", "plan", "journal", "unlock"])
def test_interrupted_recovery_remains_blocked(tmp_path, monkeypatch, crash_at):
    path = tmp_path / "config.json"
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        old = panel.scene("s1")
    show = json.loads(path.read_bytes())["show"]
    journal = scene_recovery.journal_path(path, "1.101")
    generation = scene_recovery.generation_path(path, show, "1.101")
    # A pre-upgrade journal alone was sufficient to block playback.
    save_config(journal, {"show": show, "target": "1.101", "spare": "1.1",
                          "phase": "committing", "previous_identity": old["identity"]})
    unlink = Path.unlink

    def interrupt_save(destination, data, **kwargs):
        if (crash_at == "fence" and destination == generation and data["phase"] == "committing"
                or crash_at == "plan" and destination == path
                or crash_at == "unlock" and destination == generation and data["phase"] == "verified"):
            raise SystemExit("simulated process exit")
        save_config(destination, data, **kwargs)

    def interrupt_unlink(destination, *args, **kwargs):
        if crash_at == "journal" and destination == journal:
            raise SystemExit("simulated process exit")
        unlink(destination, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(scene_recovery, "save_config", interrupt_save)
        patch.setattr(Path, "unlink", interrupt_unlink)
        with pytest.raises(SystemExit):
            scene_recovery.recover_scene(path, show, "1.101", verified_label="Verified", fixtures=[12])
    if crash_at == "fence":
        assert not generation.exists()
    else:
        assert json.loads(generation.read_bytes())["phase"] == "committing"
    assert journal.exists() == (crash_at != "unlock")
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        for action in ("scene_go", "scene_off"):
            assert_refused(panel, mock, intent(action, panel.scene("s1"), panel.config["revision"]), "action_failed")
    assert scene_recovery.recover_scene(path, show, "1.101", verified_label="Verified", fixtures=[12]) != old["identity"]
    assert json.loads(generation.read_bytes())["phase"] == "verified"


def test_failed_final_listvar_does_not_quarantine_target(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    backup = "Copy Cue 1 Executor 1.101 At Cue 2 Executor 1.1 /CueOnly"
    reply = MockMA2._reply

    def fail_final_preflight(mock, line):
        if line == "ListVar" and mock.received[-2:-1] == [backup]:
            assert json.loads(scene_recovery.journal_path(path, "1.101").read_bytes())["phase"] == "preparing"
            return "Error #72: COMMAND NOT EXECUTED\r\n[Channel]>"
        return reply(mock, line)

    with monkeypatch.context() as patch:
        patch.setattr(MockMA2, "_reply", fail_final_preflight)
        with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
            panel = Panel(ws)
            old = panel.scene("s1")
            cue = dict(mock.cues["1.101"][1])
            assert panel.action({"a": "select_fixtures", "ids": [12]})["ok"]
            before = len(mock.received)
            result = panel.action(REPLACE)
            assert not result["ok"] and result["code"] == "show_pending"
            assert backup in mock.received[before:] and OVERWRITE not in mock.received[before:]
            assert mock.cues["1.101"][1] == cue
            print("mock preflight failure", mock.received[before:])
    assert not list(tmp_path.glob("scene-*.json"))
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        assert panel.scene("s1")["identity"] == old["identity"]
        for action in ("scene_go", "scene_off"):
            assert panel.action(intent(action, old, panel.config["revision"]))["ok"]
        assert panel.action({"a": "select_fixtures", "ids": [12]})["ok"]
        assert panel.action(REPLACE)["ok"]


@pytest.mark.parametrize("active", [False, True], ids=["archive-only", "archive-and-preparing"])
def test_archived_overwrite_fences_playback(tmp_path, active):
    path = tmp_path / "config.json"
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        row = panel.scene("s1")
        record = {"show": json.loads(path.read_bytes())["show"], "target": row["exec"],
                  "phase": "committing", "previous_identity": row["identity"], "spare": "1.1"}
        save_config(scene_recovery.archived_journal_path(path, row["exec"]), record)
        if active:
            save_config(scene_recovery.journal_path(path, row["exec"]), {**record, "phase": "preparing"})
        assert_journal_blocks(panel, mock, row)

    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        assert_journal_blocks(panel, mock, panel.scene("s1"))


def assert_journal_blocks(panel, mock, row, reason="pending_overwrite"):
    before = len(mock.received)
    results = [panel.action(intent(action, row, panel.config["revision"]))
               for action in ("scene_go", "scene_off")]
    print("mock journal fence", mock.received[before:])
    assert mock.received[before:] == []
    assert all(not result["ok"] and result["outcome"] == "failed"
               and result["command_evidence"] == [] and result["code"] == "action_failed"
               and result["params"] == {"executor": row["exec"], "reason": reason} for result in results)


def test_recovery_finds_archive_behind_preparing(tmp_path):
    path = tmp_path / "config.json"
    with mock_bridge(path):
        pass
    cfg = json.loads(path.read_bytes())
    row, show = cfg["scenes"][0], cfg["show"]
    ex = row["exec"]
    archive = scene_recovery.archived_journal_path(path, ex)
    journal = scene_recovery.journal_path(path, ex)
    record = {"show": show, "target": ex, "phase": "committing", "spare": "1.1",
              "previous_identity": row["identity"]}
    save_config(archive, record)
    save_config(journal, {**record, "phase": "preparing", "spare": "1.2"})
    identity = scene_recovery.recover_scene(path, show, ex, verified_label="Verified", fixtures=[12])
    assert identity != row["identity"]
    assert not journal.exists()
    assert archive.exists()
    recovered = json.loads(path.read_bytes())["scenes"][0]
    assert recovered["identity"] == identity and recovered["backup_exec"] == "1.1"
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        for action in ("scene_go", "scene_off"):
            assert_refused(panel, mock, intent(action, row, panel.config["revision"]), "scene_target_changed")
        assert_journal_playback(panel, mock, recovered)

    save_config(path, cfg)
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        assert_journal_blocks(panel, mock, row, "generation_mismatch")


def assert_journal_playback(panel, mock, row):
    before = len(mock.received)
    for action in ("scene_go", "scene_off"):
        assert panel.action(intent(action, row, panel.config["revision"]))["ok"]
    print("mock confirmed playback", mock.received[before:])
    assert playback_lines(mock, before) == [
        "Goto Cue 1 Executor 1.101 Fade 1.5", "Masterfade 1.5 Executor 1.101", "Off Executor 1.101",
    ]


def test_preparing_alone_does_not_fence_playback(tmp_path):
    path = tmp_path / "config.json"
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        row = panel.scene("s1")
        ex, show = row["exec"], json.loads(path.read_bytes())["show"]
        record = {"show": show, "target": ex, "phase": "preparing", "previous_identity": row["identity"]}
        save_config(scene_recovery.journal_path(path, ex), record)
        save_config(scene_recovery.archived_journal_path(path, ex), record)
        with pytest.raises(ValueError, match="Нет записи"):
            scene_recovery.recover_scene(path, show, ex, verified_label="Verified", fixtures=[12])
        assert_journal_playback(panel, mock, row)


def test_verified_generation_covers_only_confirmed_archives(tmp_path):
    path = tmp_path / "config.json"
    with mock_bridge(path):
        pass
    cfg = json.loads(path.read_bytes())
    row, show = cfg["scenes"][0], cfg["show"]
    ex = row["exec"]
    generation = scene_recovery.generation_path(path, show, ex)
    journal = scene_recovery.journal_path(path, ex)
    record = {"show": show, "target": ex, "phase": "committing", "previous_identity": row["identity"],
              "spare": "1.1"}
    save_config(journal.with_suffix(".json.verified"), record)
    save_config(journal.with_suffix(".json.second"), {**record, "phase": "completed", "spare": "1.2"})
    save_config(journal.with_suffix(".json.third"), {**record, "phase": "preparing"})

    recovered = scene_recovery.recover_scene(path, show, ex, verified_label="Verified", fixtures=[12])
    proof = json.loads(generation.read_bytes())
    assert proof["generation"] == recovered and len(proof["covered_archives"]) == 2
    assert "backup_exec" not in json.loads(path.read_bytes())["scenes"][0]
    # Covered archives remain harmless after a normal overwrite publishes another generation.
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        assert panel.action({"a": "select_fixtures", "ids": [12]})["ok"]
        assert panel.action(REPLACE)["ok"]
        replacement = json.loads(path.read_bytes())["scenes"][0]
        assert replacement["identity"] != recovered
        assert_journal_playback(panel, mock, replacement)

    # A valid proof for the current plan cannot cover a newly discovered archive.
    save_config(journal.with_suffix(".json.fourth"), {**record, "operation": "different"})
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        assert_journal_blocks(panel, mock, replacement)

    # A stale proof plus a historical plan must still respect the new archive.
    old_cfg = {**cfg, "scenes": [{**row, "identity": recovered, "cue_generation": recovered}, *cfg["scenes"][1:]]}
    save_config(path, old_cfg)
    save_config(generation, proof)
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        assert_journal_blocks(panel, mock, panel.scene("s1"))


def test_plan_with_missing_generation_remains_fenced(tmp_path):
    path = tmp_path / "config.json"
    with mock_bridge(path):
        pass
    cfg = json.loads(path.read_bytes())
    row = cfg["scenes"][0]
    row["cue_generation"] = row["identity"]
    save_config(path, cfg)
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        assert_journal_blocks(panel, mock, row, "generation_mismatch")


def test_unreadable_archive_fences_both_paths(tmp_path):
    path = tmp_path / "config.json"
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        row = panel.scene("s1")
        original = path.read_bytes()
        ex, show = row["exec"], json.loads(original)["show"]
        scene_recovery.archived_journal_path(path, ex).write_text("{")
        assert_journal_blocks(panel, mock, row, "invalid_recovery_record")
    with pytest.raises(ValueError):
        scene_recovery.recover_scene(path, show, ex, verified_label="Verified", fixtures=[12])
    assert path.read_bytes() == original


@pytest.mark.parametrize("failed_write", ["generation", "journal", "plan"])
def test_overwrite_stops_on_committing_save_error(tmp_path, monkeypatch, failed_write):
    path = tmp_path / "config.json"
    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        row = panel.scene("s1")
        show = json.loads(path.read_bytes())["show"]
        destinations = {
            "generation": scene_recovery.generation_path(path, show, row["exec"]),
            "journal": scene_recovery.journal_path(path, row["exec"]),
            "plan": path,
        }

        def fail_save(destination, data, **kwargs):
            if Path(destination) == destinations[failed_write] and (
                data.get("phase") == "committing"
                or any(scene.get("write_error") for scene in data.get("scenes", []))
            ):
                raise OSError("simulated critical save failure")
            save_config(destination, data, **kwargs)

        monkeypatch.setattr("ma2panel.bridge.save_config", fail_save)
        assert panel.action({"a": "select_fixtures", "ids": [12]})["ok"]
        cue = dict(mock.cues["1.101"][1])
        before = len(mock.received)
        result = panel.action(REPLACE)
        assert not result["ok"] and result["code"] == "plan_io"
        assert OVERWRITE not in mock.received[before:]
        assert mock.cues["1.101"][1] == cue
        print("mock critical save failure", failed_write, mock.received[before:])

    with mock_bridge(path) as (client, mock), client.websocket_connect("/ws") as ws:
        panel = Panel(ws)
        if failed_write == "generation":
            assert_journal_playback(panel, mock, row)
        else:
            assert_journal_blocks(panel, mock, row)
