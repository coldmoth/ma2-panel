import asyncio
import re
import pytest
from commands import parse_dmx
from test_status_evidence import context  # noqa: F401


def test_retained_listvar_cannot_refresh_current_chunk(context):
    c = context
    async def go():
        c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
        stored = ['']
        requests = []
        async def send(line, **kw):
            if 'local a,n,v' in line:
                requests.append(line)
                if not stored[0]:
                    m = re.search(r"'T([0-9a-f]+) '", line)
                    tag = m[1] if m else ''
                    stored[0] = f'$PANELDMX120 = "T{tag} 120 255,255,0,0"'
            return True, stored[0] if line == 'ListVar' else ''
        c.link.send = send
        await c.read_dmx()
        assert c.state['dmx']
        await c.read_dmx()
        assert not c.state['dmx']
        assert not c.dmx_cycle['seen']
        assert requests[0] != requests[1]
    asyncio.run(go())


def test_marker_exact_span_and_new_identical_bytes():
    from commands import dmx_lua
    current = '0123456789abcdef'
    old = 'fedcba9876543210'
    assert parse_dmx(f'PANELDMX120 = "T{old} 120 255"', span=(120, 1), nonce=current) == {}
    assert parse_dmx('PANELDMX120 = "T 120 255"', span=(120, 1), nonce=current) == {}
    assert parse_dmx(f'PANELDMX1 = "T{current} 120 255"', span=(120, 1), nonce=current) == {}
    assert parse_dmx(f'PANELDMX120 = "T{current} 120 255"', span=(120, 1), nonce=current) == {120: 255}
    for address in (1, 9999, 131072):
        assert len(dmx_lua(address, 32, nonce=current)[0]) < 255
    assert len(f'SetVar $PANELDMX131072 = "T{current} 131072 ' + ','.join(['255'] * 32) + '"') < 255


@pytest.mark.parametrize('change', ['none', 'show', 'connection', 'timeout'])
def test_current_dmx_response_obeys_context(context, change):
    c = context
    async def go():
        c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
        marker = ['']
        async def send(line, **kw):
            if 'local a,n,v=' in line: marker[0] = re.search(r"'T([0-9a-f]+) '", line)[1]
            if line == 'ListVar':
                if change == 'show': c.state['plan_epoch'] += 1
                if change == 'connection': c.link._gen += 1
                return change != 'timeout', f'PANELDMX120 = "T{marker[0]} 120 255,255,0,0"'
            return True, ''
        c.link.send = send
        await c.read_dmx()
        assert bool(c.state['dmx']) == (change == 'none')
    asyncio.run(go())


def test_delayed_listvar_does_not_make_old_sample_current(context, monkeypatch):
    import time
    from types import SimpleNamespace
    import bridge
    c = context
    clock = [100.0]
    monkeypatch.setattr(bridge, 'time', SimpleNamespace(monotonic=lambda: clock[0], strftime=time.strftime))
    c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
    nonce = ['']
    async def send(line, **kw):
        if 'local a,n,v' in line:
            nonce[0] = re.search(r"'T([0-9a-f]+) '", line)[1]
        if line == 'ListVar':
            clock[0] += 6.1
            return True, f'PANELDMX120 = "T{nonce[0]} 120 255,255,0,0"'
        return True, ''
    c.link.send = send
    asyncio.run(c.read_dmx())
    assert not c.state['live']
    assert not c.state['dmx']
