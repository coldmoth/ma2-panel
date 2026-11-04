"""Light history and state regressions; fake transport, no console."""
import asyncio
import pytest
from test_status_evidence import context  # noqa: F401


def seed(c, values):
    c.remember("aim", {}, [], values, {})


@pytest.mark.parametrize('failed_stage', [1, 2, 3, 4])
@pytest.mark.parametrize('failure', ['error', 'unknown', 'halt'])
def test_partial_color_forgets_rgb_but_keeps_unrelated_dim(context, failed_stage, failure):
    c = context
    async def go():
        seed(c, {12: {'rgb': [10, 20, 30], 'dim': 42}})
        c.state['sent'] = {12: {'rgb', 'dim'}}
        calls = []
        async def send(line, **kw):
            calls.append(line)
            if len(calls) == failed_stage:
                if failure == 'unknown': c.on_result({'cmd': line, 'status': 'unknown'})
                return False, failure
            return True, 'ok'
        c.link.send = send
        assert await c.execute('color', {'a': 'color', 'r': 40, 'g': 50, 'b': 60}, {}, [12])
        assert len(calls) == failed_stage
        if failure == 'unknown':
            assert not c.state['shown']
        else:
            assert c.state['shown'][12]['dim'] == 42
            assert ('rgb' in c.state['shown'][12]) == (failed_stage <= 2)
    asyncio.run(go())


@pytest.mark.parametrize('failed_stage', range(1, 7))
def test_partial_position_preset_invalidates_only_successful_prefix(context, failed_stage):
    c = context
    c.cfg['fixtures'] += [{**c.cfg['fixtures'][0], 'id': 14}]
    c.cfg['presets'] = [{'id': 'test', 'pos': {'12': {'pan': 60, 'tilt': 70}, '14': {'pan': 80, 'tilt': 90}}}]
    async def go():
        seed(c, {fid: {'pan': 10, 'tilt': 20, 'dim': 42} for fid in (12, 14)})
        c.state['sent'] = {fid: {'pan', 'tilt', 'dim'} for fid in (12, 14)}
        calls = []
        async def send(line, **kw):
            calls.append(line)
            return (False, 'error') if len(calls) == failed_stage else (True, 'ok')
        c.link.send = send
        assert await c.execute('preset_go', {'a': 'preset_go', 'id': 'test'}, {}, [])
        assert len(calls) == failed_stage
        for fid, pan_stage, tilt_stage in [(12, 2, 3), (14, 5, 6)]:
            assert c.state['shown'][fid]['dim'] == 42
            assert ('pan' in c.state['shown'][fid]) == (failed_stage <= pan_stage)
            assert ('tilt' in c.state['shown'][fid]) == (failed_stage <= tilt_stage)
    asyncio.run(go())


@pytest.mark.parametrize('failed_stage', [1, 2])
@pytest.mark.parametrize('failure', ['error', 'unknown', 'halt', 'reconnect'])
def test_clearall_prefix_discards_programmer_basis(context, failed_stage, failure):
    c = context
    async def go():
        seed(c, {12: {'pan': 35, 'tilt': 65, 'dim': 42}})
        c.state['sent'] = {12: {'pan', 'tilt', 'dim'}}
        c.state['live'] = {12: {'dim': 30}}
        session = {'selection': [12], 'base': {12: {'pan': 35, 'tilt': 65}}}
        c.sessions['client'] = session
        calls = []
        async def send(line, **kw):
            calls.append(line)
            if len(calls) == failed_stage:
                if failure == 'unknown': c.on_result({'cmd': line, 'status': 'unknown'})
                if failure == 'reconnect': c.link._gen += 1; c.invalidate_evidence()
                return False, failure
            return True, 'ok'
        c.link.send = send
        assert await c.execute('scene_go', {'a': 'scene_go', 'id': 'pianist'}, session, [])
        assert len(calls) == failed_stage
        if failed_stage == 2 or failure in ('unknown', 'reconnect'):
            assert not c.state['shown'] and not c.state['sent']
            assert session['base'] is None
            assert c.fade_starts('dim', [12]) is None
        if failure not in ('unknown', 'reconnect'):
            assert c.state['live'] == {12: {'dim': 30}}
        c.sessions.clear()
    asyncio.run(go())


@pytest.mark.parametrize('kind', ['light', 'config'])
@pytest.mark.parametrize('transition', ['B', 'A-return', 'connection'])
def test_undo_cannot_cross_show_epoch(context, kind, transition):
    c = context
    async def go():
        c.state['show'] = {'name': 'A'}
        c.cfg['show'] = 'A'
        c.add_history('dim' if kind == 'light' else 'group_save', 'test', kind,
                      {12: {'dim': 20}} if kind == 'light' else {'groups': []}, [12])
        entry = c.history[-1]
        if transition == 'connection':
            c.link._gen += 1
        else:
            c.update_show({'name': 'B'})
            c.cfg['show'] = 'B'
            if transition == 'A-return':
                c.update_show({'name': 'A'})
                c.cfg['show'] = 'A'
        calls = []
        async def send(line, **kw): calls.append(line); return True, 'ok'
        c.link.send = send
        ws = object()
        c.sessions[ws] = {'selection': [12], 'base': None, 'simple': False}
        result = await c.handle(ws, '{"a":"undo","n":%d}' % entry['n'])
        assert not result['ok']
        assert not calls
        assert c.history_msg()['history'][0]['undo'] is False
        assert c.history_msg()['history'][0]['reason']
        assert not __import__('pathlib').Path(c.config_path).exists()
    asyncio.run(go())


@pytest.mark.parametrize('phase', ['waiting', 'between-lines'])
def test_undo_context_checked_after_lock_and_between_lines(context, phase):
    c = context
    async def go():
        c.add_history('dim', 'test', 'light', {12: {'dim': 20}}, [12])
        entry = c.history[-1]
        calls = []
        async def send(line, **kw):
            calls.append(line)
            c.state['plan_epoch'] += 1
            return True, 'ok'
        c.link.send = send
        ws = object()
        c.sessions[ws] = {'selection': [12], 'base': None, 'simple': False}
        if phase == 'waiting': await c.action_lock.acquire()
        task = asyncio.create_task(c.handle(ws, '{"a":"undo","n":%d}' % entry['n']))
        await asyncio.sleep(0)
        if phase == 'waiting':
            c.state['plan_epoch'] += 1
            c.action_lock.release()
        result = await task
        assert not result['ok']
        assert calls == ([] if phase == 'waiting' else ['Fixture 12'])
    asyncio.run(go())


def test_light_history_snapshot_is_taken_after_waiting_for_lock(context):
    c = context
    async def go():
        seed(c, {12: {'dim': 10}})
        c.state['sent'] = {12: {'dim'}}
        async def send(line, **kw): return True, 'ok'
        c.link.send = send
        await c.action_lock.acquire()
        task = asyncio.create_task(c.execute('dim', {'a': 'dim', 'v': 30}, {}, [12]))
        await asyncio.sleep(0)
        c.state['shown'][12]['dim'] = 20
        c.action_lock.release()
        assert await task is None
        assert c.history[-1]['before'] == {12: {'dim': 20}}
    asyncio.run(go())


def test_successful_config_history_does_not_capture_other_client_delta(context):
    import json
    c = context
    async def go():
        paused, release = asyncio.Event(), asyncio.Event()
        first = None
        class Socket:
            client = None
            async def send_json(self, msg):
                if asyncio.current_task() is first and 'config' in msg:
                    paused.set()
                    await release.wait()
        a, b = Socket(), Socket()
        for ws in (a, b):
            c.clients.add(ws)
            c.sessions[ws] = {'selection': [], 'base': None, 'requests': set(), 'legacy_revision': c.revision_token()}
        first = asyncio.create_task(c.perform_action(a, json.dumps({'a': 'group_save', 'label': 'A', 'ids': [12]})))
        await paused.wait()
        c.sessions[b]['legacy_revision'] = c.revision_token()
        second = asyncio.create_task(c.perform_action(b, json.dumps({'a': 'fixture_flag', 'id': 12, 'flip_pan': True})))
        for _ in range(100):
            await asyncio.sleep(0)
            if c.cfg['fixtures'][0].get('flip_pan'): break
        assert c.cfg['fixtures'][0]['flip_pan']
        release.set()
        await asyncio.gather(first, second)
        entry = next(e for e in c.history if e['a'] == 'group_save')
        assert set(entry['before']) == {'groups'}
        assert (await c.handle(a, json.dumps({'a': 'undo', 'n': entry['n']})))['ok']
        assert c.cfg['fixtures'][0]['flip_pan'] is True
    asyncio.run(go())


def test_concurrent_undo_has_one_owner(context):
    import json
    c = context
    async def go():
        c.add_history('dim', 'test', 'light', {12: {'dim': 20}}, [12])
        entry = c.history[-1]
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def send(line, **kw):
            calls.append(line)
            entered.set()
            await release.wait()
            return True, 'ok'
        c.link.send = send
        sockets = [object(), object()]
        for ws in sockets: c.sessions[ws] = {'selection': [12], 'base': None, 'simple': False}
        action = json.dumps({'a': 'undo', 'n': entry['n']})
        first = asyncio.create_task(c.handle(sockets[0], action))
        await entered.wait()
        second = asyncio.create_task(c.handle(sockets[1], action))
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(first, second)
        assert sorted(r['ok'] for r in results) == [False, True]
        assert calls == ['Fixture 12', 'At 20']
    asyncio.run(go())


@pytest.mark.parametrize('failure', ['error', 'unknown'])
def test_partial_undo_cannot_be_reused(context, failure):
    import json
    c = context
    async def go():
        c.add_history('aim', 'test', 'light', {12: {'pan': 20, 'tilt': 30}}, [12])
        entry = c.history[-1]
        calls = []
        async def send(line, **kw):
            calls.append(line)
            if 'Tilt' in line:
                if failure == 'unknown': c.link._result(line, 'unknown', failure)
                return False, failure
            return True, 'ok'
        c.link.send = send
        ws = object()
        c.sessions[ws] = {'selection': [12], 'base': None, 'simple': False}
        action = json.dumps({'a': 'undo', 'n': entry['n']})
        assert not (await c.handle(ws, action))['ok']
        before = len(calls)
        assert not (await c.handle(ws, action))['ok']
        assert len(calls) == before
        public = c.history_msg()['history'][0]
        assert public['undo'] is False and public['reason']
        assert public['undo_state'] == ('unknown' if failure == 'unknown' else 'partial')
        assert len(public['undo_steps']) == 3
    asyncio.run(go())


def test_master_evidence_is_independent_of_fixture_commands(context):
    c = context
    clock = [0.0]
    c.sent_evidence.clock = lambda: clock[0]
    c.remember('master', {'v': 60}, [], {}, {})
    assert c.values_meta()['master']['freshness'] == 'fresh'
    clock[0] = 7
    c.remember('dim', {'v': 42}, [12], {}, {})
    assert c.values_meta()['master']['freshness'] == 'stale'
    async def go():
        c.invalidate_evidence()
        assert c.shown_msg()['master'] is None
        assert c.values_meta()['master']['freshness'] == 'unknown'
    asyncio.run(go())


def test_unrelated_send_does_not_refresh_old_attribute_or_fade(context):
    c = context
    clock = [0.0]
    c.sent_evidence.clock = lambda: clock[0]
    c.cfg['fixtures'].append({**c.cfg['fixtures'][0], 'id': 14})
    c.remember('dim', {'v': 20}, [12], {}, {})
    assert c.fade_starts('dim', [12]) == [(20, [12])]
    clock[0] = 7
    c.remember('dim', {'v': 80}, [14], {}, {})
    assert c.fade_starts('dim', [12]) is None
    assert c.fade_starts('dim', [14]) == [(80, [14])]
    assert c.shown_msg()['shown'] == {14: {'dim': 80}}
    assert c.values_meta()['sent:12:dim']['freshness'] == 'stale'
    assert c.values_meta()['sent:14:dim']['freshness'] == 'fresh'


def test_attribute_age_is_independent_within_fixture(context):
    c = context
    clock = [0.0]
    c.sent_evidence.clock = lambda: clock[0]
    c.remember('aim', {}, [12], {12: {'pan': 20, 'tilt': 30}}, {})
    clock[0] = 5
    c.remember('aim', {}, [12], {12: {'pan': 40}}, {})
    clock[0] = 6
    shown = c.shown_msg()['shown']
    assert shown == {12: {'pan': 40}}
    assert c.values_meta()['sent:12:tilt']['freshness'] == 'stale'


def test_undo_basis_expires_even_when_latest_value_is_fresh(context):
    c = context
    clock = [0.0]
    c.sent_evidence.clock = lambda: clock[0]
    async def go():
        c.remember('dim', {'v': 20}, [12], {}, {})
        clock[0] = 5
        async def send(line, **kw): return True, 'ok'
        c.link.send = send
        await c.execute('dim', {'a': 'dim', 'v': 40}, {}, [12])
        assert c.history_msg()['history'][-1]['undo'] is True
        clock[0] = 6
        assert c.fade_starts('dim', [12]) == [(40, [12])]
        assert c.history_msg()['history'][-1]['undo'] is False
    asyncio.run(go())


def test_stale_position_cannot_seed_move_jog_or_saved_preset(context):
    from commands import ActionError
    c = context
    c.cfg['fixtures'][0]['moves'] = True
    clock = [0.0]
    c.sent_evidence.clock = lambda: clock[0]
    async def go():
        seed(c, {12: {'pan': 20, 'tilt': 30}})
        ws = object()
        session = {'selection': [12], 'base': None, 'simple': False}
        c.sessions[ws] = session
        assert (await c.handle(ws, '{"a":"move_start"}'))['ok']
        clock[0] = 6
        assert not (await c.handle(ws, '{"a":"move_start"}'))['ok']
        with pytest.raises(ActionError):
            c.config_edit('preset_save', {'label': 'stale'}, session)
        _, values = c.lines_for('nudge', {'a': 'nudge', 'attr': 'pan', 'dir': 1, 'step': 1}, session, [12])
        assert values == {}
        seed(c, {12: {'pan': 40}})
        with pytest.raises(ActionError):
            c.config_edit('preset_save', {'label': 'half-fresh'}, session)
    asyncio.run(go())


def test_undo_basis_expiring_while_waiting_sends_nothing(context):
    import json
    c = context
    clock = [0.0]
    c.sent_evidence.clock = lambda: clock[0]
    async def go():
        c.add_history('dim', 'test', 'light', {12: {'dim': 20}}, [12])
        entry = c.history[-1]
        ws = object()
        c.sessions[ws] = {'selection': [12], 'base': None, 'simple': False}
        calls = []
        async def send(line, **kw): calls.append(line); return True, 'ok'
        c.link.send = send
        await c.action_lock.acquire()
        task = asyncio.create_task(c.handle(ws, json.dumps({'a': 'undo', 'n': entry['n']})))
        await asyncio.sleep(0)
        clock[0] = 6
        c.action_lock.release()
        assert not (await task)['ok']
        assert not calls
    asyncio.run(go())


def test_last_light_reply_cannot_repopulate_state_after_reconnect(context):
    c = context
    async def go():
        calls = []
        async def send(line, **kw):
            calls.append(line)
            if line.startswith('At '):
                c.link._gen += 1
                c.invalidate_evidence()
            return True, 'ok'
        c.link.send = send
        err = await c.execute('dim', {'a': 'dim', 'v': 42}, {}, [12])
        assert err
        assert c.shown_msg()['shown'] == {}
        assert len(calls) == 2
    asyncio.run(go())
