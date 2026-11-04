"""Data from the real console (grandMA2 onPC 3.9.60.68, show "big room v2", 2026-10-18): what the mock-shaped code got wrong."""
import json
from pathlib import Path

from commands import can_move
from fixtures import merge_fixtures, parse_export
from test_bridge import FULL, ask, bridge_cfg, until  # noqa: F401

REAL = Path(__file__).parent / "real_export_3.9.60.xml"
READ = {"safety": {"mode": "full", "allow_fixture_read": True}, "ma2": {"export_wait": .6}}


def test_real_export_gives_address_and_channel_count():
    found = {f["id"]: f for f in parse_export(REAL.read_text(encoding="utf-8"))}
    assert len(found) == 24
    # List Fixture on the same console: 1 -> 1.200, 10 -> 1.082, 30 -> 1.360
    assert (found[1]["address"], found[10]["address"], found[30]["address"]) == ("1.200", "1.082", "1.360")
    assert found[1]["channels"] == 9 and found[1]["type"] == "3 ARTIST_FL_1000 RGB_CT"
    assert all(f["params"] == [] for f in found.values())  # the 3.9 export has no attribute names
    assert not any(can_move(f) for f in found.values())    # so the export alone never makes a head


def test_heads_need_the_operator_mark_and_the_mark_survives_a_new_fetch(bridge_cfg):
    real = merge_fixtures([], parse_export(REAL.read_text(encoding="utf-8")))
    assert [f["id"] for f in real if f.get("moves")] == [12, 13, 14]  # guessed from the type "Oxygen Mode 1"
    for f in real:
        f.pop("moves", None), f.pop("moves_auto", None)  # below: the operator-mark path, as before

    def edit(cfg):
        cfg.update(fixtures=real, groups=[], presets=[])

    with bridge_cfg(edit, settings=READ) as (ws, mock, path):
        assert ask(ws, {"a": "select_fixtures", "ids": [12]})["ok"]
        r = ask(ws, {"a": "nudge", "attr": "pan", "dir": 1})
        assert not r["ok"] and "отметьте головы" in r["err"]
        assert ask(ws, {"a": "layout_save", "pos": [{"id": 12, "x": .3, "y": .4}]})["ok"]
        assert ask(ws, {"a": "fixture_flag", "id": 12, "moves": True})["ok"]
        assert ask(ws, {"a": "nudge", "attr": "pan", "dir": 1})["ok"]
        assert mock.received[-1].startswith('Attribute "Pan" At +')
        mock.export_text = REAL.read_text(encoding="utf-8")
        assert ask(ws, {"a": "fixtures_fetch"})["ok"]
        f12 = next(f for f in json.loads(path.read_text())["fixtures"] if f["id"] == 12)
        assert f12["moves"] is True and (f12["x"], f12["y"]) == (.3, .4) and f12["address"] == "1.116"
        assert ask(ws, {"a": "fixture_flag", "id": 12, "moves": False})["ok"]
        assert not ask(ws, {"a": "nudge", "attr": "pan", "dir": 1})["ok"]


def test_fixture_flag_takes_exactly_one_bool_flag(bridge_cfg):
    with bridge_cfg() as (ws, _, path):
        before = path.read_bytes()
        for change in ({}, {"moves": 1}, {"moves": "true"}, {"moves": True, "service": True}):
            assert not ask(ws, {"a": "fixture_flag", "id": 12, **change})["ok"], change
        assert path.read_bytes() == before


def test_ma2_lists_in_the_real_format_are_read(bridge_cfg, monkeypatch):
    monkeypatch.setenv("MA2_MOCK_REAL", "1")
    with bridge_cfg(settings=READ) as (ws, mock, path):
        r = ask(ws, {"a": "ma2_read"})
        assert r["ok"], r
        assert [g["name"] for g in r["groups"]][:3] == ["HEAD STAGE", "ACME FRONT", "BAR ALL"]
        assert [p["name"] for p in r["colors"]] == ["red", "green", "blue", "cyan", "yellow", "magenta", "White"]
        assert r["positions"] == []


def test_real_echo_does_not_make_an_empty_slot_look_taken():
    from commands import exec_verdict, group_slot_empty
    from safety import DEFAULT_MA2 as D
    import re
    empty = lambda cmd: f"Executing : {cmd}\nWARNING, NO OBJECTS FOUND FOR LIST\n [Group]>"
    assert exec_verdict(empty("List Executor 1.101"), "1.101", re.compile(r"(?i)no objects? found"))[0] == "empty"
    assert group_slot_empty(empty("List Group 9"), 9, D["group_regex"], D["group_empty_regex"])
    taken = "Executing : List Group 1\n        No.  Name        Info  \nGroup 1 1    HEAD STAGE\n [Group]>"
    assert not group_slot_empty(taken, 1, D["group_regex"], D["group_empty_regex"])


def test_executor_list_steps_down_but_refuses_unproved_coverage(bridge_cfg, monkeypatch):
    monkeypatch.setenv("MA2_MOCK_REAL", "1")
    with bridge_cfg(settings=READ) as (ws, mock, path):
        r = ask(ws, {"a": "scenes_import"})
        lists = [c for c in mock.received if c.startswith("List Executor")]
        assert lists[0].endswith(".250") and lists[1].endswith(".200"), lists
        assert not r["ok"] and "охват" in r["err"], r
