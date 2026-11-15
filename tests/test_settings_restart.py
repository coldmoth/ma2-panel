"""Settings restart must not require silence from periodic MA2 reads."""
import asyncio
import time
from types import SimpleNamespace
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from ma2panel import bridge


@pytest.fixture
def context(tmp_path, monkeypatch):
    captured = {}
    register = bridge.register_api
    def capture(app, c, local):
        captured['c'] = c
        return register(app, c, local)
    monkeypatch.setattr(bridge, 'register_api', capture)
    monkeypatch.setattr(bridge, 'is_loopback', lambda _: True)
    app = bridge.create_app({'fixtures': [], 'groups': [], 'scenes': []}, True,
                            str(tmp_path / 'config.json'),
                            {'poll_seconds': 0, 'dmx_seconds': 0, 'simple_port': None},
                            settings_path=tmp_path / 'settings.json')
    app.state.server = SimpleNamespace(should_exit=False)
    return app, captured['c']


@contextmanager
def local_client(app, **kwargs):
    client = TestClient(app, **kwargs)
    try:
        yield client
    finally:
        client.close()


def restart(client):
    return client.post('/api/restart', headers={'X-Stop': '1'})


def test_restart_after_save_and_periodic_read_does_not_require_ten_second_silence(context):
    app, c = context
    # Saving settings and every completed ListVar/DMX read refresh these clocks.
    app.state.last_action = time.monotonic()
    async def completed_read():
        c.on_result({'cmd': 'ListVar', 'status': 'confirmed'})
        await asyncio.sleep(0)
    asyncio.run(completed_read())
    assert c.update_busy()  # Preserve the updater's existing quiet window.
    with local_client(app, base_url='http://127.0.0.1') as client:
        response = restart(client)
    assert response.status_code == 200, response.text
    assert response.json()['instance'] == app.state.instance
    assert app.state.server.should_exit and app.state.exit_code == 3
    assert not c.link.admission()


@pytest.mark.parametrize('operation', ['rdm', 'blackout', 'scene_create', 'send', 'http', 'fade', 'highlight', 'recent_command'])
def test_busy_restart_names_reason_and_can_be_retried_without_interrupting(context, operation):
    app, c = context
    if operation == 'rdm':
        # Real coordinator state, not a replacement restart gate.
        c.rdm._active = True
    elif operation in ('blackout', 'scene_create'):
        c.active_operations['test'] = {'a': operation}
    elif operation == 'send':
        asyncio.run(c.link._lock.acquire())
    elif operation == 'http':
        app.state.active_http = 1
    elif operation == 'fade':
        c.throttle.fades['test'] = object()
    elif operation == 'recent_command':
        app.state.last_write = time.monotonic()
    else:
        c.highlight['state'] = 'active'
    with local_client(app, base_url='http://127.0.0.1') as client:
        response = restart(client)
        assert response.status_code == 409
        data = response.json()
        assert data['reason'] and data['retry_after'] > 0
        assert data['reason'] in data['err']
        assert not app.state.server.should_exit and not app.state.updating
        if operation == 'rdm':
            c.rdm._active = False
        elif operation in ('blackout', 'scene_create'):
            assert c.active_operations.pop('test')['a'] == operation
        elif operation == 'send':
            assert c.link._lock.locked()
            c.link._lock.release()
        elif operation == 'http':
            app.state.active_http = 0
        elif operation == 'fade':
            c.throttle.fades.clear()
        elif operation == 'recent_command':
            app.state.last_write -= 11
        else:
            c.highlight['state'] = 'idle'
        assert restart(client).status_code == 200


def test_missing_server_is_an_error_without_closing_gate(context):
    app, _ = context
    del app.state.server
    with local_client(app, base_url='http://127.0.0.1') as client:
        response = restart(client)
    assert response.status_code == 503
    assert not app.state.updating


def test_restart_status_is_readable_only_by_local_pages(context, monkeypatch):
    app, _ = context
    with local_client(app, base_url='http://127.0.0.1:8081') as client:
        response = client.get('/api/restart/status', headers={'Origin': 'http://localhost:8080'})
        assert response.status_code == 200
        assert response.json()['instance'] == app.state.instance
        assert response.headers['access-control-allow-origin'] == 'http://localhost:8080'
        assert 'access-control-allow-origin' not in client.get('/api/restart/status', headers={'Origin': 'https://evil.example'}).headers
        monkeypatch.setattr(bridge, 'is_loopback', lambda _: False)
        assert client.get('/api/restart/status').status_code == 403


def test_idle_open_panel_does_not_block_restart(context):
    from test_bridge import ready
    app, c = context
    with TestClient(app, base_url='http://127.0.0.1') as client:
        with client.websocket_connect('/ws') as ws:
            ready(ws)
            assert any(not task.done() for task in c.bg)  # The passive worker lives until disconnect.
            response = restart(client)
            assert response.status_code == 200, response.text
            assert app.state.server.should_exit


def test_waiting_worker_is_ignored_but_queued_action_keeps_send_gate_open(context):
    app, c = context
    async def check():
        queue = asyncio.Queue()
        worker = asyncio.create_task(asyncio.Event().wait())
        c.bg.add(worker)
        c.ws_workers[worker] = queue
        try:
            queue.put_nowait('{"a":"blackout"}')
            assert not await c.update_gate(restart=True)
            assert 'очереди' in c.restart_busy()
            assert not app.state.updating and c.link.admission()
            assert queue.get_nowait() == '{"a":"blackout"}'
            # Work consumed by a worker is covered until handle_load's finally.
            app.state.active_actions = 1
            assert not await c.update_gate(restart=True)
            app.state.active_actions = 0
            assert await c.update_gate(restart=True)
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
    asyncio.run(check())
