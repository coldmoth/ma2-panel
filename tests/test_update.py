import hashlib
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zipfile import ZipFile

import pytest

import update


def archive(path, extra=None):
    with ZipFile(path, 'w') as z:
        for name, value in {'bridge.py': 'new', 'VERSION': 'v2', 'static/new.txt': 'new', **(extra or {})}.items():
            z.writestr(name, value)
    return path


@contextmanager
def server(handler):
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_port
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


class QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass


def test_good_zip(tmp_path):
    assert update.validate_zip(archive(tmp_path / 'a.zip')) == 'v2'


@pytest.mark.parametrize('name', ['settings.json', '../x.py', 'python/x', '/x.py', 'static/../../x.py', 'C:/x.py', 'static\\x'])
def test_bad_zip(tmp_path, name):
    with pytest.raises(update.UpdateError):
        update.validate_zip(archive(tmp_path / 'a.zip', {name: 'bad'}))


def test_download_and_hash(tmp_path):
    data = archive(tmp_path / 'source.zip').read_bytes()
    class Handler(QuietHandler):
        digest = hashlib.sha256(data).hexdigest()
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write((self.digest + '  update.zip').encode() if self.path.endswith('.sha256') else data)
    with server(Handler) as port:
        url = f'http://127.0.0.1:{port}/update.zip'
        assert update.download(url, tmp_path).read_bytes() == data
        Handler.digest = '0' * 64
        with pytest.raises(update.UpdateError, match='SHA256'):
            update.download(url, tmp_path)


def test_install_and_rollback(tmp_path, monkeypatch):
    root = tmp_path / 'app'
    root.mkdir()
    for name, content in {'bridge.py': 'old', 'VERSION': 'v1', 'settings.json': '{}', 'secret.env': 'secret', 'config.json': 'config'}.items():
        (root / name).write_text(content)
    (root / 'static').mkdir()
    (root / 'static/old.txt').write_text('old')
    update.install(archive(tmp_path / 'a.zip'), root)
    assert (root / 'bridge.py').read_text() == 'new'
    assert (root / 'previous/bridge.py').read_text() == 'old'
    assert not (root / 'static/old.txt').exists()
    monkeypatch.setattr(update, 'idle', lambda port: None)
    assert update.rollback(root, confirm=lambda _: 'y') == 0
    assert (root / 'bridge.py').read_text() == 'old'
    assert (root / 'static/old.txt').read_text() == 'old'
    for name, content in {'settings.json': '{}', 'secret.env': 'secret', 'config.json': 'config'}.items():
        assert (root / name).read_text() == content


def test_install_failure_restores(tmp_path, monkeypatch):
    root = tmp_path / 'app'
    root.mkdir()
    (root / 'bridge.py').write_text('old')
    original = update.shutil.copy2
    def fail(source, destination, *args, **kwargs):
        if str(source).endswith('bridge.py'):
            raise OSError('simulated failure')
        return original(source, destination, *args, **kwargs)
    monkeypatch.setattr(update.shutil, 'copy2', fail)
    with pytest.raises(OSError):
        update.install(archive(tmp_path / 'a.zip'), root)
    assert (root / 'bridge.py').read_text() == 'old'
    assert not (root / 'VERSION').exists()


def test_busy_refuses_without_changes(tmp_path, monkeypatch):
    class Handler(QuietHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"idle": false}')
    source = archive(tmp_path / 'a.zip')
    root = tmp_path / 'app'
    root.mkdir()
    with server(Handler) as port:
        (root / 'settings.json').write_text(json.dumps({'port': port}))
        before = (root / 'settings.json').read_bytes()
        monkeypatch.setattr(update, 'download', lambda *_: source)
        assert update.run(root, 'localhost:8765', confirm=lambda _: pytest.fail('must not ask')) == 2
        assert (root / 'settings.json').read_bytes() == before
        assert not (root / 'previous').exists()


def test_url():
    assert update.normalize_url('192.168.0.20:8765') == 'http://192.168.0.20:8765/ma2-panel-update.zip'


def test_usb_update_keeps_and_backs_up_user_data(tmp_path, monkeypatch):
    import zipfile
    root = tmp_path / 'app'
    root.mkdir()
    for name, text in (('bridge.py', 'old'), ('VERSION', 'v1'), ('config.json', '{"version": 4}'),
                       ('settings.json', '{"ma2": {"user": "Remote"}}'), ('secret.env', 'MA2_PASSWORD=real\n')):
        (root / name).write_text(text, encoding='utf-8')
    (root / 'shows').mkdir()
    (root / 'shows' / 'big room v2.json').write_text('{}', encoding='utf-8')
    with zipfile.ZipFile(root / 'ma2-panel-update.zip', 'w') as z:
        z.writestr('bridge.py', 'new')
        z.writestr('VERSION', 'v2')
    monkeypatch.setattr(update, 'idle', lambda port: None)
    assert update.run(root, confirm=lambda prompt: 'y') == 0
    assert (root / 'bridge.py').read_text() == 'new' and (root / 'previous' / 'bridge.py').read_text() == 'old'
    assert (root / 'secret.env').read_text() == 'MA2_PASSWORD=real\n'
    assert (root / 'settings.json').read_text() == '{"ma2": {"user": "Remote"}}'
    backup = next((root / 'backups').glob('before-update-*'))
    assert (backup / 'secret.env').exists() and (backup / 'shows' / 'big room v2.json').exists()
    assert not (root / 'update_url.txt').exists()
