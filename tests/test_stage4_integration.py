"""Integration of the concert UI barrier with reversible Grand Master suppression."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from ma2panel.mock import MockMA2
from test_highlight_ordering import context  # noqa: F401


def client(c):
    class Socket:
        client = SimpleNamespace(host='test')
        async def send_json(self, message):
            pass
    ws = Socket()
    c.sessions[ws] = {'selection': [12], 'base': None, 'simple': False}
    return ws


def desk_link(c):
    desk = MockMA2('panel', None)
    calls = []
    async def send(line, **kwargs):
        assert c.guard(line) is None, line
        calls.append(line)
        return True, desk._reply(line)
    c.link.send = send
    return desk, calls


@pytest.mark.parametrize('action', [
    {'a':'dim','v':90}, {'a':'jog','pan':1,'tilt':2},
    {'a':'aim','pan':40}, {'a':'scene_go','id':'pianist'},
    {'a':'highlight','id':12}, {'a':'ma2_preset_go','n':1,'type':'position'},
])
def test_old_browser_gesture_is_rejected_after_grand_master_toggle(context, action):
    c = context
    desk, calls = desk_link(c)
    async def go():
        ws = client(c)
        assert (await c.handle(ws,json.dumps({'a':'blackout'})))['ok']
        assert desk.grand_master == 0
        before = list(calls)
        result = await c.handle(ws,json.dumps({**action,'blackout_epoch':0}))
        assert result and not result['ok']
        assert 'устарело' in result['err']
        await c.throttle.flush_all()
        assert calls == before
        assert c.status_msg()['status']['blackout_epoch'] == 1
    asyncio.run(go())


def test_blackout_discards_pending_slider_without_sending_it(context):
    c = context
    desk, calls = desk_link(c)
    async def go():
        ws = client(c)
        assert await c.handle(ws,json.dumps({'a':'dim','v':90})) is None
        assert not calls
        assert (await c.handle(ws,json.dumps({'a':'blackout'})))['ok']
        assert not any(line.startswith(('Fixture ', 'At ')) for line in calls)
        assert desk.grand_master == 0
        epoch = c.status_msg()['status']['blackout_epoch']
        assert (await c.handle(ws,json.dumps({'a':'blackout','blackout_epoch':epoch})))['ok']
        assert desk.grand_master == 100
        assert not any(line.startswith(('ClearAll','Off Executor')) for line in calls)
    asyncio.run(go())


def test_extracted_slider_ticket_is_invalidated_by_blackout(context):
    c = context
    desk_link(c)
    async def go():
        ws = client(c)
        ticket = c.action_ticket(ws)
        await c.action_lock.acquire()
        old = asyncio.create_task(c.execute('dim',{'a':'dim','v':80},c.sessions[ws],[12],ticket=ticket))
        bo = asyncio.create_task(c.handle(ws,json.dumps({'a':'blackout'})))
        await asyncio.sleep(0)
        c.action_lock.release()
        assert await old
        assert (await bo)['ok']
    asyncio.run(go())


def test_blackout_stops_inflight_slider_after_selection_before_value(context):
    c = context
    _, calls = desk_link(c)
    send = c.link.send
    async def go():
        ws = client(c)
        entered, finish = asyncio.Event(), asyncio.Event()
        async def slow(line, **kwargs):
            if line == 'Fixture 12':
                entered.set()
                await finish.wait()
            return await send(line, **kwargs)
        c.link.send = slow
        old = asyncio.create_task(c.execute('dim',{'a':'dim','v':90},c.sessions[ws],[12],ticket=c.action_ticket(ws)))
        await entered.wait()
        bo = asyncio.create_task(c.handle(ws,json.dumps({'a':'blackout'})))
        await asyncio.sleep(0)
        finish.set()
        assert await old
        assert (await bo)['ok']
        assert 'At 90' not in calls
    asyncio.run(go())


def test_blackout_cancels_undo_already_waiting_for_action_lock(context):
    c = context
    _, calls = desk_link(c)
    async def go():
        ws = client(c)
        await c.action_lock.acquire()
        undo = asyncio.create_task(c.undo_light({12:{'dim':90}},c.sessions[ws]))
        bo = asyncio.create_task(c.handle(ws,json.dumps({'a':'blackout'})))
        await asyncio.sleep(0)
        c.action_lock.release()
        assert await undo
        assert (await bo)['ok']
        assert 'At 90' not in calls
    asyncio.run(go())


def test_duplicate_blackout_epoch_does_not_restore_grand_master(context):
    c = context
    desk, calls = desk_link(c)
    async def go():
        ws = client(c)
        first = await c.handle(ws,json.dumps({'a':'blackout','blackout_epoch':0}))
        second = await c.handle(ws,json.dumps({'a':'blackout','blackout_epoch':0}))
        assert first['ok'] and not second['ok']
        assert desk.grand_master == 0
        assert [line for line in calls if line.startswith('SpecialMaster ')] == ['SpecialMaster 2.1 At 0']
    asyncio.run(go())
