import asyncio
import pytest
from test_status_evidence import context  # noqa: F401


@pytest.mark.parametrize('action', [('dim', {'v': 71}, [12]), ('jog', {'pan': 1, 'tilt': 0}, [12]), ('master', {'v': 71}, [])])
@pytest.mark.parametrize('change', ['disconnect', 'replace', 'plan', 'connection', 'halt'])
def test_popped_intent_rechecks_scope_under_lock(context, action, change):
    c = context
    async def go():
        ws, other = object(), object()
        c.sessions[ws] = {'base': None, 'selection': [12]}
        c.sessions[other] = {'base': None, 'selection': [12]}
        a, values, ids = action
        # Capture at admission, before the throttle removes the item.
        intent = {'ws': ws, 'a': a, 'action': {'a': a, **values}, 'ids': ids,
                  'ticket': (ws, c.sessions[ws], c.state["plan_epoch"], c.link._gen, c.link._stop_epoch)}
        sent = []
        async def send(line, **kw):
            sent.append(line)
            return True, 'ok'
        c.link.send = send
        await c.action_lock.acquire()
        task = asyncio.create_task(c.throttled('test', intent))
        await asyncio.sleep(0)
        assert c.action_lock._waiters
        if change == 'disconnect': c.sessions.pop(ws)
        if change == 'replace': c.sessions[ws] = dict(c.sessions[ws])
        if change == 'plan': c.state['plan_epoch'] += 1
        if change == 'connection': c.link._gen += 1
        if change == 'halt': c.link._stop_epoch += 1
        c.action_lock.release()
        await task
        assert sent == []
        # An independent client remains admitted after a local disconnect.
        if change in ('disconnect', 'replace'):
            await c.throttled('other', {'ws': other, 'a': 'dim', 'action': {'a': 'dim', 'v': 32},
                                      'ids': [12], 'ticket': (other, c.sessions[other], c.state["plan_epoch"], c.link._gen, c.link._stop_epoch)})
            assert sent == ['Fixture 12', 'At 32']
    asyncio.run(go())


def test_disconnect_after_first_line_keeps_partial_and_finishes_once(context):
    c = context
    async def go():
        ws = object()
        c.sessions[ws] = {}
        calls = []
        async def send(line, **kw):
            calls.append(line)
            c.sessions.pop(ws, None)
            return True, 'ok'
        c.link.send = send
        ticket = (ws, c.sessions[ws], c.state['plan_epoch'], c.link._gen, c.link._stop_epoch)
        err = await c.execute('dim', {'a': 'dim', 'v': 71}, {}, [12], ticket=ticket)
        assert err and calls == ['Fixture 12']
        op = {'key': 'test', 'id': None, 'ws': ws, 'a': 'dim', 'evidence': ['sent']}
        c.active_operations['test'] = op
        await c.throttled('x', {'ws': ws, 'operation': op})
        await c.throttled('x', {'ws': ws, 'operation': op})
        assert op['finished'] and not c.active_operations
    asyncio.run(go())


def test_plan_switch_refreshes_guard_attrs_and_negative_capabilities(context):
    import json
    c = context
    async def go():
        c.state['no_attr'] = {'zoom': ['Par']}
        name = 'B'
        path = c.plan_path(name, write=True)
        path.parent.mkdir(exist_ok=True)
        plan = {**c.cfg, 'show': name, 'attrs': {**c.original_attrs, 'zoom': {'cmd': 'Attribute "CustomZoom" At {v}'}}}
        path.write_text(json.dumps(plan))
        await c.open_show_plan(name)
        assert not c.state['no_attr']
        assert 'CustomZoom' in c.attr_names
        assert c.guard('Attribute "CustomZoom" At 50') is None
        assert c.get_config_attrs()['zoom']['cmd'] == 'Attribute "CustomZoom" At {v}'
    asyncio.run(go())


def test_reconnect_resets_negative_capabilities(context):
    c = context
    c.state['no_attr'] = {'zoom': ['Par']}
    c.invalidate_profiles()
    assert not c.state['no_attr']


def test_fade_ticket_is_captured_before_task_starts(context, monkeypatch):
    import json
    from types import SimpleNamespace
    from ma2panel import bridge
    c = context
    async def go():
        ws = object()
        c.sessions[ws] = {'selection': [12], 'base': None}
        c.remember('dim', {'v': 20}, [12], {12: {'dim': 20}}, {})
        admitted = []
        class Deferred:
            def cancel(self): pass
        def defer(coro):
            if coro.cr_code.co_name != 'play_fade':
                return asyncio.create_task(coro)
            admitted.append(coro)
            return Deferred()
        proxy = SimpleNamespace(**{**vars(asyncio), 'create_task': defer})
        monkeypatch.setattr(bridge, 'asyncio', proxy)
        sent = []
        async def send(line, **kw):
            sent.append(line)
            return True, 'ok'
        c.link.send = send
        assert await c.handle(ws, json.dumps({'a': 'dim', 'v': 71, 'fade': .01})) is None
        assert len(admitted) == 1
        c.link._stop_epoch += 1  # halt/resume before the task's first timeslice
        await admitted[0]
        assert not sent
    asyncio.run(go())
