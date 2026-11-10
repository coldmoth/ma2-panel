"""The owner's hall scenario end to end on the mock: start -> connect -> read data -> select -> change parameters ->
scenes -> stop -> start again. Store mode with one fixture group and one scene allowed, as on the first hall day."""
import json

from fastapi.testclient import TestClient

from ma2panel.bridge import create_app

CONFIG = "tests/config.test.json"
SETTINGS = {"safety": {"mode": "store", "allowed_fixtures": [12, 14], "allowed_scenes": ["1.101"],
                       "store_execs": ["2.150"]}}


def until(ws, pred):
    while not pred(m := ws.receive_json()):
        pass
    return m


def ask(ws, msg):
    ws.send_json(msg)
    return until(ws, lambda m: "ok" in m)


def start(tmp_path):
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["ma2"]["port"] = 30000
    cfg["ma2"]["export_dir"] = str(tmp_path)
    path = tmp_path / "config.json"
    if not path.exists():
        path.write_text(json.dumps(cfg, ensure_ascii=False))
    return create_app(json.loads(path.read_text()), mock=True, config_path=str(path), settings={"poll_seconds": 0, **SETTINGS}), path


def test_hall_scenario(tmp_path):
    app, path = start(tmp_path)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        # start + connect: only the login goes out, the panel says "logged in", nothing else is sent
        until(ws, lambda m: m.get("status", {}).get("ma2") == "logged_in")
        mock = app.state.mock
        assert [line.split()[0] for line in mock.received] == ["login", "ListVar"]

        # read data: scenes from the console, raw replies collected for diagnostics
        r = ask(ws, {"a": "scenes_import"})
        assert r["ok"] and r["added"] == 1 and r["unrecognised"] == 0

        # select a group: nothing is sent until a value is set
        before = len(mock.received)
        assert ask(ws, {"a": "select_group", "id": "front"})["ok"]
        assert len(mock.received) == before

        # parameters: every value line sits behind an explicit Fixture line
        for msg in ({"a": "dim", "v": 20}, {"a": "color", "r": 100, "g": 0, "b": 0}, {"a": "zoom", "v": 40},
                    {"a": "focus", "v": 60}):  # strobe needs a read fixture type: test_strobe_uses_the_range_of_each_type
            ws.send_json(msg)
            until(ws, lambda m: "shown" in m)
        assert mock.received[before:before + 2] == ["Fixture 12 + 14", "At 20"]

        # pan/tilt: unknown position -> the pad is refused; a relative step and an explicit aim work
        r = ask(ws, {"a": "move_start"})
        assert not r["ok"] and "неизвестна" in r["err"]
        assert ask(ws, {"a": "nudge", "attr": "pan", "dir": 1})["ok"]
        assert mock.received[-1] == 'Attribute "Pan" At + 2'
        assert ask(ws, {"a": "aim", "pan": 10, "tilt": -5})["ok"]
        assert ask(ws, {"a": "move_start"})["ok"]
        ws.send_json({"a": "move", "dx": 1, "dy": 0})
        until(ws, lambda m: "shown" in m and m["shown"].get("12", {}).get("pan"))

        # scenes: go / off of the allowed scene only
        assert ask(ws, {"a": "scene_go", "id": "pianist"})["ok"]
        assert ask(ws, {"a": "scene_off", "id": "pianist"})["ok"]
        assert "Goto Cue 1 Executor 1.101 Fade 0" in mock.received and mock.received[-1] == "Off Executor 1.101"
        assert not ask(ws, {"a": "scene_go", "id": "s1"})["ok"]  # 1.102 is not allowed

        # store a new scene: the destination is checked on fresh console data first, never overwritten
        r = ask(ws, {"a": "scene_create", "label": "Тест", "page": 2, "exec": "2.150", "confirm": "2.150"})
        assert r["ok"], r
        assert "Store Executor 2.150 Cue 1 /Source=Output /Use=Allforselected" in mock.received
        r = ask(ws, {"a": "scene_create", "label": "Ещё", "page": 2, "exec": "2.150", "confirm": "2.150"})
        assert not r["ok"] and "занят" in r["err"]
        assert mock.received[-1] == "List Executor 2.150"

        # stop sending, then the bridge's own link: no old values come back after reconnecting
        assert ask(ws, {"a": "halt"})["ok"]
        r = ask(ws, {"a": "dim", "v": 50})
        assert not r["ok"] and "остановлена" in r["err"]
        assert ask(ws, {"a": "resume"})["ok"]
        assert ask(ws, {"a": "link_drop"})["ok"]
        until(ws, lambda m: m.get("status", {}).get("ma2") == "manual_off")
        sent = len(mock.received)
        assert ask(ws, {"a": "link_connect"})["ok"]
        until(ws, lambda m: m.get("status", {}).get("ma2") == "logged_in")
        assert [line.split()[0] for line in mock.received[sent:]] == ["login", "ListVar"]
        assert not ask(ws, {"a": "move_start"})["ok"]  # positions are unknown again after the drop
        stopped_at = len(mock.received)
    assert len(mock.received) == stopped_at  # stopping the bridge sends nothing

    # start again: same config.json (with the stored scene), nothing but login goes out, selection is empty
    app, _ = start(tmp_path)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        until(ws, lambda m: m.get("status", {}).get("ma2") == "logged_in")
        assert [s["exec"] for s in json.loads(path.read_text())["scenes"]] == ["1.101", "1.102", "2.150"]
        r = ask(ws, {"a": "dim", "v": 30})
        assert not r["ok"] and "ничего не выбрано" in r["err"]
        assert [line.split()[0] for line in app.state.mock.received] == ["login", "ListVar"]
