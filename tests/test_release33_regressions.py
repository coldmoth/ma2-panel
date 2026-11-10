"""Release blockers: identity reuse, stale group intents and bounded scene release."""
import asyncio
import copy
import json
from pathlib import Path

import pytest

from ma2panel.fixtures import merge_fixtures
from ma2panel import bridge
from test_stage4_integration import client, desk_link


@pytest.fixture
def context(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(bridge, 'register_api', lambda app, c, local: captured.append(c))
    cfg = json.loads(Path('tests/config.test.json').read_text())
    cfg['ma2']['export_dir'] = str(tmp_path)
    bridge.create_app(cfg, mock=True, config_path=str(tmp_path / 'config.json'),
                      settings={'safety': {'mode': 'full', 'allow_fixture_read': True, 'allow_group_store': True}})
    c = captured[0]
    c.link.state = 'logged_in'
    c.state['show'] = {'name': 'Mock show', 'source': 'ma2'}
    yield c
    bridge.log.removeHandler(c.diag_handler)


@pytest.mark.parametrize('reverse', [False, True])
def test_renumber_with_reused_id_transfers_only_explicit_identity(context, reverse):
    c = context
    c.cfg['fixtures'] = [{'id': 23, 'name': 'Old head', 'type': 'Head',
                          'label': 'My head', 'x': .2, 'beam': {'home': 20}}]
    c.cfg['groups'] = [{'id': 'g', 'fixtures': [23]}]
    c.cfg['ma2groups'] = [{'n': 7, 'ids': [23]}]
    c.cfg['presets'] = [{'id': 'p', 'pos': {'23': {'pan': 10}}}]
    c.cfg['scenes'][0]['fixtures'] = [23]
    scene_exec = c.cfg['scenes'][0]['exec']
    ws = client(c)
    c.sessions[ws]['selection'] = [23]
    # A saved plan has an independent Patch. Import must not mutate it.
    plan = Path(c.config_path).parent / 'shows' / 'other.json'
    plan.parent.mkdir(exist_ok=True)
    plan.write_text(json.dumps({'show': 'Other', 'fixtures': [{'id': 23}]}))
    saved = plan.read_bytes()
    rows = ['<Fixture fixture_id="23" name="New bar" type="Bar"/>',
            '<Fixture fixture_id="31" name="Old head" type="Head"/>']
    if reverse:
        rows.reverse()
    before = copy.deepcopy(c.cfg)
    async def go():
        result = c.import_xml('<MA>' + ''.join(rows) + '</MA>', 'ma2')
        assert not result['ok'] and result['ambiguous']
        assert c.cfg == before
        result = c.confirm_import({'request_token': result['request_token'],
                                   'choices': {'23': None, '31': 23}})
        assert result['ok'], result
    asyncio.run(go())
    fixtures = {f['id']: f for f in c.cfg['fixtures']}
    assert fixtures[31]['label'] == 'My head' and fixtures[31]['x'] == .2
    assert not any(k in fixtures[23] for k in ('x', 'beam'))
    assert c.cfg['groups'][0]['fixtures'] == [31]
    assert c.cfg['ma2groups'][0]['ids'] == [31]
    assert c.cfg['presets'][0]['pos'] == {'31': {'pan': 10}}
    assert c.cfg['scenes'][0]['fixtures'] == [31]
    assert c.cfg['scenes'][0]['exec'] == scene_exec
    assert c.sessions[ws]['selection'] == [31]
    assert plan.read_bytes() == saved


def test_fixture_id_swap_is_simultaneous():
    old = [{'id': 23, 'name': 'A', 'type': 'Head', 'label': 'Left'},
           {'id': 31, 'name': 'B', 'type': 'Head', 'label': 'Right'}]
    found = [{'id': 23, 'name': 'B', 'type': 'Head', 'address': '1.1'},
             {'id': 31, 'name': 'A', 'type': 'Head', 'address': '1.20'}]
    merged = merge_fixtures(old, found, choices={'23': 31, '31': 23})
    assert [(f['id'], f['label']) for f in merged] == [(23, 'Right'), (31, 'Left')]


def test_partial_patch_keeps_unseen_fixture_data():
    old = [{'id': 23, 'name': 'A', 'type': 'Head', 'label': 'Left'},
           {'id': 50, 'name': 'B', 'type': 'Bar', 'label': 'Keep', 'x': .8}]
    before = copy.deepcopy(old)
    found = [{'id': 31, 'name': 'A', 'type': 'Head', 'address': '1.20'}]
    merged = {f['id']: f for f in merge_fixtures(old, found)}
    assert merged[31]['label'] == 'Left' and 23 not in merged
    assert merged[50]['missing'] and merged[50]['label'] == 'Keep' and merged[50]['x'] == .8
    assert old == before


def test_competing_imported_identities_require_one_to_one_confirmation():
    old = [{'id': 23, 'name': 'A', 'type': 'Head', 'label': 'Mine', 'x': .2}]
    found = [{'id': n, 'name': 'A', 'type': 'Head', 'address': '1.20'} for n in (31, 32)]
    assert all(f.get('ambiguous_candidates') for f in merge_fixtures(old, found) if f['id'] in (31, 32))
    with pytest.raises(ValueError, match='дважды'):
        merge_fixtures(old, found, choices={'31': 23, '32': 23})
    merged = {f['id']: f for f in merge_fixtures(old, found, choices={'31': 23, '32': None})}
    assert merged[31]['label'] == 'Mine' and merged[31]['x'] == .2
    assert merged[32]['label'] == 'A' and 'x' not in merged[32]


@pytest.mark.parametrize('change', ['none', 'blackout', 'reconnect', 'show', 'plan', 'disconnect'])
def test_group_read_cannot_outlive_its_client_ticket(context, change):
    c = context
    desk, calls = desk_link(c)
    desk.real = True
    desk.export_dir = str(Path(c.config_path).parent)
    desk.groups[7], desk.group_members[7] = 'Heads', [12]
    c.cfg['ma2groups'] = [{'n': 7, 'name': 'Heads', 'ids': [12]}]
    original = c.link.send
    async def go():
        ws, other = client(c), client(c)
        c.sessions[ws]['selection'] = []
        entered, resume = asyncio.Event(), asyncio.Event()
        async def slow(line, **kw):
            result = await original(line, **kw)
            if line == 'List Group 1 Thru 999':
                entered.set()
                await resume.wait()
            return result[0], result[1].replace('\r', '')
        c.link.send = slow
        task = asyncio.create_task(c.handle(ws, json.dumps({'a': 'ma2_group_go', 'n': 7})))
        await asyncio.wait_for(entered.wait(), 3)
        bo = None
        if change == 'blackout':
            bo = asyncio.create_task(c.handle(other, json.dumps({'a': 'blackout'})))
            await asyncio.sleep(0)
        elif change == 'reconnect':
            c.link._gen += 1
        elif change == 'show':
            c.update_show({'name': 'Other show', 'source': 'ma2'})
        elif change == 'plan':
            c.state['plan_epoch'] += 1
        elif change == 'disconnect':
            c.sessions.pop(ws)
        resume.set()
        result = await task
        if change == 'none':
            assert result['ok'], result
            assert 'Group 7' in calls
            return
        assert not result['ok'], result
        assert 'Group 7' not in calls
        assert c.sessions.get(ws, {}).get('selection') != [12]
        if bo:
            assert (await bo)['ok']
    asyncio.run(go())


def test_scene_launch_cost_does_not_grow_with_catalogue(context):
    c = context
    desk, calls = desk_link(c)
    c.cfg['scenes'] = [{'id': str(i), 'exec': f'1.{101+i}'} for i in range(100)]
    desk.rows = {s['exec']: s['id'] for s in c.cfg['scenes']}
    desk.cues = {ex: {1: {}} for ex in desk.rows}
    # Executor addresses outside normal range are intentionally not probed:
    # unrelated catalogue rows must not block an otherwise valid launch.
    async def go():
        ws = client(c)
        for sid in ('0', '1', '2'):
            result = await c.handle(ws, json.dumps({'a': 'scene_go', 'id': sid}))
            assert result['ok'], result
    asyncio.run(go())
    assert [line for line in calls if line.startswith('Off Executor')] == [
        'Off Executor 1.101', 'Off Executor 1.102']
    assert len(calls) < 40
    assert not any('1.150' in line for line in calls)


@pytest.mark.parametrize('change', ['unknown', 'plan', 'fresh_off', 'stale_off'])
def test_next_transition_respects_ownership_and_readback(context, change):
    c = context
    c.cfg['scenes'].append({'id': 'rehearsal', 'exec': '1.102', 'label': 'Rehearsal'})
    _, calls = desk_link(c)
    original = c.link.send
    async def go():
        ws = client(c)
        async def fail_reply(line, **kw):
            ok, reply = await original(line, **kw)
            return (False, 'unknown result') if line.startswith('Goto') else (ok, reply)
        if change == 'unknown':
            c.link.send = fail_reply
        result = await c.handle(ws, json.dumps({'a': 'scene_go', 'id': 'pianist'}))
        assert result['ok'] == (change != 'unknown')
        c.link.send = original
        calls.clear()
        if change == 'plan':
            c.state['plan_epoch'] += 1
        elif change in ('fresh_off', 'stale_off'):
            c.scene_evidence.observe('pianist', False)
            if change == 'stale_off':
                value, stamp, wall = c.scene_evidence.records['pianist']
                c.scene_evidence.records['pianist'] = value, stamp - 7, wall
        result = await c.handle(ws, json.dumps({'a': 'scene_go', 'id': 'rehearsal'}))
        assert result['ok'], result
        assert ('Off Executor 1.101' in calls) == (change in ('unknown', 'stale_off'))
    asyncio.run(go())


def test_extracted_group_waiting_for_lock_is_cancelled(context):
    c = context
    _, calls = desk_link(c)
    async def go():
        ws, other = client(c), client(c)
        async with c.action_lock:
            old = asyncio.create_task(c.handle(ws, json.dumps({'a': 'ma2_group_go', 'n': 7})))
            await asyncio.sleep(0)
            bo = asyncio.create_task(c.handle(other, json.dumps({'a': 'blackout'})))
            await asyncio.sleep(0)
        assert not (await old)['ok']
        assert (await bo)['ok']
        assert not any(line.startswith(('List Group', 'Export Group', 'Group ')) for line in calls)
    asyncio.run(go())


def test_group_store_cannot_cross_blackout_after_empty_slot_read(context):
    c = context
    desk, calls = desk_link(c)
    c.cfg['groups'] = [{'id': 'local', 'label': 'Local', 'fixtures': [12]}]
    original = c.link.send
    async def go():
        ws = client(c)
        async def send(line, **kw):
            result = await original(line, **kw)
            if line == 'List Group 8':
                c.state['blackout_epoch'] += 1
            return result
        c.link.send = send
        result = await c.handle(ws, json.dumps({'a': 'group_store_ma2', 'id': 'local', 'n': 8, 'confirm': 8}))
        assert not result['ok'], result
        assert not any(line.startswith(('Fixture ', 'Store Group')) for line in calls)
        assert 8 not in desk.groups
    asyncio.run(go())
