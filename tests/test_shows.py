"""Task 3: fresh show allowlist, load confirmation and isolated panel plans."""
import json
import time

import pytest
from ma2panel.show_plans import plan_path

from ma2panel.mock import MockMA2
from test_bridge import ask, bridge_cfg, until  # noqa: F401
from test_safety import tabs

LOAD = {'a': 'show_load', 'name': 'Demo', 'confirm_name': 'Demo', 'ack_unsaved': True}
SETTINGS = {'safety': {'mode': 'full', 'allow_show_load': True, 'allow_show_save': True},
            'ma2': {'load_timeout': 10}}


@pytest.mark.parametrize('change', [{'confirm_name': 'Other'}, {'ack_unsaved': False}, {'ack_unsaved': 1},
                                    {'name': 'a"b'}, {'name': 'x' * 101}, {'name': 'a\nb'}])
def test_invalid_load_sends_nothing(bridge_cfg, change):
    with bridge_cfg(settings=SETTINGS) as (ws, mock, path):
        ask(ws, {'a': 'show_identify'})
        before = list(mock.received)
        assert not ask(ws, {**LOAD, **change})['ok']
        assert mock.received == before


def test_flags_and_save_confirmation(bridge_cfg):
    for settings in ({'safety': {'mode': 'full'}}, SETTINGS):
        with bridge_cfg(settings=settings) as (ws, mock, path):
            ask(ws, {'a': 'show_identify'})
            before = list(mock.received)
            result = ask(ws, {'a': 'show_save'})  # no typed name: SaveShow writes over the show open on the desk
            assert result['ok'] is (settings == SETTINGS)
            assert ('SaveShow' in mock.received) is result['ok']
            if result['ok']:
                assert result['reply'] == 'OK\n[Channel]>' and result['name'] == mock.show_name  # replies come back without \r and colour codes
            else:
                assert not ask(ws, LOAD)['ok']
                assert mock.received == before


def test_list_and_fresh_allowlist(bridge_cfg, tmp_path):
    (tmp_path / 'Local.show.gz').write_text('local')
    settings = {**SETTINGS, 'ma2': {'shows_dir': str(tmp_path)}}
    with bridge_cfg(settings=settings) as (ws, mock, path):
        result = ask(ws, {'a': 'shows_list'})
        assert result['ok'] and result['names'] == ['Mock show', 'Demo']
        assert result['local_names'] == ['Local'] and result['raw_lines'] and result['t']
        mock.shows.remove('Demo')
        for name in ('Demo', 'Local'):
            assert not ask(ws, {**LOAD, 'name': name, 'confirm_name': name})['ok']
        assert not any(line.startswith('LoadShow') for line in mock.received)
        mock.list_garbage = True
        result = ask(ws, {'a': 'shows_list'})
        assert result['names'] == [] and '???' in result['raw_lines']


def test_load_reconnect_plan_highlight_and_fixture_read(bridge_cfg):
    settings = {**SETTINGS, 'safety': {**SETTINGS['safety'], 'allow_highlight': True, 'allow_fixture_read': True}}
    with bridge_cfg(settings=settings) as (ws, mock, path):
        ask(ws, {'a': 'show_identify'})
        assert ask(ws, {'a': 'show_bind', 'name': mock.show_name})['ok']
        old = json.loads(path.read_text())
        assert ask(ws, {'a': 'edit_begin'})['ok']
        assert ask(ws, {'a': 'highlight', 'id': 12})['ok']
        assert ask(ws, LOAD)['ok']
        new = json.loads(path.read_text())
        assert new['show'] == 'Demo' and new['scenes'] == [] and new['groups'] == []
        assert new['fixtures']  # auto-fetch into the new plan
        assert json.loads(plan_path(path.parent / 'shows', 'Mock show').read_text()) == old
        assert mock.show_name == 'Demo'
        load = mock.received.index('LoadShow "Demo" /nosave')
        assert any(line.startswith('Off Fixture ') for line in mock.received[:load])
        assert mock.received[load + 1:].count('login "panel" ""') == 1
        assert mock.received.count('LoadShow "Demo" /nosave') == 1
        assert 'ListVar' in mock.received[load + 1:]
        status = ask(ws, {'a': 'show_status'})
        assert status['show_load']['state'] == 'done'
        assert not ask(ws, {'a': 'dim', 'v': 10})['ok']


@pytest.mark.parametrize('reply', ['???\r\n[Channel]>', '$SHOWFILE = Other\r\n[Channel]>'])
def test_unconfirmed_does_not_switch_plan(bridge_cfg, monkeypatch, reply):
    original = MockMA2._reply
    def answer(mock, text):
        if text == 'ListVar' and mock.show_name == 'Demo':
            return f'$USER = {mock.user}\r\n' + reply  # the login check sees the user; only the show is wrong
        return original(mock, text)
    monkeypatch.setattr(MockMA2, '_reply', answer)
    with bridge_cfg(settings={**SETTINGS, 'ma2': {'load_timeout': 1.5}}) as (ws, mock, path):
        before = path.read_bytes()
        result = ask(ws, LOAD)
        assert not result['ok']
        assert path.read_bytes() == before
        assert ask(ws, {'a': 'show_status'})['show_load']['state'] in ('failed', 'unknown')


def test_loading_blocks_actions_but_controls_remain_live(tmp_path):
    with tabs(tmp_path, SETTINGS) as ((a, b), mock, client, path):
        assert ask(b, {'a': 'select_fixtures', 'ids': [12]})['ok']
        a.send_json(LOAD)
        until(a, lambda m: m.get('status', {}).get('show_load', {}).get('state') == 'loading')
        rejected = ask(b, {'a': 'dim', 'v': 30})
        assert not rejected['ok']
        assert any(reason in rejected['err'] for reason in ('идёт загрузка шоу', 'действие устарело'))
        assert 'идёт загрузка шоу' in ask(b, LOAD)['err']
        # Same socket as the pending load must still process emergency controls.
        assert ask(a, {'a': 'halt'})['a'] == 'halt'
        assert ask(a, {'a': 'resume'})['a'] == 'resume'
        assert ask(b, {'a': 'link_connect'})['ok']
        assert until(a, lambda m: m.get('a') == 'show_load' and 'ok' in m)['ok']
        assert not any(line == 'At 30' for line in mock.received)
        assert ask(b, {'a': 'show_status'})['show_load']['state'] == 'done'


def test_mock_unknown_load_is_error():
    mock = MockMA2('panel', None)
    assert 'Error' in mock._reply('LoadShow "unknown" /nosave')
    assert mock.show_name == 'Mock show'


def test_template_cannot_load_a_different_unchecked_name(bridge_cfg):
    settings = {**SETTINGS, 'ma2': {'loadshow_cmd': 'LoadShow "Never listed" /nosave', 'load_timeout': .2}}
    with bridge_cfg(settings=settings) as (ws, mock, path):
        assert not ask(ws, LOAD)['ok']
        assert not any(line.startswith('LoadShow') for line in mock.received)


def test_load_aborted_when_highlight_cannot_be_released(bridge_cfg, monkeypatch):
    original = MockMA2._reply
    monkeypatch.setattr(MockMA2, '_reply', lambda mock, text: 'Error: refused\r\n[Channel]>' if text.startswith('Off Fixture') else original(mock, text))
    settings = {**SETTINGS, 'safety': {**SETTINGS['safety'], 'allow_highlight': True}}
    with bridge_cfg(settings=settings) as (ws, mock, path):
        ask(ws, {'a': 'edit_begin'})
        assert ask(ws, {'a': 'highlight', 'id': 12})['ok']
        before = path.read_bytes()
        assert not ask(ws, LOAD)['ok']
        assert not any(line.startswith('LoadShow') for line in mock.received)
        assert path.read_bytes() == before
        assert (path.parent / 'highlight.json').exists()
        assert ask(ws, {'a': 'show_status'})['show_load']['state'] == 'failed'


def test_login_failure_after_load_is_reported(bridge_cfg, monkeypatch):
    original = MockMA2._reply
    def reply(mock, text):
        if text.lower().startswith('login') and mock.show_name == 'Demo':
            return 'Error: login failed\r\n[Channel]>'
        return original(mock, text)
    monkeypatch.setattr(MockMA2, '_reply', reply)
    with bridge_cfg(settings={**SETTINGS, 'ma2': {'load_timeout': 1.5}}) as (ws, mock, path):
        before = path.read_bytes()
        result = ask(ws, LOAD)  # a failed login may be transient while MA2 loads: reported at the timeout
        assert not result['ok'] and 'вход' in result['err']
        assert path.read_bytes() == before
        assert ask(ws, {'a': 'show_status'})['show_load']['state'] == 'unknown'


def test_load_command_error_is_not_confirmation_success(bridge_cfg, monkeypatch):
    original = MockMA2._reply
    monkeypatch.setattr(MockMA2, '_reply', lambda mock, text: 'Error: cannot load\r\n[Channel]>' if text.startswith('LoadShow') else original(mock, text))
    with bridge_cfg(settings=SETTINGS) as (ws, mock, path):
        assert not ask(ws, LOAD)['ok']
        assert ask(ws, {'a': 'show_status'})['show_load']['state'] == 'failed'


def test_action_queued_during_fresh_list_is_refused(tmp_path):
    with tabs(tmp_path, SETTINGS) as ((a, b), mock, client, path):
        mock.late = .2
        a.send_json(LOAD)
        deadline = time.monotonic() + 2
        while 'ListShows' not in mock.received and time.monotonic() < deadline:
            time.sleep(.01)
        assert 'ListShows' in mock.received
        result = ask(b, {'a': 'show_open_plan', 'name': 'Race'})
        assert not result['ok'] and 'идёт загрузка шоу' in result['err']


def test_success_opens_saved_plan_without_replaying_values(bridge_cfg):
    with bridge_cfg(settings=SETTINGS) as (ws, mock, path):
        assert ask(ws, {'a': 'show_bind', 'name': 'Mock show'})['ok']
        saved = json.loads(path.read_text())
        saved['show'] = 'Demo'
        saved['fixtures'][0]['label'] = 'Saved position'
        folder = path.parent / 'shows'
        folder.mkdir(exist_ok=True)
        (folder / 'Demo.json').write_text(json.dumps(saved))
        assert ask(ws, {'a': 'select_fixtures', 'ids': [12]})['ok']
        ws.send_json({'a': 'dim', 'v': 23})
        time.sleep(.2)
        before = len(mock.received)
        assert ask(ws, LOAD)['ok']
        assert json.loads(path.read_text()) == saved
        assert not any(line.startswith(('At ', 'Go ', 'Attribute ')) for line in mock.received[before:])


@pytest.mark.parametrize('value', [0, -1, '120', True, float('inf')])
def test_load_timeout_must_be_positive_finite(value):
    from ma2panel.bridge import validate_settings
    with pytest.raises(ValueError):
        validate_settings({'ma2': {'load_timeout': value}})


def test_unreadable_fresh_list_never_loads(bridge_cfg):
    with bridge_cfg(settings=SETTINGS) as (ws, mock, path):
        mock.list_garbage = True
        # The list is unreadable, so no privileged command may leave at all.
        before = path.read_bytes()
        result = ask(ws, LOAD)
        assert not result['ok'] and path.read_bytes() == before
        assert not any(line.startswith('LoadShow') for line in mock.received)


def test_late_confirmation_cannot_succeed_after_deadline(bridge_cfg, monkeypatch):
    import asyncio
    from ma2panel.bridge import MA2Link
    original = MA2Link.send
    with bridge_cfg(settings={**SETTINGS, 'ma2': {'load_timeout': .1}}) as (ws, mock, path):
        ask(ws, {'a': 'show_identify'})
        # Simulate an acknowledged load that retains Telnet; delay its ListVar response.
        async def send(link, cmd, *args, **kwargs):
            if cmd.startswith('LoadShow'):
                mock.show_name = 'Demo'
                return True, 'OK\r\n[Channel]>'
            if cmd == 'ListVar' and mock.show_name == 'Demo':
                await asyncio.sleep(.6)
            return await original(link, cmd, *args, **kwargs)
        monkeypatch.setattr(MA2Link, 'send', send)
        before = path.read_bytes()
        started = time.monotonic()
        assert not ask(ws, LOAD)['ok']
        assert time.monotonic() - started < .5
        assert path.read_bytes() == before
        assert ask(ws, {'a': 'show_status'})['show_load']['state'] == 'unknown'


def test_old_name_during_load_means_still_loading(bridge_cfg, monkeypatch):
    original = MockMA2._reply
    polls = {'n': 0}
    def answer(mock, text):
        if text == 'ListVar' and mock.show_name == 'Demo' and polls['n'] < 2:
            polls['n'] += 1
            return f'$USER = {mock.user}\r\n$SHOWFILE = Mock show\r\n[Channel]>'  # the console still reports the old show for a while
        return original(mock, text)
    monkeypatch.setattr(MockMA2, '_reply', answer)
    with bridge_cfg(settings=SETTINGS) as (ws, mock, path):
        ask(ws, {'a': 'show_identify'})
        assert ask(ws, LOAD)['ok']
        assert polls['n'] == 2 and json.loads(path.read_text())['show'] == 'Demo'


def test_real_ma2_listshows_format():
    # hall 2026-10-18: grandMA2 3.9.60 prints "<name> HH:MM D.Mon.YYYY N KB" with no quotes and no .show suffix
    import re
    from ma2panel.safety import DEFAULT_MA2
    reply = ('Executing : ListShows\r\n         big room v2 18:49 16.Okt.2026   175 KB\r\n'
             '     school cocerts 17:20 13.Okt.2026   171 KB\r\n         newshow 14:58  9.Okt.2026    95 KB\r\n [Group]>')
    names = [next(v for v in m.groups() if v).strip() for m in re.finditer(DEFAULT_MA2['listshows_regex'], reply)]
    assert names == ['big room v2', 'school cocerts', 'newshow']


def saved_auto_plan(path, name='Concert B'):
    folder = path.parent / 'shows'
    folder.mkdir(exist_ok=True)
    candidate = plan_path(folder, name, write=True)
    data = json.loads(path.read_text())
    data['show'] = name
    data['fixtures'][0]['label'] = 'B position'
    candidate.write_text(json.dumps(data))
    return candidate


def test_identify_automatically_opens_existing_plan(bridge_cfg):
    with bridge_cfg(settings=SETTINGS) as (ws, mock, path):
        candidate = saved_auto_plan(path)
        before = path.read_bytes(), candidate.read_bytes()
        mock.show_name = 'Concert B'
        assert ask(ws, {'a': 'show_identify'})['ok']
        assert json.loads(path.read_text())['show'] == 'Concert B'
        assert plan_path(candidate.parent, 'Mock show').read_bytes() == before[0]
        assert candidate.read_bytes() == before[1]


def identify_plan(ws):
    ws.send_json({'a': 'show_identify'})
    status = None
    while 'ok' not in (message := ws.receive_json()):
        status = message.get('status', status)
    assert message['ok'] and status is not None, message
    return status


def test_auto_match_and_unknown_leave_files_as_is(bridge_cfg):
    with bridge_cfg(settings=SETTINGS) as (ws, mock, path):
        candidate = saved_auto_plan(path)
        initial = path.read_bytes(), path.stat().st_mtime_ns, candidate.read_bytes()
        start = len(mock.received)
        assert identify_plan(ws)['plan_selection'] == {'state': 'matched'}
        mock.show_name = ''
        assert identify_plan(ws)['plan_selection'] == {'state': 'pending'}
        assert (path.read_bytes(), path.stat().st_mtime_ns, candidate.read_bytes()) == initial
        assert list(candidate.parent.iterdir()) == [candidate]
        assert mock.received[start:] == ['ListVar', 'ListVar']


@pytest.mark.parametrize(('problem', 'code'), [
    ('missing', 'plan_missing'), ('broken', 'plan_conflict'), ('owner', 'plan_conflict'),
    ('invalid_scene', 'plan_conflict'), ('invalid_map', 'plan_conflict'), ('copies', 'plan_conflict'),
    ('archive', 'plan_archive_conflict'), ('working_revision', 'plan_conflict'),
    ('foreign_legacy', 'plan_missing'),
])
def test_auto_refuses_unsafe_files(bridge_cfg, problem, code):
    with bridge_cfg(settings=SETTINGS) as (ws, mock, path):
        target = saved_auto_plan(path)
        data = json.loads(target.read_text())
        if problem in ('missing', 'foreign_legacy'):
            target.unlink()
        if problem == 'broken':
            target.write_text('{broken')
        if problem == 'owner':
            target.write_text(json.dumps({**data, 'show': 'Other'}))
        if problem == 'invalid_scene':
            target.write_text(json.dumps({**data, 'scenes': [{'id': 's', 'exec': '1.101; Go'}]}))
        if problem == 'invalid_map':
            target.write_text(json.dumps({**data, 'dmx_map': {'type': {'strobe': {'attr': []}}}}))
        if problem in ('copies', 'foreign_legacy'):
            legacy = target.parent / 'Concert B.json'
            legacy.write_text(json.dumps({**data, 'show': 'Other' if problem == 'foreign_legacy' else 'Concert B',
                                          'fixtures': []}))
        if problem == 'archive':
            archive = plan_path(target.parent, 'Mock show', write=True)
            archive.write_text(json.dumps({**data, 'show': 'Mock show', 'fixtures': []}))
        if problem == 'working_revision':
            path.write_text(json.dumps({**json.loads(path.read_text()), 'fixtures': []}))
        before = path.read_bytes(), {p.name: p.read_bytes() for p in target.parent.iterdir()}
        start = len(mock.received)
        mock.show_name = 'Concert B'
        status = identify_plan(ws)
        assert status['plan_selection']['code'] == code
        if code in ('plan_missing', 'plan_conflict'):
            assert status['plan_selection']['params'] == {'deskShow': 'Concert B'}
        assert status['readiness']['actions']['light']['scene_go']['code'] == 'show_mismatch'
        assert (path.read_bytes(), {p.name: p.read_bytes() for p in target.parent.iterdir()}) == before
        assert mock.received[start:] == ['ListVar']


def test_two_tabs_choose_once_and_reject_old_light(tmp_path, monkeypatch):
    from ma2panel import bridge

    with tabs(tmp_path, SETTINGS) as ((first, second), mock, _, path):
        candidate = saved_auto_plan(path)
        initial = candidate.read_bytes()
        status = identify_plan(first)
        assert ask(first, {'a': 'select_fixtures', 'ids': [12]})['ok']
        assert ask(second, {'a': 'select_fixtures', 'ids': [12]})['ok']
        old_epoch = status['blackout_epoch']
        saved = []
        save = bridge.save_config

        def track(filename, *args, **kwargs):
            saved.append(filename)
            return save(filename, *args, **kwargs)

        monkeypatch.setattr(bridge, 'save_config', track)
        before = len(mock.received)
        mock.show_name = 'Concert B'
        first.send_json({'a': 'show_identify'})
        second.send_json({'a': 'show_identify'})
        for ws in (first, second):
            transition = until(ws, lambda m: m.get('config', {}).get('show') == 'Concert B')
            assert transition['status']['plan_selection']['state'] == 'loaded'
            assert transition['config']['fixtures'][0]['label'] == 'B position'
            assert until(ws, lambda m: m.get('a') == 'show_identify' and 'ok' in m)['ok']
            assert not ask(ws, {'a': 'dim', 'v': 50, 'blackout_epoch': old_epoch})['ok']
            assert not ask(ws, {'a': 'select_fixtures', 'ids': [12], 'blackout_epoch': old_epoch})['ok']
            refused = ask(ws, {'a': 'clear', 'blackout_epoch': old_epoch})
            assert not refused['ok'] and refused['code'] == 'plan_context_changed'
            assert refused['err'] == 'План изменился; начните новое действие.'
        archive = plan_path(candidate.parent, 'Mock show')
        assert ask(first, {'a': 'show_status'})['plan_selection']['state'] == 'loaded'
        assert saved == [str(archive), str(path)]
        assert json.loads(archive.read_text())['show'] == 'Mock show'
        assert candidate.read_bytes() == initial
        assert mock.received[before:] == ['ListVar', 'ListVar']


def test_open_draft_in_one_tab_blocks_other_tab(tmp_path):
    with tabs(tmp_path, SETTINGS) as ((first, second), mock, _, path):
        candidate = saved_auto_plan(path)
        second.send_json({'a': 'show_bind', 'name': 'Mock show'})
        revision = until(second, lambda m: 'config' in m)['config']['revision']
        assert until(second, lambda m: 'ok' in m)['ok']
        initial = path.read_bytes(), candidate.read_bytes()
        assert ask(second, {'a': 'plan_editing', 'active': True, 'config_revision': revision})['ok']
        mock.show_name = 'Concert B'
        assert identify_plan(first)['plan_selection']['code'] == 'plan_draft'
        assert (path.read_bytes(), candidate.read_bytes()) == initial
        assert ask(second, {'a': 'plan_editing', 'active': False})['ok']
        assert identify_plan(first)['plan_selection']['state'] == 'loaded'


@pytest.mark.parametrize('failure', ['archive_write', 'working_write', 'generation', 'target_revision'])
def test_auto_can_recover_after_fault_between_saves(bridge_cfg, monkeypatch, failure):
    from ma2panel import bridge

    with bridge_cfg(settings=SETTINGS) as (ws, mock, path):
        candidate = saved_auto_plan(path)
        initial = path.read_bytes(), candidate.read_bytes()
        archive = plan_path(candidate.parent, 'Mock show', write=True)
        save = bridge.save_config
        send = bridge.MA2Link.send
        link = None
        writes = []

        async def track_send(self, *args, **kwargs):
            nonlocal link
            link = self
            return await send(self, *args, **kwargs)

        def fail(filename, data, *, before_replace=None):
            writes.append(filename)
            if (filename == str(archive) and failure == 'archive_write' or
                    filename == str(path) and failure == 'working_write'):
                raise OSError('disk unavailable')
            if filename == str(path) and failure == 'generation':
                link.disconnect()
            if filename == str(path) and failure == 'target_revision':
                candidate.write_bytes(initial[1] + b'\n')
            return save(filename, data, before_replace=before_replace)

        monkeypatch.setattr(bridge.MA2Link, 'send', track_send)
        monkeypatch.setattr(bridge, 'save_config', fail)
        start = len(mock.received)
        mock.show_name = 'Concert B'
        status = identify_plan(ws)
        expected = 'pending' if failure == 'generation' else 'operator'
        assert status['plan_selection']['state'] == expected
        assert path.read_bytes() == initial[0]
        assert candidate.read_bytes() == initial[1] + (b'\n' if failure == 'target_revision' else b'')
        if failure == 'archive_write':
            assert not archive.exists()
        else:
            assert json.loads(archive.read_text())['show'] == 'Mock show'
        assert not list(path.parent.glob('*.tmp')) and not list(archive.parent.glob('*.tmp'))
        assert mock.received[start:] == ['ListVar']

        monkeypatch.setattr(bridge, 'save_config', save)
        if failure == 'generation':
            assert ask(ws, {'a': 'link_connect'})['ok']
            until(ws, lambda m: m.get('status', {}).get('plan_selection', {}).get('state') == 'operator')
            assert path.read_bytes() == initial[0]
        if archive.exists():
            archived_at = archive.stat().st_mtime_ns
        else:
            archived_at = None
        assert identify_plan(ws)['plan_selection']['state'] == 'loaded'
        if archived_at is not None:
            assert archive.stat().st_mtime_ns == archived_at


def test_disconnect_before_identification_leaves_plans_untouched(bridge_cfg):
    with bridge_cfg(settings=SETTINGS) as (ws, mock, path):
        candidate = saved_auto_plan(path)
        initial = path.read_bytes(), candidate.read_bytes()
        assert ask(ws, {'a': 'link_drop'})['ok']
        mock.show_name = 'Concert B'
        assert not ask(ws, {'a': 'select_fixtures', 'ids': [12]})['ok']
        assert (path.read_bytes(), candidate.read_bytes()) == initial
        assert list(candidate.parent.iterdir()) == [candidate]
        assert ask(ws, {'a': 'link_connect'})['ok']
        until(ws, lambda m: m.get('config', {}).get('show') == 'Concert B')
        assert candidate.read_bytes() == initial[1]


def test_poll_opens_compatible_legacy_plan(bridge_cfg):
    with bridge_cfg(settings={**SETTINGS, 'poll_seconds': 0.05}) as (ws, mock, path):
        canonical = saved_auto_plan(path)
        legacy = canonical.parent / 'Concert B.json'
        canonical.rename(legacy)
        original = legacy.read_bytes()
        mock.show_name = 'Concert B'
        until(ws, lambda m: m.get('config', {}).get('show') == 'Concert B')
        assert json.loads(path.read_text())['show'] == 'Concert B'
        assert legacy.read_bytes() == original and not canonical.exists()


def test_create_only_does_not_open_existing_plan(bridge_cfg):
    with bridge_cfg(settings=SETTINGS) as (ws, mock, path):
        candidate = saved_auto_plan(path)
        before = path.read_bytes(), candidate.read_bytes()
        result = ask(ws, {'a': 'show_open_plan', 'name': 'Concert B', 'create_only': True})
        assert not result['ok'] and 'существует' in result['err']
        assert result['code'] == 'plan_exists' and result['params'] == {}
        assert (path.read_bytes(), candidate.read_bytes()) == before



def test_plan_selection_waits_for_active_http_operation(tmp_path):
    with tabs(tmp_path, SETTINGS, n=1) as ((ws,), mock, client, path):
        candidate = saved_auto_plan(path)
        before = path.read_bytes(), candidate.read_bytes()
        def set_busy(active):
            client.app.state.active_http = active

        client.portal.call(set_busy, 1)
        mock.show_name = 'Concert B'
        assert identify_plan(ws)['plan_selection']['code'] == 'plan_busy'
        assert (path.read_bytes(), candidate.read_bytes()) == before
        client.portal.call(set_busy, 0)
        assert identify_plan(ws)['plan_selection']['state'] == 'loaded'
