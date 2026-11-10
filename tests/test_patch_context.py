"""DATA-018: an admitted patch never crosses context or stop boundaries."""
import asyncio
import pytest
from ma2panel.commands import ActionError
from test_status_evidence import context  # noqa: F401


def setup(c):
    c.cfg['show'] = 'Old'
    c.state['show'] = {'name': 'Old', 'source':'ma2'}
    c.safety.update(allow_patch=True, allow_rdm=True, allow_fixture_read=False)
    c.cfg['fixtures'] = [{'id': 12, 'address': '1.120', 'footprint': 17,
                          'rdm': {'uid': '43500F019FCB', 'address': 120, 'footprint': 17, 'universe': 1}}]
    action = {'id': 12, 'address': 200, 'patch': True, 'physical': True}
    action['token'] = c.patch_offer(action)['token']
    return action


def change(c, kind):
    if kind == 'gen': c.link._gen += 1
    elif kind == 'stop': c.link._stop_epoch += 1
    elif kind == 'epoch': c.state['plan_epoch'] += 1
    else: c.state['show'] = {'name': 'New', 'source':'ma2'}


@pytest.mark.parametrize('kind', ['gen', 'stop', 'epoch', 'show'])
@pytest.mark.parametrize('phase', ['lock', 'write', 'readback'])
def test_patch_cannot_cross_context(context, kind, phase):
    c = context
    action = setup(c)
    async def go():
        calls = []
        async def send(line, **kw):
            calls.append((line, kw.get('gen')))
            if phase == 'write' and line.startswith('RdmSetParameter'):
                change(c, kind)
            if phase == 'readback' and line.startswith('RdmList'):
                change(c, kind)
            return True, 'ok'
        c.link.send = send
        await c.action_lock.acquire()
        task = asyncio.create_task(c.patch_action('patch_apply', action))
        await asyncio.sleep(0)
        if phase == 'lock': change(c, kind)
        c.action_lock.release()
        try:
            result = await task
        except ActionError:
            assert phase == 'lock'
        else:
            assert result['ok'] is False
            assert 'контекст' in result['err']
            assert result['steps']
        if phase == 'lock': assert not calls
        if phase == 'write':
            assert len(calls) == 1
            assert c.cfg['fixtures'][0]['rdm']['address'] == 120
        assert all(gen == 0 for _, gen in calls)
    asyncio.run(go())


@pytest.mark.parametrize('kind', ['gen', 'stop', 'epoch', 'show'])
def test_patch_context_is_checked_after_transport_lock(context, kind):
    c = context
    action = setup(c)
    async def go():
        writes = []
        async def exchange(line, timeout):
            writes.append(line)
            return 'ok', True
        c.link._exchange = exchange
        await c.link._lock.acquire()
        task = asyncio.create_task(c.patch_action('patch_apply', action))
        await asyncio.sleep(0)
        change(c, kind)
        c.link._lock.release()
        result = await task
        assert result['ok'] is False
        assert writes == []
    asyncio.run(go())


@pytest.mark.parametrize('kind', ['gen', 'stop', 'epoch', 'show'])
def test_patch_offer_cannot_be_reused_in_a_new_context(context, kind):
    c = context
    action = setup(c)
    async def go():
        offer = await c.patch_action('patch_plan', action)
        action['token'] = offer['plan']['token']
        change(c, kind)
        if kind == 'show':
            c.cfg['show'] = 'New'
        writes = []
        async def send(line, **kw):
            writes.append(line)
            return True, 'ok'
        c.link.send = send
        with pytest.raises(ActionError, match='устарел'):
            await c.patch_action('patch_apply', action)
        assert writes == []
    asyncio.run(go())


@pytest.mark.parametrize('kind', ['gen', 'stop', 'epoch', 'show'])
def test_patch_export_cannot_apply_another_context(context, kind):
    import re
    from pathlib import Path
    c = context
    action = setup(c)
    c.safety['allow_fixture_read'] = True
    async def go():
        calls = []
        async def send(line, **kw):
            calls.append((line, kw.get('gen')))
            if line.startswith('Export Fixture '):
                name = re.search(r'"([^"]+)"', line)[1]
                Path(c.export_dir, name + '.xml').write_text('<MA><Fixture id="12" type="3 New"><Patch><Address>200</Address></Patch></Fixture></MA>')
                change(c, kind)
            return True, 'ok'
        c.link.send = send
        result = await c.patch_action('patch_apply', action)
        assert result['ok'] is False
        assert 'контекст' in result['check']['error']
        assert c.cfg['fixtures'][0]['address'] == '1.120'
        assert all(gen == 0 for _, gen in calls)
    asyncio.run(go())


@pytest.mark.parametrize('kind', ['gen', 'stop'])
@pytest.mark.parametrize('phase', ['type_export', 'type_list'])
def test_patch_profile_readback_preserves_context_through_last_stage(context, kind, phase):
    import re
    from pathlib import Path
    c = context
    action = setup(c)
    c.cfg['fixtures'][0].update(name='Head', type='3 Current')
    action['physical'] = False
    action['token'] = c.patch_offer(action)['token']
    c.safety['allow_fixture_read'] = True
    async def go():
        calls = []
        async def send(line, **kw):
            calls.append(line)
            if line.startswith('Export Fixture '):
                name = re.search(r'"([^"]+)"', line)[1]
                Path(c.export_dir, name + '.xml').write_text('<MA><Fixture id="12" name="Head" type="3 Current"><Patch><Address>200</Address></Patch></Fixture></MA>')
            if phase == 'type_export' and line.startswith('Export FixtureType'):
                change(c, kind)
                return False, 'Error'
            if line == 'List FixtureType':
                if phase == 'type_list': change(c, kind)
                return True, Path('ma2panel/resources/mock/list_fixturetype_3.9.60.txt').read_text()
            return True, 'ok'
        c.link.send = send
        c.ma2['export_wait'] = 0
        result = await c.patch_action('patch_apply', action)
        assert result['ok'] is False
        assert 'контекст' in result['check']['error']
        if phase == 'type_export': assert 'List FixtureType' not in calls
    asyncio.run(go())
