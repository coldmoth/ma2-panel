"""Task 1: show identity, isolated plans, safe fixture reads."""
import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import bridge
from fixtures import parse_export, merge_fixtures
from safety import effective_safety, make_guard
from show_plans import plan_path
from test_bridge import bridge_cfg, ask, until  # noqa: F401

EXPORT = 'Export Fixture 1 Thru 9999 "panel_fixtures"'
READ = {'safety': {'mode': 'full', 'allow_fixture_read': True}}


@pytest.mark.parametrize('key', ['fixture_id', 'id'])
def test_xml_variants(key):
    found = parse_export(f'<MA xmlns="urn:ma"><Fixture {key}="12" name="Front" type="Spot">'
                         '<Attribute name="Dimmer"/><Channel name="Pan"/>'
                         '<SubAttribute name="Dimmer"/></Fixture></MA>')
    assert found == [{'id': 12, 'name': 'Front', 'type': 'Spot', 'params': ['Dimmer', 'Pan'], 'address': None}]


@pytest.mark.parametrize('text', ['<x', '<MA/>', '<MA><Fixture id="1"/><Fixture fixture_id="1"/></MA>',
                                  '<MA><Fixture index="0" name="A"/></MA>'])  # a bare index is a pool position, never an id
def test_invalid_xml(text):
    with pytest.raises(ValueError):
        parse_export(text)


def test_merge_display_and_metadata():
    old = [{'id': 12, 'label': 'Manual', 'x': .1, 'y': .2, 'color': 'cmy', 'moves': True, 'beam': {'home': 1}}, {'id': 2}]
    before = json.dumps(old)
    merged = merge_fixtures(old, [{'id': 12, 'name': 'MA', 'type': 'Spot', 'params': ['Pan'], 'address': '1.001'}])
    assert next(f for f in merged if f['id'] == 12) == {**old[0], 'name': 'MA', 'type': 'Spot', 'params': ['Pan'], 'address': '1.001'}
    assert merged[0]['missing'] is True
    assert json.dumps(old) == before


@pytest.mark.parametrize('mode', ['test', 'store', 'full'])
def test_guard_flags_cannot_be_bypassed(mode):
    safety = effective_safety({'safety': {'mode': mode, 'allowed_fixtures': [12], 'extra_allowed_regex': ['.*']}})
    lines = {'allow_fixture_read': EXPORT, 'allow_highlight': 'Off Fixture 12',
             'allow_show_load': 'LoadShow "Demo" /nosave', 'allow_show_save': 'SaveShow'}
    for flag, line in lines.items():
        assert make_guard(safety, export_cmd=EXPORT)(line)
        guard = make_guard({**safety, flag: True}, export_cmd=EXPORT)
        assert guard(line) is None
    guard = make_guard({**safety, **dict.fromkeys(lines, True)}, export_cmd=EXPORT)
    for bad in [EXPORT + ' /o', 'Export Fixture 1 "other"', 'SaveShow "other"',
                'LoadShow "a\x00b"', 'LoadShow "a\x85b"', 'Off  Fixture 12', 'LoadShow "a"; Clear', 'Off Fixture 12 Thru 15']:
        assert guard(bad)
    other = make_guard({**safety, 'allow_highlight': True})('Off Fixture 13')
    assert (other is None) == (mode == 'full')
    assert guard('ListVar') is None and guard('ListShows') is None


@pytest.mark.parametrize('flag', ['allow_fixture_read', 'allow_highlight', 'allow_show_load', 'allow_show_save'])
@pytest.mark.parametrize('value', [1, 'true', None, []])
def test_flags_bool_only(flag, value):
    with pytest.raises(ValueError):
        bridge.validate_settings({'safety': {flag: value}})


def test_identify_and_fetch(bridge_cfg):
    with bridge_cfg(settings=READ) as (ws, mock, path):
        assert ask(ws, {'a': 'show_identify'})['ok']
        status = until_status(ws, {'a': 'show_identify'})
        assert status['show'] == {'name': mock.show_name, 'source': 'ma2'}
        result = ask(ws, {'a': 'fixtures_fetch'})
        assert result['ok'] and result['source'] == 'ma2' and result['total'] > 0
        assert Path(result['file']).name.startswith('fixture-panel_fixtures_')
        assert any(c.startswith(EXPORT[:-1] + '_') for c in mock.received)
        assert (path.parent / 'diag/last_export.xml').exists()
        assert json.loads(path.read_text())['show'] == mock.show_name  # first fetch binds the plan
        before = path.read_bytes()
        mock.export_text = '<bad'
        assert not ask(ws, {'a': 'fixtures_fetch'})['ok']
        assert path.read_bytes() == before


def until_status(ws, action):
    ws.send_json(action)
    status = until(ws, lambda m: 'status' in m)['status']
    until(ws, lambda m: 'ok' in m)
    return status


def test_unknown_mismatch_and_binding(bridge_cfg):
    with bridge_cfg(settings=READ) as (ws, mock, path):
        mock.list_garbage = True
        assert until_status(ws, {'a': 'show_identify'})['show']['name'] is None
        assert 'привяжите' in ask(ws, {'a': 'fixtures_fetch'})['err']
        assert ask(ws, {'a': 'show_bind', 'name': 'Plan'})['ok']
        assert not ask(ws, {'a': 'show_bind', 'name': 'Other'})['ok']
        assert ask(ws, {'a': 'show_bind', 'name': 'Other', 'confirm': True})['ok']
        mock.list_garbage = False
        ask(ws, {'a': 'show_identify'})
        # The desk shows another show: fetching moves to its plan (the old one is kept in shows/) and imports there.
        result = ask(ws, {'a': 'fixtures_fetch'})
        assert result['ok'] and result['switched'] == mock.show_name
        assert json.loads(path.read_text())['show'] == mock.show_name
        assert json.loads(plan_path(path.parent / 'shows', 'Other').read_text())['show'] == 'Other'


def test_plans_and_selection_reset(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        mock.show_name = 'A/Б'  # the desk has this plan's show open: plan actions are allowed
        assert ask(ws, {'a': 'show_identify'})['ok']
        assert ask(ws, {'a': 'show_bind', 'name': 'A/Б'})['ok']
        old = json.loads(path.read_text())
        assert ask(ws, {'a': 'select_fixtures', 'ids': [12]})['ok']
        before = list(mock.received)
        assert ask(ws, {'a': 'show_open_plan', 'name': 'B'})['ok']
        empty = json.loads(path.read_text())
        assert empty['show'] == 'B' and empty['fixtures'] == empty['groups'] == empty['scenes'] == empty['presets'] == []
        assert empty['pages'] == {} and empty['attrs'] == old['attrs']
        assert json.loads(plan_path(path.parent / 'shows', 'A/Б').read_text()) == old
        assert ask(ws, {'a': 'show_open_plan', 'name': 'A/Б'})['ok']
        assert json.loads(path.read_text()) == old
        ws.send_json({'a': 'dim', 'v': 10})
        assert 'ничего не выбрано' in until(ws, lambda m: 'ok' in m)['err']
        assert mock.received == before


def test_empty_plan_and_remove_tile(bridge_cfg):
    with bridge_cfg(edit=lambda cfg: cfg.update(fixtures=[], groups=[], scenes=[], presets=[])) as (ws, mock, path):
        assert ask(ws, {'a': 'show_open_plan', 'name': 'Empty'})['ok']
        assert json.loads(path.read_text())['fixtures'] == []
    with bridge_cfg() as (ws, mock, path):
        before = list(mock.received)
        assert ask(ws, {'a': 'layout_save', 'pos': [{'id': 12, 'x': None, 'y': None}]})['ok']
        assert mock.received == before


def test_manual_import(tmp_path, monkeypatch):
    cfg = json.loads(Path('tests/config.test.json').read_text())
    cfg['show'] = 'Demo'
    cfg['ma2']['export_dir'] = str(tmp_path)
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(cfg))
    with TestClient(bridge.create_app(cfg, True, str(path))) as client:
        time.sleep(.1)
        monkeypatch.setattr(bridge, 'is_loopback', lambda request: False)
        xml = '<MA><Fixture id="99" name="New"/></MA>'
        assert client.post('/api/fixtures/import_file', content=xml).status_code == 403
        monkeypatch.setattr(bridge, 'is_loopback', lambda request: True)
        # The mock's current show must match the bound plan.
        # No command is sent by this endpoint.
        client.app.state.mock.show_name = 'Demo'
        with client.websocket_connect('/ws') as ws:
            ask(ws, {'a': 'show_identify'})
        before = list(client.app.state.mock.received)
        r = client.post('/api/fixtures/import_file', content=xml).json()
        assert r['ok'] and r['source'] == 'file'
        assert client.app.state.mock.received == before
        with zipfile.ZipFile(io.BytesIO(client.get('/api/diag.zip').content)) as archive:
            assert archive.read('diag/last_export.xml').decode() == xml
        assert client.get('/api/log').json()[0]['a'] == 'fixtures_import_file'


def test_fetch_requires_flag_even_full(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        before = path.read_bytes(), list(mock.received)
        assert 'allow_fixture_read' in ask(ws, {'a': 'fixtures_fetch'})['err']
        assert (path.read_bytes(), mock.received) == before
        assert not ask(ws, {'a': 'import_fixtures'})['ok']


@pytest.mark.parametrize('fresh', [False, True])
def test_export_search_freshness(bridge_cfg, tmp_path, fresh):
    import os
    other = tmp_path / 'other'
    other.mkdir()
    target = other / 'fixture-panel_fixtures.xml'
    target.write_text('<MA><Fixture id="99"/></MA>')
    os.utime(target, (1, 1))
    settings = {**READ, 'ma2': {'export_search': [str(other)], 'export_wait': .3}}
    with bridge_cfg(settings=settings) as (ws, mock, path):
        # Export goes to another drive. A stale file there must not be accepted.
        mock.export_dir = str(other) if fresh else None
        before = path.read_bytes()
        result = ask(ws, {'a': 'fixtures_fetch'})
        assert result['ok'] is fresh
        if fresh:
            assert Path(result['file']).parent == other and Path(result['file']) != target
        else:
            assert path.read_bytes() == before
        assert sum(c.startswith(EXPORT[:-1] + '_') for c in mock.received) == 1


def test_export_search_finds_console_fixtures_folder(bridge_cfg, tmp_path):
    install = tmp_path / 'grandma' / 'gma2_V_3.9.63'
    (install / 'importexport').mkdir(parents=True)
    fixtures = install / 'fixtures'
    fixtures.mkdir()
    settings = {**READ, 'ma2': {'export_search': [str(install.parent / '*' / 'importexport')]}}
    with bridge_cfg(settings=settings) as (ws, mock, path):
        mock.fixture_dir = str(fixtures)
        result = ask(ws, {'a': 'fixtures_fetch'})
        assert result['ok'], result
        assert Path(result['file']).parent == fixtures
        assert json.loads(path.read_text())['fixtures_read']['source'] == 'ma2'
        assert sum(c.startswith(EXPORT[:-1] + '_') for c in mock.received) == 1


def test_delayed_export_is_awaited(bridge_cfg, monkeypatch):
    import asyncio
    from mock import MockMA2
    original = MockMA2._reply
    def reply(mock, text):
        if text.startswith(EXPORT[:-1] + '_'):
            folder = mock.export_dir
            mock.export_dir = None
            result = original(mock, text)
            mock.export_dir = folder
            async def write():
                await asyncio.sleep(.25)
                (Path(folder) / f"fixture-{text.split(chr(34))[1]}.xml").write_text('<MA><Fixture id="99"/></MA>')
            asyncio.create_task(write())
            return result
        return original(mock, text)
    monkeypatch.setattr(MockMA2, '_reply', reply)
    with bridge_cfg(settings={**READ, 'ma2': {'export_wait': 1}}) as (ws, mock, path):
        assert ask(ws, {'a': 'fixtures_fetch'})['ok']
        assert sum(c.startswith(EXPORT[:-1] + '_') for c in mock.received) == 1


def test_show_open_resets_all_sessions(tmp_path):
    from test_safety import tabs
    with tabs(tmp_path, {'safety': {'mode': 'full'}}) as ((a, b), mock, client, path):
        assert ask(a, {'a': 'select_fixtures', 'ids': [12]})['ok']
        assert ask(b, {'a': 'select_fixtures', 'ids': [14]})['ok']
        before = list(mock.received)
        assert ask(a, {'a': 'show_open_plan', 'name': 'Mock show'})['ok']  # the desk's own show: a new, empty plan
        b.send_json({'a': 'dim', 'v': 10})
        assert 'ничего не выбрано' in until(b, lambda m: 'ok' in m)['err']
        assert mock.received == before


@pytest.mark.parametrize('reply', ['$SHOWFILE = "Quoted show"\r\n[Channel]>', '???\r\n[Channel]>', 'Error: denied\r\n[Channel]>'])
def test_identification_reply_and_raw(bridge_cfg, monkeypatch, reply):
    from mock import MockMA2
    original = MockMA2._reply
    monkeypatch.setattr(MockMA2, '_reply', lambda mock, text: reply if text == 'ListVar' and 'ListVar' in mock.received[:-1] else original(mock, text))  # login check first
    with bridge_cfg() as (ws, mock, path):
        status = until_status(ws, {'a': 'show_identify'})
        expected = {'name': 'Quoted show', 'source': 'ma2'} if reply.startswith('$') else {'name': None, 'source': 'unknown'}
        assert status['show'] == expected


def test_export_save_failure_keeps_live_config(bridge_cfg, monkeypatch):
    with bridge_cfg(settings=READ) as (ws, mock, path):
        before = path.read_bytes()
        def fail(*args):
            raise OSError('disk full')
        monkeypatch.setattr(bridge, 'save_config', fail)
        assert not ask(ws, {'a': 'fixtures_fetch'})['ok']
        assert path.read_bytes() == before
        # A fixture absent from the failed XML import remains selectable.
        assert ask(ws, {'a': 'select_fixtures', 'ids': [14]})['ok']


def test_panel_scripts_v4():
    import shutil
    import subprocess
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is needed for the panel script smoke test')
    result = subprocess.run([node, 'tests/panel-v4.cjs'], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_fixture_flag_rot(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        assert ask(ws, {'a': 'fixture_flag', 'id': 12, 'rot': 90})['ok']
        assert [f for f in json.loads(path.read_text())['fixtures'] if f['id'] == 12][0]['rot'] == 90
        assert not ask(ws, {'a': 'fixture_flag', 'id': 12, 'rot': 45})['ok']
        assert not ask(ws, {'a': 'fixture_flag', 'id': 12, 'rot': True})['ok']


def test_head_guess_and_same_type(bridge_cfg):
    from fixtures import guess_head, merge_fixtures
    assert guess_head("5 Oxygen Mode 1") and not guess_head("4 Mini-B Basic RGBW") and not guess_head("8 PAR 14X15 SLIM 10 ch")
    got = merge_fixtures([{"id": 2, "label": "x", "moves": False}],
                         [{"id": 1, "name": "a", "type": "Oxygen", "address": None}, {"id": 2, "name": "b", "type": "Oxygen", "address": None}])
    assert got[0]["moves"] is True and got[0]["moves_auto"] is True and got[1]["moves"] is False
    with bridge_cfg(lambda cfg: [f.update(type="T1") for f in cfg["fixtures"] if f["id"] in (10, 11)]) as (ws, mock, path):
        assert ask(ws, {"a": "fixture_flag", "id": 10, "moves": True, "same_type": True})["ok"]
        fx = {f["id"]: f for f in json.loads(path.read_text())["fixtures"]}
        assert fx[10]["moves"] and fx[11]["moves"] and not fx[1].get("moves")
        assert not ask(ws, {"a": "fixture_flag", "id": 10, "service": True, "same_type": True})["ok"]
