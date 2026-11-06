import json
from pathlib import Path

import pytest

from ma2panel.commands import load_config
from ma2panel.fixtures import merge_fixtures, parse_export, save_config


def test_parse_sample():
    found = parse_export(Path("ma2panel/resources/mock/sample_export.xml").read_text())
    assert [f["id"] for f in found] == [1, 2, 12, 99]
    assert found[2] == {"id": 12, "name": "Front", "type": "ACME", "params": [], "address": "2.001"}
    assert found[3]["address"] is None


@pytest.mark.parametrize("text", ["<x", "<MA/>"])
def test_parse_bad(text):
    with pytest.raises(ValueError):
        parse_export(text)


def test_merge_keeps_manual():
    old = [{"id": 12, "label": "Фронт левый", "x": 0.1, "y": 0.2}, {"id": 5, "label": "BAR 5"}]
    found = [{"id": 12, "name": "Front", "type": "ACME", "params": [], "address": "2.001"},
             {"id": 99, "name": "New", "type": "PAR", "address": None}]
    merged = merge_fixtures(old, found)
    assert [f["id"] for f in merged] == [5, 12, 99]
    assert merged[0]["missing"] is True
    assert merged[1] == {**old[0], "name": "Front", "type": "ACME", "params": [], "address": "2.001"}
    assert merged[2] == {"id": 99, "label": "New", "name": "New", "params": [], "type": "PAR", "address": None}
    assert "missing" not in old[1]


def test_merge_keeps_calibration():
    old = [{"id": 12, "label": "ACME 12", "moves": True, "beam": {"home": 40, "invert": True}}]
    found = [{"id": 12, "name": "ACME", "type": "acme", "address": "1.101"}]
    m = merge_fixtures(old, found)[0]
    assert m["moves"] is True and m["beam"] == {"home": 40, "invert": True}


def test_merge_unmissing():
    merged = merge_fixtures([{"id": 12, "label": "Manual", "missing": True}],
                            [{"id": 12, "name": "", "type": "BAR", "address": None},
                             {"id": 99, "name": "", "type": "", "address": None}])
    assert "missing" not in merged[0]
    assert merged[1]["label"] == "#99"


def test_save_atomic(tmp_path, monkeypatch):
    from ma2panel import fixtures
    cfg = json.loads(Path("tests/config.test.json").read_text())
    path = tmp_path / "config.json"
    path.write_text("old")
    replace = fixtures.os.replace
    def checked_replace(src, dst):
        assert path.read_text() == "old"
        assert Path(src).parent == tmp_path
        replace(src, dst)
    monkeypatch.setattr(fixtures.os, "replace", checked_replace)
    save_config(str(path), cfg)
    assert load_config(str(path)) == cfg
    assert list(tmp_path.iterdir()) == [path]


def test_merge_moves_place_to_repatched_number():
    old = [{"id": 5, "label": "Левый", "name": "PAR L", "type": "par", "x": 0.2, "y": 0.3, "flip_pan": True}]
    found = [{"id": 31, "name": "PAR L", "type": "par", "address": "1.400"}]
    assert merge_fixtures(old, found) == [{"id": 31, "label": "Левый", "name": "PAR L", "type": "par", "x": 0.2, "y": 0.3,
                                           "flip_pan": True, "params": [], "address": "1.400", "repatched_from": 5}]
    two = old + [{"id": 6, "name": "PAR L", "type": "par"}]
    assert {f["id"] for f in merge_fixtures(two, found)} == {5, 6, 31}  # ambiguous: nothing is moved


def test_export_reports_fixtures_without_id():
    xml = ('<MA><Fixture fixture_id="1" name="A"><FixtureType name="t"/></Fixture>'
           '<Fixture index="5" name="L-4 WINDOW" channel_id="301"><FixtureType name="t"/></Fixture></MA>')
    skipped = []
    assert [f["id"] for f in parse_export(xml, skipped)] == [1] and skipped == ["L-4 WINDOW"]
