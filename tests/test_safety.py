"""What the bridge may send to MA2: live light only in test mode, one explicit target per command, nothing on connect."""
import asyncio
import json
import time
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from bridge import HALTED, NO_LINK, UNKNOWN, MA2Link, create_app
from mock import start_mock
from safety import effective_safety, make_guard
from test_bridge import CONFIG, FULL, ask, bridge_cfg, ready, until, wait_state  # noqa: F401  (bridge_cfg is a fixture)

LIVE = {"safety": {"mode": "test", "allowed_fixtures": [12, 14], "allowed_scenes": ["1.101"]}}
LOGIN = 'login "panel" ""'


def cfg_for(tmp_path):
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["ma2"]["export_dir"] = str(tmp_path)
    return cfg


@contextmanager
def tabs(tmp_path, settings, n=2, password=""):
    path = tmp_path / "config.json"
    cfg = cfg_for(tmp_path)
    path.write_text(json.dumps(cfg, ensure_ascii=False))
    app = create_app(cfg, True, str(path), settings, password)
    with TestClient(app) as client:
        sockets = [client.websocket_connect("/ws").__enter__() for _ in range(n)]
        try:
            for ws in sockets:
                ready(ws)
            yield sockets, app.state.mock, client, path
        finally:
            for ws in sockets:
                ws.__exit__(None, None, None)


def test_connect_sends_only_login(bridge_cfg):
    with bridge_cfg(settings=LIVE) as (ws, mock, _):
        time.sleep(1.5)
        assert mock.received == [LOGIN, "ListVar"]  # only login and read-only show identification


def test_test_mode_blocks_stored_data_and_system(bridge_cfg):
    with bridge_cfg(settings=LIVE) as (ws, mock, _):
        for bad in ({"a": "store_scene", "id": "pianist"}, {"a": "scene_create", "label": "X", "page": 2},
                    {"a": "scene_rename", "id": "pianist", "label": "X"}, {"a": "page_save", "n": 2, "label": "X"},
                    {"a": "fixtures_fetch"}, {"a": "master", "v": 50},
                    {"a": "page_go", "n": 2}):
            r = ask(ws, bad)
            assert r["ok"] is False, bad
            assert ("перезапись существующей сцены отключена" if bad["a"] == "store_scene" else "заблокир") in r["err"], bad
        assert mock.received == [LOGIN, "ListVar"]
        assert ask(ws, {"a": "scene_go", "id": "pianist"})["ok"] is True
        assert mock.received[-1] == "Go Executor 1.101"


def test_nothing_allowed_by_default(bridge_cfg):
    with bridge_cfg(settings={}) as (ws, mock, _):
        assert ask(ws, {"a": "select_fixtures", "ids": [12]})["ok"] is False
        assert ask(ws, {"a": "scene_go", "id": "pianist"})["ok"] is False
        assert ask(ws, {"a": "blackout"})["ok"] is False
        assert mock.received == [LOGIN, "ListVar"]


def test_dim_has_explicit_target(bridge_cfg):
    with bridge_cfg(settings=LIVE) as (ws, mock, _):
        assert ask(ws, {"a": "select_fixtures", "ids": [12]})["ok"] is True
        assert mock.received == [LOGIN, "ListVar"]  # selecting touches nothing on the console
        ws.send_json({"a": "dim", "v": 30})
        until(ws, lambda m: m.get("shown", {}).get("12"))
        assert mock.received[-2:] == ["Fixture 12", "At 30"]


def test_fixture_outside_allowlist_refused(bridge_cfg):
    with bridge_cfg(settings=LIVE) as (ws, mock, _):
        assert ask(ws, {"a": "select_fixtures", "ids": [13]})["ok"] is False
        assert ask(ws, {"a": "select_group", "id": "potolok"})["ok"] is False
        assert ask(ws, {"a": "preset_go", "id": "p1"})["ok"] is False  # preset heads 12+14: allowed; p1 absent in test config
        assert mock.received == [LOGIN, "ListVar"]


def test_empty_selection_refused(bridge_cfg):
    with bridge_cfg(settings=LIVE) as (ws, mock, _):
        for action in ({"a": "dim", "v": 50}, {"a": "color", "r": 1, "g": 2, "b": 3}, {"a": "strobe", "v": 5},
                       {"a": "zoom", "v": 5}):
            ws.send_json(action)
            r = until(ws, lambda m: "ok" in m)
            assert r["ok"] is False and r["err"] == "ничего не выбрано"
        ask(ws, {"a": "select_fixtures", "ids": [12]})
        ask(ws, {"a": "clear"})
        ws.send_json({"a": "dim", "v": 50})
        assert until(ws, lambda m: "ok" in m)["ok"] is False
        time.sleep(0.5)
        assert mock.received == [LOGIN, "ListVar"]


def test_two_tabs_do_not_mix(tmp_path):
    with tabs(tmp_path, {"safety": {**LIVE["safety"]}, "rate_hz": 10}) as ((a, b), mock, _, _p):
        assert ask(a, {"a": "select_fixtures", "ids": [12]})["ok"] is True
        assert ask(b, {"a": "select_fixtures", "ids": [14]})["ok"] is True
        b.send_json({"a": "dim", "v": 30})
        a.send_json({"a": "dim", "v": 70})
        time.sleep(0.8)
        pairs = list(zip(mock.received[2:], mock.received[3:]))
        assert ("Fixture 14", "At 30") in pairs and ("Fixture 12", "At 70") in pairs
        assert not [p for p in pairs if p[0].startswith("Fixture") and p[1].startswith("At") and p not in
                    [("Fixture 14", "At 30"), ("Fixture 12", "At 70")]]


def test_value_queued_before_group_change_goes_to_old_group(tmp_path):
    with tabs(tmp_path, {"safety": {**LIVE["safety"]}, "rate_hz": 1}, n=1) as ((a,), mock, _, _p):
        ask(a, {"a": "select_fixtures", "ids": [12]})
        a.send_json({"a": "dim", "v": 40})
        ask(a, {"a": "select_fixtures", "ids": [14]})
        a.send_json({"a": "dim", "v": 60})
        time.sleep(1.5)
        assert mock.received[2:] == ["Fixture 12", "At 40", "Fixture 14", "At 60"]


def test_halt_stops_and_drops_queue(tmp_path):
    with tabs(tmp_path, {"safety": {**LIVE["safety"]}, "rate_hz": 1}, n=1) as ((a,), mock, _, _p):
        ask(a, {"a": "select_fixtures", "ids": [12]})
        a.send_json({"a": "dim", "v": 40})   # waits in the throttle
        assert ask(a, {"a": "halt"})["ok"] is True
        time.sleep(1.5)
        assert mock.received == [LOGIN, "ListVar"]      # the queued value never left, nothing else was sent either
        for action in ({"a": "scene_go", "id": "pianist"}, {"a": "blackout"}, {"a": "select_fixtures", "ids": [12]}):
            r = ask(a, action)
            assert r["ok"] is False and r["err"] == HALTED
        a.send_json({"a": "dim", "v": 50})
        assert until(a, lambda m: "ok" in m)["err"] == HALTED
        assert mock.received == [LOGIN, "ListVar"]
        assert ask(a, {"a": "resume"})["ok"] is True
        ask(a, {"a": "select_fixtures", "ids": [12]})
        a.send_json({"a": "dim", "v": 50})
        time.sleep(1.5)
        assert mock.received[2:] == ["Fixture 12", "At 50"]  # the dim 40 from before the halt did not come back


def test_halt_is_not_blackout(tmp_path):
    with tabs(tmp_path, {"safety": {**LIVE["safety"]}}, n=1) as ((a,), mock, _, _p):
        ask(a, {"a": "halt"})
        assert mock.received == [LOGIN, "ListVar"]


def test_origin_of_other_site_refused(tmp_path):
    app = create_app(cfg_for(tmp_path), True, str(tmp_path / "c.json"), LIVE)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws", headers={"origin": "http://evil.example"}) as ws:
                ws.receive_json()
        with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
            assert "status" in ws.receive_json()


def test_stop_endpoint_is_local_and_needs_header(tmp_path):
    app = create_app(cfg_for(tmp_path), True, str(tmp_path / "c.json"), LIVE)
    with TestClient(app) as client:
        assert client.post("/api/stop").status_code == 403
        assert client.post("/api/stop", headers={"x-stop": "1"}).status_code == 403  # not from loopback


def test_password_stays_out(tmp_path, caplog):
    caplog.set_level("DEBUG")
    cfg = cfg_for(tmp_path)
    cfg["ma2"]["password"] = "oldSecretInConfig"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg))
    app = create_app(cfg, True, str(path), LIVE, password="s3cr3tPW")
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        msgs = [ws.receive_json() for _ in range(3)]
        until(ws, lambda m: m.get("status", {}).get("ma2") == "logged_in")
        ask(ws, {"a": "layout_save", "pos": [{"id": 12, "x": 0.1, "y": 0.2}]})
        assert f'login "panel" "s3cr3tPW"' in app.state.mock.received
        assert "/api/log" and "s3cr3tPW" not in json.dumps(client.get("/api/log").json())
    assert "s3cr3tPW" not in json.dumps(msgs) and "s3cr3tPW" not in caplog.text and "oldSecretInConfig" not in caplog.text
    assert "s3cr3tPW" not in path.read_text() and "oldSecretInConfig" not in path.read_text()


def test_no_browser_storage_applied_to_console():
    from pathlib import Path
    import re
    for f in Path("static").glob("*"):
        if f.suffix in (".js", ".html"):
            text = f.read_text(encoding="utf-8")
            assert "sessionStorage" not in text, f
            # Only which section and which picker tab this device showed last, and grid snap; nothing that reaches the console.
            assert set(re.findall(r"localStorage\.\w+\('([^']*)'", text)) <= {"ma2.sec", "ma2.pick", "ma2.snap"}, f
            assert text.count("localStorage") == len(re.findall(r"localStorage\.\w+\('ma2\.(?:sec|pick|snap)'", text)), f


FORBIDDEN = ["Store Group 101", "Store Preset 4.1", "StoreLook Executor 1.101 Cue 1", "Delete Group 101", "Delete Fixture 12",
             "SaveShow", "LoadShow", "Clear", "Oops", "Assign Group 101 At Executor 1.1", "Macro 1", "Go Macro 1",
             "Patch", "Fixture 12 Thru 14", "Fixture 13", "Fixture 12 + 13", "Off Executor 1.102", "Go Executor 9.9",
             "Label Executor 1.101 \"x\"", "Copy Group 1 At 2", "Import x", "Export Fixture 1", "Login \"a\" \"b\"",
             "Master 2.1 At 50", "Page 2", "At 50; ClearAll", "At 50\r\nClearAll", "At 50\nClearAll", "At 50 ", " At 50",
             "Attribute \"Dimmer\" At 5", "Attribute \"Pan\" At x", "Fixture 12 + ", "Select Fixture 12", "Delete"]
ALLOWED = ["Fixture 12", "Fixture 12 + 14", "At 50", "At 12.5", "At 50 Fade 3", "Go Executor 1.101", "Off Executor 1.101",
           'Attribute "ColorRGB1" At 50', 'Attribute "Pan" At -270', 'Attribute "Tilt" At 12.5 Fade 2', "List Executor 1.1 Thru 1.250",
           "List Group", "Group 101", "ClearAll"]  # v4: explicit imported MA2 group selection is supported


@pytest.mark.parametrize("line", FORBIDDEN)
def test_guard_blocks(line):
    assert make_guard(effective_safety(LIVE))(line), line


@pytest.mark.parametrize("line", ALLOWED)
def test_guard_allows(line):
    assert make_guard(effective_safety(LIVE))(line) is None, line


def test_guard_store_mode_is_one_slot():
    guard = make_guard(effective_safety({"safety": {"mode": "store", "store_execs": ["2.150"]}}))
    assert guard("StoreLook Executor 2.150 Cue 1 /Source=Output") is None and guard('Label Executor 2.150 "Рояль"') is None
    assert guard("StoreLook Executor 2.150 Cue 1 /Source=Output /Overwrite")
    assert guard("StoreLook Executor 1.101 Cue 1 /Source=Output") and guard("SaveShow")


def test_store_mode_needs_named_empty_slot(bridge_cfg):
    settings = {"safety": {"mode": "store", "store_execs": ["2.150", "1.101"]}}
    with bridge_cfg(settings=settings) as (ws, mock, _):
        create = {"a": "scene_create", "label": "Тест", "page": 2, "exec": "2.150"}
        assert ask(ws, create)["ok"] is False                                   # no confirmation
        assert ask(ws, {**create, "confirm": "2.151"})["ok"] is False           # confirmation names another place
        assert ask(ws, {**create, "exec": "2.151", "confirm": "2.151"})["ok"] is False  # not in store_execs
        assert ask(ws, {**create, "exec": "1.101", "confirm": "1.101"})["err"].endswith("запрещена")  # occupied
        assert mock.received == [LOGIN, "ListVar", "List Executor 1.101"]
        assert ask(ws, {**create, "confirm": "2.150"})["ok"] is True
        assert mock.received[3:] == ["List Executor 2.150", "StoreLook Executor 2.150 Cue 1 /Source=Output",
                                     'Label Executor 2.150 "Тест"']
        assert ask(ws, {"a": "store_scene", "id": "pianist", "confirm": "1.101"})["ok"] is False  # occupied: never overwritten
        assert not [r for r in mock.received if "SaveShow" in r or "Overwrite" in r]


def run_link(coro_fn, **kw):
    async def go():
        mock = await start_mock(0, "panel")
        link = MA2Link("127.0.0.1", mock.port, "panel", "", lambda s: None, **kw)
        task = asyncio.create_task(link.run())
        await wait_state(link, "logged_in", 3)
        try:
            await coro_fn(mock, link)
        finally:
            task.cancel()
    asyncio.run(go())


def test_no_prompt_is_not_success():
    async def body(mock, link):
        mock.no_prompt = True
        ok, reply = await link.send("Go Executor 1.101")
        assert (ok, reply) == (False, UNKNOWN)
    run_link(body)


def test_no_prompt_lenient_mode():
    async def body(mock, link):
        mock.no_prompt = True
        assert (await link.send("Go Executor 1.101"))[0] is True
    run_link(body, require_prompt=False)


def test_timeout_is_not_replayed():
    async def body(mock, link):
        mock.mute = True
        ok, reply = await link.send("Go Executor 1.101")
        assert (ok, reply) == (False, UNKNOWN)
        mock.mute = False
        await asyncio.sleep(1.5)
        assert mock.received.count("Go Executor 1.101") == 1  # sent once, never retried
    run_link(body)


def test_line_queued_before_a_drop_never_runs_after_it():
    async def body(mock, link):
        gen = link._gen
        mock.drop()
        await wait_state(link, "down", 2)
        await wait_state(link, "logged_in", 5)
        assert await link.send("At 100", gen=gen) == (False, NO_LINK)
        assert "At 100" not in mock.received
    run_link(body)


def test_halted_link_sends_nothing():
    async def body(mock, link):
        link.halted = True
        assert await link.send("At 100") == (False, HALTED)
        assert mock.received == [LOGIN, "ListVar"]  # login check only
    run_link(body)


def test_value_line_needs_fixture_in_same_action():
    async def body(mock, link):
        assert (await link.send("At 100"))[0] is False and (await link.send('Attribute "Pan" At 5'))[0] is False
        assert mock.received == [LOGIN, "ListVar"]
        link.new_action()
        assert (await link.send("Fixture 12"))[0] is True and (await link.send("At 100"))[0] is True
        link.new_action()
        assert (await link.send("At 50"))[0] is False  # the next action starts without a target
    run_link(body)


def test_guard_mapped_and_relative():
    guard = make_guard(effective_safety(LIVE), ["Yaw"])
    assert guard('Attribute "Yaw" At + 2') is None
    assert guard('Attribute "Yaw" At - 1.5') is None
    assert guard('Attribute "Yaw" At -20 Fade 2') is None
    assert guard('Attribute "Pan" At 20')
    assert guard('Attribute "Yaw" At +2')


def test_guard_empty_mapping_rejects_empty_name():
    assert make_guard(effective_safety(LIVE), [])('Attribute "" At 2')


@pytest.mark.parametrize("mode", ["test", "store", "full"])
def test_guard_refuses_overwrite_in_every_mode(mode):
    guard = make_guard(effective_safety({"safety": {"mode": mode, "store_execs": ["2.150"],
                                                   "extra_allowed_regex": [".*"]}}))
    assert guard("StoreLook Executor 2.150 Cue 1 /Source=Output /Overwrite")


def test_guard_allows_attribute_names_added_later():
    """Spec 24: names read from fixture type exports join the live set the guard was made with."""
    names = {"Pan"}
    guard = make_guard(effective_safety({"safety": {"mode": "test", "allowed_fixtures": [1], "allowed_scenes": []}}), names)
    assert guard('Attribute "SHUTTER" At 50')
    names.add("SHUTTER")
    assert guard('Attribute "SHUTTER" At 50') is None
