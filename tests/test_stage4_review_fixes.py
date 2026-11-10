"""Independent review regressions on the public package architecture."""
import asyncio
import copy
import json

import pytest

from ma2panel.commands import build
from ma2panel.fixtures import merge_fixtures
from test_highlight_ordering import context  # noqa: F401
from test_stage4_integration import client, desk_link


@pytest.mark.parametrize('action', [
    {'a': 'dim', 'v': 80}, {'a': 'color', 'r': 100, 'g': 0, 'b': 0},
    {'a': 'move', 'pan': 10, 'tilt': 20}, {'a': 'jog', 'pan': 1, 'tilt': 1},
    {'a': 'nudge', 'attr': 'pan', 'step': 1, 'dir': 1},
])
def test_recovery_blocks_execution_even_after_admission(context, action):
    c = context
    _, calls = desk_link(c)
    async def go():
        c.state['recovering'] = True
        error = await c.execute(action['a'], action, {'selection': [12], 'base': {12: {'pan': 50, 'tilt': 50}}}, [12])
        assert error and ('восстан' in error or 'контекст' in error)
        assert calls == []
    asyncio.run(go())


def test_recovery_starts_while_execution_waits_for_lock(context):
    c = context
    _, calls = desk_link(c)
    async def go():
        ws = client(c)
        ticket = c.action_ticket(ws)
        async with c.action_lock:
            task = asyncio.create_task(c.execute('dim', {'a': 'dim', 'v': 80}, {}, [12], ticket=ticket))
            await asyncio.sleep(0)
            c.state['recovering'] = True
        assert await task
        assert calls == []
    asyncio.run(go())


def test_partial_action_stops_when_recovery_begins(context):
    c = context
    calls = []
    async def send(line, **kw):
        calls.append(line)
        c.state['recovering'] = True
        return True, 'OK'
    c.link.send = send
    async def go():
        error = await c.execute('color', {'a': 'color', 'r': 100, 'g': 0, 'b': 0}, {}, [12])
        assert error
        assert calls == ['Fixture 12']
    asyncio.run(go())


def test_extracted_slider_is_not_replayed_after_recovery_cycle(context):
    c = context
    _, calls = desk_link(c)
    async def go():
        ws = client(c)
        ticket = c.action_ticket(ws)
        # Authentication callbacks can start recovery without a generation change.
        c.on_state('disconnected')
        await asyncio.sleep(0)
        c.link.state = 'logged_in'
        c.state['recovering'] = False
        c.state['show'] = {'name': 'Mock show', 'source': 'ma2'}
        error = await c.execute('dim', {'a': 'dim', 'v': 80}, {}, [12], ticket=ticket)
        assert error
        assert calls == []
    asyncio.run(go())


def test_reused_fixture_id_requires_explicit_identity():
    old = [{'id': 23, 'name': 'RGB bar', 'type': 'Bar', 'label': 'Old', 'x': .2, 'y': .4,
            'beam': {'home': 20}, 'rdm': {'uid': 'old-uid'}}]
    found = [{'id': 23, 'name': 'Moving head', 'type': 'Head', 'address': '1.100'}]
    before = copy.deepcopy(old)
    preview = merge_fixtures(old, found)
    assert preview[0].get('ambiguous_candidates')
    assert old == before
    fresh = merge_fixtures(old, found, choices={'23': None})[0]
    assert fresh['label'] == 'Moving head'
    assert not any(k in fresh for k in ('x', 'y', 'beam', 'rdm'))
    kept = merge_fixtures(old, found, choices={'23': 23})[0]
    assert kept['label'] == 'Old' and kept['x'] == .2


def test_import_new_identity_detaches_groups_presets_and_selection(context):
    c = context
    c.cfg['fixtures'] = [{'id': 23, 'name': 'RGB bar', 'type': 'Bar', 'label': 'Old', 'x': .2}]
    c.cfg['groups'] = [{'id': 'local', 'fixtures': [23]}, {'id': 'desk', 'n': 1, 'fixtures': [23]}]
    c.cfg['ma2groups'] = [{'n': 1, 'ids': [23]}]
    c.cfg['presets'] = [{'id': 'position', 'pos': {'23': {'pan': 20, 'tilt': 40}}}]
    scenes = copy.deepcopy(c.cfg['scenes'])
    before = copy.deepcopy(c.cfg)
    ws = client(c)
    c.sessions[ws]['selection'] = [23]
    result = c.import_xml('<MA><Fixture fixture_id="23" name="Moving head" type="Head"/></MA>', 'ma2')
    assert not result['ok'] and result['ambiguous']
    assert c.cfg == before
    async def confirm():
        return c.confirm_import({'request_token': result['request_token'], 'choices': {'23': None}})
    asyncio.run(confirm())
    assert all(g['fixtures'] == [] for g in c.cfg['groups'])
    assert c.cfg['ma2groups'][0]['ids'] == []
    assert c.cfg['presets'][0]['pos'] == {}
    assert c.sessions[ws]['selection'] == []
    assert c.cfg['scenes'] == scenes  # native executor references are not fixture IDs


def test_renumber_moves_position_preset_reference(context):
    c = context
    c.cfg['fixtures'] = [{'id': 23, 'name': 'Head', 'type': 'Head', 'label': 'Mine'}]
    c.cfg['presets'] = [{'id': 'p', 'pos': {'23': {'pan': 20}}}]
    async def refresh():
        return c.import_xml('<MA><Fixture fixture_id="31" name="Head" type="Head"/></MA>', 'ma2')
    assert asyncio.run(refresh())['ok']
    assert c.cfg['presets'][0]['pos'] == {'31': {'pan': 20}}


def test_manual_off_updates_off_time_after_shared_fade_change(context):
    c = context
    _, calls = desk_link(c)
    async def go():
        ws = client(c)
        result = await c.handle(ws, json.dumps({'a': 'scene_fade', 'fade': 7}))
        assert result['ok']
        result = await c.handle(ws, json.dumps({'a': 'scene_off', 'id': 'pianist', 'fade': 29}))
        assert result['ok'], result
        assert calls[-2:] == ['Masterfade 7 Executor 1.101', 'Off Executor 1.101']
    asyncio.run(go())


@pytest.mark.parametrize('fade', [0, .5, 30])
def test_manual_off_builds_bounded_native_fade(fade):
    assert build({'a': 'scene_off', 'id': 's', 'fade': fade}, {'scenes': [{'id': 's', 'exec': '1.101'}]}) == [
        f'Masterfade {fade:g} Executor 1.101', 'Off Executor 1.101']


def test_transport_waiter_is_cancelled_even_when_recovery_already_finished(context):
    c = context
    exchanged = []
    async def exchange(line, timeout):
        exchanged.append(line)
        return 'OK', True
    c.link._exchange = exchange
    async def go():
        async with c.link._lock:
            task = asyncio.create_task(c.execute('dim', {'a': 'dim', 'v': 80}, {}, [12]))
            await asyncio.sleep(0)
            c.on_state('disconnected')
            c.state['recovering'] = False
            c.state['show'] = {'name': 'Mock show', 'source': 'ma2'}
        assert await task
        assert exchanged == []
    asyncio.run(go())


@pytest.mark.parametrize('old,found', [
    ({'name': 'Old', 'type': 'Head'}, {'name': 'New', 'type': 'Head'}),
    ({'name': 'Head', 'type': 'Old'}, {'name': 'Head', 'type': 'New'}),
    ({}, {'name': 'Head', 'type': 'Head'}),
])
def test_id_alone_never_confirms_identity(old, found):
    previous = {'id': 23, 'label': 'Mine', 'x': .2, **old}
    current = {'id': 23, 'address': '1.1', **found}
    assert merge_fixtures([previous], [current])[0].get('ambiguous_candidates')


def test_late_old_client_message_cannot_cross_completed_recovery(context):
    c = context
    _, calls = desk_link(c)
    async def go():
        ws = client(c)
        c.state['was_ready'] = True
        c.on_state('disconnected')
        await asyncio.sleep(0)
        c.state.update(recovering=False, show={'name': 'Mock show', 'source': 'ma2'})
        # The old WebSocket message arrived only after recovery completed.
        result = await c.handle(ws, json.dumps({'a': 'dim', 'v': 80, 'blackout_epoch': 0}))
        assert result and not result['ok']
        await c.throttle.flush_all()
        assert calls == []
        # A current browser can explicitly start a new action in the new context.
        epoch = c.state['blackout_epoch']
        assert await c.handle(ws, json.dumps({'a': 'dim', 'v': 20, 'blackout_epoch': epoch})) is None
        await c.throttle.flush_all()
        assert 'At 20' in calls
    asyncio.run(go())


def test_identity_confirmation_cancels_previously_extracted_intent(context):
    c = context
    _, calls = desk_link(c)
    c.cfg['fixtures'] = [{'id': 23, 'name': 'Bar', 'type': 'Bar', 'label': 'Old'}]
    async def go():
        ws = client(c)
        c.sessions[ws]['selection'] = [23]
        ticket = c.action_ticket(ws)
        preview = c.import_xml('<MA><Fixture fixture_id="23" name="Head" type="Head"/></MA>', 'ma2')
        c.confirm_import({'request_token': preview['request_token'], 'choices': {'23': None}})
        assert await c.execute('dim', {'a': 'dim', 'v': 100}, {}, [23], ticket=ticket)
        assert calls == []
    asyncio.run(go())


def test_shared_import_confirmation_finishes_recovery_for_http_and_ws(context):
    c = context
    c.cfg['fixtures'] = [{'id': 23, 'name': 'Bar', 'type': 'Bar'}]
    async def go():
        c.state['recovering'] = True
        c.state['recovery_error'] = 'ambiguous Patch'
        preview = c.import_xml('<MA><Fixture fixture_id="23" name="Head" type="Head"/></MA>', 'ma2')
        assert c.confirm_import({'request_token': preview['request_token'], 'choices': {'23': None}})['ok']
        assert c.state['recovering'] is False
        assert 'recovery_error' not in c.state
    asyncio.run(go())
