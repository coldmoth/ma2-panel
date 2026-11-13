"""The independent quality desk supports the public 3.3 scene/Grand protocol."""
import pytest
from ma2panel import mock as model
from ma2panel.mock import MockMA2
from ma2panel.mock_console import validate, is_read_only
from ma2panel.scene_runtime import probe_command


def desk():
    value = MockMA2('qa', None)
    value.configure_simulation({'fixtures': [{'id': 1}, {'id': 2}]})
    value.strict_console = True
    return value


def send(value, *lines):
    for line in lines:
        assert 'Error' not in value._reply(line), line


def test_strict_quality_desk_stores_selected_scene_and_restores_grand():
    value = desk()
    send(value, 'Fixture 1', 'At 80', 'Attribute "ColorRGB2" At 0',
         'Store Executor 1.23 Cue 1 /Source=Output /Use=Allforselected',
         'Assign Cue 1 Executor 1.23 /Trig=Go', probe_command('1.23', 'a' * 16),
         'ClearAll', 'Goto Cue 1 Executor 1.23 Fade 0')
    assert value.simulation_output()[1]['dim'] == 80
    assert value.simulation_output()[1]['rgb'] == [100, 0, 100]
    assert value.simulation_output()[2]['dim'] == 0
    send(value, 'SpecialMaster 2.1 At 0')
    assert value.simulation_output()[1]['dim'] == 0
    send(value, 'SpecialMaster 2.1 At 75')
    assert value.simulation_output()[1]['dim'] == 60


def test_outgoing_off_does_not_erase_incoming_scene_fade(monkeypatch):
    from types import SimpleNamespace
    clock = [100.0]
    monkeypatch.setattr(model, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    value = desk()
    value.sim_scenes = {'1.1': {1: {'dim': 20}}, '1.2': {1: {'dim': 80}}}
    send(value, 'Goto Cue 1 Executor 1.1 Fade 0', 'Masterfade 2 Executor 1.1',
         'Goto Cue 1 Executor 1.2 Fade 2', 'Off Executor 1.1')
    clock[0] += 1
    assert value.simulation_output()[1]['dim'] == 50
    clock[0] += 1
    assert value.simulation_output()[1]['dim'] == 80


def test_scene_probe_is_read_only_but_modified_lua_is_rejected():
    command = probe_command('1.23', 'a' * 16)
    assert is_read_only(command)
    assert validate(command, []) is None
    assert validate(command[:-1] + ';gma.cmd("At 0")"', [])


@pytest.mark.parametrize('line', ['Store Executor 1.23 Cue 1 /Overwrite',
    'SpecialMaster 2.1 At 101', 'Lua "os.execute(\'anything\')"',
    'Assign Cue 1 Executor 1.23 /Trig=Time', 'DoInventedThing'])
def test_strict_quality_desk_keeps_unknown_and_unsafe_commands_rejected(line):
    assert validate(line, [1])


def test_demo_fixture_identity_survives_console_reimport(tmp_path):
    import json
    from pathlib import Path
    from scripts.concert_demo import demo_data, seed_mock
    from ma2panel.fixtures import parse_export, merge_fixtures
    cfg = json.loads(Path('ma2panel/resources/config.example.json').read_text())
    settings = json.loads(Path('ma2panel/resources/settings.example.json').read_text())
    cfg, _ = demo_data(cfg, settings, tmp_path, (12345, 12346))
    value = MockMA2('qa', str(tmp_path))
    seed_mock(value, cfg, tmp_path)
    found = parse_export(value.export_text)
    merged = merge_fixtures(cfg['fixtures'], found)
    assert len(merged) == 60
    assert not any(f.get('ambiguous_candidates') for f in merged)
    assert [f.get('name') for f in cfg['fixtures']] == [f['name'] for f in found]
