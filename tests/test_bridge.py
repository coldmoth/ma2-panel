import asyncio
import json
import re
import time
from pathlib import Path
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from ma2panel.bridge import PROMPT, MA2Link, clean, Throttle, create_app
from ma2panel.mock import start_mock

CONFIG = "tests/config.test.json"  # not the live config.json: the owner edits that one in the hall
FULL = {"safety": {"mode": "full"}, "poll_seconds": 0}


def test_throttle_keeps_last():
    sent = []
    async def send(k, act): sent.append(act["v"])
    async def go():
        t = Throttle(10, send); task = asyncio.create_task(t.run())
        for v in range(50): t.put("dim", {"a": "dim", "v": v})   # «два планшета» = один ключ
        await asyncio.sleep(0.25); task.cancel()
    asyncio.run(go())
    assert sent == [49]

def test_throttle_clear():
    sent = []
    async def send(k, act): sent.append(act)
    async def go():
        t = Throttle(10, send); t.put("dim", {"a": "dim", "v": 1}); t.clear()
        task = asyncio.create_task(t.run()); await asyncio.sleep(0.25); task.cancel()
    asyncio.run(go())
    assert sent == []

def test_throttle_survives_failed_send():
    sent = []
    async def send(k, act):
        if act == "boom": raise RuntimeError("ws closed")
        sent.append(act)
    async def go():
        t = Throttle(20, send); task = asyncio.create_task(t.run())
        t.put("dim", "boom"); await asyncio.sleep(0.15)
        t.put("dim", "next"); await asyncio.sleep(0.15); task.cancel()
    asyncio.run(go())
    assert sent == ["next"]

async def wait_state(link, state, timeout):
    for _ in range(int(timeout * 20)):
        if link.state == state:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"{link.state} != {state}")

async def connect(user="panel"):
    mock = await start_mock(0, user)
    link = MA2Link("127.0.0.1", mock.port, "panel", "", lambda s: None)
    return mock, link, asyncio.create_task(link.run())

def test_login_and_send():
    async def go():
        mock, link, task = await connect()
        await wait_state(link, "logged_in", 2)
        ok, reply = await link.send("Go Executor 1.101")
        assert ok and "Go Executor 1.101" in mock.received
        task.cancel()
    asyncio.run(go())

def test_login_failed():
    async def go():
        mock, link, task = await connect(user="other")
        await wait_state(link, "login_failed", 3)
        task.cancel()
    asyncio.run(go())

def test_drop_reconnect():
    async def go():
        mock, link, task = await connect()
        await wait_state(link, "logged_in", 2)
        mock.drop()
        await wait_state(link, "down", 1)
        assert await link.send("Go Executor 1.102") == (False, "нет связи с пультом")
        await wait_state(link, "logged_in", 4)
        assert "Go Executor 1.102" not in mock.received
        task.cancel()
    asyncio.run(go())

def test_paused_mock_is_not_connected():
    async def go():
        mock = await start_mock(0, "panel"); mock.paused = True
        link = MA2Link("127.0.0.1", mock.port, "panel", "", lambda s: None)
        task = asyncio.create_task(link.run())
        await asyncio.sleep(0.5)
        assert link.state == "down"
        mock.paused = False
        await wait_state(link, "logged_in", 4)
        task.cancel()
    asyncio.run(go())


@pytest.fixture
def bridge_cfg(tmp_path):
    @contextmanager
    def start(edit=lambda cfg: None, settings=FULL, confirmed_profiles=False, mock_setup=None):
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["show"] = "Mock show"  # control tests have an explicitly bound show
        cfg["ma2"]["port"] = 30000  # mock on a free port
        cfg["ma2"]["export_dir"] = str(tmp_path)
        edit(cfg)
        path = tmp_path / "config.json"
        path.write_text(json.dumps(cfg, ensure_ascii=False))
        from unittest.mock import patch
        from ma2panel import bridge as module
        initial = json.loads(json.dumps(cfg))
        captured = []
        register = module.register_api
        def capture(app, c, local):
            captured.append(c)
            return register(app, c, local)
        original_start = module.start_mock
        async def configured_start(*args, **kwargs):
            mock = await original_start(*args, **kwargs)
            if mock_setup:
                mock_setup(mock)
            return mock
        with patch.object(module, 'register_api', capture), patch.object(module, 'start_mock', configured_start):
            app = create_app(cfg, mock=True, config_path=str(path), settings={"poll_seconds": 0, **settings})
        with patch.object(module, "start_mock", configured_start), TestClient(app) as client, client.websocket_connect("/ws") as ws:
            ready(ws)
            if confirmed_profiles:
                # Inject current profile evidence for tests of DMX transport/control, not profile discovery.
                def confirm():
                    c = captured[0]
                    for f, original in zip(c.cfg['fixtures'], initial['fixtures']):
                        f['footprint'] = original.get('footprint', original.get('channels', 1))
                    c.cfg['dmx_map'] = initial.get('dmx_map', {})
                    c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
                    for session in c.sessions.values():
                        session['legacy_revision'] = c.revision_token()
                client.portal.call(confirm)
            yield ws, app.state.mock, path
    return start

@pytest.fixture
def bridge(bridge_cfg):
    with bridge_cfg() as b:
        yield b

def until(ws, pred):
    while not pred(m := ws.receive_json()):
        pass
    return m

def ready(ws):
    """Wait for logged_in AND the connect-time status/config/shown trio: when login finishes before the socket opens,
    the first status is already logged_in and the stale connect-time config would be read as a later broadcast."""
    seen = set()
    while seen != {"in", "shown"}:
        m = ws.receive_json()
        if m.get("status", {}).get("ma2") == "logged_in":
            seen.add("in")
        if "shown" in m:
            seen.add("shown")

def ask(ws, msg):
    ws.send_text(msg) if isinstance(msg, str) else ws.send_json(msg)
    return until(ws, lambda m: "ok" in m)

def confirm_fixture_import(ws, result):
    """Explicit same-ID operator choice for export tests using legacy fixtures."""
    if not result.get('ambiguous'):
        return result
    choices = {}
    for item in result['ambiguous']:
        fid = item['new_id']
        assert fid in {candidate['old_id'] for candidate in item['candidates']}
        choices[str(fid)] = fid
    return ask(ws, {'a': 'import_confirm_merge', 'request_token': result['request_token'], 'choices': choices})


def test_ws_config_hides_secrets(tmp_path):
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["ma2"]["port"] = 30000
    with TestClient(create_app(cfg, True, str(tmp_path / "c.json"), FULL)) as client, client.websocket_connect("/ws") as ws:
        conf = until(ws, lambda m: "config" in m)["config"]
    assert "pin" not in conf and "ma2" not in conf and conf["groups"] and conf["plan"]

def test_ws_store(bridge):
    ws, mock, _ = bridge
    r = ask(ws, {"a": "store_scene", "id": "pianist"})
    assert r["ok"] is False and "перезапись существующей сцены отключена" in r["err"]
    assert not any("StoreLook" in line for line in mock.received)

def test_ws_shown(bridge):
    ws, mock, _ = bridge
    assert ask(ws, {"a": "select_group", "id": "front"})["ok"] is True
    ws.send_json({"a": "color", "r": 100, "g": 0, "b": 0})
    m = until(ws, lambda m: m.get("shown"))
    assert set(m["shown"]) == {"12", "14"} and m["shown"]["12"]["rgb"] == [100, 0, 0] and m["tracked"] is True
    assert "dim" not in m["shown"]["12"]  # a colour alone never shows a brightness the panel did not send
    ws.send_json({"a": "blackout"})
    shown = until(ws, lambda m: "shown" in m)["shown"]
    assert shown == {}  # The barrier invalidates evidence; it never clears the desk Programmer.

def test_ws_layout_save(bridge):
    ws, _, path = bridge
    assert ask(ws, {"a": "layout_save", "pos": [{"id": 12, "x": 0.1, "y": 0.2}]})["ok"] is True
    f12 = next(f for f in json.loads(path.read_text())["fixtures"] if f["id"] == 12)
    assert (f12["x"], f12["y"]) == (0.1, 0.2)
    assert ask(ws, {"a": "layout_save", "pos": [{"id": 12, "x": None, "y": None}]})["ok"] is True
    f12 = next(f for f in json.loads(path.read_text())["fixtures"] if f["id"] == 12)
    assert "x" not in f12 and "y" not in f12

def test_ws_garbage(bridge):
    ws, mock, path = bridge
    before = path.read_bytes()
    for bad in ("not json", "[1]", {"a": [1]}, {"a": "dim", "v": "50; ClearAll"},
                {"a": "layout_save", "pos": [{"id": 12, "x": 5, "y": 0}]}, {"a": "select_group", "id": "nope"}):
        assert ask(ws, bad)["ok"] is False
    assert ask(ws, {"a": "scene_go", "id": "pianist"})["ok"] is True
    assert [r for r in mock.received if "ClearAll" in r] == [] and path.read_bytes() == before  # only the scene's own


def test_ws_import(bridge_cfg):
    with bridge_cfg(settings={"safety": {"mode": "full", "allow_fixture_read": True}}) as b:
        check_ws_import(b)


def check_ws_import(bridge):
    ws, mock, path = bridge
    before = path.read_bytes()
    preview = ask(ws, {"a": "fixtures_fetch"})
    assert not preview["ok"] and preview["ambiguous"]
    assert path.read_bytes() == before
    choices = {str(item["new_id"]): item["new_id"] for item in preview["ambiguous"]}
    ws.send_json({"a": "import_confirm_merge", "request_token": preview["request_token"], "choices": choices})
    msg = until(ws, lambda m: "config" in m)
    conf = msg["config"]
    assert until(ws, lambda m: "ok" in m)["source"] == "ma2"
    saved = json.loads(path.read_text())
    assert conf["fixtures"] == saved["fixtures"]
    assert next(f for f in saved["fixtures"] if f["id"] == 99)["label"] == "New"
    assert any(c.startswith(json.loads((path.parent / "settings.json").read_text())["ma2"]["export_cmd"][:-1] + "_") for c in mock.received)  # one-off file name per export


def test_ws_import_bad_xml(bridge_cfg):
    with bridge_cfg(settings={"safety": {"mode": "full", "allow_fixture_read": True}}) as b:
        check_ws_import_bad_xml(b)


def check_ws_import_bad_xml(bridge):
    ws, mock, path = bridge
    before = path.read_bytes()
    mock.export_text = "<x"
    assert ask(ws, {"a": "fixtures_fetch"})["ok"] is False
    assert path.read_bytes() == before
    mock.export_text = None
    preview = ask(ws, {"a": "fixtures_fetch"})
    assert not preview["ok"] and preview["ambiguous"]
    choices = {str(item["new_id"]): None for item in preview["ambiguous"]}
    assert ask(ws, {"a": "import_confirm_merge", "request_token": preview["request_token"], "choices": choices})["ok"]


def test_throttle_flush():
    sent = []
    async def send(k, act): sent.append(act)
    async def go():
        t = Throttle(10, send); t.put("move", {"x": 1})
        await t.flush("move"); await t.flush("move")
    asyncio.run(go())
    assert sent == [{"x": 1}]


def saved(path):
    return json.loads(path.read_text())


def attr_lines(mock):
    return [r for r in mock.received if r.startswith("Attribute")]


def test_ws_move(bridge):
    ws, mock, _ = bridge
    assert ask(ws, {"a": "select_group", "id": "front"})["ok"] is True
    assert ask(ws, {"a": "aim", "pan": 0, "tilt": 0})["ok"]
    assert ask(ws, {"a": "move_start"})["ok"] is True
    ws.send_json({"a": "move", "dx": 5, "dy": 0})
    ws.send_json({"a": "move", "dx": 20, "dy": -10})
    m = until(ws, lambda m: m.get("shown", {}).get("12", {}).get("pan") == 70)
    assert mock.received[-3:] == ["Fixture 12 + 14", 'Attribute "Pan" At 108', 'Attribute "Tilt" At -27']
    assert m["shown"]["12"] == m["shown"]["14"] == {"pan": 70, "tilt": 40}


def test_ws_move_flush(bridge):
    ws, mock, _ = bridge
    ask(ws, {"a": "select_group", "id": "front"})
    assert ask(ws, {"a": "aim", "pan": 0, "tilt": 0})["ok"]
    ask(ws, {"a": "move_start"})
    ws.send_json({"a": "move", "dx": 10, "dy": 0})
    assert ask(ws, {"a": "move_start"})["ok"] is True
    ws.send_json({"a": "move", "dx": 10, "dy": 0})
    m = until(ws, lambda m: m.get("shown", {}).get("12", {}).get("pan") == 70)
    assert m["shown"]["12"]["pan"] == 70


def test_ws_move_no_heads(bridge):
    ws, mock, _ = bridge
    ask(ws, {"a": "select_fixtures", "ids": [5]})
    r = ask(ws, {"a": "move_start"})
    assert r["ok"] is False and r["err"].startswith("нет подвижных приборов: отметьте головы")
    ws.send_json({"a": "zoom", "v": 50})
    assert until(ws, lambda m: "ok" in m)["ok"] is False
    assert not attr_lines(mock)


def test_ws_move_before_start(bridge):
    ws, mock, _ = bridge
    ask(ws, {"a": "select_group", "id": "front"})
    ws.send_json({"a": "move", "dx": 10, "dy": 0})
    assert until(ws, lambda m: "ok" in m) == {"ok": False, "a": "move", "err": "нет move_start"}
    assert ask(ws, {"a": "scene_go", "id": "pianist"})["ok"] is True


def move_front(ws):
    ask(ws, {"a": "select_group", "id": "front"})
    assert ask(ws, {"a": "aim", "pan": 0, "tilt": 0})["ok"]
    ask(ws, {"a": "move_start"})
    ws.send_json({"a": "move", "dx": 20, "dy": -10})
    until(ws, lambda m: m.get("shown", {}).get("12", {}).get("pan") == 70)


def test_ws_preset(bridge):
    ws, mock, path = bridge
    move_front(ws)
    assert ask(ws, {"a": "preset_save", "label": "Рояль"})["ok"] is True
    presets = saved(path)["presets"]
    assert [p["id"] for p in presets] == ["p1"] and presets[0]["pos"]["12"] == {"pan": 70, "tilt": 40}
    assert ask(ws, {"a": "preset_save", "label": " Рояль "})["ok"] is True
    assert len(saved(path)["presets"]) == 1
    ask(ws, {"a": "clear"})
    n = len(mock.received)
    assert ask(ws, {"a": "preset_go", "id": "p1"})["ok"] is True
    assert mock.received[n:] == ["Fixture 12 + 14", 'Attribute "Pan" At 108', 'Attribute "Tilt" At -27']
    assert ask(ws, {"a": "preset_delete", "id": "p1"})["ok"] is True
    assert saved(path)["presets"] == []


def test_ws_preset_missing(bridge_cfg):
    def edit(cfg):
        next(f for f in cfg["fixtures"] if f["id"] == 14)["missing"] = True
        cfg["presets"] = [{"id": "p1", "label": "Рояль",
                           "pos": {"12": {"pan": 70, "tilt": 40}, "14": {"pan": 10, "tilt": 10}}}]
    with bridge_cfg(edit) as (ws, mock, _):
        n = len(mock.received)
        assert ask(ws, {"a": "preset_go", "id": "p1"})["ok"] is True
        assert mock.received[n:] == ["Fixture 12", 'Attribute "Pan" At 108', 'Attribute "Tilt" At -27']


def test_ws_preset_needs_aim(bridge):
    ws, mock, path = bridge
    ask(ws, {"a": "select_group", "id": "front"})
    assert ask(ws, {"a": "preset_save", "label": "Рояль"})["err"] == "сначала наведите головы"


def test_ws_groups(bridge):
    ws, mock, path = bridge
    assert ask(ws, {"a": "group_save", "label": "Мои", "ids": [12, 5]})["ok"] is True
    g1 = next(g for g in saved(path)["groups"] if g["id"] == "g1")
    assert g1 == {"id": "g1", "label": "Мои", "fixtures": [12, 5]}
    assert ask(ws, {"a": "select_group", "id": "g1"})["ok"] is True
    ws.send_json({"a": "dim", "v": 40})
    until(ws, lambda m: m.get("shown", {}).get("5"))
    assert mock.received[-2:] == ["Fixture 12 + 5", "At 40"]
    assert ask(ws, {"a": "group_delete", "id": "front"}) == {"ok": False, "a": "group_delete",
                                                             "err": "группа из пульта"}
    assert ask(ws, {"a": "group_delete", "id": "g1"})["ok"] is True
    assert "g1" not in [g["id"] for g in saved(path)["groups"]]


def test_ws_beam(bridge):
    ws, mock, path = bridge
    assert ask(ws, {"a": "beam_home", "id": 12})["ok"] is False
    move_front(ws)
    assert ask(ws, {"a": "beam_home", "id": 12})["ok"] is True
    beam = next(f for f in saved(path)["fixtures"] if f["id"] == 12)["beam"]
    assert beam["home"] == 70
    assert ask(ws, {"a": "beam_invert", "id": 12})["ok"] is True
    assert next(f for f in saved(path)["fixtures"] if f["id"] == 12)["beam"]["invert"] is not beam["invert"]
    assert ask(ws, {"a": "beam_home", "id": 5})["ok"] is False


V2 = [{"a": "move_start"}, {"a": "move", "dx": 1, "dy": 1}, {"a": "zoom", "v": 50}, {"a": "focus", "v": 50},
      {"a": "preset_save", "label": "x"}, {"a": "preset_go", "id": "p1"}, {"a": "preset_delete", "id": "p1"},
      {"a": "group_save", "label": "x", "ids": [12]}, {"a": "group_delete", "id": "front"},
      {"a": "beam_home", "id": 12}, {"a": "beam_invert", "id": 12}]


def test_ws_v2_garbage(bridge):
    ws, mock, path = bridge
    before = path.read_bytes()
    ask(ws, {"a": "select_group", "id": "front"})
    for bad in ({"a": "move", "dx": "5; ClearAll", "dy": 0}, {"a": "move", "dx": 500, "dy": 0},
                {"a": "zoom", "v": "1; ClearAll"}, {"a": "preset_go", "id": "nope"},
                {"a": "preset_delete", "id": "nope"}, {"a": "group_save", "label": "x", "ids": [99]},
                {"a": "group_save", "label": "x", "ids": "12"}, {"a": "preset_save", "label": ""},
                {"a": "group_save", "label": "x" * 31, "ids": [12]}, {"a": "group_delete", "id": "nope"},
                {"a": "beam_invert", "id": "12"}):
        assert ask(ws, bad)["ok"] is False, bad
    assert ask(ws, {"a": "scene_go", "id": "pianist"})["ok"] is True
    assert [r for r in mock.received if "ClearAll" in r] == [] and path.read_bytes() == before  # only the scene's own


def test_ws_move_lands_before_next_action(bridge):
    ws, mock, path = bridge
    ask(ws, {"a": "select_group", "id": "front"})
    assert ask(ws, {"a": "aim", "pan": 0, "tilt": 0})["ok"]
    ask(ws, {"a": "move_start"})
    ws.send_json({"a": "move", "dx": 20, "dy": -10})
    assert ask(ws, {"a": "preset_save", "label": "Рояль"})["ok"] is True  # the move is still in the throttle
    assert saved(path)["presets"][0]["pos"]["12"] == {"pan": 70, "tilt": 40}
    ask(ws, {"a": "move_start"})
    ws.send_json({"a": "move", "dx": 10, "dy": 0})
    assert ask(ws, {"a": "blackout"})["ok"] is True
    tail = mock.received[-4:]  # Blackout cancels pending moves instead of flushing them
    assert "SpecialMaster 2.1 At 0" in tail and mock.grand_master == 0
    time.sleep(0.5)  # > 1/rate_hz: nothing is left in the throttle to resurrect shown
    assert ask(ws, {"a": "scene_go", "id": "pianist", "blackout_epoch": 1})["ok"] is True
    assert not [r for r in mock.received[-3:] if "Pan" in r]


def test_ws_zoom_lands_before_selection(bridge):
    ws, mock, _ = bridge
    ask(ws, {"a": "select_fixtures", "ids": [12]})
    ws.send_json({"a": "zoom", "v": 80})
    ws.send_json({"a": "select_fixtures", "ids": [14]})  # the zoom is still in the throttle
    m = until(ws, lambda m: "shown" in m or "ok" in m)
    assert m["shown"] == {"12": {"zoom": 80}}  # zoom went to 12 before the selection moved on


def test_prompt_ends_reply():
    assert PROMPT.search(clean(b"OK\r\n[Channel]>")) and PROMPT.search(clean(b"\x1b[32m[Fixture]>\x1b[0m "))
    assert PROMPT.search(clean(b"\x1b[32m[Group]>\x1b[37m\x1b[K"))  # MA2 3.9.60.68 as seen on site
    assert not PROMPT.search(b"[Channel]> Attribute") and not PROMPT.search(b"OK\r\n")

def test_ws_scenes_import_and_create(bridge):
    ws, mock, path = bridge
    r = ask(ws, {"a": "scenes_import"})
    assert r["ok"] is True and r["added"] == 1  # 1.101 Pianist is already in the config, 1.102 is new
    assert ask(ws, {"a": "select_fixtures", "ids": [12]})["ok"]
    r = ask(ws, {"a": "scene_create", "label": "Рояль", "page": 2, "exec": "2.101", "confirm": "2.101"})
    assert r["ok"] is True
    assert "Store Executor 2.101 Cue 1 /Source=Output /Use=Allforselected" in mock.received
    scenes = json.loads(path.read_text())["scenes"]
    assert [s["exec"] for s in scenes] == ["1.101", "1.102", "2.101"]
    assert ask(ws, {"a": "scene_create", "label": 'a"b', "page": 1})["ok"] is False

def test_ws_page(bridge):
    ws, mock, path = bridge
    assert ask(ws, {"a": "page_go", "n": 3})["ok"] is True
    assert mock.received[-1] == "Page 3"
    assert ask(ws, {"a": "page_save", "n": 3, "label": "Концерт"})["ok"] is True
    assert mock.received[-1] == 'Label Page 3 "Концерт"'
    assert json.loads(path.read_text())["pages"] == [{"n": 3, "label": "Концерт"}]
    assert ask(ws, {"a": "page_go", "n": 0})["ok"] is False

def test_journal(tmp_path):
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["ma2"]["port"] = 30000
    with TestClient(create_app(cfg, True, str(tmp_path / "c.json"), FULL)) as client, client.websocket_connect("/ws") as ws:
        until(ws, lambda m: m.get("status", {}).get("ma2") == "logged_in")
        ask(ws, {"a": "scene_go", "id": "pianist"})
        entry = client.get("/api/log").json()[0]
    assert entry["a"] == "scene_go" and entry["what"] == {"id": "pianist"} and entry["ok"] is True

def test_ws_scene_rename_delete(bridge):
    ws, mock, path = bridge
    assert ask(ws, {"a": "scene_rename", "id": "pianist", "label": "Рояль"})["ok"] is True
    assert mock.received[-1] == 'Label Executor 1.101 "Рояль"'
    assert ask(ws, {"a": "scene_rename", "id": "pianist", "label": 'a"b'})["ok"] is False
    scene = json.loads(path.read_text())["scenes"][0]
    assert scene["label"] == "Рояль" and scene["named"] is True  # the tile shows only names set from the panel
    assert ask(ws, {"a": "scene_delete", "id": "pianist"})["ok"] is True
    assert json.loads(path.read_text())["scenes"] == [] and not any(l.startswith("Delete") for l in mock.received)


def test_scene_delete_on_the_desk(bridge_cfg):
    with bridge_cfg(settings=FULL) as (ws, mock, path):
        assert ask(ws, {"a": "scene_delete", "id": "pianist", "desk": True})["ok"] is True
        assert mock.received[-1] == "Delete Executor 1.101" and json.loads(path.read_text())["scenes"] == []
    with bridge_cfg(settings={"safety": {"mode": "test", "allowed_scenes": ["1.101"]}}) as (ws, mock, path):  # test mode: the desk keeps it and so does the panel
        assert ask(ws, {"a": "scene_delete", "id": "pianist", "desk": True})["ok"] is False
        assert json.loads(path.read_text())["scenes"] and not any(l.startswith("Delete") for l in mock.received)

def test_scene_overwrite(bridge_cfg):
    with bridge_cfg(settings=FULL) as (ws, mock, path):
        assert ask(ws, {"a": "scenes_import"})["ok"] is True
        assert ask(ws, {"a": "select_fixtures", "ids": [12]})["ok"]
        r = ask(ws, {"a": "scene_create", "label": "Рояль 2", "page": 1, "exec": "1.101", "confirm": "1.101", "replace": True})
        assert r["ok"] is True, r
        assert not any(l.startswith("Delete") for l in mock.received)
        assert "Copy Cue 1 Executor 1.101 At Cue 2 Executor 1.1 /CueOnly" in mock.received
        assert "Copy Cue 1 Executor 1.1 At Cue 1 Executor 1.101 /CueOnly /Overwrite" in mock.received
        scenes = [s for s in json.loads(path.read_text())["scenes"] if s["exec"] == "1.101"]
        assert len(scenes) == 1 and scenes[0]["label"] == "Рояль 2"
        assert ask(ws, {"a": "scene_create", "label": "X", "page": 1, "exec": "1.199", "confirm": "1.199", "replace": True})["ok"] is False  # nothing to overwrite

def test_running_poll(bridge_cfg):
    with bridge_cfg(settings={**FULL, "poll_seconds": 0.3}) as (ws, mock, _):
        assert ask(ws, {"a": "scenes_import"})["ok"] is True
        ask(ws, {"a": "scene_go", "id": "pianist"})
        m = until(ws, lambda m: m.get("running", {}).get("pianist") is True and m.get("running", {}).get("s1") is False)
        assert m["running_meta"]["s1"]["source"] == "ma2"

def test_probe_and_backup(tmp_path, monkeypatch):
    from ma2panel import bridge as b
    monkeypatch.setattr(b, "HERE", tmp_path)
    async def go():
        mock = await start_mock(0, "panel")
        await b.probe({"ma2": {"host": "127.0.0.1", "port": mock.port, "user": "panel", "password": ""}})
    asyncio.run(go())
    assert "List Group" in (tmp_path / "probe.txt").read_text(encoding="utf-8")
    cfg = tmp_path / "c.json"; cfg.write_text("{}")
    for day in range(10):
        (tmp_path / "backups").mkdir(exist_ok=True); (tmp_path / "backups" / f"config-2026010{day}.json").write_text("{}")
    b.backup_config(str(cfg))
    assert len(list((tmp_path / "backups").glob("*.json"))) == 7


def test_unknown_result_is_not_retried_and_late_reply_is_drained():
    async def go():
        mock, link, task = await connect()
        link.timeout = 0.3
        await wait_state(link, "logged_in", 2)
        mock.late = 0.6
        ok, why = await link.send("Go Executor 1.101")
        assert not ok and "неизвестен" in why and link.last["status"] == "unknown"
        mock.late = 0
        ok, reply = await link.send("Off Executor 1.101")  # the late "OK" of Go is drained first, not read as Off's answer
        assert ok and link.last["status"] == "sent"
        assert mock.received.count("Go Executor 1.101") == 1
        assert any(r["status"] == "late" for r in link.raw)
        task.cancel()
    asyncio.run(go())

def test_error_reply_status():
    async def go():
        mock, link, task = await connect()
        await wait_state(link, "logged_in", 2)
        mock._reply = lambda text: "Error: illegal object\r\n[Channel]>"
        ok, _ = await link.send("Go Executor 1.101")
        assert not ok and link.last["status"] == "error"
        task.cancel()
    asyncio.run(go())

def test_manual_drop_only_closes_own_session_until_connect():
    async def go():
        mock, link, task = await connect()
        await wait_state(link, "logged_in", 2)
        link.disconnect()
        await wait_state(link, "manual_off", 1)
        await asyncio.sleep(1)  # no automatic reconnect while dropped by hand (RECONNECT_S is 0.2 in tests)
        assert link.state == "manual_off"
        assert (await link.send("Go Executor 1.101"))[0] is False
        link.connect()
        await wait_state(link, "logged_in", 2)
        assert "Go Executor 1.101" not in mock.received
        task.cancel()
    asyncio.run(go())

def test_login_ma2_wire_format_chunked_and_password_masked():
    """MA2 3.9.60: colour codes, "[Channel]>cmd" echo, prompt followed by \\x1b[K, replies split over TCP chunks."""
    async def go():
        mock = await start_mock(0, "Remote")
        mock.echo, mock.ansi, mock.chunk = True, True, 7
        link = MA2Link("127.0.0.1", mock.port, "Remote", "s3cr3t", lambda s: None, login_ok=__import__("re").compile("NEVER"))
        task = asyncio.create_task(link.run())
        await wait_state(link, "logged_in", 4)
        assert link.vars["USER"] == "Remote" and link.vars["USERRIGHTS"] == "Program"
        assert "s3cr3t" not in link.login_reply and "***" in link.login_reply and "\x1b" not in link.login_reply
        assert all("s3cr3t" not in r["reply"] and "\x1b" not in r["reply"] for r in link.raw)
        ok, reply = await link.send("Go Executor 1.101")
        assert ok and "OK" in reply
        task.cancel()
    asyncio.run(go())

def test_login_not_confirmed_sends_nothing():
    async def go():
        mock = await start_mock(0, "panel")
        mock.list_garbage = True  # ListVar without $USER: the login is not confirmed
        link = MA2Link("127.0.0.1", mock.port, "panel", "", lambda s: None)
        task = asyncio.create_task(link.run())
        await wait_state(link, "login_unknown", 4)
        assert (await link.send("Go Executor 1.101"))[0] is False
        assert "Go Executor 1.101" not in mock.received
        task.cancel()
    asyncio.run(go())

def test_listvar_other_user_is_login_failed():
    async def go():
        mock = await start_mock(0, "panel")
        real = mock._reply
        mock._reply = lambda t: "$USER = administrator\r\n[Channel]>" if t == "ListVar" else real(t)
        link = MA2Link("127.0.0.1", mock.port, "panel", "", lambda s: None)
        task = asyncio.create_task(link.run())
        await wait_state(link, "login_failed", 4)
        task.cancel()
    asyncio.run(go())

def test_login_incorrect_reply():
    async def go():
        mock = await start_mock(0, "panel")
        real = mock._reply
        mock._reply = lambda t: "Login incorrect\r\n[Channel]>" if t.lower().startswith("login") else real(t)
        link = MA2Link("127.0.0.1", mock.port, "panel", "", lambda s: None)
        task = asyncio.create_task(link.run())
        await wait_state(link, "login_failed", 4)
        assert "ListVar" not in mock.received
        task.cancel()
    asyncio.run(go())

def test_ws_link_drop_and_connect(bridge):
    ws, mock, _ = bridge
    assert ask(ws, {"a": "link_drop"})["ok"] is True
    until(ws, lambda m: m.get("status", {}).get("ma2") == "manual_off")
    assert ask(ws, {"a": "scene_go", "id": "pianist"})["ok"] is False
    assert ask(ws, {"a": "link_connect"})["ok"] is True
    until(ws, lambda m: m.get("status", {}).get("ma2") == "logged_in")
    assert "Go Executor 1.101" not in mock.received


def test_unknown_aim_nudge_and_scene(bridge):
    ws, mock, _ = bridge
    ask(ws, {"a": "select_group", "id": "front"})
    r = ask(ws, {"a": "move_start"})
    assert not r["ok"] and "позиция головы 12 неизвестна" in r["err"]
    assert ask(ws, {"a": "nudge", "attr": "pan", "dir": -1})["ok"]
    assert mock.received[-2:] == ["Fixture 12 + 14", 'Attribute "Pan" At - 2']
    assert not ask(ws, {"a": "move_start"})["ok"]
    assert not ask(ws, {"a": "aim", "pan": 271, "tilt": 0})["ok"]
    assert ask(ws, {"a": "aim", "pan": 0, "tilt": 0})["ok"]
    assert ask(ws, {"a": "move_start"})["ok"]
    ws.send_json({"a": "nudge", "attr": "pan", "dir": 1})
    m = until(ws, lambda m: "shown" in m)
    assert m["shown"]["12"]["pan"] == pytest.approx(50 + 2 / 540 * 100)
    until(ws, lambda m: m.get("a") == "nudge" and "ok" in m)
    assert ask(ws, {"a": "scene_go", "id": "pianist"})["ok"]
    assert ask(ws, {"a": "move_start"})["ok"]


@pytest.mark.parametrize("value, text", [(False, "отключена в настройках (features.move)"), ("дефект", "заблокирована: дефект")])
def test_feature_switch(bridge_cfg, value, text):
    with bridge_cfg(settings={**FULL, "features": {"move": value}}) as (ws, mock, _):
        r = ask(ws, {"a": "aim", "pan": 0, "tilt": 0})
        assert not r["ok"] and text in r["err"]


def test_nudge_bad_step(bridge_cfg):
    with bridge_cfg(settings={**FULL, "attrs": {"pan": {"step": 11}}}) as (ws, mock, _):
        ask(ws, {"a": "select_group", "id": "front"})
        r = ask(ws, {"a": "nudge", "attr": "pan", "dir": 1})
        assert not r["ok"] and "attrs.pan.step" in r["err"]


def test_color_modes(bridge_cfg):
    def edit(cfg):
        next(f for f in cfg["fixtures"] if f["id"] == 14)["color"] = "cmy"
    with bridge_cfg(edit) as (ws, mock, _):
        ask(ws, {"a": "select_group", "id": "front"})
        ws.send_json({"a": "color", "r": 100, "g": 20, "b": 0})
        until(ws, lambda m: "shown" in m)
        assert mock.received[-8:] == ["Fixture 12", 'Attribute "ColorRGB1" At 100', 'Attribute "ColorRGB2" At 20',
                                     'Attribute "ColorRGB3" At 0', "Fixture 14", 'Attribute "ColorRGB1" At 0',
                                     'Attribute "ColorRGB2" At 80', 'Attribute "ColorRGB3" At 100']


def test_positions_forgotten_on_link_loss(bridge):
    ws, mock, _ = bridge
    ask(ws, {"a": "select_group", "id": "front"})
    assert ask(ws, {"a": "aim", "pan": 0, "tilt": 0})["ok"]
    ws.send_json({"a": "zoom", "v": 25})
    until(ws, lambda m: m.get("shown", {}).get("12", {}).get("zoom") == 25)
    ws.send_json({"a": "link_drop"})
    messages = []
    while not (any("shown" in m for m in messages) and any(m.get("a") == "link_drop" and "ok" in m for m in messages)):
        messages.append(ws.receive_json())
    assert next(m["shown"] for m in messages if "shown" in m) == {}
    assert ask(ws, {"a": "link_connect"})["ok"]
    until(ws, lambda m: m.get("status", {}).get("ma2") == "logged_in")
    assert not ask(ws, {"a": "move_start"})["ok"]


def test_color_all_none(bridge_cfg):
    def edit(cfg):
        for f in cfg["fixtures"]:
            f["color"] = "none"
    with bridge_cfg(edit) as (ws, mock, _):
        ask(ws, {"a": "select_group", "id": "front"})
        ws.send_json({"a": "color", "r": 0, "g": 0, "b": 0})
        r = until(ws, lambda m: "ok" in m)
        assert not r["ok"] and "color: none" in r["err"]
        assert not attr_lines(mock)


def test_mapping_settings_config_guard_and_persistence(tmp_path):
    cfg = json.loads(open(CONFIG).read())
    cfg["ma2"].update(port=30000, export_dir=str(tmp_path))
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg))
    settings = {"safety": {"allowed_fixtures": [12, 14]},
                "attrs": {"pan": {"cmd": 'Attribute "Yaw" At {v}', "rel_cmd": 'Attribute "Yaw" At {sign} {v}', "step": 3}}}
    with TestClient(create_app(cfg, True, str(path), settings)) as client, client.websocket_connect("/ws") as ws:
        conf = until(ws, lambda m: "config" in m)["config"]
        assert conf["attrs"]["pan"]["step"] == 3
        until(ws, lambda m: m.get("status", {}).get("ma2") == "logged_in")
        ask(ws, {"a": "select_group", "id": "front"})
        assert ask(ws, {"a": "nudge", "attr": "pan", "dir": 1})["ok"]
        assert client.app.state.mock.received[-1] == 'Attribute "Yaw" At + 3'
        assert ask(ws, {"a": "aim", "pan": 0, "tilt": 0})["ok"]
        assert ask(ws, {"a": "preset_save", "label": "T"})["ok"]
        assert json.loads(path.read_text())["attrs"] == cfg["attrs"]


def test_invalid_attribute_name_startup(tmp_path):
    cfg = json.loads(open(CONFIG).read())
    with pytest.raises(SystemExit, match="имя атрибута"):
        create_app(cfg, True, str(tmp_path / "c.json"), {"attrs": {"pan": {"cmd": 'Attribute "Bad Name" At {v}'}}})


@pytest.mark.parametrize("action", [{"a": "nudge", "attr": "zoom", "dir": 1},
                                    {"a": "nudge", "attr": "pan", "dir": True},
                                    {"a": "nudge", "attr": "tilt", "dir": 1.0},
                                    {"a": "aim", "pan": True, "tilt": 0},
                                    {"a": "aim", "pan": 0, "tilt": -136}])
def test_aim_nudge_strict_validation(bridge, action):
    ws, mock, _ = bridge
    ask(ws, {"a": "select_group", "id": "front"})
    assert not ask(ws, action)["ok"]
    assert not attr_lines(mock)


def test_still_silent_after_timeout_reopens_the_session():
    async def go():
        mock, link, task = await connect()
        link.timeout = 0.3
        await wait_state(link, "logged_in", 2)
        mock.mute = True
        assert (await link.send("Go Executor 1.101"))[0] is False
        ok, why = await link.send("Off Executor 1.101")  # Go never answered: Off is not sent on that session
        assert not ok and "переоткрыто" in why and "Off Executor 1.101" not in mock.received
        mock.mute = False
        await wait_state(link, "down", 2)
        await wait_state(link, "logged_in", 5)
        assert (await link.send("Off Executor 1.101"))[0] is True
        task.cancel()
    asyncio.run(go())


@pytest.mark.parametrize("mode", ["store", "full"])
@pytest.mark.parametrize("case", ["empty", "occupied", "garbage", "timeout", "store_unknown", "store_error", "label_unknown", "label_error", "confirm", "format", "missing", "list_error"])
def test_scene_write_safety(bridge_cfg, mode, case):
    settings = {"safety": {"mode": mode, "store_execs": ["2.150", "1.101"], "allowed_fixtures": [12]}, "ma2": {"timeout": 0.1}}
    with bridge_cfg(settings=settings) as (ws, mock, path):
        assert ask(ws, {"a": "select_fixtures", "ids": [12]})["ok"]
        before = path.read_bytes()
        action = {"a": "scene_create", "label": "New", "page": 2, "exec": "2.150", "confirm": "2.150"}
        if case == "occupied": action.update(exec="1.101", confirm="1.101")
        elif case == "garbage": mock.list_garbage = True
        elif case == "timeout": mock.mute = True
        elif case == "confirm": action['confirm'] = '2.151'
        elif case == "format": action.update(exec='bad', confirm='bad')
        elif case == "missing": action.pop('exec')
        if case.startswith(('store_', 'label_', 'list_')):
            original = mock._reply
            def reply(text):
                prefix = 'Store Executor' if case.startswith('store') else 'Label Executor' if case.startswith('label') else 'List Executor'
                if text.startswith(prefix):
                    return 'OK\r\n' if case.endswith('unknown') else 'Error: illegal\r\n[Channel]>'
                return original(text)
            mock._reply = reply
        result = ask(ws, action)
        assert result['ok'] is (case == 'empty'), result
        assert not any(x.startswith('Delete') or '/Overwrite' in x for x in mock.received)
        store = 'Store Executor 2.150 Cue 1 /Source=Output /Use=Allforselected'
        if case == 'empty':
            assert json.loads(path.read_text())['scenes'][-1]['exec'] == '2.150'
            assert mock.received.count(store) == 1
            assert not ask(ws, action)['ok']
        else:
            assert path.read_bytes() == before
            if case.startswith(('store_', 'label_')):
                assert mock.received.count(store) == 1
                assert (path.parent / 'scene-write-2.150.json').exists()
            else:
                assert store not in mock.received


def test_import_unrecognised_keeps_scenes(bridge):
    ws, mock, path = bridge
    before = path.read_bytes()
    original = mock._reply
    mock._reply = lambda cmd: "???\r\n[Channel]>" if cmd.startswith("List Executor") else original(cmd)
    r = ask(ws, {"a": "scenes_import"})
    assert r == {"ok": True, "a": "scenes_import", "added": 0, "unrecognised": 1, "total": 1, "switched": None}
    assert path.read_bytes() == before


def test_import_failure_keeps_config(bridge):
    ws, mock, path = bridge
    before = path.read_bytes()
    mock._reply = lambda text: "Error: illegal\r\n[Channel]>"
    assert not ask(ws, {"a": "scenes_import"})["ok"]
    assert path.read_bytes() == before


def test_custom_empty_regex(bridge_cfg):
    with bridge_cfg(settings={**FULL, "ma2": {"exec_empty_regex": "^VACANT"}}) as (ws, mock, path):
        original = mock._reply
        mock._reply = lambda text: "VACANT\r\n[Channel]>" if text.startswith("List Executor") and text.split()[-1] not in mock.rows else original(text)
        assert ask(ws, {"a": "select_fixtures", "ids": [12]})["ok"]
        assert ask(ws, {"a": "scene_create", "label": "T", "page": 2, "exec": "2.150", "confirm": "2.150"})["ok"]
        assert json.loads(path.read_text())["scenes"][-1]["exec"] == "2.150"


def test_invalid_empty_regex_startup(tmp_path):
    cfg = json.loads(open(CONFIG).read())
    with pytest.raises(SystemExit, match="ma2.exec_empty_regex"):
        create_app(cfg, True, str(tmp_path / "c.json"), {"ma2": {"exec_empty_regex": "["}})


def test_listvar_real_console_format():
    """MA2 3.9.60 prefixes every variable with "Global : "; the diagnostics bundle of 2026-10-18 showed it."""
    from ma2panel.bridge import VAR
    reply = "Executing : ListVar\nGlobal : $USER = Remote\nGlobal : $USERRIGHTS = Program\nGlobal : $SHOWFILE = big room v2\n [Group]>"
    assert dict(VAR.findall(reply)) == {"USER": "Remote", "USERRIGHTS": "Program", "SHOWFILE": "big room v2"}


def test_scene_crossfade(bridge_cfg):
    with bridge_cfg(lambda cfg: cfg["scenes"].append({"id": "choir", "exec": "1.102", "label": "Choir"})) as b:
        check_scene_crossfade(b)


















def check_scene_crossfade(bridge):
    ws, mock, _ = bridge
    assert ask(ws, {"a": "scene_fade", "fade": 0.2})["ok"]
    assert ask(ws, {"a": "scene_go", "id": "choir"})["ok"]
    assert ask(ws, {"a": "scene_go", "id": "pianist", "swap": ["choir"]})["ok"]
    assert mock.received[-3:] == ["Masterfade 0.2 Executor 1.102", "Goto Cue 1 Executor 1.101 Fade 0.2", "Off Executor 1.102"]
    assert ask(ws, {"a": "scene_go", "id": "pianist", "swap": ["nope"]})["ok"] is False
    assert ask(ws, {"a": "scene_go", "id": "pianist", "swap": "choir"})["ok"] is False


def per_fixture(received, attr):
    """Sum of relative steps per fixture: {12: 3.0} from "Fixture 12 + 14", 'Attribute "Pan" At + 3' ..."""
    total, current = {}, []
    for line in received:
        if line.startswith("Fixture "):
            current = [int(n) for n in line[8:].split(" + ")]
        elif m := re.fullmatch(rf'Attribute "{attr}" At ([+-]) (\S+)', line):
            for fid in current:
                total[fid] = total.get(fid, 0) + float(m[2]) * (1 if m[1] == "+" else -1)
    return total


def test_jog_relative_summed_and_flipped(bridge_cfg):
    def edit(cfg):
        next(f for f in cfg["fixtures"] if f["id"] == 14)["flip_pan"] = True
    with bridge_cfg(edit) as (ws, mock, _):
        ask(ws, {"a": "select_group", "id": "front"})
        start = len(mock.received)
        ws.send_json({"a": "jog", "pan": 1.5, "tilt": 0})
        ws.send_json({"a": "jog", "pan": 1.5, "tilt": -1.25})
        assert ask(ws, {"a": "clear"})["ok"]  # flushes waiting slider values first
        lines = mock.received[start:]
        assert per_fixture(lines, "Pan") == {12: 3, 14: -3}  # 14 hangs upside down
        assert per_fixture(lines, "Tilt") == {12: -1.25, 14: -1.25}
        r = ask(ws, {"a": "jog", "pan": 46, "tilt": 0})
        assert not r["ok"] and "-45…45" in r["err"]


def test_flip_flag_and_nudge(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        assert ask(ws, {"a": "fixture_flag", "id": 12, "flip_tilt": True})["ok"]
        assert next(f for f in json.loads(path.read_text())["fixtures"] if f["id"] == 12)["flip_tilt"] is True
        assert not ask(ws, {"a": "fixture_flag", "id": 12, "flip_tilt": 1})["ok"]
        ask(ws, {"a": "select_group", "id": "front"})
        assert ask(ws, {"a": "nudge", "attr": "tilt", "dir": 1})["ok"]
        assert mock.received[-4:] == ["Fixture 12", 'Attribute "Tilt" At - 2', "Fixture 14", 'Attribute "Tilt" At + 2']


def test_missing_attribute_learned(bridge_cfg):
    with bridge_cfg() as (ws, mock, _):
        mock.missing_attrs = {"Focus"}
        ask(ws, {"a": "select_group", "id": "front"})
        ws.send_json({"a": "focus", "v": 40})
        r = until(ws, lambda m: m.get("a") == "focus" and m.get("ok") is False)
        assert "нет атрибута «Focus»" in r["err"] and "attrs.focus.cmd" in r["err"]
        until(ws, lambda m: m.get("status", {}).get("no_attr", {}).get("focus") == ["acme"])


def test_poll_sees_show_loaded_on_desk(bridge_cfg):
    with bridge_cfg(settings={**FULL, "poll_seconds": 0.3}) as (ws, mock, _):
        mock.show_name = "Demo"
        until(ws, lambda m: m.get("status", {}).get("show", {}).get("name") == "Demo")


def test_jog_mirror_closes_in(bridge_cfg):
    def edit(cfg):
        for f in cfg["fixtures"]:
            if f["id"] in (12, 14):
                f["x"] = 0.8 if f["id"] == 12 else 0.2
    with bridge_cfg(edit) as (ws, mock, _):
        ask(ws, {"a": "select_group", "id": "front"})
        start = len(mock.received)
        ws.send_json({"a": "jog", "pan": 2, "tilt": 1, "mirror": True})
        assert ask(ws, {"a": "clear"})["ok"]
        assert per_fixture(mock.received[start:], "Pan") == {12: 2, 14: -2}  # 14 is on the left of the plan
        assert per_fixture(mock.received[start:], "Tilt") == {12: 1, 14: 1}
        assert not ask(ws, {"a": "jog", "pan": 1, "tilt": 0, "mirror": "yes"})["ok"]


def test_plan_copy_from_other_show(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        assert ask(ws, {"a": "show_bind", "name": "Old", "confirm": True})["ok"]
        assert ask(ws, {"a": "fixture_flag", "id": 12, "flip_pan": True})["ok"]
        old = json.loads(path.read_text())
        # the new show's plan has fixtures 12 and 99 only (as an import would leave it)
        (path.parent / "shows").mkdir(exist_ok=True)
        (path.parent / "shows/New.json").write_text(json.dumps({**old, "show": "New", "groups": [], "scenes": [], "presets": [],
            "fixtures": [{"id": 12, "label": "#12", "type": "acme"}, {"id": 99, "label": "#99", "type": "par"}]}))
        assert ask(ws, {"a": "show_open_plan", "name": "New"})["ok"]
        before = list(mock.received)
        r = ask(ws, {"a": "plan_copy", "from": "Old", "ids": [12, 13]})
        assert r["ok"] and r["copied"] == 1 and r["skipped"] == [13]
        f12 = next(f for f in json.loads(path.read_text())["fixtures"] if f["id"] == 12)
        o12 = next(f for f in old["fixtures"] if f["id"] == 12)
        assert f12["flip_pan"] is True and f12["label"] == o12["label"] and f12.get("x") == o12.get("x")
        assert mock.received == before  # nothing goes to the desk
        assert not ask(ws, {"a": "plan_copy", "from": "Nope"})["ok"]


def test_scenes_import_reads_filled_pages_and_follows_desk_show(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        assert ask(ws, {"a": "show_bind", "name": "Old plan", "confirm": True})["ok"]
        mock.rows["2.5"] = "Chorus"  # a page the plan has never seen
        r = ask(ws, {"a": "scenes_import"})
        assert r["ok"] and r["switched"] == mock.show_name
        cfg = json.loads(path.read_text())
        assert cfg["show"] == mock.show_name and {s["exec"] for s in cfg["scenes"]} >= {"1.101", "2.5"}


def test_fixture_icon_flag(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        assert ask(ws, {"a": "fixture_flag", "id": 17, "icon": "bar"})["ok"]
        assert next(f for f in json.loads(path.read_text())["fixtures"] if f["id"] == 17)["icon"] == "bar"
        assert not ask(ws, {"a": "fixture_flag", "id": 17, "icon": "star"})["ok"]


def test_blackout_without_scenes_darkens_fixtures(bridge_cfg):
    def edit(cfg):
        cfg["scenes"] = []  # a new show's plan before its scenes are read
    with bridge_cfg(edit) as (ws, mock, _):
        assert ask(ws, {"a": "blackout"})["ok"] is True
        assert mock.grand_master == 0 and "SpecialMaster 2.1 At 0" in mock.received


def test_halt_overtakes_this_tabs_running_action(bridge):
    ws, mock, _ = bridge
    mock.late = 0.5  # a slow console: the Go is still waiting for its answer when Stop arrives
    ws.send_json({"a": "scene_go", "id": "pianist"})
    ws.send_json({"a": "halt"})
    assert until(ws, lambda m: "ok" in m)["a"] == "halt"


def test_other_show_on_desk_refuses_plan_lines(bridge_cfg):
    with bridge_cfg(edit=lambda cfg: cfg.update(show="Plan show")) as (ws, mock, _):
        before = list(mock.received)
        for action in ({"a": "scene_go", "id": "pianist"}, {"a": "select_fixtures", "ids": [12]}):
            r = ask(ws, action)
            assert not r["ok"] and "другое шоу" in r["err"]
        assert mock.received == before
        assert ask(ws, {"a": "blackout"})["ok"] is True  # the emergency button still works


def test_ma2_position_preset_obeys_move_switch(bridge_cfg):
    with bridge_cfg(edit=lambda cfg: cfg.update(ma2presets={"positions": [{"n": 1, "name": "P"}]}),
                    settings={**FULL, "features": {"move": False}}) as (ws, mock, _):
        r = ask(ws, {"a": "ma2_preset_go", "type": "position", "n": 1})
        assert not r["ok"] and "features.move" in r["err"]


def test_background_poll_is_not_activity(tmp_path):
    from test_safety import tabs
    with tabs(tmp_path, {"safety": {"mode": "full"}, "poll_seconds": 0.2}, n=1) as ((ws,), mock, client, path):
        time.sleep(0.3)
        last = getattr(client.app.state, "last_send", None)
        polls = len(mock.received)
        time.sleep(0.6)
        assert len(mock.received) > polls  # the poll did run
        assert getattr(client.app.state, "last_send", None) == last


def test_dim_fade_played_by_bridge(bridge):
    ws, mock, _ = bridge
    ask(ws, {"a": "select_group", "id": "front"})
    ws.send_json({"a": "dim", "v": 0})
    assert ask(ws, {"a": "clear"})["ok"]
    ask(ws, {"a": "select_group", "id": "front"})
    start = len(mock.received)
    ws.send_json({"a": "dim", "v": 100, "fade": 1})
    until(ws, lambda m: any(v.get("dim") == 100 for v in m.get("shown", {}).values()))
    levels = [float(line[3:]) for line in mock.received[start:] if line.startswith("At ")]
    assert len(levels) >= 3 and levels == sorted(levels) and levels[-1] == 100 and not any("Fade" in l for l in mock.received[start:])


def test_dmx_read_back_lights_the_plan(bridge_cfg):
    from ma2panel.commands import DMX_CANARY, dmx_lua, live_from_dmx, parse_dmx
    from ma2panel.safety import DEFAULT_SAFETY, make_guard
    lines = dmx_lua(82, 100)
    assert [len(l) < 255 for l in lines] == [True] * 4 and "local a,n,v=178,4," in lines[3]
    assert len("SetVar $PANELDMX9 = \"T 9999 " + ",".join(["255"] * 32) + '"') < 255
    assert all(len(line) < 255 for line in dmx_lua(9990, 64) + [DMX_CANARY.format(a=9990)])
    line = lines[0]
    assert make_guard({**DEFAULT_SAFETY, "mode": "full", "allow_fixture_read": True})(line)  # never a free Lua line
    assert make_guard({**DEFAULT_SAFETY, "mode": "full", "allow_fixture_read": True}, export_extra={line})(line) is None
    dmx = parse_dmx('PANELDMX0=T 10 255,128,0\n Global : $PANELDMX1 = "T 74 7"')
    assert dmx == {10: 255, 11: 128, 12: 0, 74: 7}
    fx = [{"id": 1, "type": "A", "address": "1.010"}, {"id": 2, "type": "B", "address": "1.010"}]
    assert live_from_dmx(fx, dmx, {"A": {"dim": 1, "r": 2, "g": 3, "b": 1}, "B": {"r": 2, "g": 3, "b": 1}}) == {
        1: {"dim": 100.0, "rgb": [50.2, 0.0, 100.0]}, 2: {"dim": 100.0, "rgb": [50.2, 0.0, 100.0]}}

    def edit(cfg):
        for f in cfg["fixtures"]:
            f.update(address=f"1.{f['id'] * 10:03d}", channels=4, type="Par")
        cfg["dmx_map"] = {"Par": {"dim": 1, "r": 2, "g": 3, "b": 4}}
    with bridge_cfg(edit, confirmed_profiles=True, settings={"safety": {"mode": "full", "allow_fixture_read": True}, "dmx_seconds": 0.05}) as (ws, mock, _):
        mock.dmx = {120: 255, 121: 255}
        live = until(ws, lambda m: "12" in m.get("live", {}) and "14" in m.get("live", {}))["live"]
        assert live["12"] == {"dim": 100.0, "rgb": [100.0, 0.0, 0.0]} and live["14"]["dim"] == 0
        assert ask(ws, {"a": "dmx_map", "type": "Par", "map": {}})["ok"]


def test_dmx_read_back_takes_channels_from_the_fixture_type(bridge_cfg):
    from ma2panel.fixtures import parse_fixture_type
    xml = ('<MA xmlns="http://schemas.malighting.de/grandma2/xml/MA"><FixtureType name="Par"><Modules><Module index="0">'
           '<ChannelType index="0" attribute="SHUTTER" coarse="1"><ChannelSet name="Open" from_dmx="0" to_dmx="255"/></ChannelType><ChannelType index="1" attribute="DIM" coarse="2" fine="3"/>'
           '<ChannelType index="2" attribute="COLORRGB1" coarse="4"/><ChannelType index="3" attribute="COLORRGB2" coarse="5"/>'
           '<ChannelType index="4" attribute="COLORRGB3" coarse="6"/></Module></Modules></FixtureType></MA>')
    assert parse_fixture_type(xml) == {"dim": 2, "r": 4, "g": 5, "b": 6, "shutter": 1, "shutter_open": [[0, 255]], "has": []}

    def edit(cfg):
        for f in cfg["fixtures"]:
            f.update(address=f"1.{f['id'] * 10:03d}", channels=6, type="3 Par")
    with bridge_cfg(edit, mock_setup=lambda mock: setattr(mock, "fixture_types", {3: xml}), settings={"safety": {"mode": "full", "allow_fixture_read": True}, "dmx_seconds": 0.05}) as (ws, mock, path):
        mock.fixture_types = {3: xml}
        mock.dmx = {121: 255, 123: 255}
        live = until(ws, lambda m: "12" in m.get("live", {}))["live"]
        assert live["12"] == {"dim": 100.0, "rgb": [100.0, 0.0, 0.0]}
        assert json.loads(path.read_text())["dmx_map"] == {"3 Par": {"dim": 2, "r": 4, "g": 5, "b": 6, "shutter": 1, "shutter_open": [[0, 255]], "has": []}}
        assert sum(line.startswith("Export FixtureType") for line in mock.received) == 1  # once, not every read
        assert not list((Path(mock.export_dir).parent / "fixture_types").glob("*.xml"))  # our one-off file is removed


def test_dmx_read_back_backs_off_when_the_desk_refuses_lua(bridge_cfg):
    def edit(cfg):
        cfg["fixtures"] = cfg["fixtures"][:1]  # refusal backoff is scoped to this block
        for f in cfg["fixtures"]:
            f.update(address=f"1.{f['id'] * 10:03d}", channels=4)
    with bridge_cfg(edit, confirmed_profiles=True, settings={"safety": {"mode": "full", "allow_fixture_read": True}, "dmx_seconds": 0.05}) as (ws, mock, _):
        mock.lua_error = True
        until(ws, lambda m: (m.get("last") or {}).get("status") == "error")
        time.sleep(0.3)
        assert sum(line.startswith("Lua") for line in mock.received) == 1


def test_history_undoes_light_and_config(bridge):
    ws, mock, path = bridge
    groups = json.loads(path.read_text())["groups"]
    assert ask(ws, {"a": "group_save", "label": "Мои", "ids": [12]})["ok"] is True
    entry = until(ws, lambda m: m.get("history"))["history"][-1]
    assert entry["what"] == "Группа" and entry["undo"] is True
    assert ask(ws, {"a": "undo", "n": entry["n"]})["ok"] is True
    assert json.loads(path.read_text())["groups"] == groups
    assert ask(ws, {"a": "undo", "n": entry["n"]})["ok"] is False  # once
    ask(ws, {"a": "select_fixtures", "ids": [12]})
    for v in (50, 80):
        ws.send_json({"a": "dim", "v": v})
        until(ws, lambda m: m.get("shown", {}).get("12", {}).get("dim") == v)
    light = until(ws, lambda m: m.get("history") and m["history"][-1]["a"] == "dim" and m["history"][-1]["undo"])["history"][-1]
    assert ask(ws, {"a": "undo", "n": light["n"]})["ok"] is True
    assert mock.received[-2:] == ["Fixture 12", "At 50"]
    assert ask(ws, {"a": "scene_go", "id": "pianist"})["ok"] is True
    last = until(ws, lambda m: m.get("history") and m["history"][-1]["a"] == "scene_go")["history"][-1]
    assert last["undo"] is False

def test_capture_replies_at_start(tmp_path, monkeypatch):
    """Owner 2026-10-22: a real start writes the guessed-format replies to field-data/auto/, plus a running scene's row."""
    from ma2panel import bridge
    monkeypatch.setattr(bridge, "HERE", tmp_path)
    (tmp_path / "static").mkdir()
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["ma2"]["port"] = 30000
    app = create_app(cfg, True, str(tmp_path / "c.json"), FULL, capture=True)

    def text(want):
        for _ in range(100):
            files = list((tmp_path / "field-data" / "auto").glob("*.txt"))
            if files and want in (body := files[0].read_text(encoding="utf-8")):
                return files, body
            time.sleep(0.05)
        raise AssertionError(f"no {want!r} in the capture")

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ready(ws)
        files, body = text("### ListShows")
        assert "### ListVar  (ok=True)" in body and "### List Executor 1.101  (ok=True)" in body
        assert ask(ws, {"a": "scene_go", "id": "pianist"})["ok"] is True
        files, body = text("после Go сцены 1.101")
        assert len(files) == 1  # one file per run


@pytest.fixture
def simple_bridge(tmp_path):
    cfg = json.loads(Path(CONFIG).read_text())
    cfg['ma2']['port'] = 30000
    cfg['ma2']['export_dir'] = str(tmp_path)
    app = create_app(cfg, True, str(tmp_path / 'simple-config.json'), FULL)
    app.mount('/simple-test', app.state.simple_app)
    app.router.routes.insert(0, app.router.routes.pop())
    with TestClient(app) as main:
        with main.websocket_connect('/ws') as normal, main.websocket_connect('/simple-test/ws') as ws:
            ready(normal)
            conf, logged_in = None, False
            while conf is None or not logged_in:
                msg = ws.receive_json()
                assert 'history' not in msg and 'shown' not in msg  # no log on the simple port
                if 'config' in msg:
                    conf = msg['config']
                logged_in |= msg.get('status', {}).get('ma2') == 'logged_in'
            yield ws, normal, TestClient(app.state.simple_app), app.state.mock, conf


@pytest.mark.parametrize('action', [
    {'a': 'dim', 'v': 90}, {'a': 'select_fixtures', 'ids': [12]},
    {'a': 'select_group', 'id': 'front'}, {'a': 'halt'}, {'a': 'resume'},
    {'a': 'link_drop'}, {'a': 'show_load', 'name': 'Other'},
    {'a': 'scene_create'}, {'a': 'page_go', 'n': 2}, {'a': 'unknown'},
])
def test_simple_rejects_actions(simple_bridge, action):
    ws, normal, _, mock, _ = simple_bridge
    before = list(mock.received)
    result = ask(ws, action)
    assert result == {'ok': False, 'a': action['a'], 'err': 'в простом режиме недоступно'}
    assert mock.received == before
    assert ask(normal, {'a': 'select_fixtures', 'ids': [12]})['ok'] is True


def test_simple_allowed(simple_bridge):
    ws, _, _, mock, _ = simple_bridge
    for a in ('scene_go', 'scene_off'):
        assert ask(ws, {'a': a, 'id': 'pianist'})['ok'] is True
    assert 'Goto Cue 1 Executor 1.101 Fade 0' in mock.received
    assert 'Off Executor 1.101' in mock.received
    assert ask(ws, {'a': 'blackout'})['ok'] is True


def test_simple_config_and_routes(simple_bridge):
    ws, normal, client, _, conf = simple_bridge
    assert set(conf) == {'scenes', 'pages'}
    assert conf['scenes']
    assert ask(normal, {'a': 'scene_rename', 'id': 'pianist', 'label': 'New name'})['ok']
    updated = until(ws, lambda m: 'config' in m)['config']
    assert set(updated) == {'scenes', 'pages'}
    assert updated['scenes'][0]['label'] == 'New name'
    assert 'Погасить всё' in client.get('/').text
    for path in ('/style.css', '/simple.js', '/command-feedback.js'):
        assert client.get(path).status_code == 200
    for path in ('/api/settings', '/api/diag', '/settings.html', '/log.html', '/index.html', '/app.js', '/docs', '/openapi.json'):
        assert client.get(path).status_code == 404
    assert client.post('/api/stop').status_code == 404


@pytest.mark.parametrize('port', [0, 65536, True, '8090', 8090.0])
def test_simple_port_invalid(port):
    from ma2panel.safety import validate_settings
    with pytest.raises(ValueError, match='simple_port'):
        validate_settings({'simple_port': port})


@pytest.mark.parametrize('settings', [{}, {'simple_port': None}, {'simple_port': 8090}, {'simple_port': 1}])
def test_simple_port_valid(settings):
    from ma2panel.safety import validate_settings
    validate_settings(settings)


def test_simple_port_must_differ():
    from ma2panel.safety import validate_settings
    with pytest.raises(ValueError, match='simple_port'):
        validate_settings({'port': 8090})



def test_simple_running_shared_with_main(simple_bridge):
    ws, normal, _, _, _ = simple_bridge
    assert ask(normal, {"a": "scene_go", "id": "pianist"})["ok"]
    assert until(ws, lambda m: "pianist" in m.get("running", {}))["running"]["pianist"] is None
    assert ask(normal, {"a": "blackout"})["ok"]
    assert until(ws, lambda m: "pianist" in m.get("running", {}))["running"]["pianist"] is None


def test_simple_obeys_safety(tmp_path):
    cfg = json.loads(Path(CONFIG).read_text())
    cfg["ma2"]["port"] = 30000
    app = create_app(cfg, True, str(tmp_path / "c.json"),
                     {"safety": {"mode": "test", "allowed_scenes": [], "allowed_fixtures": [12]}, "poll_seconds": 0})
    app.mount("/simple-test", app.state.simple_app)
    app.router.routes.insert(0, app.router.routes.pop())
    with TestClient(app) as client, client.websocket_connect("/simple-test/ws") as ws:
        until(ws, lambda m: m.get("status", {}).get("ma2") == "logged_in")
        result = ask(ws, {"a": "scene_go", "id": "pianist"})
        assert not result["ok"] and "в простом режиме" not in result["err"]
        assert "Go Executor 1.101" not in app.state.mock.received
        assert not ask(ws, {"a": "blackout"})["ok"]
        assert not any(x.startswith("SpecialMaster ") for x in app.state.mock.received)


# Spec 24: strobe and Zoom/Focus presence come from the fixture type export.
SPOT_TYPE = ('<MA xmlns="http://schemas.malighting.de/grandma2/xml/MA"><FixtureType name="Spot"><Modules><Module index="0">'
             '<ChannelType index="0" attribute="SHUTTER" coarse="1"><ChannelFunction from="0" to="255" attribute="SHUTTER">'
             '<ChannelSet name="Closed" from="0" to="31"/><ChannelSet name="Open" from="32" to="63"/>'
             '<ChannelSet name="Strobe slow - fast" from="64" to="255"/></ChannelFunction></ChannelType>'
             '<ChannelType index="1" attribute="DIM" coarse="2"/><ChannelType index="2" attribute="ZOOM" coarse="3"/>'
             '</Module></Modules></FixtureType></MA>')


def test_type_export_names_strobe_range_and_present_attributes():
    from ma2panel.fixtures import parse_fixture_type
    spec = parse_fixture_type(SPOT_TYPE)
    assert spec["dim"] == 2 and spec["has"] == ["strobe", "zoom"]
    assert spec["strobe"] == {"attr": "SHUTTER", "open": 12.5, "from": 25.1, "to": 100.0}  # DMX 32, 64, 255 as % of 255, one decimal
    focus = SPOT_TYPE.replace('attribute="ZOOM"', 'attribute="FOCUS1"')
    assert parse_fixture_type(focus)["has"] == ["focus", "strobe"]
    no_strobe = SPOT_TYPE.replace("Strobe slow - fast", "Pulse")
    assert "strobe" not in parse_fixture_type(no_strobe) and "strobe" not in parse_fixture_type(no_strobe)["has"]


def test_strobe_uses_the_range_of_each_type(bridge_cfg):
    def edit(cfg):
        for f in cfg["fixtures"]:
            f.update(type="3 Spot")
        cfg["fixtures"][-1]["type"] = "4 Par"
        cfg["dmx_map"] = {"3 Spot": {"dim": 2, "has": ["strobe"], "strobe": {"attr": "SHUTTER", "open": 12.5, "from": 25.1, "to": 100.0}},
                          "4 Par": {"dim": 1, "has": []}}
    with bridge_cfg(edit, confirmed_profiles=True, settings={"safety": {"mode": "test", "allowed_fixtures": list(range(1, 25)), "allowed_scenes": []}}) as (ws, mock, path):
        ids = [f["id"] for f in json.loads(path.read_text())["fixtures"]]
        spots, par = ids[:-1], ids[-1]
        assert ask(ws, {"a": "select_fixtures", "ids": spots[:2] + [par]})["ok"]

        def slide(v):  # a slider gets no "ok" on success: wait for the shown echo or the error
            n = len(mock.received)
            ws.send_json({"a": "strobe", "v": v})
            m = until(ws, lambda m: "shown" in m or m.get("ok") is False)
            return m, mock.received[n:]

        m, sent = slide(100)
        assert sent == [f"Fixture {spots[0]} + {spots[1]}", 'Attribute "SHUTTER" At 100']  # the Par has no strobe: skipped
        assert slide(1)[1][-1] == 'Attribute "SHUTTER" At 25.1'
        assert slide(0)[1][-1] == 'Attribute "SHUTTER" At 12.5'  # 0 = open, never closed
        assert ask(ws, {"a": "select_fixtures", "ids": [par]})["ok"]
        m, sent = slide(50)
        assert "строб" in m["err"] and sent == []

def test_type_read_again_when_presence_unknown(bridge_cfg):
    """A type read before spec 24 has no "has": it is exported once more, so its sliders can be hidden."""
    def edit(cfg):
        for f in cfg["fixtures"]:
            f.update(address=f"1.{f['id'] * 10:03d}", channels=3, type="3 Spot")
        cfg["dmx_map"] = {"3 Spot": {"dim": 2}}
    with bridge_cfg(edit, mock_setup=lambda mock: setattr(mock, "fixture_types", {3: SPOT_TYPE}), settings={"safety": {"mode": "full", "allow_fixture_read": True}, "dmx_seconds": 0.05}) as (ws, mock, path):
        mock.fixture_types = {3: SPOT_TYPE}
        deadline = time.monotonic() + 5  # a plain loop, not until(): a red run must fail, not hang
        while "has" not in json.loads(path.read_text())["dmx_map"]["3 Spot"] and time.monotonic() < deadline:
            time.sleep(0.1)
        assert json.loads(path.read_text())["dmx_map"]["3 Spot"]["has"] == ["strobe", "zoom"]
        assert (path.parent / "diag" / "fixture_type_3.xml").read_text(encoding="utf-8") == SPOT_TYPE  # kept for the hall check


def test_update_gate_rechecks_a_line_waiting_for_transport():
    async def go():
        mock, link, task = await connect()
        try:
            await wait_state(link, 'logged_in', 2)
            gate = {'open': True}
            link.admission = lambda: gate['open']
            await link._lock.acquire()
            pending = asyncio.create_task(link.send('Go Executor 1.101'))
            await asyncio.sleep(0)
            gate['open'] = False
            link._lock.release()
            ok, reason = await pending
            assert ok is False
            assert 'обновлен' in reason
            assert 'Go Executor 1.101' not in mock.received
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(go())


def test_unknown_color_is_not_an_undo_base(bridge):
    ws, mock, _ = bridge
    assert ask(ws, {"a": "select_fixtures", "ids": [12]})["ok"]
    ws.send_json({"a": "dim", "v": 42})
    assert ask(ws, {"a": "select_fixtures", "ids": [12]})["ok"]
    ws.send_json({"a": "color", "r": 20, "g": 30, "b": 40})
    until(ws, lambda m: m.get("shown", {}).get("12", {}).get("rgb") == [20, 30, 40])
    entry = until(ws, lambda m: m.get("history") and m["history"][-1]["a"] == "color")["history"][-1]
    assert entry["undo"] is False
    start = len(mock.received)
    assert ask(ws, {"a": "undo", "n": entry["n"]})["ok"] is False
    assert len(mock.received) == start


@pytest.mark.parametrize("mixed", [False, True])
def test_unknown_dim_uses_console_fade_without_default_steps(bridge, mixed):
    ws, mock, _ = bridge
    if mixed:
        assert ask(ws, {"a": "select_fixtures", "ids": [14]})["ok"]
        ws.send_json({"a": "dim", "v": 25})
    assert ask(ws, {"a": "select_fixtures", "ids": [12]})["ok"]
    ws.send_json({"a": "color", "r": 20, "g": 30, "b": 40})
    assert ask(ws, {"a": "select_fixtures", "ids": [12, 14] if mixed else [12]})["ok"]
    start = len(mock.received)
    ws.send_json({"a": "dim", "v": 42, "fade": .2})
    until(ws, lambda m: m.get("shown", {}).get("12", {}).get("dim") == 42)
    levels = [line for line in mock.received[start:] if line.startswith("At ")]
    assert levels == ["At 42 Fade 0.2"]
