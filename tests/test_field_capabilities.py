"""Field startup regressions; synthetic profiles do not claim actual V2 channels."""
import asyncio
import re
from contextlib import suppress
from pathlib import Path
import pytest

from ma2panel.fixtures import parse_fixture_type
from test_status_evidence import context  # noqa: F401


@pytest.mark.parametrize('session', [{'editing': True}, {'scene_offer': {'expires': float('inf')}}])
def test_background_profiles_do_not_invalidate_active_editor_or_scene_offer(context, session):
    from ma2panel.commands import ActionError
    import copy
    c = context
    c.sessions[object()] = session
    before = copy.deepcopy(c.cfg)
    with pytest.raises(ActionError, match='редактирование'):
        asyncio.run(c.read_types(background=True))
    assert c.cfg == before


def test_fixture_type_retains_confirmed_motion_attributes():
    profile = parse_fixture_type('<FixtureType><Module>'
        '<ChannelType attribute="PAN" coarse="1"/>'
        '<ChannelType attribute="TILT" coarse="3"/>'
        '</Module></FixtureType>')
    assert 'pos' in profile['has']


def test_cancelled_type_commit_does_not_cache_an_unapplied_profile(context):
    from ma2panel.commands import ActionError
    c = context
    c.cfg['fixtures'] = [{'id': 12, 'type': '3 Par', 'address': '1.001'}]
    c.cfg['dmx_map'] = {}
    c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
    calls = []
    owner = object()
    async def send(line, **kwargs):
        calls.append(line)
        if line.startswith('Export FixtureType'):
            name = re.search(r'"([^"]+)"', line)[1]
            Path(c.export_dir, name + '.xml').write_text('<FixtureType><Module>'
                '<ChannelType attribute="DIM" coarse="1"/></Module></FixtureType>')
        if line == 'List FixtureType' and owner not in c.sessions:
            c.sessions[owner] = {'editing': True}
        return True, ''
    c.link.send = send
    async def run():
        with pytest.raises(ActionError):
            await c.read_types(background=True)
        assert not c.cfg['dmx_map']
        c.sessions[owner]['editing'] = False
        await c.read_types(background=True)
        assert c.cfg['dmx_map']['3 Par']['dim'] == 1
        assert sum(v.startswith('Export FixtureType') for v in calls) == 2
    asyncio.run(run())


def test_transient_type_export_failure_is_recoverable_without_reconnect(context, monkeypatch):
    """Removing the bounded retry must strand this confirmed RGB type and fail."""
    from ma2panel import bridge
    import time
    from types import SimpleNamespace
    c = context
    c.cfg['fixtures'] = [{'id': 12, 'type': '3 Par', 'address': '1.001'}]
    c.cfg['dmx_map'] = {}
    c.ma2['export_wait'] = .01
    clock = [100.0]
    monkeypatch.setattr(bridge, 'time', SimpleNamespace(**{**vars(time), 'monotonic': lambda: clock[0]}))
    calls = []

    async def send(line, **kwargs):
        calls.append(line)
        if line.startswith('Export FixtureType'):
            if len([v for v in calls if v.startswith('Export FixtureType')]) == 1:
                return False, 'Error: temporary export failure'
            name = re.search(r'"([^"]+)"', line)[1]
            Path(c.export_dir, name + '.xml').write_text('<FixtureType><Module>'
                '<ChannelType attribute="DIM" coarse="1"/>'
                '<ChannelType attribute="COLORRGB1" coarse="2"/>'
                '<ChannelType attribute="COLORRGB2" coarse="3"/>'
                '<ChannelType attribute="COLORRGB3" coarse="4"/>'
                '</Module></FixtureType>')
        return True, ''

    c.link.send = send

    async def run():
        await c.read_types()
        assert not c.cfg['dmx_map']
        await c.read_types()
        assert sum(v.startswith('Export FixtureType') for v in calls) == 1, 'avoid tight retry loop'
        clock[0] += 31
        await c.read_types()
        assert c.cfg['dmx_map']['3 Par']['r'] == 2
        assert not c.cfg['dmx_map']['3 Par'].get('stale')
    asyncio.run(run())


def test_profile_recovery_survives_rejected_dmx_readback(context, monkeypatch):
    """A rejected Lua read must not kill type discovery for later connections."""
    from ma2panel import bridge
    from types import SimpleNamespace
    c = context
    c.cfg['fixtures'] = [{'id': 12, 'type': '3 Par', 'address': '1.001', 'footprint': 4}]
    c.cfg['dmx_map'] = {'3 Par': {'dim': 1, 'r': 2, 'g': 3, 'b': 4, 'has': []}}
    c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
    original_sleep = asyncio.sleep
    async def quick_sleep(delay):
        await original_sleep(.01)
    monkeypatch.setattr(bridge, 'asyncio', SimpleNamespace(**{**vars(asyncio), 'sleep': quick_sleep}))
    calls = []

    async def run():
        refused, recovered = asyncio.Event(), asyncio.Event()
        async def send(line, **kwargs):
            calls.append(line)
            if line.startswith('Lua'):
                refused.set()
                return False, 'Error: Lua disabled'
            if line.startswith('Export FixtureType'):
                recovered.set()
                return False, 'Error: test complete'
            return True, ''
        c.link.send = send
        task = asyncio.create_task(c.poll_dmx())
        try:
            await asyncio.wait_for(refused.wait(), 1)
            c.link._gen += 1
            await asyncio.wait_for(recovered.wait(), 1)
            assert sum(v.startswith('Lua') for v in calls) == 1
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    asyncio.run(run())
