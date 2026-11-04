"""Synthetic scheduling measurements, not MA2 latency claims."""
import asyncio
import json
import re
import time
from types import SimpleNamespace
import pytest
import bridge
from test_status_evidence import context  # noqa: F401


@pytest.mark.parametrize('chunks,sparse,rtt', [(1, False, .05), (3, False, .05), (10, False, .05), (10, True, .25)])
def test_measure_dmx_round_robin_and_five_clients(context, monkeypatch, chunks, sparse, rtt):
    c = context
    clock = [0.0]
    sleep = asyncio.sleep
    async def virtual_sleep(delay):
        clock[0] += delay
        await sleep(0)
    monkeypatch.setattr(bridge, 'time', SimpleNamespace(monotonic=lambda: clock[0], strftime=time.strftime))
    monkeypatch.setattr(bridge, 'asyncio', SimpleNamespace(**{**vars(asyncio), 'sleep': virtual_sleep}))
    c.cfg['fixtures'] = ([{'id': i + 1, 'type': 'Par', 'address': f'{i + 1}.001', 'footprint': 1} for i in range(chunks)] if sparse else
                         [{'id': 1, 'type': 'Par', 'address': '1.001', 'footprint': chunks * 32}])
    c.cfg['dmx_map'] = {'Par': {'dim': 1, 'has': []}}
    c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
    stored, tasks, latencies, spans, ages = {}, [], [], [], []
    starts, measured = [], {}
    async def manual(ws):
        start = clock[0]
        assert not await c.execute('dim', {'a': 'dim', 'v': 42}, c.sessions[ws], [1])
        latencies.append(clock[0] - start)
    async def send(line, **kw):
        clock[0] += rtt
        if m := re.search(r'local a,n,v=(\d+),(\d+),', line):
            a, n = map(int, m.groups())
            tag = re.search(r"'T([0-9a-f]+) '", line)[1]
            stored[a] = f'PANELDMX{a} = "T{tag} {a} ' + ','.join(['255'] * n) + '"'
            spans.append(a)
            starts.append(clock[0])
            measured[a] = clock[0]
            if not tasks:
                for _ in range(5):
                    ws = object()
                    c.sessions[ws] = {}
                    tasks.append(asyncio.create_task(manual(ws)))
        await sleep(0)
        return True, '\n'.join(stored.values()) if line == 'ListVar' else ''
    c.link.send = send
    async def go():
        for _ in range(chunks * 3):
            await virtual_sleep(2)
            assert await c.read_dmx() != 30
            ages.extend(clock[0] - stamp for stamp in measured.values())
        await asyncio.gather(*tasks)
    asyncio.run(go())
    assert spans[:chunks] == spans[chunks:2 * chunks]
    assert len(set(spans)) == chunks
    row = {'chunks': chunks, 'sparse': sparse, 'rtt_ms': rtt * 1000,
           'steady_cycle_seconds': round(starts[-1] - starts[-1 - chunks], 3),
           'manual_five_p50_seconds': round(sorted(latencies)[2], 3),
           'manual_five_p95_seconds': round(max(latencies), 3),
           'max_observed_age_seconds': round(max(ages), 3)}
    print(json.dumps(row))
