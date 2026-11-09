"""First-run information must reflect the running bridge, without issuing actions."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from ma2panel import bridge
from test_bridge import ready


@pytest.fixture
def running(tmp_path, monkeypatch):
    cfg = json.loads(Path('ma2panel/resources/config.example.json').read_text())
    settings = {'bind': '0.0.0.0', 'port': 8123, 'simple_port': None,
                'poll_seconds': 0, 'dmx_seconds': 0, 'ma2': {'user': 'Remote'}}
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(cfg))
    stored = tmp_path / 'settings.json'
    stored.write_text(json.dumps(settings))
    monkeypatch.setattr(bridge, 'is_loopback', lambda request: True)
    monkeypatch.setattr(bridge, 'local_addresses', lambda: [
        '192.168.50.12', '127.0.0.1', '169.254.2.3', '0.0.0.0', '192.168.50.12'])
    app = bridge.create_app(cfg, True, str(config), settings, settings_path=stored)
    with TestClient(app, base_url='http://127.0.0.1:8123') as client:
        with client.websocket_connect('/ws') as ws:
            ready(ws)
            yield client, stored


def test_setup_reports_active_connection_and_never_sends_commands(running):
    client, stored = running
    before = list(client.app.state.mock.received)
    # Saving new values is not the same as applying them to the running process.
    stored.write_text(json.dumps({'bind': '127.0.0.1', 'port': 9999}))
    response = client.get('/api/setup')
    assert response.status_code == 200
    data = response.json()
    assert data['bind'] == '0.0.0.0'
    assert data['port'] == 8123
    assert data['urls'] == ['http://192.168.50.12:8123/']
    assert data['ma2']['state'] == 'logged_in'
    assert data['ma2']['user'] == 'Remote'
    assert data['mock'] is True
    assert 'password' not in json.dumps(data).lower()
    assert client.app.state.mock.received == before


def test_setup_refreshes_addresses_and_does_not_accept_old_qr(running, monkeypatch):
    client, _ = running
    assert client.get('/api/setup/qr', params={'address': '192.168.50.12'}).status_code == 200
    monkeypatch.setattr(bridge, 'local_addresses', lambda: ['192.168.2.8'])
    assert client.get('/api/setup').json()['urls'] == ['http://192.168.2.8:8123/']
    assert client.get('/api/setup/qr', params={'address': '192.168.50.12'}).status_code == 400
    assert client.get('/api/setup/qr', params={'address': 'evil.example/"<script>'}).status_code == 400
    qr = client.get('/api/setup/qr', params={'address': '192.168.2.8'})
    assert qr.status_code == 200
    assert qr.headers['content-type'].startswith('image/svg+xml')
    assert 'no-store' in qr.headers['cache-control']
    assert ET.fromstring(qr.content).tag == '{http://www.w3.org/2000/svg}svg'


def test_setup_rejects_remote_and_rebound_host(running, monkeypatch):
    client, _ = running
    assert client.get('/api/setup', headers={'Host': 'untrusted.example'}).status_code == 403
    monkeypatch.setattr(bridge, 'is_loopback', lambda request: False)
    assert client.get('/api/setup').status_code == 403
    assert client.get('/api/setup/qr', params={'address': '192.168.50.12'}).status_code == 403


def test_loopback_listener_does_not_advertise_tablet_access(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, 'is_loopback', lambda request: True)
    monkeypatch.setattr(bridge, 'local_addresses', lambda: ['192.168.50.12'])
    cfg = {'fixtures': [], 'groups': [], 'scenes': []}
    app = bridge.create_app(cfg, True, str(tmp_path / 'config.json'),
                            {'bind': '127.0.0.1', 'simple_port': None, 'poll_seconds': 0})
    with TestClient(app, base_url='http://127.0.0.1') as client:
        response = client.get('/api/setup')
        assert response.status_code == 200
        assert response.json()['urls'] == []
        assert response.json()['lan_enabled'] is False


def test_browser_opens_only_when_http_ready():
    import asyncio
    from types import SimpleNamespace
    opened = []
    async def run():
        server = SimpleNamespace(started=False, should_exit=False)
        task = asyncio.create_task(bridge.open_start_page(server, 8123, opened.append))
        await asyncio.sleep(0)
        assert opened == []
        server.started = True
        await task
        assert opened == ['http://127.0.0.1:8123/setup.html']
        stopped = SimpleNamespace(started=False, should_exit=True)
        await bridge.open_start_page(stopped, 8123, opened.append)
        assert len(opened) == 1
    asyncio.run(run())
