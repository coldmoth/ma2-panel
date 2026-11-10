"""Evidence expires independently of whether another read succeeds."""
import pytest


def book(clock):
    from ma2panel.status_evidence import Evidence
    return Evidence(clock=lambda: clock[0], wall=lambda: 1000 + clock[0])


def test_missing_scene_is_unknown_and_expiry_is_not_off():
    clock = [0.0]
    e = book(clock)
    values, meta = e.snapshot(['a', 'b'])
    assert values == {'a': None, 'b': None}
    assert meta['a']['source'] == 'unknown'
    e.observe('a', True)
    clock[0] = 5.99
    assert e.snapshot(['a'])[0] == {'a': True}
    clock[0] = 6.0
    values, meta = e.snapshot(['a', 'b'])
    assert values == {'a': None, 'b': None}
    assert meta['a'] == {'source': 'ma2', 'freshness': 'stale', 'updated_at': 1000.0}


def test_identical_read_refreshes_and_invalidation_forgets_source():
    clock = [0.0]
    e = book(clock)
    e.observe('a', False)
    clock[0] = 5
    e.observe('a', False)
    clock[0] = 7
    assert e.snapshot(['a'])[0] == {'a': False}
    e.invalidate(['a'])
    values, meta = e.snapshot(['a'])
    assert values == {'a': None}
    assert meta['a'] == {'source': 'unknown', 'freshness': 'unknown', 'updated_at': None}


def test_new_simple_client_does_not_treat_sent_command_as_evidence(tmp_path):
    import json
    from fastapi.testclient import TestClient
    from ma2panel.bridge import create_app
    from test_bridge import CONFIG, FULL, ask, ready, until
    from pathlib import Path
    cfg = json.loads(Path(CONFIG).read_text())
    cfg['ma2']['port'] = 30000
    cfg['ma2']['export_dir'] = str(tmp_path)
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(cfg))
    app = create_app(cfg, mock=True, config_path=str(path), settings={**FULL, 'poll_seconds': 0})
    app.mount('/simple-test', app.state.simple_app)
    app.router.routes.insert(0, app.router.routes.pop())
    with TestClient(app) as c, c.websocket_connect('/ws') as ws:
        ready(ws)
        assert ask(ws, {'a': 'scene_go', 'id': 'pianist'})['ok']
        with c.websocket_connect('/simple-test/ws') as simple:
            m = until(simple, lambda m: 'running' in m)
            assert m['running']['pianist'] is None
            assert m['running_meta']['pianist']['freshness'] == 'unknown'


@pytest.fixture
def context(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    from ma2panel import bridge
    captured = []
    monkeypatch.setattr(bridge, 'register_api', lambda app, c, local: captured.append(c))
    cfg = json.loads(Path('tests/config.test.json').read_text())
    cfg['ma2']['export_dir'] = str(tmp_path)
    cfg['fixtures'] = [{'id': 12, 'type': 'Par', 'address': '1.120', 'channels': 4, 'footprint': 4}]
    cfg['dmx_map'] = {'Par': {'dim': 1, 'r': 2, 'g': 3, 'b': 4}}
    bridge.create_app(cfg, mock=True, config_path=str(tmp_path / 'config.json'),
                      settings={'safety': {'mode': 'full', 'allow_fixture_read': True}, 'poll_seconds': .01})
    c = captured[0]
    c.link.state = 'logged_in'
    c.state['show'] = {'name':'Mock show','source':'ma2'}
    yield c
    bridge.log.removeHandler(c.diag_handler)


def test_dmx_reply_cannot_cross_connection_generation(context):
    import asyncio
    c = context
    async def scenario():
        async def send(line, **kw):
            if line == 'ListVar':
                c.link._gen += 1  # reconnect while this read is in flight
                return True, '$PANELDMX0 = "T 120 255,255,0,0"'
            return True, ''
        c.link.send = send
        await c.read_dmx()
        assert c.state['live'] == {}
        assert c.state['dmx'] == {}
    asyncio.run(scenario())


def test_partial_scene_read_does_not_make_missing_scene_off(context):
    import asyncio
    c = context
    c.cfg['scenes'].append({'id': 'missing', 'exec': '1.199', 'label': 'Missing'})
    async def scenario():
        calls = []
        complete = asyncio.Event()
        async def send(line, **kw):
            if line == 'ListVar': return True, 'Global : $SHOWFILE = Mock show'
            calls.append(line)
            if line == 'List Executor 1.101':
                return True, '  Executor 1.101  Piano  Sequence 1  Running\r\n'
            if line == 'List Executor 1.199':
                complete.set()
                return True, 'No objects found\r\n'
            return True, ''
        c.link.send = send
        task = asyncio.create_task(c.poll_running())
        try:
            await asyncio.wait_for(complete.wait(), 1)
            await asyncio.sleep(0)
            m = c.scenes_msg()
            assert m['running'] == {'pianist': True, 'missing': None}
            assert m['running_meta']['pianist']['source'] == 'ma2'
            assert m['running_meta']['missing']['source'] == 'unknown'
            assert all('Thru' not in cmd for cmd in calls)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def test_expiry_broadcasts_without_successful_poll(context):
    import asyncio
    from ma2panel.status_evidence import Evidence
    c = context
    async def scenario():
        clock = [0]
        c.scene_evidence.clock = lambda: clock[0]
        c.value_evidence.clock = lambda: clock[0]
        c.scene_evidence.observe('pianist', True)
        c.value_evidence.observe('live', True)
        c.state['live'] = {12: {'dim': 100}}
        c.state['dmx'] = {120: 255}
        messages = []
        class Client:
            async def send_json(self, m):
                messages.append(m)
        ws = Client()
        c.clients.add(ws)
        task = asyncio.create_task(c.expire_evidence())
        await asyncio.sleep(0)
        clock[0] = 6
        try:
            await asyncio.sleep(.55)
            m = next(m for m in messages if 'running' in m)
            assert m['running']['pianist'] is None
            assert m['running_meta']['pianist']['freshness'] == 'stale'
            assert m['live'] == {} and m['dmx'] == {}
            assert m['values_meta']['live']['freshness'] == 'stale'
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def test_slow_client_cannot_publish_old_scene_after_invalidation(context):
    import asyncio
    c = context
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        received = []
        class Slow:
            async def send_json(self, msg):
                if msg.get('running', {}).get('pianist') is True:
                    entered.set()
                    await release.wait()
        class Observer:
            async def send_json(self, msg):
                if 'running' in msg:
                    received.append(msg['running']['pianist'])
        slow, observer = Slow(), Observer()
        # A list preserves the slow-first order to reproduce a mid-broadcast drop.
        c.clients.clear()
        c.clients.add(slow)
        c.clients.add(observer)
        # Whichever set element is first must be the gated client.
        first = next(iter(c.clients))
        if first is not slow:
            slow.send_json, observer.send_json = observer.send_json, slow.send_json
        c.scene_evidence.observe('pianist', True)
        old = asyncio.create_task(c.broadcast(c.scenes_msg()))
        await asyncio.wait_for(entered.wait(), 1)
        c.invalidate_evidence()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        release.set()
        await old
        await asyncio.gather(*list(c.bg))
        assert received[-1] is None, received
    asyncio.run(scenario())


def test_poll_does_not_hold_action_lock_for_slow_client(context):
    import asyncio
    c = context
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        class Slow:
            async def send_json(self, msg):
                if msg.get('running', {}).get('pianist') is True:
                    entered.set()
                    await release.wait()
        c.clients.add(Slow())
        async def send(line, **kw):
            if line == 'ListVar': return True, 'Global : $SHOWFILE = Mock show'
            if line == 'List Executor 1.101':
                return True, '  Executor 1.101  Piano  Sequence 1  Running\r\n'
            return True, ''
        c.link.send = send
        task = asyncio.create_task(c.poll_running())
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert not c.action_lock.locked()
        finally:
            release.set()
            task.cancel()
            await asyncio.gather(task, *list(c.bg), return_exceptions=True)
    asyncio.run(scenario())


def test_stalled_client_is_closed_so_it_can_reconnect(context):
    import asyncio
    c = context
    async def scenario():
        class Stalled:
            closed = False
            async def send_json(self, msg):
                await asyncio.Event().wait()
            async def close(self, code):
                self.closed = True
        ws = Stalled()
        c.clients.add(ws)
        await c.broadcast({'running': {'pianist': None}})
        assert ws not in c.clients
        assert ws.closed
    asyncio.run(scenario())


def test_client_swap_cannot_release_unowned_catalogue_entries(context):
    import asyncio, json
    c = context
    c.cfg['scenes'].extend({'id': f's{i}', 'exec': f'1.{110+i}', 'label': str(i)} for i in range(17))
    async def scenario():
        sent = []
        probe = ""
        async def send(line, **kw):
            nonlocal probe
            sent.append(line)
            if line.startswith('List Executor '): return True, 'Executor '+line.split()[-1]+' Priority=Normal SoftLTP=on Chaser=off'
            if 'PANELSCENE' in line:
                import re
                probe = re.search(r"PANELSCENE','([a-f0-9]{16})", line)[1] + ' manual'
            return True, 'Global : $SHOWFILE = Mock show\nGlobal : $PANELSCENE = ' + probe if line == 'ListVar' else ''
        c.link.send = send
        ws = object()
        c.sessions[ws] = {'selection': [], 'base': None}
        swap = [f's{i}' for i in range(17)]
        result = await c.handle(ws, json.dumps({'a': 'scene_go', 'id': 'pianist', 'swap': swap}))
        try:
            assert result['ok'], result
            await asyncio.gather(*list(c.bg))
            assert not any(line.startswith(('Off Executor', 'Masterfade')) for line in sent)
            result = await c.handle(ws, json.dumps({'a': 'scene_go', 'id': 'pianist', 'swap': ['s0', 's0']}))
            assert not result['ok']
        finally:
            await asyncio.gather(*list(c.bg), return_exceptions=True)
    asyncio.run(scenario())
