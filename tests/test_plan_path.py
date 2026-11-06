"""Real show-plan path resolution: names, legacy files and damaged storage."""
import json
from pathlib import Path

import pytest


def resolve(folder, name, *, write=False):
    from ma2panel.show_plans import plan_path
    return plan_path(folder, name, write=write)


def put(path, show, **extra):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"show": show, **extra}), encoding="utf-8")


@pytest.mark.parametrize("first,second", [("Concert/A", "Concert?A"), ("Show", "show"), ("CON", "con")])
def test_distinct_show_names_have_windows_distinct_paths(tmp_path, first, second):
    one = resolve(tmp_path, first, write=True)
    two = resolve(tmp_path, second, write=True)
    assert one.name.casefold() != two.name.casefold()
    put(one, first, value=1)
    put(two, second, value=2)
    assert resolve(tmp_path, first) == one
    assert resolve(tmp_path, second) == two
    assert json.loads(one.read_text())["value"] == 1


def test_legacy_plan_reads_by_embedded_name(tmp_path):
    legacy = tmp_path / "MyShow.json"
    put(legacy, "MyShow")
    assert resolve(tmp_path, "MyShow") == legacy
    assert resolve(tmp_path, "MyShow", write=True) != legacy
    assert json.loads(legacy.read_text())["show"] == "MyShow"


def test_new_plan_precedes_stale_legacy(tmp_path):
    legacy = tmp_path / "MyShow.json"
    put(legacy, "MyShow", value="old")
    latest = resolve(tmp_path, "MyShow", write=True)
    put(latest, "MyShow", value="new")
    assert resolve(tmp_path, "MyShow") == latest
    assert json.loads(legacy.read_text())["value"] == "old"


def test_foreign_legacy_plan_is_never_used(tmp_path):
    legacy = tmp_path / "Concert_A.json"
    put(legacy, "Concert/A", value="other show")
    target = resolve(tmp_path, "Concert?A")
    assert target != legacy
    assert not target.exists()
    assert resolve(tmp_path, "Concert/A") == legacy
    put(resolve(tmp_path, "Concert?A", write=True), "Concert?A")
    assert json.loads(legacy.read_text())["value"] == "other show"


@pytest.mark.parametrize("write", [False, True])
def test_refuse_hash_path_owned_by_different_show(tmp_path, write):
    target = resolve(tmp_path, "MyShow", write=True)
    put(target, "Foreign")
    with pytest.raises(ValueError, match="план"):
        resolve(tmp_path, "MyShow", write=write)
    assert json.loads(target.read_text())["show"] == "Foreign"


@pytest.mark.parametrize("write", [False, True])
def test_damaged_hash_path_is_not_overwritten(tmp_path, write):
    target = resolve(tmp_path, "MyShow", write=True)
    target.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="план"):
        resolve(tmp_path, "MyShow", write=write)
    assert target.read_text() == "{broken"


def test_damaged_legacy_file_refuses_read(tmp_path):
    (tmp_path / "MyShow.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="план"):
        resolve(tmp_path, "MyShow")


def test_long_unicode_names_have_bounded_ascii_filenames(tmp_path):
    name = "Очень длинное имя шоу 🎭 / " * 100
    target = resolve(tmp_path, name, write=True)
    assert target.parent == tmp_path
    assert target.name.isascii()
    assert len(target.name.encode()) < 100
    put(target, name)
    assert resolve(tmp_path, name) == target


def test_long_missing_legacy_name_does_not_break_lookup(tmp_path):
    name = "Длинное шоу" * 100
    assert resolve(tmp_path, name) == resolve(tmp_path, name, write=True)


def test_legacy_utf8_bom_is_supported(tmp_path):
    legacy = tmp_path / "MyShow.json"
    legacy.write_text(json.dumps({"show": "MyShow"}), encoding="utf-8-sig")
    assert resolve(tmp_path, "MyShow") == legacy


# Exercise the public WebSocket flow as well as the pure path helper above.
from contextlib import contextmanager
from copy import deepcopy

from fastapi.testclient import TestClient
from ma2panel.bridge import create_app
from test_bridge import ask, ready, until


def example_plan(name, *, x=0.1):
    return {"version": 5, "show": name, "fixtures": [{"id": 12, "label": name, "type": "par", "x": x, "y": 0.2}],
            "groups": [], "scenes": [], "presets": [], "attrs": {}}


@contextmanager
def panel(tmp_path):
    config_path = tmp_path / "config.json"  # absent at app creation: no migration side effects
    settings = {"safety": {"mode": "full"}, "poll_seconds": 0,
                "ma2": {"export_dir": str(tmp_path)}}
    app = create_app(example_plan("Mock show"), mock=True, config_path=str(config_path),
                     settings=settings, settings_path=tmp_path / "settings.json")
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ready(ws)
        yield ws, app.state.mock, config_path


def open_plan(ws, mock, name):
    mock.show_name = name
    assert ask(ws, {"a": "show_identify"})["ok"]
    reply = ask(ws, {"a": "show_open_plan", "name": name})
    assert reply["ok"], reply


def test_panel_legacy_plan_keeps_edits_after_switching_show(tmp_path):
    legacy = tmp_path / "shows" / "Legacy.json"
    put(legacy, "Legacy", **{k: v for k, v in example_plan("Legacy").items() if k != "show"})
    original = legacy.read_bytes()
    with panel(tmp_path) as (ws, mock, config):
        open_plan(ws, mock, "Legacy")
        assert ask(ws, {"a": "layout_save", "pos": [{"id": 12, "x": 0.75, "y": 0.45}]})["ok"]
        open_plan(ws, mock, "Other")
        open_plan(ws, mock, "Legacy")
        fixture = json.loads(config.read_text())["fixtures"][0]
        assert (fixture["x"], fixture["y"]) == (0.75, 0.45)
    assert legacy.read_bytes() == original


def test_panel_collision_with_foreign_legacy_creates_independent_plan(tmp_path):
    legacy = tmp_path / "shows" / "Concert_A.json"
    put(legacy, "Concert/A", **{k: v for k, v in example_plan("Concert/A", x=0.9).items() if k != "show"})
    original = legacy.read_bytes()
    with panel(tmp_path) as (ws, mock, config):
        open_plan(ws, mock, "Concert?A")
        new = json.loads(config.read_text())
        assert new["show"] == "Concert?A" and new["fixtures"] == []
        open_plan(ws, mock, "Concert/A")
        assert json.loads(config.read_text())["fixtures"][0]["x"] == 0.9
        open_plan(ws, mock, "Concert?A")
        assert json.loads(config.read_text())["fixtures"] == []
    assert legacy.read_bytes() == original


def test_panel_plan_copy_cannot_use_foreign_legacy(tmp_path):
    legacy = tmp_path / "shows" / "Concert_A.json"
    put(legacy, "Concert/A", **{k: v for k, v in example_plan("Concert/A", x=0.95).items() if k != "show"})
    with panel(tmp_path) as (ws, mock, config):
        assert ask(ws, {"a": "show_bind", "name": "Mock show"})["ok"]
        before = config.read_bytes()
        rejected = ask(ws, {"a": "plan_copy", "from": "Concert?A", "ids": [12]})
        assert not rejected["ok"]
        assert config.read_bytes() == before
        accepted = ask(ws, {"a": "plan_copy", "from": "Concert/A", "ids": [12]})
        assert accepted["ok"], accepted
        assert json.loads(config.read_text())["fixtures"][0]["x"] == 0.95


def test_panel_plan_list_deduplicates_legacy_and_latest(tmp_path):
    legacy = tmp_path / "shows" / "Legacy.json"
    data = {k: v for k, v in example_plan("Legacy").items() if k != "show"}
    put(legacy, "Legacy", **deepcopy(data))
    put(resolve(legacy.parent, "Legacy", write=True), "Legacy", **data)
    with panel(tmp_path) as (ws, mock, config):
        ws.send_json({"a": "show_bind", "name": "Mock show"})
        names = until(ws, lambda msg: "config" in msg)["config"]["plans"]
        assert names == ["Legacy"]
        assert until(ws, lambda msg: "ok" in msg)["ok"]


def test_panel_open_legacy_plan_keeps_v5_site_settings_separate(tmp_path):
    legacy = example_plan("Legacy")
    legacy.update(version=4, port=9099, rate_hz=2,
                  ma2={"host": "192.0.2.5", "export_dir": "old-console-path"},
                  master={"cmd": "Master 3.1 At {v}"})
    target = tmp_path / "shows" / "Legacy.json"
    put(target, "Legacy", **{k: v for k, v in legacy.items() if k != "show"})
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"port": 8080, "rate_hz": 10,
                                         "ma2": {"host": "127.0.0.1"},
                                         "master": {"cmd": "Master 2.1 At {v}"}}))
    original_settings = settings_path.read_bytes()
    with panel(tmp_path) as (ws, mock, config):
        open_plan(ws, mock, "Legacy")
        loaded = json.loads(config.read_text())
        assert loaded["version"] == 5
        assert not {"port", "rate_hz", "ma2", "master"}.intersection(loaded)
        assert loaded["fixtures"] == legacy["fixtures"]
        assert settings_path.read_bytes() == original_settings


def test_panel_reopen_current_unsaved_show_keeps_fixtures(tmp_path):
    with panel(tmp_path) as (ws, mock, config):
        open_plan(ws, mock, "Mock show")
        loaded = json.loads(config.read_text())
        assert loaded["show"] == "Mock show"
        assert loaded["fixtures"] == example_plan("Mock show")["fixtures"]
