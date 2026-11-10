"""Transaction/order regressions; the model is not evidence of MA2 semantics."""
import asyncio
import pytest
from ma2panel.commands import build, ActionError
from test_bridge import bridge_cfg, ask  # noqa: F401
from test_status_evidence import context  # noqa: F401


def test_launch_is_explicit_even_at_zero_and_never_clears_other_programmer():
    cfg = {'scenes': [{'id': 'a', 'exec': '1.101'}, {'id': 'b', 'exec': '1.102'}]}
    lines = build({'a': 'scene_go', 'id': 'b', 'fade': 0}, cfg)
    assert lines == ['Goto Cue 1 Executor 1.102 Fade 0']


def test_native_transition_has_no_timer_and_scopes_release():
    from ma2panel.scene_runtime import transition_lines
    cfg = {'scenes': [{'id': 'a', 'exec': '1.101'}, {'id': 'b', 'exec': '1.102'}]}
    assert transition_lines({'id': 'b', 'fade': 5}, cfg, lambda ex: True, {'1.101'}) == [
        'Masterfade 5 Executor 1.101', 'Goto Cue 1 Executor 1.102 Fade 5', 'Off Executor 1.101']


def test_unconfirmed_show_blocks_plan_writes(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        mock.show_name = 'Another show'
        before = len(mock.received)
        result = ask(ws, {'a': 'scene_go', 'id': 'pianist'})
        assert not result['ok']
        assert not any(x.startswith(('Goto', 'Go Executor', 'Off Executor')) for x in mock.received[before:])


def test_blackout_restores_grand_master_without_erasing_playbacks(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        mock.grand_master = 37.5
        mock.running.add('9.101')
        mock.programmer = {99: {'dim': 80}}
        assert ask(ws, {'a': 'blackout'})['ok']
        assert mock.grand_master == 0
        assert mock.running == {'9.101'} and mock.programmer == {99: {'dim': 80}}
        assert ask(ws, {'a': 'blackout'})['ok']
        assert mock.grand_master == 37.5


def test_update_known_failure_keeps_previous_cue():
    from ma2panel.scene_runtime import store_scene
    calls = []
    async def send(cmd):
        calls.append(cmd)
        if cmd.startswith('Store '): raise ActionError('known refusal')
        return 'OK'
    with pytest.raises(ActionError, match='known refusal'):
        asyncio.run(store_scene(send, '1.101', 'New', [12], spare='1.1'))
    assert not any(x.startswith(('Delete', 'Copy')) for x in calls)


def test_partial_overlap_release_and_interruption_model():
    from ma2panel.mock import MockMA2
    from ma2panel.scene_runtime import transition_lines
    mock = MockMA2('panel', None)
    now = [0.0]
    mock.clock = lambda: now[0]
    mock.cues = {'1.101': {1: {1: {'dim': 100, 'pan': 10}, 2: {'dim': 80, 'pan': 20}}},
                 '1.102': {1: {2: {'dim': 20, 'pan': 80}, 3: {'dim': 100}}},
                 '9.101': {1: {99: {'dim': 88}}}}
    mock.running = {'9.101'}
    cfg = {'scenes': [{'id': 'a', 'exec': '1.101'}, {'id': 'b', 'exec': '1.102'}]}
    owned = set()
    def launch(id, seconds):
        for line in transition_lines({'id': id, 'fade': seconds}, cfg, lambda ex: True, owned):
            mock.received.append(line)
            mock._reply(line)
            if line.startswith('Off Executor '):
                owned.discard(line[len('Off Executor '):])
        owned.add(next(s['exec'] for s in cfg['scenes'] if s['id'] == id))
    launch('a', 0)
    launch('b', 4)
    now[0] = 2
    output = mock.output()
    assert output[1]['dim'] == 50 and output[1]['pan'] == 10
    assert output[2] == {'dim': 50, 'pan': 50}
    assert output[3]['dim'] == 50 and output[99]['dim'] == 88
    launch('a', 4)  # a fresh manual gesture, while both executors are still fading
    assert mock.output() == output
    now[0] = 6
    output = mock.output()
    assert output[1]['dim'] == 100 and output[2]['dim'] == 80
    assert output[99]['dim'] == 88 and '1.102' not in mock.running


def test_common_fade_is_persisted_and_client_cannot_override(bridge_cfg):
    import json
    with bridge_cfg() as (ws, mock, path):
        assert ask(ws, {'a': 'scene_fade', 'fade': 5})['ok']
        assert json.loads(path.read_text())['scene_fade'] == 5
        assert ask(ws, {'a': 'scene_go', 'id': 'pianist', 'fade': 0})['ok']
        assert 'Goto Cue 1 Executor 1.101 Fade 5' in mock.received
        assert not any(x.startswith(('ClearAll', 'Go Executor')) for x in mock.received)


def test_config_snapshot_broadcasts_the_shared_fade(context):
    context.cfg['scene_fade'] = 5
    assert context.config_msg()['config']['scene_fade'] == 5


@pytest.mark.parametrize('automatic', [True, False])
def test_unknown_or_multiple_cues_do_not_start(bridge_cfg, automatic):
    with bridge_cfg() as (ws, mock, path):
        if automatic: mock.cue_triggers['1.101'] = 'Follow'
        else: mock.cues['1.101'][2] = {12: {'dim': 0}}
        before = len(mock.received)
        assert not ask(ws, {'a': 'scene_go', 'id': 'pianist'})['ok']
        assert not any(x.startswith(('Goto', 'Go Executor', 'Off Executor', 'Masterfade')) for x in mock.received[before:])


@pytest.mark.parametrize('priority,soft', [('HTP', 'On'), ('High', 'On'), ('LTP', 'Off'), (None, None)])
def test_unconfirmed_ltp_soft_transfer_refuses_before_mutation(bridge_cfg, priority, soft):
    with bridge_cfg() as (ws, mock, path):
        mock.playback_options = {'1.101': (priority, soft)}
        before = len(mock.received)
        assert not ask(ws, {'a': 'scene_go', 'id': 'pianist'})['ok']
        assert not any(x.startswith(('Goto', 'Off Executor', 'Masterfade')) for x in mock.received[before:])


def test_accepted_but_timed_out_commit_preserves_backup_and_never_replays(bridge_cfg, monkeypatch):
    from ma2panel.mock import MockMA2
    original = MockMA2._reply
    def reply(self, line):
        result = original(self, line)
        return 'OK\r\n' if line.endswith('/Overwrite') else result
    monkeypatch.setattr(MockMA2, '_reply', reply)
    with bridge_cfg(settings={'safety': {'mode': 'full'}, 'ma2': {'timeout': 0.05}}) as (ws, mock, path):
        mock.cues['1.101'][1] = {12: {'dim': 70}}
        mock.programmer = {12: {'dim': 25}}
        assert ask(ws, {'a': 'select_fixtures', 'ids': [12]})['ok']
        action = {'a': 'scene_create', 'exec': '1.101', 'confirm': '1.101', 'replace': True, 'page': 1, 'label': 'New'}
        assert not ask(ws, action)['ok']
        assert mock.cues['1.101'][1] == {12: {'dim': 25}}
        assert mock.cues['1.1'][2] == {12: {'dim': 70}}
        assert not ask(ws, action)['ok']
        assert sum(x.endswith('/Overwrite') for x in mock.received) == 1
        assert (path.parent / 'scene-write-1.101.json').exists()


def test_blackout_external_changes_and_native_mask_are_preserved(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        mock.native_blackout = True
        assert ask(ws, {'a': 'blackout'})['ok']
        mock.grand_master = 20  # another operator changed the suppression mechanism
        before = len(mock.received)
        assert not ask(ws, {'a': 'blackout'})['ok']
        assert mock.grand_master == 20 and mock.native_blackout
        assert not any(x.startswith('SpecialMaster ') for x in mock.received[before:])


def test_unknown_grand_read_is_refused_without_a_master_write(bridge_cfg, monkeypatch):
    from ma2panel.mock import MockMA2
    original = MockMA2._reply
    def reply(self, line):
        result = original(self, line)
        if "setvar('PANELGM'" in line: self.vars['PANELGM'] = 'obsolete 100'
        return result
    monkeypatch.setattr(MockMA2, '_reply', reply)
    with bridge_cfg() as (ws, mock, path):
        assert not ask(ws, {'a': 'blackout'})['ok']
        assert mock.grand_master == 100
        assert not any(x.startswith('SpecialMaster ') for x in mock.received)


def test_bare_numeric_grand_value_has_no_proven_units(bridge_cfg, monkeypatch):
    from ma2panel.mock import MockMA2
    original = MockMA2._reply
    def reply(self, line):
        result = original(self, line)
        if "setvar('PANELGM'" in line:
            self.vars['PANELGM'] = self.vars['PANELGM'].split()[0] + ' 37.5'
        return result
    monkeypatch.setattr(MockMA2, '_reply', reply)
    with bridge_cfg() as (ws, mock, path):
        mock.grand_master = 37.5
        assert not ask(ws, {'a': 'blackout'})['ok']
        assert mock.grand_master == 37.5
        assert not any(x.startswith('SpecialMaster ') for x in mock.received)


def test_show_change_during_preparation_keeps_old_target(bridge_cfg, monkeypatch):
    from ma2panel.mock import MockMA2
    original = MockMA2._reply
    def reply(self, line):
        result = original(self, line)
        if line.startswith('Store Executor 1.1 '): self.show_name = 'Other'
        return result
    monkeypatch.setattr(MockMA2, '_reply', reply)
    with bridge_cfg() as (ws, mock, path):
        mock.cues['1.101'][1] = {12: {'dim': 70}}
        assert ask(ws, {'a': 'select_fixtures', 'ids': [12]})['ok']
        result = ask(ws, {'a':'scene_create','label':'New','page':1,'exec':'1.101','confirm':'1.101','replace':True})
        assert not result['ok']
        assert mock.cues['1.101'][1] == {12: {'dim': 70}}
        assert not any(x.startswith(('Copy', 'Delete')) for x in mock.received)


@pytest.mark.parametrize('level', [0, 37.123456789, 100])
def test_restore_preserves_original_level_across_precision_and_zero(bridge_cfg, level):
    with bridge_cfg() as (ws, mock, path):
        mock.grand_master = level
        # Read format is a runtime prerequisite; test a precise supported value.
        # Cover the real formatted command rather than a pre-rounded mock property.
        original = mock._reply
        def reply(line):
            result = original(line)
            if "setvar('PANELGM'" in line:
                nonce = mock.vars['PANELGM'].split()[0]
                mock.vars['PANELGM'] = nonce + ' ' + str(mock.grand_master) + '%'
            return result
        mock._reply = reply
        assert ask(ws, {'a':'blackout'})['ok']
        assert ask(ws, {'a':'blackout'})['ok']
        assert mock.grand_master == level


@pytest.mark.parametrize('phase', ['Store Executor 1.1', 'Copy Cue 1 Executor 1.101', 'Copy Cue 1 Executor 1.1'])
def test_failed_save_never_deletes_or_retries(bridge_cfg, monkeypatch, phase):
    from ma2panel.mock import MockMA2
    original = MockMA2._reply
    def reply(self, line):
        if line.startswith(phase): return 'Error #72: COMMAND NOT EXECUTED\r\n[Channel]>'
        return original(self, line)
    monkeypatch.setattr(MockMA2, '_reply', reply)
    with bridge_cfg() as (ws, mock, path):
        mock.cues['1.101'][1] = {12: {'dim': 70}}
        mock.programmer = {12: {'dim': 25}, 99: {'dim': 90}}
        assert ask(ws, {'a': 'select_fixtures', 'ids': [12]})['ok']
        result = ask(ws, {'a': 'scene_create', 'exec': '1.101', 'confirm': '1.101', 'replace': True, 'page': 1, 'label': 'New'})
        assert not result['ok']
        assert mock.cues['1.101'][1] == {12: {'dim': 70}}
        assert not any(x.startswith('Delete') for x in mock.received)
        assert sum(x.startswith(phase) for x in mock.received) == 1
        assert list(path.parent.glob('scene-write-*.json'))


def test_successful_update_keeps_old_cue_in_spare_and_excludes_outsider(bridge_cfg):
    import json
    with bridge_cfg() as (ws, mock, path):
        mock.cues['1.101'][1] = {12: {'dim': 70}}
        mock.programmer = {12: {'dim': 25}, 99: {'dim': 90}}
        assert ask(ws, {'a': 'select_fixtures', 'ids': [12]})['ok']
        result = ask(ws, {'a': 'scene_create', 'exec': '1.101', 'confirm': '1.101', 'replace': True, 'page': 1, 'label': 'New'})
        assert result['ok'], result
        assert mock.cues['1.101'][1] == {12: {'dim': 25}}
        assert mock.cues['1.1'][2] == {12: {'dim': 70}}
        assert mock.programmer[99] == {'dim': 90}
        scene = next(sc for sc in json.loads(path.read_text())['scenes'] if sc['exec'] == '1.101')
        assert scene['backup_exec'] == '1.1' and scene['label'] == 'New'


def test_unknown_save_result_is_not_replayed():
    from ma2panel.scene_runtime import store_scene
    calls = []
    async def send(line):
        calls.append(line)
        if line.endswith('/Overwrite'): raise ActionError('результат неизвестен')
        if line.startswith('List Executor '): return 'Executor '+line.split()[-1]+' Priority=Normal SoftLTP=on Chaser=off'
        if 'PANELSCENE' in line:
            import re
            send.probe = re.search(r"PANELSCENE','([a-f0-9]{16})", line)[1] + ' manual'
        if line == 'ListVar': return '$PANELSCENE = ' + send.probe
        return 'OK'
    with pytest.raises(ActionError, match='неизвестен'):
        asyncio.run(store_scene(send, '1.101', 'New', [12], spare='1.1'))
    assert calls[-2:] == ['Copy Cue 1 Executor 1.101 At Cue 2 Executor 1.1 /CueOnly',
                          'Copy Cue 1 Executor 1.1 At Cue 1 Executor 1.101 /CueOnly /Overwrite']
    assert sum(x.endswith('/Overwrite') for x in calls) == 1


@pytest.mark.parametrize('change', ['gen', 'stop', 'show'])
def test_loss_of_context_stops_native_transition_without_late_commands(tmp_path, monkeypatch, change):
    from ma2panel import bridge
    import json
    captured = []
    monkeypatch.setattr(bridge, 'register_api', lambda app, c, local: captured.append(c))
    cfg = json.loads(__import__('pathlib').Path('tests/config.test.json').read_text())
    cfg['show'] = 'Mock show'
    bridge.create_app(cfg, mock=True, config_path=str(tmp_path / 'config.json'), settings={'safety': {'mode': 'full'}})
    c = captured[0]
    c.state['show'] = {'name': 'Mock show', 'source': 'ma2'}
    c.link.state = 'logged_in'
    calls = []
    async def send(line, **kw):
        calls.append(line)
        if line == 'ListVar': return True, 'Global : $SHOWFILE = Mock show\nGlobal : $PANELSCENE = ' + c.state.get('probe', '')
        if line.startswith('List Executor '): return True, 'Executor '+line.split()[-1]+' Priority=Normal SoftLTP=on Chaser=off'
        if 'PANELSCENE' in line:
            import re
            c.state['probe'] = re.search(r"PANELSCENE','([a-f0-9]{16})", line)[1] + ' manual'
        if line.startswith('Goto '):
            if change == 'gen': c.link._gen += 1
            elif change == 'stop': c.link.halted = True; c.link.halted = False
            else: c.state['plan_epoch'] += 1
        return True, 'OK'
    c.link.send = send
    async def run():
        assert await c.execute('scene_go', {'id': 'pianist', 'fade': 5}, {}, [])
        assert not any(x.startswith('Off Executor') for x in calls)
        assert not c.bg or all(t.get_coro().__name__ != 'swap_off' for t in c.bg)
        for t in list(c.bg): t.cancel()
        await asyncio.gather(*c.bg, return_exceptions=True)
    try: asyncio.run(run())
    finally: bridge.log.removeHandler(c.diag_handler)
