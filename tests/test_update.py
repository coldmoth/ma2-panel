import hashlib
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zipfile import ZipFile, ZipInfo

import pytest

import update


def archive(path, extra=None):
    with ZipFile(path, 'w') as z:
        for name, value in {'bridge.py': 'new', 'VERSION': 'v2', 'static/new.txt': 'new', **(extra or {})}.items():
            info = ZipInfo(name)
            # Preserve malicious names verbatim even on Windows.
            info.filename = name
            z.writestr(info, value)
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
    package = archive(tmp_path / 'a.zip', {name: 'bad'})
    with ZipFile(package) as z:
        assert name in [item.orig_filename for item in z.infolist()]
    with pytest.raises(update.UpdateError):
        update.validate_zip(package)


@pytest.mark.parametrize('manifest', [False, True])
def test_zip_rejects_names_normalized_by_reader(tmp_path, monkeypatch, manifest):
    extra = {'static\\x': 'bad'}
    if manifest:
        extra['program-manifest.json'] = '{}'
    package = archive(tmp_path / 'raw.zip', extra)
    original = ZipInfo.__init__

    def windows_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.filename = self.filename.replace('\\', '/')

    # Exercise Windows reader normalization on every platform.
    monkeypatch.setattr(ZipInfo, '__init__', windows_init)
    with pytest.raises(update.UpdateError, match='Недопустимый'):
        update.validate_zip(package)


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


def test_rollback_restores_exact_program_tree(tmp_path, monkeypatch):
    root = tmp_path / 'app'
    root.mkdir()
    (root / 'bridge.py').write_text('old')
    (root / 'VERSION').write_text('v1')
    (root / 'static').mkdir()
    (root / 'static/old.txt').write_text('old')
    (root / 'notes.py').write_text('user file')
    update.install(archive(tmp_path / 'v2.zip', {'added.py': 'new'}), root)
    monkeypatch.setattr(update, 'idle', lambda _: None)
    assert update.rollback(root, confirm=lambda _: 'y') == 0
    assert not (root / 'added.py').exists()
    assert not (root / 'static/new.txt').exists()
    assert (root / 'static/old.txt').read_text() == 'old'
    assert (root / 'notes.py').read_text() == 'user file'


def test_failed_second_install_keeps_last_rollback(tmp_path, monkeypatch):
    root = tmp_path / 'app'
    root.mkdir()
    (root / 'bridge.py').write_text('v1')
    (root / 'VERSION').write_text('v1')
    update.install(archive(tmp_path / 'v2.zip'), root)
    original = update.shutil.copy2
    def fail(source, destination, *args, **kwargs):
        if str(destination) == str(root / 'bridge.py') and 'backup' not in str(source) and 'previous' not in str(source):
            raise OSError('install failed')
        return original(source, destination, *args, **kwargs)
    monkeypatch.setattr(update.shutil, 'copy2', fail)
    with pytest.raises(OSError):
        update.install(archive(tmp_path / 'v3.zip', {'VERSION': 'v3'}), root)
    assert (root / 'VERSION').read_text() == 'v2'
    assert (root / 'previous/VERSION').read_text() == 'v1'


def test_interrupted_install_is_recovered_idempotently(tmp_path, monkeypatch):
    root = tmp_path / 'app'
    root.mkdir()
    (root / 'bridge.py').write_text('v1')
    (root / 'VERSION').write_text('v1')
    original = update.shutil.copy2
    def power_loss(source, destination, *args, **kwargs):
        if str(destination) == str(root / 'bridge.py') and 'backup' not in str(source) and 'previous' not in str(source):
            raise KeyboardInterrupt('power loss')
        return original(source, destination, *args, **kwargs)
    monkeypatch.setattr(update.shutil, 'copy2', power_loss)
    with pytest.raises(KeyboardInterrupt):
        update.install(archive(tmp_path / 'v2.zip'), root)
    monkeypatch.setattr(update.shutil, 'copy2', original)
    update.recover(root)
    update.recover(root)
    assert (root / 'bridge.py').read_text() == 'v1'
    assert (root / 'VERSION').read_text() == 'v1'
    assert not (root / 'static').exists()


def test_unverified_browser_install_rolls_back_after_worker_death(tmp_path):
    root = tmp_path / 'app'
    root.mkdir()
    (root / 'bridge.py').write_text('v1')
    (root / 'VERSION').write_text('v1')
    update.install(archive(tmp_path / 'v2.zip'), root, operation='5' * 32)
    update.atomic_json(root / '.updates/browser-state.json', {'id': '5' * 32, 'phase': 'verifying', 'owner': 999999999})
    update.recover(root)
    assert update.version(root) == 'v1'


def test_recovery_bootstrap_is_not_truncated_by_failed_publish(tmp_path, monkeypatch):
    root = tmp_path / 'app'
    root.mkdir()
    (root / 'bridge.py').write_text('v1')
    (root / 'VERSION').write_text('v1')
    work = root / '.updates'
    work.mkdir()
    (work / 'recovery.py').write_text('known good recovery')
    original = update.shutil.copy2
    def interrupted(source, target, *args, **kwargs):
        if str(target).endswith('recovery.py') or str(target).endswith('recovery.py.tmp'):
            Path(target).write_text('broken prefix')
            raise OSError('disk failure')
        return original(source, target, *args, **kwargs)
    from pathlib import Path
    monkeypatch.setattr(update.shutil, 'copy2', interrupted)
    with pytest.raises(OSError):
        update.install(archive(tmp_path / 'v2.zip'), root)
    assert (work / 'recovery.py').read_text() == 'known good recovery'
    assert (root / 'bridge.py').read_text() == 'v1'


def test_backup_flush_failure_aborts_before_program_removal(tmp_path, monkeypatch):
    root = tmp_path / 'app'
    root.mkdir()
    (root / 'bridge.py').write_text('old program')
    (root / 'VERSION').write_text('v1')
    original = update.os.fsync
    def fail_backup(fd):
        inode = update.os.fstat(fd).st_ino
        if any(p.stat().st_ino == inode for p in root.glob('.updates/*/backup/bridge.py')):
            raise OSError('backup flush failed')
        return original(fd)
    monkeypatch.setattr(update.os, 'fsync', fail_backup)
    with pytest.raises(OSError, match='flush failed'):
        update.install(archive(tmp_path / 'v2.zip'), root)
    assert (root / 'bridge.py').read_text() == 'old program'
    assert (root / 'VERSION').read_text() == 'v1'


def test_cli_confirmation_uses_atomic_quiesce_not_unconditional_stop():
    paths = []
    class Handler(QuietHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"idle": true}')
        def do_POST(self):
            paths.append(self.path)
            self.send_response(409 if self.path == '/api/update/quiesce' else 200)
            self.end_headers()
    with server(Handler) as port:
        assert update.prepare_bridge(port, 'v1', 'v2', confirm=lambda _: 'y', wait_seconds=0) == 2
    assert paths == ['/api/update/quiesce']


def test_backups_containing_credentials_are_private(tmp_path):
    import os
    import stat
    if os.name == 'nt':
        pytest.skip('NTFS ACL requires Windows smoke')
    (tmp_path / 'secret.env').write_text('password')
    folder = update.backup_user_data(tmp_path)
    assert stat.S_IMODE(folder.stat().st_mode) & 0o077 == 0


def test_backup_parent_flush_failure_precedes_mutation(tmp_path, monkeypatch):
    root = tmp_path / 'app'
    root.mkdir()
    (root / 'bridge.py').write_text('v1')
    (root / 'VERSION').write_text('v1')
    original = update.sync_directory
    def fail_parent(path):
        if (path / 'backup').is_dir():
            assert update.version(root) == 'v1', 'program changed before backup parent sync'
            raise OSError('backup parent flush')
        return original(path)
    monkeypatch.setattr(update, 'sync_directory', fail_parent)
    with pytest.raises(OSError, match='parent flush'):
        update.install(archive(tmp_path / 'v2.zip'), root)
    assert update.version(root) == 'v1'


def test_removal_flush_failure_does_not_commit_rollback(tmp_path, monkeypatch):
    root = tmp_path / 'app'
    root.mkdir()
    (root / 'bridge.py').write_text('old')
    (root / 'VERSION').write_text('v1')
    update.install(archive(tmp_path / 'v2.zip', {'zzz_added.py': 'new'}), root)
    original = update.sync_directory
    def fail_removal(path):
        if path == root and not (root / 'zzz_added.py').exists():
            raise OSError('removal flush')
        return original(path)
    monkeypatch.setattr(update, 'sync_directory', fail_removal)
    monkeypatch.setattr(update, 'idle', lambda _: None)
    with pytest.raises(OSError, match='removal flush'):
        update.rollback(root, confirm=lambda _: 'y')
    assert json.loads((root / '.updates/active.json').read_text())['phase'] == 'restoring'

@pytest.mark.parametrize('failure', [None, 'runtime', 'snapshot', 'apply'])
def test_external_usb_route_preserves_installed_updater(tmp_path, monkeypatch, failure):
    import sys
    root = tmp_path / 'старая установка'
    root.mkdir()
    original = {'bridge.py': b'old bridge', 'update.py': b'old updater',
                'release.py': b'old release', 'VERSION': b'v1'}
    for name, value in original.items():
        (root / name).write_bytes(value)
    stage = tmp_path / 'USB staging'
    stage.mkdir()
    package = archive(stage / 'ma2-panel-update.zip',
                      {'update.py': 'new updater', 'release.py': 'new release'})
    monkeypatch.setattr(sys, 'argv', [str(stage / 'update.py'), '--root', str(root), str(package)])
    monkeypatch.setattr(update, '__file__', str(stage / 'update.py'))
    (stage / 'update.py').write_bytes(b'external updater')
    monkeypatch.setattr(update, 'prepare_bridge', lambda *args: 0)
    monkeypatch.setattr(update, 'idle', lambda _: None)
    if failure == 'runtime':
        with ZipFile(package, 'a') as z:
            z.writestr('program-manifest.json', '{}')
        monkeypatch.setattr(update, 'validate_zip', lambda _: 'v2')
    if failure in ('snapshot', 'apply'):
        copy = update.copy_entry
        injected = []
        def fail_copy(source, target):
            if not injected and ((failure == 'snapshot' and target.parent.name == 'backup') or
                    (failure == 'apply' and target.parent == root)):
                injected.append(True)
                raise OSError('injected ' + failure)
            return copy(source, target)
        monkeypatch.setattr(update, 'copy_entry', fail_copy)
    assert update.main() == (1 if failure else 0)
    if not failure:
        assert (root / 'previous/update.py').read_bytes() == original['update.py']
        assert (root / 'previous/release.py').read_bytes() == original['release.py']
        assert update.rollback(root, confirm=lambda _: 'y') == 0
    if failure in ('snapshot', 'apply'):
        assert injected
    if failure == 'runtime':
        assert not (root / '.updates/active.json').exists()
        assert not (root / 'previous').exists()
    assert {name: (root / name).read_bytes() for name in original} == original

@pytest.mark.parametrize('journal', [
    b'{"version":1,"pending":true,"id":"pending-op","target":{"host":"192.0.2.5","port":30001}}',
    b'{"version":1,"pending":true,"target":null}',
    b'{broken journal\x00',
])
def test_rdm_journal_survives_backup_transfer_update_rollback(tmp_path, monkeypatch, journal):
    import asyncio
    import shutil
    from types import SimpleNamespace
    from rdm_search import RDMSearch
    from commands import ActionError

    root = tmp_path / 'source'
    root.mkdir()
    (root / 'bridge.py').write_text('old')
    (root / 'rdm-search.json').write_bytes(journal)
    backup = update.backup_user_data(root)
    assert (backup / 'rdm-search.json').read_bytes() == journal
    restored = tmp_path / 'restored'
    shutil.copytree(backup, restored)
    transferred = tmp_path / 'transferred'
    transferred.mkdir()
    for name in update.USER_DATA:
        source = root / name
        if source.is_file():
            shutil.copy2(source, transferred / name)
        elif source.is_dir():
            shutil.copytree(source, transferred / name)
    update.install(archive(tmp_path / 'update.zip'), root)
    monkeypatch.setattr(update, 'idle', lambda _: None)
    assert update.rollback(root, confirm=lambda _: 'y') == 0
    async def check_pending(folder):
        async def no_commands(*args, **kwargs):
            pytest.fail('RDM command attempted')
        link = SimpleNamespace(host='127.0.0.1', port=30000, ready=True, halted=False, send=no_commands)
        controller = RDMSearch(link, asyncio.Lock(), folder / 'rdm-search.json',
                               lambda: True, lambda: (), no_commands, lambda: False)
        assert controller.snapshot()['pending']
        with pytest.raises(ActionError):
            await controller.prepare()
        if journal.startswith(b'{"version"'):
            assert controller._target == json.loads(journal)['target']
        assert (folder / 'rdm-search.json').read_bytes() == journal
    for folder in (root, backup, restored, transferred):
        asyncio.run(check_pending(folder))


@pytest.mark.parametrize('output_encoding', [None, 'cp1252'])
def test_external_usb_isolated_python_uses_staged_release(tmp_path, output_encoding):
    import subprocess
    import sys
    from pathlib import Path
    stage = tmp_path / 'USB staging'
    stage.mkdir()
    root = tmp_path / 'установка'
    root.mkdir()
    source = Path(__file__).resolve().parents[1]
    update.shutil.copy2(source / 'update.py', stage / 'update.py')
    # A distinct release module proves the import origin without using installed modules.
    (stage / 'release.py').write_text(
        "def check(*args):\n    raise ValueError('staged release reached')\n")
    (root / 'release.py').write_bytes(b'old release')
    package = archive(stage / 'ma2-panel-update.zip', {'program-manifest.json': '{}'})
    command = [sys.executable, '-I', str(stage / 'update.py'),
               '--root', str(root), str(package)]
    if output_encoding:
        # -I ignores PYTHONIOENCODING: force the actual stream, as on CI.
        command = [sys.executable, '-I', '-c',
                   'import runpy,sys; sys.stdout.reconfigure(encoding="cp1252"); '
                   'sys.stderr.reconfigure(encoding="cp1252"); '
                   'sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name="__main__")',
                   *command[2:]]
    result = subprocess.run(command, cwd=root, capture_output=True,
                            text=True, encoding='utf-8', timeout=10)
    assert result.returncode == 1
    assert 'Обновление не выполнено: staged release reached' in result.stdout, result.stdout + result.stderr
    assert 'UnicodeEncodeError' not in result.stderr
    assert (root / 'release.py').read_bytes() == b'old release'
    assert not (root / 'previous').exists()
