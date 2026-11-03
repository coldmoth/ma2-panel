"""Local browser updates. The detached stdlib worker survives bridge shutdown."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.parse
import urllib.request
import uuid

import release
import update

REPO = 'coldmoth/ma2-panel'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
TERMINAL = {'idle', 'completed', 'rolled_back', 'failed'}


def download(url, path, limit):
    request = urllib.request.Request(url, headers={'User-Agent': 'ma2-panel-updater', 'Accept': 'application/octet-stream'})
    with urllib.request.urlopen(request, timeout=20) as response, Path(path).open('wb') as stream:
        total = 0
        while chunk := response.read(65536):
            total += len(chunk)
            if total > limit:
                raise update.UpdateError('Файл обновления слишком большой')
            stream.write(chunk)


def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'ma2-panel-updater', 'Accept': 'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise update.UpdateError('Слишком большой ответ GitHub')
        return json.loads(raw)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise update.UpdateError('Опубликованных релизов пока нет') from exc
        if exc.code in (403, 429):
            raise update.UpdateError('GitHub временно ограничил запросы; повторите позже') from exc
        raise update.UpdateError(f'GitHub: HTTP {exc.code}') from exc


def latest():
    data = fetch_json(API)
    if not isinstance(data, dict) or data.get('draft') or data.get('prerelease'):
        raise update.UpdateError('Нет стабильного релиза')
    assets = {a['name']: a['browser_download_url'] for a in data.get('assets', [])}
    names = ('ma2-panel-update.zip', 'ma2-panel-update.zip.sha256')
    if not all(name in assets for name in names):
        raise update.UpdateError('В релизе нет комплекта обновления и SHA256')
    for name in names:
        parsed = urllib.parse.urlsplit(assets[name])
        if parsed.scheme != 'https' or parsed.netloc != 'github.com' or not parsed.path.startswith(f'/{REPO}/releases/download/') or parsed.query or parsed.fragment:
            raise update.UpdateError('Недопустимый источник обновления')
    return {'version': str(data.get('tag_name', '')), 'url': assets[names[0]], 'checksum_url': assets[names[1]]}


def status(root):
    path = Path(root) / '.updates/browser-state.json'
    if not path.exists():
        return {'phase': 'idle'}
    try:
        result = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(result, dict) or 'phase' not in result:
            raise ValueError()
        return result
    except (OSError, ValueError):
        return {'phase': 'failed', 'error': 'Повреждён журнал обновления; требуется проверка на ПК'}


def progress(root, ident, phase, **fields):
    before = status(root)
    if before.get('id') != ident:
        before = {'id': ident}
    update.atomic_json(update.transaction(Path(root)) / 'browser-state.json',
                       {**before, 'phase': phase, **fields})


def release_lock(root):
    update.remove(Path(root) / '.updates/browser.lock')


def prepare(root, ident, info):
    root = Path(root)
    try:
        installed = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
        release.verify_runtime(root)
    except (OSError, ValueError) as exc:
        raise update.UpdateError('Нет сведений о Python/lib. Сначала установите полный Windows-комплект блока Б') from exc
    folder = update.transaction(root) / ('browser-' + ident)
    folder.mkdir()
    archive, checksum = folder / 'update.zip', folder / 'checksum.txt'
    download(info['url'], archive, release.MAX_TOTAL)
    download(info['checksum_url'], checksum, 1024)
    tokens = checksum.read_text(encoding='ascii').split()
    if not tokens or not re.fullmatch('[0-9a-fA-F]{64}', tokens[0]) or hashlib.sha256(archive.read_bytes()).hexdigest() != tokens[0].lower():
        raise update.UpdateError('Контрольная сумма SHA256 не совпадает')
    manifest = release.check(archive, installed)
    # Room for stage, original program, new rollback copy and user backup.
    need = sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink() and '.updates' not in p.relative_to(root).parts)
    if shutil.disk_usage(root).free < need * 3 + archive.stat().st_size * 4 + 16 * 1024 * 1024:
        raise update.UpdateError('Недостаточно свободного места для обновления и копий')
    if manifest['version'] == update.version(root):
        raise update.UpdateError('Эта версия уже установлена')
    return archive, manifest


def launch(spec):
    root = Path(spec['root'])
    env = {**os.environ, 'MA2_UPDATE_ID': spec['id']}
    log = (root / '.updates/startup.log').open('ab')
    try:
        return subprocess.Popen([sys.executable, str(root / 'bridge.py'), *spec['args']], cwd=root,
                                env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    finally:
        log.close()


def stop_child(child):
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)


def health(spec, version):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        try:
            for port in spec['ports']:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/update/health', timeout=2) as response:
                    result = json.load(response)
                if (result.get('version') != version or result.get('operation') != spec['id']
                        or (spec.get('child_pid') and result.get('pid') != spec['child_pid'])):
                    raise ValueError('wrong instance')
            return
        except (OSError, ValueError):
            time.sleep(0.25)
    raise update.UpdateError('Новая версия не подтвердила запуск на всех портах')


class StatusRelay:
    """Read-only loopback status on the original port while the bridge is absent."""
    def __init__(self, root, port):
        self.root, self.port = Path(root), port
        self.server = self.thread = None
        self.delivered = threading.Event()

    def start(self):
        if self.server:
            return
        relay = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                host = urllib.parse.urlsplit('http://' + self.headers.get('Host', '')).hostname
                if host not in ('localhost', '127.0.0.1', '::1'):
                    self.send_error(403)
                    return
                if self.path == '/api/update/status':
                    data = status(relay.root)
                    body = json.dumps({'ok': True, 'current': update.version(relay.root), **data}).encode()
                    mime = 'application/json'
                    if data['phase'] in TERMINAL:
                        relay.delivered.set()
                elif self.path in ('/', '/settings.html'):
                    body = ("<!doctype html><html lang='ru'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                            "<title>Обновление MA2</title><body style='background:#111;color:#eee;font:20px system-ui;padding:24px'>"
                            "<h1>Обновление программы</h1><p id='s' role='status'>Ожидаем результат…</p>"
                            "<p>При ошибке запуска подробности сохранены в .updates/startup.log на ПК моста.</p>"
                            "<script>async function poll(){try{let d=await(await fetch('/api/update/status')).json();"
                            "document.getElementById('s').textContent=(d.error||d.phase);if(d.phase==='completed'||d.phase==='rolled_back')location.href='/settings.html';"
                            "}catch(e){}setTimeout(poll,1500)}poll()</script></body></html>").encode()
                    mime = 'text/html; charset=utf-8'
                else:
                    self.send_error(503)
                    return
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        self.server = ThreadingHTTPServer(('127.0.0.1', self.port), Handler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
            self.server = self.thread = None


def apply(spec):
    root, ident = Path(spec['root']), spec['id']
    old = update.version(root)
    child = None
    installed = False
    relay = spec.get('relay')
    try:
        if relay:
            relay.start()
        progress(root, ident, 'installing', owner=os.getpid())
        update.backup_user_data(root)
        update.install(spec['archive'], root, operation=ident)
        installed = True
        progress(root, ident, 'starting')
        if relay:
            relay.stop()
        child = launch(spec)
        spec['child_pid'] = child.pid if child else None
        progress(root, ident, 'verifying')
        health(spec, spec['version'])
        progress(root, ident, 'completed', version=spec['version'], error='')
    except Exception as exc:
        stop_child(child)
        failure = str(exc)
        try:
            progress(root, ident, 'rolling_back', error=failure)
            if relay:
                relay.start()
            update.recover(root)
            if installed:
                # The previous bridge is gone, and we own the transaction lock.
                meta = json.loads((root / 'previous/rollback.json').read_text(encoding='utf-8'))
                ident_restore = uuid.uuid4().hex
                folder = update.transaction(root) / ident_restore
                shutil.copytree(root / 'previous/program', folder / 'backup')
                update.sync_tree(folder)
                update.sync_directory(root / '.updates')
                tx = {'id': ident_restore, 'phase': 'restoring', 'snapshot': meta}
                update.atomic_json(root / '.updates/active.json', tx)
                update.recover(root)
            if relay:
                relay.stop()
            child = launch(spec)
            spec['child_pid'] = child.pid if child else None
            health(spec, old)
            progress(root, ident, 'rolled_back', version=old, error=failure)
        except Exception as rollback_error:
            stop_child(child)
            progress(root, ident, 'failed', error=f'{failure}. Восстановление: {rollback_error}')
    finally:
        release_lock(root)


def wait_parent(pid, timeout=45):
    """Acquire a Windows process handle before acknowledging readiness (no PID reuse race)."""
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            raise update.UpdateError('Не удалось открыть процесс моста')
        def wait():
            try:
                if kernel.WaitForSingleObject(handle, int(timeout * 1000)) != 0:
                    raise update.UpdateError('Мост не остановился')
            finally:
                kernel.CloseHandle(handle)
        return wait
    # The worker is spawned by the still-running parent. Capture a pidfd where available.
    def wait():
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        raise update.UpdateError('Мост не остановился')
    return wait


def worker(spec_path):
    spec = json.loads(Path(spec_path).read_text(encoding='utf-8'))
    root, ident = Path(spec['root']), spec['id']
    try:
        wait = wait_parent(spec['parent_pid'])
        progress(root, ident, 'waiting', owner=os.getpid())
        wait()
        relay = StatusRelay(root, spec['ports'][0])
        spec['relay'] = relay
        apply(spec)
        if status(root)['phase'] == 'failed':
            relay.start()
            relay.delivered.wait(timeout=180)
            relay.stop()
    except Exception as exc:
        progress(root, ident, 'failed', error=str(exc))
        release_lock(root)


class Updater:
    def __init__(self, root):
        self.root = Path(root)
        self.task = None

    def begin(self, gate, stop, launch_spec):
        work = update.transaction(self.root)
        ident = uuid.uuid4().hex
        if not update.acquire_lock(self.root, ident):
            return status(self.root)
        progress(self.root, ident, 'downloading', owner=os.getpid(), error='')
        self.task = asyncio.create_task(self._run(ident, gate, stop, launch_spec))
        return status(self.root)

    async def _run(self, ident, gate, stop, launch_spec):
        closed = False
        child = None
        try:
            info = await asyncio.to_thread(latest)
            archive, manifest = await asyncio.to_thread(prepare, self.root, ident, info)
            progress(self.root, ident, 'validated', version=manifest['version'])
            if not await gate():
                raise update.UpdateError('Панель занята. Дождитесь окончания действий и повторите')
            closed = True
            folder = archive.parent / 'worker'
            folder.mkdir()
            for name in ('browser_update.py', 'update.py', 'release.py'):
                shutil.copy2(Path(__file__).parent / name, folder / name)
            spec = {**{k: v for k, v in launch_spec.items() if k != 'reopen'}, 'id': ident, 'root': str(self.root), 'parent_pid': os.getpid(),
                    'archive': str(archive), 'version': manifest['version']}
            update.atomic_json(folder / 'job.json', spec)
            flags = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS} if sys.platform == 'win32' else {'start_new_session': True}
            child = subprocess.Popen([sys.executable, str(folder / 'browser_update.py'), str(folder / 'job.json')],
                                     cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, **flags)
            for _ in range(100):
                current = status(self.root)
                if current.get('phase') == 'waiting':
                    stop()
                    return
                if child.poll() is not None or current.get('phase') == 'failed':
                    raise update.UpdateError('Внешний updater не запустился')
                await asyncio.sleep(0.1)
            raise update.UpdateError('Внешний updater не подтвердил готовность')
        except Exception as exc:
            if child is not None:
                stop_child(child)
            progress(self.root, ident, 'failed', error=str(exc))
            if closed:
                launch_spec['reopen']()
            release_lock(self.root)


def recover_pending(root):
    current = status(root)
    lock = Path(root) / '.updates/browser.lock'
    if lock.exists():
        owner = json.loads((lock / 'owner.json').read_text(encoding='utf-8'))
        if current.get('id') != owner.get('id'):
            if not update.process_alive(owner.get('owner')):
                update.recover(root)
                release_lock(root)
            return
    if current['phase'] in TERMINAL:
        if lock.exists() and not update.process_alive(current.get('owner')):
            release_lock(root)
        return
    if not update.process_alive(current.get('owner')):
        update.recover(root)
        progress(root, current.get('id', ''), 'failed', error='Прерванное обновление восстановлено; проверьте версию и повторите')
        release_lock(root)


async def watch_orphan(app, root):
    ident = os.environ.get('MA2_UPDATE_ID')
    if not ident or not re.fullmatch('[0-9a-f]{32}', ident):
        return
    while True:
        await asyncio.sleep(0.3)
        current = status(root)
        if current.get('id') != ident or current['phase'] in TERMINAL:
            continue
        if not update.process_alive(current.get('owner')):
            app.state.updating = True
            app.state.update_hold = None
            folder = Path(root) / '.updates' / ('browser-' + ident) / 'worker'
            try:
                # Replace this uncommitted bridge with the stable worker. Exec closes its sockets;
                # on Windows the worker additionally waits for this exact process to terminate.
                os.execv(sys.executable, [sys.executable, str(folder / 'browser_update.py'),
                                         '--orphan', str(folder / 'job.json'), str(os.getpid())])
            except OSError as exc:
                progress(root, ident, 'failed', error=f'Нужен ручной recovery на ПК: {exc}')
                return


def orphan_worker(spec_path, former_pid):
    spec = json.loads(Path(spec_path).read_text(encoding='utf-8'))
    root, ident = Path(spec['root']), spec['id']
    child = None
    relay = StatusRelay(root, spec['ports'][0])
    try:
        if os.getpid() != former_pid and update.process_alive(former_pid):
            wait_parent(former_pid)()
        tx = json.loads((root / '.updates/active.json').read_text(encoding='utf-8'))
        if tx.get('operation') != ident:
            raise update.UpdateError('Не совпадает транзакция восстановления')
        if tx['phase'] == 'installed':
            tx['phase'] = 'applying'
            update.atomic_json(root / '.updates/active.json', tx)
        update.recover(root)
        progress(root, ident, 'rolling_back', owner=os.getpid(), error='Процесс обновления прервался; возвращена предыдущая программа')
        child = launch(spec)
        spec['child_pid'] = child.pid
        health(spec, update.version(root))
        progress(root, ident, 'rolled_back', version=update.version(root))
    except Exception as exc:
        stop_child(child)
        progress(root, ident, 'failed', error=f'Восстановление прерванного обновления: {exc}')
        relay.start()
        relay.delivered.wait(timeout=180)
        relay.stop()
    finally:
        release_lock(root)


def register(app, root, is_loopback, gate, reopen, stop, health_info, launch_spec, busy):
    from fastapi import Request
    from fastapi.responses import JSONResponse
    manager = Updater(root)
    app.state.updater = manager

    def local(request, mutate=False):
        try:
            origin = urllib.parse.urlsplit(request.headers.get('origin', ''))
            host = urllib.parse.urlsplit('http://' + request.headers.get('host', ''))
            good_origin = not request.headers.get('origin') or (origin.scheme in ('http', 'https')
                and origin.netloc == host.netloc and not (origin.path or origin.query or origin.fragment or origin.username))
            return (is_loopback(request) and host.hostname in ('localhost', '127.0.0.1', '::1') and good_origin
                    and (not mutate or request.headers.get('x-update') == '1'))
        except ValueError:
            return False

    def denied():
        return JSONResponse({'ok': False, 'err': 'Откройте настройки через localhost на самом ПК моста'}, status_code=403)

    @app.get('/api/update/health')
    def update_health():
        return health_info()

    @app.get('/api/update/status')
    def update_status(request: Request):
        if not local(request):
            return denied()
        return {'ok': True, 'current': update.version(root), **status(root)}

    @app.post('/api/update/check')
    async def check_update(request: Request):
        if not local(request, True):
            return denied()
        try:
            info = await asyncio.to_thread(latest)
            return {'ok': True, 'current': update.version(root), 'available': info,
                    'compatible_installation': (Path(root) / 'runtime.json').is_file()}
        except Exception as exc:
            return JSONResponse({'ok': False, 'err': str(exc)}, status_code=502)

    @app.get('/api/update/idle')
    def updater_idle(request: Request):
        if not local(request):
            return denied()
        return {'idle': not busy(), 'pid': os.getpid()}

    @app.post('/api/update/quiesce')
    async def quiesce(request: Request):
        if not local(request, True):
            return denied()
        if not launch_spec() or not await gate():
            return JSONResponse({'ok': False, 'err': 'Панель занята; остановка отменена'}, status_code=409)
        stop()
        return {'ok': True, 'pid': os.getpid()}

    @app.post('/api/update/start')
    async def start_update(request: Request):
        if not local(request, True):
            return denied()
        spec = launch_spec()
        if not spec:
            return JSONResponse({'ok': False, 'err': 'Обновление доступно в обычном запуске моста'}, status_code=409)
        return {'ok': True, **manager.begin(gate, stop, {**spec, 'reopen': reopen})}


if __name__ == '__main__':
    if sys.argv[1:2] == ['--orphan']:
        orphan_worker(sys.argv[2], int(sys.argv[3]))
    else:
        worker(sys.argv[1])
