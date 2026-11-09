"""MA2-010: deterministic lifecycle races and explicitly confirmed recovery."""
import asyncio
import pytest
from ma2panel.commands import ActionError
import json
from pathlib import Path
from ma2panel import bridge


@pytest.fixture
def context(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(bridge, 'register_api', lambda app, c, local: captured.append(c))
    cfg = json.loads(Path('tests/config.test.json').read_text())
    cfg['ma2']['export_dir'] = str(tmp_path)
    bridge.create_app(cfg, mock=True, config_path=str(tmp_path / 'config.json'),
                      settings={'safety': {'mode': 'full', 'allow_highlight': True}})
    c = captured[0]
    c.link.state = 'logged_in'
    yield c
    bridge.log.removeHandler(c.diag_handler)


def active(c):
    c.safety['allow_highlight'] = True
    c.highlight.update(state='active', zone=[12], owner=object(), show=None, target=12,
                       restore={12: {'dim': 40}})
    c.highlight_path.write_text('{"zone":[12],"target":12}')


@pytest.mark.parametrize('phase', ['Fixture 12', 'Off Fixture 12', 'At 40'])
@pytest.mark.parametrize('change', ['gen', 'halt', 'plan'])
def test_release_stops_after_lifecycle_change(context, phase, change):
    c = context
    active(c)
    calls = []
    async def send(line, **kw):
        calls.append(line)
        if line == phase:
            if change == 'gen': c.link._gen += 1
            elif change == 'halt': c.link.halted = True; c.link.halted = False
            else: c.state['plan_epoch'] += 1
        return True, 'OK'
    c.link.send = send
    async def go():
        with pytest.raises(ActionError): await c.release_highlight('lease')
        first = list(calls)
        with pytest.raises(ActionError): await c.release_highlight('disconnect')
        assert calls == first  # no compensation or retry of unknown result
        assert calls[-1] == phase
        assert c.highlight['state'] == 'stuck'
    asyncio.run(go())


@pytest.mark.parametrize('superseded', [False, True])
def test_manual_release_requires_current_confirmation_and_never_restores(context, superseded):
    c = context
    active(c)
    calls = []
    async def send(line, **kw): calls.append(line); return True, 'OK'
    c.link.send = send
    async def go():
        # Another client's mutation shares the bridge's light ownership.
        await c.execute('dim', {'a': 'dim', 'v': 10}, {}, [12])
        token = c.highlight_status().get('release_token')
        assert token
        if superseded:
            await c.execute('dim', {'a': 'dim', 'v': 20}, {}, [12])
        calls.clear()
        if superseded:
            with pytest.raises(ActionError): await c.release_highlight('manual', token)
            assert not calls
        else:
            await c.release_highlight('manual', token)
            assert calls == ['Fixture 12', 'Off Fixture 12']
            assert c.highlight['state'] == 'idle'
    asyncio.run(go())


@pytest.mark.parametrize('first', ['release', 'mutation'])
def test_release_and_other_client_mutation_orders(context, first):
    c = context
    active(c)
    async def go():
        entered, complete = asyncio.Event(), asyncio.Event()
        calls = []
        async def send(line, **kw):
            calls.append(line)
            if len(calls) == 1:
                entered.set()
                await complete.wait()
            return True, 'OK'
        c.link.send = send
        async def release():
            async with c.action_lock:
                try: await c.release_highlight('disconnect')
                except ActionError: pass
        async def mutation():
            assert await c.execute('dim', {'a': 'dim', 'v': 10}, {}, [12]) is None
        leading = asyncio.create_task(release() if first == 'release' else mutation())
        await entered.wait()
        trailing = asyncio.create_task(mutation() if first == 'release' else release())
        await asyncio.sleep(0)
        complete.set()
        await asyncio.gather(leading, trailing)
        assert calls[-1] == 'At 10'
        if first == 'mutation': assert calls == ['Fixture 12', 'At 10']
        else: assert calls.index('At 40') < calls.index('At 10')
    asyncio.run(go())


@pytest.mark.parametrize('change', ['gen', 'stop', 'plan', 'show_roundtrip'])
def test_saved_highlight_context_cannot_be_revived(context, change):
    c = context
    active(c)
    c.highlight['context'] = (c.link._gen, c.link._stop_epoch, c.state['plan_epoch'])
    calls = []
    async def send(line, **kw): calls.append(line); return True, 'OK'
    c.link.send = send
    async def go():
        if change == 'gen': c.link._gen += 1
        elif change == 'stop': c.link._stop_epoch += 1
        elif change == 'plan': c.state['plan_epoch'] += 1
        else:
            c.update_show({'name': 'Other'})
            c.update_show({'name': None})
        with pytest.raises(ActionError): await c.release_highlight('lease')
        assert not calls
    asyncio.run(go())


@pytest.mark.parametrize('newer', ['rdm_identify', 'patch_command', 'scene_delete'])
def test_direct_mutations_also_supersede_highlight(context, newer):
    c = context
    active(c)
    calls = []
    async def send(line, **kw): calls.append(line); return True, 'OK'
    c.link.send = send
    c.safety['allow_rdm'] = True
    async def go():
        if newer == 'patch_command':
            await c.send_planned('Assign Fixture 12 At Dmx 1.200')
        else:
            ws = object()
            c.sessions[ws] = {'selection': [], 'base': None}
            action = {'a': 'scene_delete', 'id': 'pianist', 'desk': True} if newer == 'scene_delete' else {'a': 'rdm_identify', 'uid': '43500F019FCB', 'on': True}
            result = await c.handle(ws, json.dumps(action))
            assert result['ok'], result
        calls.clear()
        with pytest.raises(ActionError): await c.release_highlight('disconnect')
        assert not calls
    asyncio.run(go())
