import asyncio
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

import browser_update as bu
import release
import update


def package(tmp_path):
    files = {'bridge.py': b'new', 'update.py': b'new', 'VERSION': b'v2'}
    runtime = {'python': '3.12', 'lock_sha256': 'a' * 64}
    manifest = {'schema': 1, 'version': 'v2', 'runtime': runtime,
                'files': {k: {'sha256': hashlib.sha256(v).hexdigest(), 'size': len(v)} for k, v in files.items()}}
    files['program-manifest.json'] = json.dumps(manifest).encode()
    archive = tmp_path / 'release.zip'
    release.write_zip(files, archive)
    return archive, runtime



@pytest.mark.parametrize('field', ['version', 'operation', 'pid', 'unreachable'])
def test_health_rejection_records_expected_and_observed(tmp_path, monkeypatch, field):
    from contextlib import contextmanager
    expected = {'version': 'v2', 'operation': 'a' * 32, 'pid': 123}
    observed = {**expected, 'unrelated_secret': 'must not be recorded'}
    if field != 'unreachable':
        observed[field] = 'wrong'

    @contextmanager
    def response(*args, **kwargs):
        import io
        if field == 'unreachable':
            raise OSError('unreachable')
        yield io.StringIO(json.dumps(observed))

    ticks = iter([0, 0, 36])
    monkeypatch.setattr(bu.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(bu.time, 'sleep', lambda _: None)
    monkeypatch.setattr(bu.urllib.request, 'urlopen', response)
    (tmp_path / '.updates').mkdir()
    spec = {'root': str(tmp_path), 'id': expected['operation'], 'child_pid': 123, 'ports': [8080, 8090]}
    with pytest.raises(update.UpdateError, match='всех портах'):
        bu.health(spec, 'v2')
    diagnostic = json.loads((tmp_path / '.updates/health.json').read_text())
    assert diagnostic['expected'] == expected
    assert diagnostic['ports'] == [8080, 8090]
    assert diagnostic['observed'][0]['port'] == 8080
    if field == 'unreachable':
        assert diagnostic['observed'][0]['error'] == 'OSError'
    else:
        assert diagnostic['observed'][0]['result'][field] == 'wrong'
    assert 'must not be recorded' not in json.dumps(diagnostic)


def test_release_selection_rejects_foreign_assets(monkeypatch):
    monkeypatch.setattr(bu, 'fetch_json', lambda _: {'tag_name': 'v2', 'draft': False, 'prerelease': False, 'assets': [
        {'name': 'ma2-panel-update.zip', 'browser_download_url': 'https://evil.invalid/a.zip'},
        {'name': 'ma2-panel-update.zip.sha256', 'browser_download_url': 'https://evil.invalid/a.sha256'}]})
    with pytest.raises(update.UpdateError):
        bu.latest()


def install_runtime(root):
    (root / 'python').mkdir()
    (root / 'python/python.exe').write_bytes(b'python')
    (root / 'lib').mkdir()
    (root / 'lib/a.py').write_bytes(b'lib')
    release.record_runtime(root)


def test_prepare_checks_runtime_before_any_install(tmp_path, monkeypatch):
    monkeypatch.setattr(bu, 'supported_platform', lambda: True)
    archive, runtime = package(tmp_path)
    root = tmp_path / 'app'
    root.mkdir()
    (root / 'bridge.py').write_text('old')
    install_runtime(root)
    (root / 'runtime.json').write_text(json.dumps({**runtime, 'lock_sha256': 'b' * 64}))
    def download(url, path, limit):
        path.write_bytes(archive.read_bytes() if url.endswith('.zip') else hashlib.sha256(archive.read_bytes()).hexdigest().encode())
    monkeypatch.setattr(bu, 'download', download)
    with pytest.raises(ValueError):
        bu.prepare(root, '1' * 32, {'url': 'a.zip', 'checksum_url': 'a.sha256'})
    assert (root / 'bridge.py').read_text() == 'old'
    assert not (root / 'previous').exists()


def test_bad_checksum_leaves_program_running(tmp_path, monkeypatch):
    monkeypatch.setattr(bu, 'supported_platform', lambda: True)
    archive, runtime = package(tmp_path)
    install_runtime(tmp_path)
    (tmp_path / 'runtime.json').write_text(json.dumps(runtime))
    monkeypatch.setattr(bu, 'download', lambda url, path, limit: path.write_bytes(archive.read_bytes() if url.endswith('.zip') else b'0' * 64))
    with pytest.raises(update.UpdateError, match='SHA256'):
        bu.prepare(tmp_path, '2' * 32, {'url': 'a.zip', 'checksum_url': 'a.sha256'})
    assert not (tmp_path / 'previous').exists()


def test_failed_health_restores_old_program_and_preserves_data(tmp_path, monkeypatch):
    archive, _ = package(tmp_path)
    root = tmp_path / 'app'
    root.mkdir()
    (root / 'bridge.py').write_text('old')
    (root / 'VERSION').write_text('v1')
    (root / 'config.json').write_text('user data')
    starts = []
    monkeypatch.setattr(bu, 'launch', lambda spec: starts.append(update.version(root)))
    def health(spec, version):
        if version == 'v2':
            raise update.UpdateError('health failed')
    monkeypatch.setattr(bu, 'health', health)
    monkeypatch.setattr(bu, 'stop_child', lambda child: None)
    spec = {'root': str(root), 'id': '3' * 32, 'archive': str(archive), 'version': 'v2', 'ports': [8080], 'args': []}
    bu.apply(spec)
    assert starts == ['v2', 'v1']
    assert update.version(root) == 'v1'
    assert (root / 'config.json').read_text() == 'user data'
    assert bu.status(root)['phase'] == 'rolled_back'


def test_begin_is_idempotent_and_busy_does_not_stop(tmp_path, monkeypatch):
    async def go():
        manager = bu.Updater(tmp_path)
        monkeypatch.setattr(bu, 'latest', lambda: {'version': 'v3.2.0', 'url': 'x', 'checksum_url': 'y'})
        monkeypatch.setattr(bu, 'prepare', lambda *args: (_ for _ in ()).throw(update.UpdateError('network down')))
        async def gate():
            pytest.fail('gate must not close before successful verification')
        first = manager.begin(gate, lambda: None, {'args': [], 'ports': [8080]})
        second = manager.begin(gate, lambda: None, {'args': [], 'ports': [8080]})
        assert first['id'] == second['id']
        await manager.task
        assert bu.status(tmp_path)['phase'] == 'failed'
    asyncio.run(go())


def test_update_api_is_local_and_protected(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import bridge
    cfg = json.loads(Path('tests/config.test.json').read_text())
    cfg['ma2']['port'] = 30000
    cfg['ma2']['export_dir'] = str(tmp_path)
    monkeypatch.setattr(bridge, 'HERE', tmp_path)
    (tmp_path / 'static').mkdir()
    (tmp_path / 'VERSION').write_text('3.1.0')
    monkeypatch.setattr(bu, 'latest', lambda: {'version': 'v3.2.0', 'url': 'x', 'checksum_url': 'y'})
    app = bridge.create_app(cfg, True, str(tmp_path / 'config.json'), settings={'poll_seconds': 0})
    with TestClient(app, base_url='http://localhost', client=('127.0.0.1', 123)) as client:
        assert client.post('/api/update/check').status_code == 403
        assert client.post('/api/update/check', headers={'X-Update': '1', 'Origin': 'https://foreign.invalid'}).status_code == 403
        assert client.post('/api/update/check', headers={'X-Update': '1'}).json()['available']['version'] == 'v3.2.0'
        app.state.updating = True
        assert client.post('/api/settings', json={}).status_code == 409
        with client.websocket_connect('/ws') as ws:
            ws.send_json({'a': 'dim', 'ids': [1], 'v': 100})
            for _ in range(20):
                message = ws.receive_json()
                if 'ok' in message:
                    assert message['ok'] is False
                    assert 'обновлен' in message['err']
                    break
            else:
                pytest.fail('no refusal')
    with TestClient(app, base_url='http://localhost', client=('192.168.1.9', 123)) as client:
        assert client.get('/api/update/status').status_code == 403
        assert client.post('/api/update/check', headers={'X-Update': '1'}).status_code == 403


def test_status_relay_reports_failure_while_bridge_is_down(tmp_path):
    from urllib.request import urlopen
    bu.progress(tmp_path, '4' * 32, 'failed', error='start failed')
    relay = bu.StatusRelay(tmp_path, 0)
    try:
        relay.start()
        with urlopen(f'http://127.0.0.1:{relay.port}/api/update/status') as response:
            assert json.load(response)['error'] == 'start failed'
    finally:
        relay.stop()


def test_real_worker_update_restart_and_both_ports(tmp_path):
    """Real detached worker/HTTP restart; only GitHub transport is replaced by localhost."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import os
    import signal
    import socket
    import subprocess
    import sys
    import threading
    import time
    from urllib.request import Request, urlopen

    source = Path(__file__).resolve().parents[1]
    root = tmp_path / 'panel space зал'
    root.mkdir()
    release.write_tree(release.build(source, version='3.1.0+smoke1'), root)
    install_runtime(root)
    (root / 'runtime.json').write_text(json.dumps(release.runtime(source)))
    cfg = json.loads((source / 'tests/config.test.json').read_text())
    cfg['ma2'].update(port=30000, export_dir=str(tmp_path / 'exports'))
    cfg['scenes'] = []
    (root / 'config.json').write_text(json.dumps(cfg))
    ports = []
    for _ in range(2):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            ports.append(sock.getsockname()[1])
    settings = {'bind': '127.0.0.1', 'port': ports[0], 'simple_port': ports[1], 'poll_seconds': 0}
    (root / 'settings.json').write_text(json.dumps(settings))
    bundle = tmp_path / 'bundle.zip'
    release.write_zip(release.build(source, version='3.2.0+smoke2'), bundle)
    payload = bundle.read_bytes()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            body = hashlib.sha256(payload).hexdigest().encode() if self.path.endswith('.sha256') else payload
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{httpd.server_port}/update.zip'
    info = {'version': 'v3.2.0', 'url': url, 'checksum_url': url + '.sha256'}
    args = ['--mock', '--config', str(root / 'config.json'), '--settings', str(root / 'settings.json')]
    code = f'import sys;sys.path.insert(0,{str(root)!r});import bridge,browser_update;browser_update.latest=lambda:{info!r};browser_update.supported_platform=lambda:True;browser_update._open=lambda req,timeout:__import__("urllib.request",fromlist=["urlopen"]).urlopen(req,timeout=timeout);sys.argv=[{str(root / "bridge.py")!r},*{args!r}];bridge.main()'
    log = (tmp_path / 'bridge-output.log').open('wb')
    parent = subprocess.Popen([sys.executable, '-c', code], cwd=root, stdout=log, stderr=log)
    new_pid = None
    base = f'http://127.0.0.1:{ports[0]}'
    def get(path, port=None):
        with urlopen(f'http://127.0.0.1:{port or ports[0]}' + path, timeout=1) as response:
            return json.load(response)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                get('/api/update/health')
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail((tmp_path / 'bridge-output.log').read_text())
        # Migration belongs to startup; updates must preserve the resulting site settings.
        settings = json.loads((root / 'settings.json').read_text())
        time.sleep(0.3)
        with urlopen(Request(base + '/api/update/start', data=json.dumps({'version':'v3.2.0'}).encode(), headers={'X-Update': '1'}, method='POST'), timeout=3) as response:
            operation = json.load(response)['id']
        deadline = time.monotonic() + 30
        current = {}
        while time.monotonic() < deadline:
            parent.poll()  # reap the old process so POSIX wait_parent sees its termination
            try:
                current = get('/api/update/status')
                if current.get('id') == operation and current.get('phase') in bu.TERMINAL:
                    break
            except OSError:
                pass
            time.sleep(0.1)
        if current.get('phase') != 'completed':
            # Observe both ports independently; HTTP 200 alone proves no identity.
            diagnostic = {'state': current, 'parent_pid': parent.pid,
                          'parent_returncode': parent.poll(), 'ports': {}}
            owner = current.get('owner')
            diagnostic['worker_alive'] = update.process_alive(owner) if owner else None
            for port in ports:
                try:
                    observed = get('/api/update/health', port)
                    diagnostic['ports'][str(port)] = {k: observed.get(k) for k in
                                                      ('version', 'operation', 'pid', 'instance')}
                except (OSError, ValueError) as exc:
                    diagnostic['ports'][str(port)] = {'error': type(exc).__name__}
            (tmp_path / 'worker-failure.json').write_text(json.dumps(diagnostic, indent=2), encoding='utf-8')
        assert current.get('phase') == 'completed', (current, (root / '.updates/startup.log').read_text() if (root / '.updates/startup.log').exists() else '')
        for port in ports:
            result = get('/api/update/health', port)
            new_pid = result['pid']
            assert result['version'] == '3.2.0+smoke2'
            assert result['operation'] == operation
            assert result['pid'] != parent.pid
        assert json.loads((root / 'settings.json').read_text()) == settings
        assert json.loads((root / 'config.json').read_text())['fixtures'] == cfg['fixtures']
        # Simulate the exact persisted state of a worker killed after child startup.
        bu.progress(root, operation, 'verifying', owner=999999999)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try:
                current = get('/api/update/status')
                if current.get('phase') == 'rolled_back':
                    break
            except OSError:
                pass
            time.sleep(0.1)
        assert current.get('phase') == 'rolled_back', current
        for port in ports:
            result = get('/api/update/health', port)
            new_pid = result['pid']
            assert result['version'] == '3.1.0+smoke1'
    finally:
        try:
            with urlopen(Request(base + '/api/stop', data=b'', headers={'X-Stop': '1'}, method='POST'), timeout=2):
                pass
        except OSError:
            if new_pid:
                os.kill(new_pid, signal.SIGTERM)
        if parent.poll() is None:
            parent.terminate()
        parent.wait(timeout=5)
        httpd.shutdown()
        httpd.server_close()
        log.close()


def test_orphan_lock_before_status_write_is_recovered(tmp_path, monkeypatch):
    ident = '6' * 32
    assert update.acquire_lock(tmp_path, ident)
    monkeypatch.setattr(update, 'process_alive', lambda _: False)
    bu.recover_pending(tmp_path)
    assert update.acquire_lock(tmp_path, '7' * 32)
    update.remove(tmp_path / '.updates/browser.lock')
