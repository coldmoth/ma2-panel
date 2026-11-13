import asyncio
import pytest
from test_status_evidence import context  # noqa: F401


@pytest.mark.parametrize('change', ['none', 'show', 'connection', 'halt', 'config'])
def test_manual_clients_do_not_wait_for_background_file_deadline(context, change):
    c = context
    async def go():
        c.cfg['fixtures'] = [{'id': 12, 'type': '1 Missing', 'address': '1.001'}]
        c.cfg['dmx_map'] = {}
        c.ma2['export_wait'] = .65
        entered = asyncio.Event()
        calls = []
        async def send(line, **kw):
            assert c.action_lock.locked()
            calls.append(line)
            if line.startswith('Export FixtureType'): entered.set()
            return True, ''
        c.link.send = send
        reader = asyncio.create_task(c.read_dmx())
        await asyncio.wait_for(entered.wait(), 1)
        if change == 'show': c.state['plan_epoch'] += 1
        if change == 'connection': c.link._gen += 1
        if change == 'halt': c.link._stop_epoch += 1
        if change == 'config': c.cfg['fixtures'] = []
        async def manual():
            assert not await c.execute('master', {'a': 'master', 'v': 42}, {}, [])
        clients = [asyncio.create_task(manual()) for _ in range(5)]
        await asyncio.wait_for(asyncio.gather(*clients), .2)
        await reader
        if change != 'none':
            assert 'List FixtureType' not in calls
            assert not c.cfg['dmx_map']
    asyncio.run(go())


@pytest.mark.parametrize('change', [False, True, 'editing', 'scene'])
def test_delayed_export_file_applies_only_in_same_context(context, change):
    import re
    from pathlib import Path
    c = context
    async def go():
        c.cfg['fixtures'] = [{'id': 12, 'type': '1 Test', 'address': '1.001'}]
        c.cfg['dmx_map'] = {}
        c.ma2['export_wait'] = 1
        entered = asyncio.Event()
        names = []
        async def send(line, **kw):
            assert c.action_lock.locked()
            if line.startswith('Export FixtureType'):
                names.append(re.search(r'"([^"]+)"', line)[1])
                entered.set()
            return True, ''
        c.link.send = send
        reader = asyncio.create_task(c.read_dmx())
        await entered.wait()
        if change is True: c.state['plan_epoch'] += 1
        elif change == 'editing': c.sessions[object()] = {'editing': True}
        elif change == 'scene': c.sessions[object()] = {'scene_offer': {'expires': float('inf')}}
        Path(c.export_dir).mkdir(exist_ok=True)
        Path(c.export_dir, names[0] + '.xml').write_text('<FixtureType><Modules><Module><ChannelType attribute="DIM" coarse="1"/></Module></Modules></FixtureType>')
        await reader
        assert bool(c.cfg['dmx_map']) == (not change)
        assert not c.state['background_type_read']
    asyncio.run(go())


@pytest.mark.parametrize('mode', ['before', 'after'])
def test_measure_background_file_queue(context, mode):
    import time
    import json
    c = context
    async def go():
        c.cfg['fixtures'] = [{'id': 12, 'type': '1 Missing', 'address': '1.001'}]
        c.cfg['dmx_map'] = {}
        c.ma2['export_wait'] = .65
        entered = asyncio.Event()
        async def send(line, **kw):
            assert c.action_lock.locked()
            if line.startswith('Export FixtureType'): entered.set()
            return True, ''
        c.link.send = send
        async def reader():
            if mode == 'before':
                async with c.action_lock:
                    await c.read_types(max_types=1)
            else:
                await c.read_dmx()
        task = asyncio.create_task(reader())
        await entered.wait()
        durations = []
        async def manual():
            start = time.perf_counter()
            await c.execute('master', {'a': 'master', 'v': 42}, {}, [])
            durations.append(time.perf_counter() - start)
        await asyncio.gather(*(manual() for _ in range(5)))
        await task
        row = {'mode': mode, 'p50_ms': round(sorted(durations)[2] * 1000, 2),
               'p95_ms': round(max(durations) * 1000, 2), 'max_ms': round(max(durations) * 1000, 2)}
        print(json.dumps(row))
        assert (max(durations) >= .6) if mode == 'before' else (max(durations) < .2)
    asyncio.run(go())
