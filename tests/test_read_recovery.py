"""FIELD-01: temporary read failures must not require restarting the bridge."""
import asyncio
import re
import time
from pathlib import Path
from types import SimpleNamespace

from ma2panel import bridge
import pytest
from test_status_evidence import context  # noqa: F401


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(bridge, 'time', SimpleNamespace(monotonic=lambda: now[0], strftime=time.strftime))
    return now


@pytest.mark.parametrize('failure', ['refused', 'empty_list'])
def test_profile_and_footprint_recover_after_temporary_export_failure(context, clock, failure):
    c = context
    c.cfg['fixtures'] = [{'id': 12, 'type': '3 Current', 'address': '1.120'}]
    c.cfg['dmx_map'] = {}
    c.ma2['export_wait'] = 0
    attempts = []
    available = [False]
    marker = ['']

    async def send(line, **kwargs):
        if line.startswith('Export FixtureType'):
            attempts.append(line)
            if available[0]:
                name = re.search(r'"([^"]+)"', line)[1]
                (Path(c.config_path).parent / (name + '.xml')).write_text(
                    '<FixtureType><Module><ChannelType attribute="DIM" coarse="1"/></Module></FixtureType>')
                return True, 'OK'
        elif line == 'List FixtureType' and available[0]:
            return True, Path('ma2panel/resources/mock/list_fixturetype_3.9.60.txt').read_text()
        elif line == 'List FixtureType' and failure == 'empty_list':
            return True, 'OK\n[Group]>'
        elif 'local a,n,v=' in line:
            marker[0] = re.search(r"'T([0-9a-f]+) '", line)[1]
            return True, 'OK'
        elif line == 'ListVar':
            return True, f'$PANELDMX120 = "T{marker[0]} 120 ' + ','.join(['255'] * 9) + '"'
        elif line.startswith('Lua'):
            return True, 'OK'
        return False, 'Error #9'

    async def go():
        c.link.send = send
        await c.read_types()
        assert c.config_msg()['config']['dmx_map'] == {}
        available[0] = True
        clock[0] = 29
        await c.read_types(background=True)
        assert len(attempts) == 1
        clock[0] = 30
        await c.read_types(background=True)
        assert c.cfg['dmx_map']['3 Current']['dim'] == 1
        assert c.cfg['fixtures'][0]['footprint'] == 9
        assert len(attempts) == 2 and attempts[0] != attempts[1]
        await c.read_dmx()
        assert c.state['live'][12] == {'dim': 100.0, 'rgb': [100.0, 100.0, 100.0]}
    asyncio.run(go())


def test_profile_failures_are_bounded_and_manual_refresh_rearms(context, clock):
    c = context
    c.cfg['fixtures'] = [{'id': 12, 'type': '3 Current', 'address': '1.120'}]
    c.cfg['dmx_map'] = {}
    attempts = []

    async def send(line, **kwargs):
        attempts.append(line)
        return False, 'Error #9'

    async def go():
        c.link.send = send
        for stamp in (0, 30, 60, 90, 120):
            clock[0] = stamp
            await c.read_types(background=True)
        assert sum(line.startswith('Export FixtureType') for line in attempts) == 3
        assert attempts.count('List FixtureType') == 3
        await c.read_types(force=True)
        assert sum(line.startswith('Export FixtureType') for line in attempts) == 4
        assert attempts.count('List FixtureType') == 4
    asyncio.run(go())


def test_dmx_refusal_recovers_without_restart(context, clock, monkeypatch):
    c = context
    c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
    refused = [True]
    marker = ['']
    lines = []

    async def send(line, **kwargs):
        lines.append(line)
        if refused[0]:
            return False, 'Error #44: NOT ALLOWED'
        if 'local a,n,v=' in line:
            marker[0] = re.search(r"'T([0-9a-f]+) '", line)[1]
        return True, f'$PANELDMX120 = "T{marker[0]} 120 255,255,0,0"' if line == 'ListVar' else 'OK'

    async def go():
        c.link.send = send
        assert await c.read_dmx() == 30
        refused[0] = False
        for stamp in (0, 29):
            clock[0] = stamp
            await c.read_dmx()
            assert len(lines) == 1 and not c.state['live']
        clock[0] = 30
        await c.read_dmx()
        assert c.state['live'][12] == {'dim': 100.0, 'rgb': [100.0, 0.0, 0.0]}
        # The production polling task also survives a refusal, rather than returning forever.
        refused[0] = True
        clock[0] = 31
        before = len(lines)
        sleep = asyncio.sleep

        async def virtual_sleep(delay):
            clock[0] += delay
            if delay >= 30:
                refused[0] = False
            await sleep(0)

        monkeypatch.setattr(bridge, 'asyncio', SimpleNamespace(**{**vars(asyncio), 'sleep': virtual_sleep}))
        task = asyncio.create_task(c.poll_dmx())
        try:
            for _ in range(100):
                await sleep(0)
                if len(lines) > before and not refused[0] and c.state['dmx_read']['values'] == 4:
                    break
            assert len(lines) > before and not refused[0] and c.state['dmx_read']['values'] == 4
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(go())


@pytest.mark.parametrize('reset', ['connection', 'manual'])
def test_dmx_refusal_limit_rearms_only_after_context_reset(context, clock, reset):
    c = context
    c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
    lines = []

    async def send(line, **kwargs):
        lines.append(line)
        return False, 'Error #44'

    async def go():
        c.link.send = send
        for stamp in (0, 30, 60, 90, 120):
            clock[0] = stamp
            await c.read_dmx()
        assert len(lines) == 3
        if reset == 'connection':
            c.link._gen += 1
        else:
            c.invalidate_profiles()
        c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
        c.cfg['fixtures'][0]['footprint'] = 4
        await c.read_dmx()
        assert len(lines) == 4
    asyncio.run(go())
