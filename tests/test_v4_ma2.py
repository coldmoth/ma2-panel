"""Task 3: MA2 catalogues and guarded, empty-slot-only group storage."""
import asyncio
import json
import threading

import pytest

from ma2panel import bridge
from ma2panel.safety import DEFAULT_MA2, effective_safety, make_guard
from test_bridge import FULL, ask, bridge_cfg, until  # noqa: F401
from test_safety import tabs

STORE = {'safety': {'mode': 'full', 'allow_group_store': True}}
IMPORT = {'a': 'ma2_import', 'groups': [1], 'colors': True, 'positions': True, 'scenes': False}


def test_read_defaults_and_no_writes(bridge_cfg):
    assert DEFAULT_MA2['preset_types'] == {'color': 4, 'position': 2}
    with bridge_cfg(settings={}) as (ws, mock, path):
        before = path.read_bytes()
        result = ask(ws, {'a': 'ma2_read'})
        assert result['ok'], result
        assert result['groups'] == [{'n': 1, 'name': 'Front'}]
        assert result['colors'] == [{'n': 1, 'name': 'Red'}]
        assert result['positions'] == [{'n': 1, 'name': 'Stage'}]
        assert result['raw']
        assert mock.received[-3:] == ['List Group 1 Thru 999', 'List Preset 4.1 Thru 4.999', 'List Preset 2.1 Thru 2.999']
        assert path.read_bytes() == before


def test_unrecognised_read_and_import_keep_config(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        mock.list_garbage = True
        before = path.read_bytes()
        for action in ({'a': 'ma2_read'}, IMPORT):
            result = ask(ws, action)
            assert result['ok'] is False
            if action['a'] == 'ma2_read':
                assert '???' in str(result['raw'])
            else:
                assert 'шоу' in result['err']
        assert path.read_bytes() == before


def test_import_broadcasts_separate_catalogues_and_scenes(tmp_path):
    with tabs(tmp_path, {**FULL, "safety": {**FULL["safety"], "allow_fixture_read": True}}) as ((a, b), mock, client, path):
        before = json.loads(path.read_text())
        mock.rows['1.103'] = 'Imported scene'
        result = ask(a, {**IMPORT, 'scenes': True})
        assert result['ok'], result
        config = until(b, lambda m: 'config' in m)['config']
        saved = json.loads(path.read_text())
        assert config['ma2groups'] == saved['ma2groups'] == [{'n': 1, 'name': 'Front', 'ids': [1, 2]}]
        assert config['ma2presets'] == saved['ma2presets'] == {'colors': [{'n': 1, 'name': 'Red'}], 'positions': [{'n': 1, 'name': 'Stage'}]}
        assert saved['groups'] == before['groups']
        assert any(s['exec'] == '1.103' for s in saved['scenes'])
        assert client.get('/api/log').json()[0]['a'] == 'ma2_import'


def test_import_only_selected_and_save_failure(bridge_cfg, monkeypatch):
    with bridge_cfg() as (ws, _, path):
        before = path.read_bytes()
        def fail(*args):
            raise OSError('disk full')
        monkeypatch.setattr(bridge, 'save_config', fail)
        assert not ask(ws, IMPORT)['ok']
        assert path.read_bytes() == before
        monkeypatch.undo()
        assert ask(ws, {'a': 'layout_save', 'pos': [{'id': 12, 'x': .2, 'y': .3}]})['ok']
        assert not json.loads(path.read_text()).get('ma2groups')
        assert ask(ws, {**IMPORT, 'groups': [], 'positions': False})['ok']
        saved = json.loads(path.read_text())
        assert saved['ma2groups'] == []
        assert saved['ma2presets'] == {'colors': [{'n': 1, 'name': 'Red'}], 'positions': []}


def catalogue(cfg):
    cfg['ma2groups'] = [{'n': 7, 'name': 'Heads', 'ids': [12, 13]}]
    cfg['ma2presets'] = {'colors': [{'n': 3, 'name': 'Blue'}], 'positions': [{'n': 2, 'name': 'Stage'}]}


def test_go_validates_membership_and_selection(bridge_cfg):
    with bridge_cfg(catalogue, settings={"safety": {"mode": "full", "allow_fixture_read": True}}) as (ws, mock, _):
        mock.groups[7] = "Current"
        mock.group_members[7] = [12, 13]
        assert not ask(ws, {'a': 'ma2_preset_go', 'type': 'color', 'n': 3})['ok']
        assert ask(ws, {'a': 'ma2_group_go', 'n': 7})['ok']
        assert mock.received[-1] == 'Group 7'
        assert ask(ws, {'a': 'ma2_preset_go', 'type': 'color', 'n': 3})['ok']
        assert mock.received[-2:] == ['Fixture 12 + 13', 'At Preset 4.3']
        assert ask(ws, {'a': 'ma2_preset_go', 'type': 'position', 'n': 2})['ok']
        assert mock.received[-1] == 'At Preset 2.2'
        before = list(mock.received)
        for action in ({'a': 'ma2_group_go', 'n': 8}, {'a': 'ma2_group_go', 'n': True},
                       {'a': 'ma2_preset_go', 'type': 'color', 'n': 2},
                       {'a': 'ma2_preset_go', 'type': 'gobo', 'n': 3}):
            assert not ask(ws, action)['ok']
        assert mock.received == before


@pytest.mark.parametrize('mode', ['test', 'store', 'full'])
def test_store_guard_requires_flag_even_with_extra_regex(mode):
    safety = effective_safety({'safety': {'mode': mode, 'extra_allowed_regex': ['.*']}})
    assert make_guard(safety)('Store Group 8 "Front"')
    guard = make_guard({**safety, 'allow_group_store': True})
    assert guard('Store Group 8 "Front"') is None
    for suffix in (' /Overwrite', ' /o', ' /merge', ' /noconfirm', '; Clear', '\nClear'):
        assert guard('Store Group 8 "Front"' + suffix)
    for line in ('List Group 8', 'List Group 1 Thru 999', 'List Preset 4.1 Thru 4.999', 'Group 8', 'At Preset 4.3'):
        assert make_guard(effective_safety({}))(line) is None


@pytest.mark.parametrize('value', [None, 0, 1, 'true', [], {}])
def test_store_flag_must_be_bool(value):
    with pytest.raises(ValueError):
        bridge.validate_settings({'safety': {'allow_group_store': value}})


def test_group_store_empty_slot_and_mock_persistence(bridge_cfg):
    with bridge_cfg(settings=STORE) as (ws, mock, path):
        group = json.loads(path.read_text())['groups'][0]
        result = ask(ws, {'a': 'group_store_ma2', 'id': group['id'], 'n': 8, 'confirm': 8})
        assert result['ok'], result
        assert mock.received[-3:] == ['List Group 8', 'Fixture ' + ' + '.join(map(str, group['fixtures'])), f'Store Group 8 "{group["label"]}"']
        assert not ask(ws, {'a': 'group_store_ma2', 'id': group['id'], 'n': 8, 'confirm': 8})['ok']
        assert mock.received[-1] == 'List Group 8'
        result = ask(ws, {'a': 'ma2_read'})
        assert {'n': 8, 'name': group['label']} in result['groups']


@pytest.mark.parametrize('settings,number,confirm,garbage', [(FULL, 8, 8, False), (STORE, 8, 7, False),
    (STORE, 1, 1, False), (STORE, 8, 8, True), (STORE, True, True, False), (STORE, '8', '8', False)])
def test_store_refuses_unsafe_requests(bridge_cfg, settings, number, confirm, garbage):
    with bridge_cfg(settings=settings) as (ws, mock, path):
        mock.list_garbage = garbage
        group = json.loads(path.read_text())['groups'][0]
        before = list(mock.received)
        assert not ask(ws, {'a': 'group_store_ma2', 'id': group['id'], 'n': number, 'confirm': confirm})['ok']
        assert not any(line.startswith(('Fixture', 'Store')) for line in mock.received[len(before):])


def test_import_waits_for_lock(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = bridge.MA2Link.send
    async def delayed(link, cmd, *args, **kwargs):
        if cmd == 'Goto Cue 1 Executor 1.101 Fade 0':
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.01)
        return await original(link, cmd, *args, **kwargs)
    monkeypatch.setattr(bridge.MA2Link, 'send', delayed)
    with tabs(tmp_path, {**FULL, "safety": {**FULL["safety"], "allow_fixture_read": True}}) as ((a, b), _, client, path):
        before = path.read_bytes()
        a.send_json({'a': 'scene_go', 'id': 'pianist'})
        assert entered.wait(3)
        b.send_json(IMPORT)
        try:
            assert client.get('/api/idle').json()['idle'] is False
            assert path.read_bytes() == before
        finally:
            release.set()
        assert until(a, lambda m: 'ok' in m)['ok']
        assert until(b, lambda m: 'ok' in m)['ok']
        assert json.loads(path.read_text())['ma2groups']


def test_catalogues_follow_show_plans(tmp_path):
    with tabs(tmp_path, {**FULL, "safety": {**FULL["safety"], "allow_fixture_read": True}}) as ((ws, _), mock, client, path):
        assert ask(ws, {'a': 'show_bind', 'name': 'Mock show'})['ok']
        assert ask(ws, IMPORT)['ok']
        assert ask(ws, {'a': 'show_open_plan', 'name': 'Other show'})['ok']
        saved = json.loads(path.read_text())
        assert saved.get('ma2groups', []) == []
        assert saved.get('ma2presets', {'colors': [], 'positions': []}) == {'colors': [], 'positions': []}
        assert not ask(ws, {'a': 'ma2_group_go', 'n': 1})['ok']
        assert ask(ws, {'a': 'show_open_plan', 'name': 'Mock show'})['ok']
        assert json.loads(path.read_text())['ma2groups'] == [{'n': 1, 'name': 'Front', 'ids': [1, 2]}]


@pytest.mark.parametrize('reply', ['OK\r\n[Channel]>', '[Channel]>', 'List Group 8\r\n[Channel]>',
    'Group 8 "Occupied"\r\nNo objects found\r\n[Channel]>',
    'Error: No objects found\r\n[Channel]>', '???\r\nNo objects found\r\n[Channel]>'])
def test_store_never_treats_ambiguous_reply_as_empty(bridge_cfg, monkeypatch, reply):
    with bridge_cfg(settings=STORE) as (ws, mock, path):
        original = mock._reply
        monkeypatch.setattr(mock, '_reply', lambda line: reply if line == 'List Group 8' else original(line))
        group = json.loads(path.read_text())['groups'][0]
        before = len(mock.received)
        assert not ask(ws, {'a': 'group_store_ma2', 'id': group['id'], 'n': 8, 'confirm': 8})['ok']
        assert mock.received[before:] == ['List Group 8']


def test_custom_catalogue_regexes_and_type_numbers(bridge_cfg, monkeypatch):
    settings = {'ma2': {'preset_types': {'color': 5, 'position': 3},
        'group_regex': r'(?m)^G=(?P<n>\d+);(?P<name>[^;\r\n]+);(?P<ids>[0-9,+ ]+)\r?$',
        'preset_regex': r'(?m)^P=(?P<n>\d+);(?P<name>[^\r\n]+)\r?$'}}
    with bridge_cfg(settings=settings) as (ws, mock, _):
        original = mock._reply
        replies = {'List Group 1 Thru 999': 'G=9;Heads;12,13\r\n[Channel]>',
                   'List Preset 5.1 Thru 5.999': 'P=7;Blue\r\n[Channel]>',
                   'List Preset 3.1 Thru 3.999': 'P=2;Home\r\n[Channel]>'}
        monkeypatch.setattr(mock, '_reply', lambda line: replies.get(line, original(line)))
        result = ask(ws, {'a': 'ma2_read'})
        assert result['ok'], result
        assert result['groups'] == [{'n': 9, 'name': 'Heads', 'ids': [12, 13]}]
        assert result['colors'] == [{'n': 7, 'name': 'Blue'}]
        assert result['positions'] == [{'n': 2, 'name': 'Home'}]


@pytest.mark.parametrize('action', [{'a': 'ma2_read'}, IMPORT,
    {'a': 'ma2_group_go', 'n': 7}, {'a': 'ma2_preset_go', 'type': 'color', 'n': 3},
    {'a': 'group_store_ma2', 'id': 'front', 'n': 8, 'confirm': 8}])
def test_new_actions_obey_halt_and_journal(tmp_path, action):
    with tabs(tmp_path, STORE) as ((ws, _), mock, client, _):
        assert ask(ws, {'a': 'halt'})['ok']
        before = list(mock.received)
        assert not ask(ws, action)['ok']
        assert mock.received == before
        entry = client.get('/api/log').json()[0]
        assert entry['a'] == action['a'] and not entry['ok']
        assert entry['what'] == {k: v for k, v in action.items() if k != 'a'}


def test_store_obeys_allowed_fixtures_and_unsafe_template(bridge_cfg):
    for settings in ({'safety': {'allow_group_store': True, 'allowed_fixtures': [12]}},
                     {**STORE, 'ma2': {'group_store_cmd': 'Store Group {n} "{name}" /merge'}}):
        with bridge_cfg(settings=settings) as (ws, mock, _):
            before = list(mock.received)
            assert not ask(ws, {'a': 'group_store_ma2', 'id': 'front', 'n': 8, 'confirm': 8})['ok']
            assert mock.received == before


@pytest.mark.parametrize('key', ['group_regex', 'preset_regex'])
def test_catalogue_regex_needs_named_groups(key):
    with pytest.raises(ValueError):
        bridge.validate_settings({'ma2': {key: r'(.+)'}})


def test_group_go_needs_known_members(bridge_cfg):
    def unknown(cfg):
        cfg['ma2groups'] = [{'n': 5, 'name': 'Blind'}]
    with bridge_cfg(unknown) as (ws, mock, _):
        before = list(mock.received)
        reply = ask(ws, {'a': 'ma2_group_go', 'n': 5})
        assert not reply['ok'] and 'состав' in reply['err']
        assert all(line.startswith(('List ', 'ListVar')) for line in mock.received[len(before):])


@pytest.mark.parametrize('pattern', ['.*', '(?s).*', '.+'])
def test_permissive_empty_pattern_is_rejected(pattern):
    with pytest.raises(ValueError, match='занятой группе'):
        bridge.validate_settings({'ma2': {'group_empty_regex': pattern}})


def test_heads_from_export_params_can_move():
    from ma2panel.commands import can_move
    assert can_move({'params': ['DIM', 'PAN', 'TILT']}) and can_move({'moves': True})
    assert not can_move({'params': ['DIM', 'COLORRGB1']}) and not can_move({})


def test_row_naming_the_group_is_never_empty():
    from ma2panel.commands import group_slot_empty
    assert not group_slot_empty('Group 11 "Choir"\r\n[Channel]>', 11, r'(?!x)x', r'.*')
    assert group_slot_empty('No objects found\r\n[Channel]>', 11, DEFAULT_MA2['group_regex'], DEFAULT_MA2['group_empty_regex'])


def test_group_members_from_export_and_forget(bridge_cfg):
    from ma2panel.fixtures import parse_group_export
    xml = '<MA><Group index="1" name="B"><Subfixture fix_id="5"/><Subfixture fix_id="6"/><Subfixture cha_id="9"/></Group></MA>'
    assert parse_group_export(xml, {2: 'B'}) == {2: [5, 6]}
    assert parse_group_export(xml, {1: 'B'}) == {1: [5, 6]}  # index is the number itself when the names say so
    with bridge_cfg(settings={'safety': {'mode': 'full', 'allow_fixture_read': True}}) as (ws, mock, path):
        assert ask(ws, IMPORT)['ok']
        assert any(line.startswith('Export Group 1 Thru 999 "panel_groups_') for line in mock.received)
        assert json.loads(path.read_text())['ma2groups'] == [{'n': 1, 'name': 'Front', 'ids': [1, 2]}]
        assert ask(ws, {'a': 'group_delete', 'n': 1})['ok']
        assert json.loads(path.read_text())['ma2groups'] == []
        assert not ask(ws, {'a': 'group_delete', 'n': 1})['ok']
