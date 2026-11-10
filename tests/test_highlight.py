"""Plan editor highlight: bounded commands, ownership and recovery on the mock."""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ma2panel import bridge
from ma2panel.commands import select_line
from test_bridge import ask, until, bridge_cfg  # noqa: F401
from test_safety import tabs
from test_v3 import until_status

SETTINGS = {'safety': {'mode': 'test', 'allowed_fixtures': [12, 14, 15, 16], 'allow_highlight': True},
            'highlight': {'exclude': [16], 'level': 80, 'lease_s': 10}}
ZONE = [12, 14]
OFF = [select_line(ZONE), 'Off ' + select_line(ZONE)]


def edit(cfg):
    next(f for f in cfg['fixtures'] if f['id'] == 15)['service'] = True
    next(f for f in cfg['fixtures'] if f['id'] == 12)['type'] = '3 Spot'  # strobe comes from the type (spec 24)
    cfg['dmx_map'] = {'3 Spot': {'has': ['strobe'], 'strobe': {'attr': 'SHUTTER', 'open': 12.5, 'from': 25.1, 'to': 100.0}}}


def start(ws, id_=12):
    assert ask(ws, {'a': 'edit_begin'})['ok']
    assert ask(ws, {'a': 'highlight', 'id': id_})['ok']


def wait_for(predicate):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.02)
    assert predicate()


def test_highlight_lines_restore_and_journal(bridge_cfg):
    with bridge_cfg(edit, SETTINGS) as (ws, mock, path):
        ask(ws, {'a': 'select_fixtures', 'ids': [12]})
        ws.send_json({'a': 'dim', 'v': 37})
        ask(ws, {'a': 'clear'})  # flush the slider
        before = len(mock.received)
        start(ws)
        assert mock.received[before:] == ['Fixture 14', 'At 0', 'Fixture 12', 'At 80']
        saved = json.loads((path.parent / 'highlight.json').read_text())
        assert saved['zone'] == ZONE and saved['target'] == 12 and saved['show'] == mock.show_name
        assert ask(ws, {'a': 'highlight', 'id': 14})['ok']
        assert mock.received[-4:] == ['Fixture 12', 'At 0', 'Fixture 14', 'At 80']
        before = len(mock.received)
        assert ask(ws, {'a': 'highlight_off'})['ok']
        assert mock.received[before:before + 4] == OFF + ['Fixture 12', 'At 37']
        assert not (path.parent / 'highlight.json').exists()
        assert until_status(ws, {'a': 'show_identify'})['highlight']['state'] == 'idle'


def test_restore_skips_values_the_panel_never_sent(bridge_cfg):
    with bridge_cfg(edit, SETTINGS) as (ws, mock, path):
        ask(ws, {'a': 'select_fixtures', 'ids': [14]})
        ws.send_json({'a': 'color', 'r': 100, 'g': 0, 'b': 0})
        ask(ws, {'a': 'clear'})  # flush the slider; shown now holds a display default dim 100 for 14
        start(ws)
        before = len(mock.received)
        assert ask(ws, {'a': 'highlight_off'})['ok']
        restored = mock.received[before + 2:]
        assert 'At 100' not in restored and any(line.startswith('Attribute "ColorRGB1"') for line in restored)


@pytest.mark.parametrize('case', ['flag', 'editor', 'excluded', 'service', 'missing', 'empty'])
def test_highlight_refusals(bridge_cfg, case):
    settings = {**SETTINGS, 'safety': dict(SETTINGS['safety'])}
    if case == 'flag':
        settings['safety'].update(mode='full', allow_highlight=False)
    def configure(cfg):
        edit(cfg)
        if case == 'missing':
            next(f for f in cfg['fixtures'] if f['id'] == 12)['missing'] = True
        if case == 'empty':
            cfg['fixtures'] = []
    with bridge_cfg(configure, settings) as (ws, mock, path):
        if case != 'editor':
            assert ask(ws, {'a': 'edit_begin'})['ok']
        before = list(mock.received)
        target = {'excluded': 16, 'service': 15}.get(case, 12)
        assert not ask(ws, {'a': 'highlight', 'id': target})['ok']
        assert mock.received == before and not (path.parent / 'highlight.json').exists()


def test_owner_and_disconnect(tmp_path):
    settings = {**SETTINGS, 'highlight': {'exclude': [15, 16]}}
    with tabs(tmp_path, settings) as ((a, b), mock, client, path):
        start(a)
        assert ask(b, {'a': 'edit_begin'})['ok']
        before = list(mock.received)
        assert 'другое устройство' in ask(b, {'a': 'highlight', 'id': 14})['err']
        assert not ask(b, {'a': 'highlight_off'})['ok']
        assert mock.received == before
        a.__exit__(None, None, None)
        # The mock records Off before the bridge receives its reply and clears the journal.
        wait_for(lambda: mock.received[-2:] == OFF and not (path.parent / 'highlight.json').exists())
        assert not (path.parent / 'highlight.json').exists()


def test_lease_and_ping(bridge_cfg):
    settings = {**SETTINGS, 'highlight': {**SETTINGS['highlight'], 'lease_s': .35}}
    with bridge_cfg(edit, settings) as (ws, mock, path):
        start(ws)
        for _ in range(3):
            time.sleep(.15)
            assert ask(ws, {'a': 'highlight_ping'})['ok']
            assert (path.parent / 'highlight.json').exists()
        # The mock records Off before the bridge receives its reply and clears the journal.
        wait_for(lambda: mock.received[-2:] == OFF and not (path.parent / 'highlight.json').exists())
        assert not (path.parent / 'highlight.json').exists()


@pytest.mark.parametrize('reason', ['link_drop', 'halt'])
def test_stuck_and_recovery(bridge_cfg, reason):
    with bridge_cfg(edit, SETTINGS) as (ws, mock, path):
        start(ws)
        assert ask(ws, {'a': reason})['ok']
        before = list(mock.received)
        assert not ask(ws, {'a': 'highlight_off'})['ok']
        assert (path.parent / 'highlight.json').exists()
        if reason != 'halt':
            assert until_status(ws, {'a': 'show_identify'})['highlight']['state'] == 'stuck'
        assert mock.received == before
        assert ask(ws, {'a': 'link_connect' if reason == 'link_drop' else 'resume'})['ok']
        # Reconnect and resume send nothing by themselves: Off would wipe what the operator set on the desk.
        wait_for(lambda: until_status(ws, {'a': 'show_identify'})['ma2'] == 'logged_in')
        assert until_status(ws, {'a': 'show_identify'})['highlight']['state'] == 'stuck'
        assert not any(line.startswith('Off Fixture') for line in mock.received[len(before):])
        before = len(mock.received)
        assert not ask(ws, {'a': 'highlight_off'})['ok']
        assert len(mock.received) == before and (path.parent / 'highlight.json').exists()


@pytest.mark.parametrize('show', ['Mock show', 'Other show', None])
def test_restart_recovers_only_same_or_unknown_show(tmp_path, show):
    cfg = json.loads(Path('tests/config.test.json').read_text())
    cfg['ma2']['export_dir'] = str(tmp_path)
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(cfg))
    recovery = tmp_path / 'highlight.json'
    recovery.write_text(json.dumps({'show': show, 'zone': ZONE, 'target': 12, 't': 1}))
    with TestClient(bridge.create_app(cfg, True, str(path), SETTINGS)) as client:
        with client.websocket_connect('/ws') as ws:
            until(ws, lambda m: m.get('status', {}).get('ma2') == 'logged_in')
            status = until_status(ws, {'a': 'show_identify'})
            if show and show != client.app.state.mock.show_name:
                assert recovery.exists() and status['highlight']['state'] == 'stuck'
                assert not any(line.startswith('Off Fixture') for line in client.app.state.mock.received)
                assert not ask(ws, {'a': 'highlight_off'})['ok']
            else:  # restart never sends Off by itself; the operator's button does
                assert recovery.exists() and status['highlight']['state'] == 'stuck'
                assert not any(line.startswith('Off Fixture') for line in client.app.state.mock.received)
                status = until_status(ws, {'a': 'show_identify'})
                token = status['highlight']['release_token']
                assert ask(ws, {'a': 'highlight_off', 'release_token': token})['ok']
                assert client.app.state.mock.received.count(OFF[1]) == 1


def test_editor_exit_releases(bridge_cfg):
    with bridge_cfg(edit, SETTINGS) as (ws, mock, path):
        start(ws)
        assert ask(ws, {'a': 'edit_end'})['ok']
        assert mock.received[-2:] == OFF
        assert not (path.parent / 'highlight.json').exists()


def test_plan_switch_sends_no_off(bridge_cfg):
    with bridge_cfg(edit, SETTINGS) as (ws, mock, path):
        start(ws)
        before = len(mock.received)
        assert ask(ws, {'a': 'show_open_plan', 'name': 'New'})['ok']
        assert not any(line.startswith('Off') for line in mock.received[before:])
        assert until_status(ws, {'a': 'show_identify'})['highlight']['state'] == 'stuck'


def test_disk_failure_sends_nothing(bridge_cfg, monkeypatch):
    with bridge_cfg(edit, SETTINGS) as (ws, mock, path):
        assert ask(ws, {'a': 'edit_begin'})['ok']
        before = list(mock.received)
        def fail(*args):
            raise OSError('disk full')
        monkeypatch.setattr(bridge, 'save_config', fail)
        assert not ask(ws, {'a': 'highlight', 'id': 12})['ok']
        assert mock.received == before


def test_full_zone_and_single_fixture(bridge_cfg):
    settings = {'safety': {'mode': 'full', 'allow_highlight': True}}
    with bridge_cfg(settings=settings) as (ws, mock, path):
        start(ws)
        assert json.loads((path.parent / 'highlight.json').read_text())['zone'] == list(range(1, 25))
        assert ask(ws, {'a': 'highlight_off'})['ok']
    with bridge_cfg(lambda cfg: cfg.update(fixtures=[f for f in cfg['fixtures'] if f['id'] == 12]), settings) as (ws, mock, path):
        start(ws)
        assert mock.received[-2:] == ['Fixture 12', 'At 100']
        assert ask(ws, {'a': 'highlight_off'})['ok']
        assert mock.received[-2:] == ['Fixture 12', 'Off Fixture 12']


@pytest.mark.parametrize('reason', ['lease', 'disconnect'])
def test_release_serialized_with_slider(tmp_path, monkeypatch, reason):
    import asyncio
    original = bridge.MA2Link.send
    async def send(link, cmd, *args, **kwargs):
        result = await original(link, cmd, *args, **kwargs)
        if cmd == 'Fixture 12 + 14':
            await asyncio.sleep(.15)  # give another tab a chance to change MA2 selection
        return result
    monkeypatch.setattr(bridge.MA2Link, 'send', send)
    settings = {**SETTINGS, 'highlight': {'exclude': [15, 16], 'lease_s': .25}}
    with tabs(tmp_path, settings) as ((a, b), mock, client, path):
        start(a)
        ask(b, {'a': 'select_fixtures', 'ids': [16]})
        if reason == 'disconnect':
            a.__exit__(None, None, None)
        else:
            time.sleep(.27)
        b.send_json({'a': 'dim', 'v': 22})
        ask(b, {'a': 'clear'})
        if 'Off Fixture 12 + 14' in mock.received:
            i = mock.received.index('Fixture 12 + 14')
            assert mock.received[i:i + 2] == OFF
        else:  # the newer slider won the lock: late Off would overwrite it
            assert (path.parent / 'highlight.json').exists()


def test_release_restores_only_zone_known_attributes(bridge_cfg):
    with bridge_cfg(edit, SETTINGS, confirmed_profiles=True) as (ws, mock, path):
        ask(ws, {'a': 'select_fixtures', 'ids': [12]})
        for action in [{'a': 'color', 'r': 10, 'g': 20, 'b': 30}, {'a': 'aim', 'pan': 0, 'tilt': 0},
                       {'a': 'zoom', 'v': 25}, {'a': 'focus', 'v': 35}, {'a': 'strobe', 'v': 45}]:
            if action['a'] == 'aim':
                assert ask(ws, action)['ok']
            else:
                ws.send_json(action)
            assert ask(ws, {'a': 'select_fixtures', 'ids': [12]})['ok']
        start(ws)
        before = len(mock.received)
        assert ask(ws, {'a': 'highlight_off'})['ok']
        assert mock.received[before:] == OFF + ['Fixture 12',  # no 'At 100': the panel never sent a dim, only colour
            'Attribute "ColorRGB1" At 10', 'Attribute "ColorRGB2" At 20', 'Attribute "ColorRGB3" At 30',
            'Fixture 12', 'Attribute "Pan" At 0', 'Attribute "Tilt" At 0', 'Attribute "Zoom" At 25',
            'Attribute "Focus" At 35', 'Fixture 12', 'Attribute "SHUTTER" At 58.4']  # 45 inside the type's strobe range 25.1..100


def test_identify_does_not_end_live_highlight(bridge_cfg):
    with bridge_cfg(edit, SETTINGS) as (ws, mock, path):
        start(ws)
        before = len(mock.received)
        status = until_status(ws, {'a': 'show_identify'})
        assert status['highlight']['state'] == 'active'
        assert mock.received[before:] == ['ListVar']
        assert (path.parent / 'highlight.json').exists()


@pytest.mark.parametrize('failure', ['error', 'unknown'])
def test_failed_release_keeps_journal_and_reopens_unknown(bridge_cfg, monkeypatch, failure):
    from ma2panel.mock import MockMA2
    original = MockMA2._reply
    def reply(mock, text):
        if text.startswith('Off Fixture'):
            return 'Error: denied\r\n[Channel]>' if failure == 'error' else 'OK\r\n'
        return original(mock, text)
    with bridge_cfg(edit, {**SETTINGS, 'ma2': {'timeout': .1}}) as (ws, mock, path):
        start(ws)
        monkeypatch.setattr(MockMA2, '_reply', reply)
        before = len(mock.received)
        assert not ask(ws, {'a': 'highlight_off'})['ok']
        assert (path.parent / 'highlight.json').exists()
        assert mock.received[before:] == OFF
        status = until_status(ws, {'a': 'show_identify'})
        assert status['highlight']['state'] == 'stuck'
        monkeypatch.setattr(MockMA2, '_reply', original)
        if failure != 'error':  # the uncertain line reopens the session; the relogin itself sends no Off
            wait_for(lambda: sum(line.lower().startswith('login ') for line in mock.received) >= 2)
            wait_for(lambda: until_status(ws, {'a': 'show_identify'})['ma2'] == 'logged_in')
        before = len(mock.received)
        assert not ask(ws, {'a': 'highlight_off'})['ok']
        assert len(mock.received) == before and (path.parent / 'highlight.json').exists()


def test_restart_unknown_current_show(tmp_path, monkeypatch):
    from ma2panel.mock import MockMA2
    original = MockMA2._reply
    monkeypatch.setattr(MockMA2, '_reply', lambda mock, text: f'$USER = {mock.user}\r\n???\r\n[Channel]>' if text == 'ListVar' else original(mock, text))
    cfg = json.loads(Path('tests/config.test.json').read_text())
    cfg['ma2']['export_dir'] = str(tmp_path)
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(cfg))
    recovery = tmp_path / 'highlight.json'
    recovery.write_text(json.dumps({'show': 'Unrecognised', 'zone': ZONE, 'target': 12, 't': 1}))
    with TestClient(bridge.create_app(cfg, True, str(path), SETTINGS)) as client, client.websocket_connect('/ws') as ws:
        until(ws, lambda m: m.get('status', {}).get('ma2') == 'logged_in')
        assert until_status(ws, {'a': 'show_identify'})['highlight']['state'] == 'stuck'
        assert not any(line.startswith('Off Fixture') for line in client.app.state.mock.received)


def test_restore_template_cannot_send_outside_zone(bridge_cfg):
    settings = {**SETTINGS, 'safety': {**SETTINGS['safety'], 'mode': 'full'},
                'attrs': {'pan': {'cmd': 'Fixture 999; Attribute "Pan" At {v}'}}}
    # The existing normal action path uses user templates. Recovery must preflight them independently.
    with bridge_cfg(edit, settings) as (ws, mock, path):
        ask(ws, {'a': 'select_fixtures', 'ids': [12]})
        assert ask(ws, {'a': 'aim', 'pan': 0, 'tilt': 0})['ok']
        start(ws)
        before = list(mock.received)
        assert not ask(ws, {'a': 'highlight_off'})['ok']
        assert mock.received == before
        assert (path.parent / 'highlight.json').exists()


def test_dim_only_fixture_restores_without_color(bridge_cfg):
    def configure(cfg):
        edit(cfg)
        next(f for f in cfg['fixtures'] if f['id'] == 12)['color'] = 'none'
    with bridge_cfg(configure, SETTINGS) as (ws, mock, path):
        ask(ws, {'a': 'select_fixtures', 'ids': [12]})
        ws.send_json({'a': 'dim', 'v': 37})
        ask(ws, {'a': 'clear'})
        start(ws)
        before = len(mock.received)
        assert ask(ws, {'a': 'highlight_off'})['ok']
        assert mock.received[before:] == OFF + ['Fixture 12', 'At 37']


@pytest.mark.parametrize('newer', ['scene_go', 'dim', 'color'])
def test_newer_light_blocks_automatic_highlight_release(bridge_cfg, newer):
    with bridge_cfg(edit, {**SETTINGS, 'safety': {**SETTINGS['safety'], 'allowed_scenes': ['1.101']}}) as (ws, mock, path):
        ask(ws, {'a': 'select_fixtures', 'ids': [12]})
        ws.send_json({'a': 'dim', 'v': 40})
        ask(ws, {'a': 'clear'})
        start(ws)
        ask(ws, {'a': 'select_fixtures', 'ids': [12]})
        action = {'a': newer, **({'id': 'pianist'} if newer == 'scene_go' else
                  {'v': 10} if newer == 'dim' else {'r': 10, 'g': 20, 'b': 30} if newer == 'color' else {})}
        ws.send_json(action)
        if newer in ('dim', 'color'):
            ws.send_json({'a': 'select_fixtures', 'ids': [12]})
            result = until(ws, lambda m: m.get('a') == 'select_fixtures' and 'ok' in m)
        else:
            result = until(ws, lambda m: m.get('a') == newer and 'ok' in m)
        assert result['ok'], result
        before = len(mock.received)
        ws.send_json({'a': 'edit_end'})
        result = until(ws, lambda m: m.get('a') == 'edit_end' and 'ok' in m)
        assert not result['ok']
        assert not any(line.startswith(('Off Fixture', 'At ', 'Attribute ')) for line in mock.received[before:])
        assert (path.parent / 'highlight.json').exists()
