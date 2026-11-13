"""Local browser updates. The detached stdlib worker survives bridge shutdown."""
import asyncio
import hashlib
import json
import os
import platform
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
import zipfile

if __package__:
    from . import release, update, release_quality
else:
    # Detached workers run with embedded Python, which may omit this directory.
    import importlib.util
    for _name in ('release', 'update', 'release_quality'):
        _spec = importlib.util.spec_from_file_location(_name, Path(__file__).with_name(_name + '.py'))
        _module = importlib.util.module_from_spec(_spec)
        sys.modules[_name] = _module
        _spec.loader.exec_module(_module)
        globals()[_name] = _module

REPO = 'coldmoth/ma2-panel'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
TERMINAL = {'idle', 'completed', 'rolled_back', 'failed'}
TRUSTED_HOSTS = {'api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}


def trusted_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc not in TRUSTED_HOSTS
            or parsed.username or parsed.fragment):
        raise update.UpdateError('Недопустимый HTTPS-источник обновления')


class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        trusted_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(request, timeout):
    trusted_url(request.full_url)
    return urllib.request.build_opener(GitHubRedirect()).open(request, timeout=timeout)


def supported_platform():
    return sys.platform == 'win32' and platform.machine().lower() in ('amd64', 'x86_64') and sys.maxsize > 2**32


def version_key(value):
    # Normalize historical Python spellings, then apply SemVer 2 precedence.
    if not isinstance(value, str):
        raise update.UpdateError('Неизвестный формат версии')
    value = re.sub(r'^(v?\d+\.\d+\.\d+)(rc|beta|b)(\d+)(?=\+|$)',
                   lambda m: m[1] + '-' + ('beta' if m[2] == 'b' else m[2]) + '.' + m[3], value)
    ident = r'[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*'
    match = re.fullmatch(r'v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(' + ident + r'))?(?:\+' + ident + r')?', value)
    if not match:
        raise update.UpdateError('Неизвестный формат версии; нужна проверка полного комплекта')
    parts = (match[4] or '').split('.') if match[4] else []
    if any(p.isdigit() and len(p) > 1 and p[0] == '0' for p in parts):
        raise update.UpdateError('Недопустимый номер предварительной версии')
    return (*map(int, match.group(1, 2, 3)), not parts,
            tuple((0, int(p)) if p.isdigit() else (1, p) for p in parts))


def newer(candidate, current):
    return version_key(candidate) > version_key(current)


def download(url, path, limit):
    request = urllib.request.Request(url, headers={'User-Agent': 'ma2-panel-updater', 'Accept': 'application/octet-stream'})
    deadline = time.monotonic() + 120
    with _open(request, timeout=20) as response, Path(path).open('wb') as stream:
        total = 0
        while chunk := response.read1(65536):
            total += len(chunk)
            if time.monotonic() > deadline:
                raise update.UpdateError('Истекло время скачивания обновления')
            if total > limit:
                raise update.UpdateError('Файл обновления слишком большой')
            stream.write(chunk)


def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'ma2-panel-updater', 'Accept': 'application/vnd.github+json'})
    try:
        deadline = time.monotonic() + 30
        with _open(request, timeout=15) as response:
            parts, size = [], 0
            while chunk := response.read1(65536):
                size += len(chunk)
                if size > 2 * 1024 * 1024:
                    raise update.UpdateError('Слишком большой ответ GitHub')
                if time.monotonic() > deadline:
                    raise update.UpdateError('Истекло время проверки GitHub')
                parts.append(chunk)
        return json.loads(b''.join(parts))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise update.UpdateError('Опубликованных релизов пока нет') from exc
        if exc.code in (403, 429):
            raise update.UpdateError('GitHub временно ограничил запросы; повторите позже') from exc
        raise update.UpdateError(f'GitHub: HTTP {exc.code}') from exc


def release_info(data):
    tag = data.get('tag_name')
    test = not version_key(tag)[3]
    records = data.get('assets')
    if not isinstance(records, list) or any(not isinstance(a, dict) or not isinstance(a.get('name'), str)
                                             or not isinstance(a.get('browser_download_url'), str) for a in records):
        raise update.UpdateError('Неверные метаданные GitHub-релиза')
    assets = {a['name']: a['browser_download_url'] for a in records}
    if len(assets) != len(records):
        raise update.UpdateError('Повторные файлы релиза')
    proof_name = 'quality.json' if test else release_quality.NAME
    names = ('ma2-panel-update.zip', 'ma2-panel-update.zip.sha256', proof_name)
    if not all(name in assets for name in names):
        raise update.UpdateError('В релизе нет комплекта обновления, SHA256 или свидетельства качества')
    for name in names:
        parsed = urllib.parse.urlsplit(assets[name])
        if parsed.scheme != 'https' or parsed.netloc != 'github.com' or parsed.path != f'/{REPO}/releases/download/{tag}/{name}' or parsed.query or parsed.fragment:
            raise update.UpdateError('Недопустимый источник обновления')
    try:
        authenticate = release_quality.authenticate_candidate if test else release_quality.authenticate
        quality = authenticate(fetch_json(assets[proof_name]), tag, REPO, fetch_json)
        commit = fetch_json(f'https://api.github.com/repos/{REPO}/commits/{tag}')
        if not isinstance(commit, dict) or commit.get('sha') != quality['source_sha']:
            raise ValueError('Тег указывает на другой SHA')
    except (ValueError, TypeError, KeyError) as exc:
        raise update.UpdateError('Свидетельство качества не подтверждено: ' + str(exc)) from exc
    notes = data.get('body') or ''
    if not isinstance(notes, str):
        raise update.UpdateError('Неверное описание релиза')
    return {'version': tag, 'url': assets[names[0]], 'checksum_url': assets[names[1]], 'notes': notes[:8000], 'quality': quality}


def latest(include_test=False, current=None, runtime=None):
    if include_test:
        records = []
        for page in range(1, 11):
            batch = fetch_json(API.removesuffix('/latest') + f'?per_page=100&page={page}')
            if not isinstance(batch, list):
                raise update.UpdateError('Неверный список релизов GitHub')
            records.extend(batch)
            if len(batch) < 100:
                break
        else:
            raise update.UpdateError('Список релизов слишком большой; проверка не завершена')
    else:
        records = [fetch_json(API)]
    eligible = []
    for data in records:
        if not isinstance(data, dict) or data.get('draft') is not False or type(data.get('prerelease')) is not bool:
            continue
        tag = data.get('tag_name')
        try:
            key = version_key(tag)
        except update.UpdateError:
            continue
        test = not key[3]
        # GitHub tags are canonical; legacy spellings are only accepted in VERSION.
        if not re.fullmatch(r'v?\d+\.\d+\.\d+(?:-(?:rc|beta)\.(?:0|[1-9][0-9]*))?', tag):
            continue
        if data['prerelease'] != test or (test and not include_test):
            continue
        if current is None or newer(tag, current):
            eligible.append(data)
    errors = []
    for data in sorted(eligible, key=lambda d: version_key(d['tag_name']), reverse=True):
        try:
            info = release_info(data)
            if runtime is not None and info['quality'].get('runtime') != runtime:
                continue
            return info
        except update.UpdateError as exc:
            errors.append(exc)
    if errors:
        raise errors[0]
    if current is None:
        raise update.UpdateError('Нет подходящего опубликованного релиза')
    return None


def test_updates(settings_path):
    from .safety import read_settings_pair
    settings, _, _ = read_settings_pair(Path(settings_path))
    return settings.get('test_updates') is True


def verify_quality(info, archive=None):
    tag = info.get('version')
    test = not version_key(tag)[3]
    authenticate = release_quality.authenticate_candidate if test else release_quality.authenticate
    proof = authenticate(info.get('quality'), tag, REPO, fetch_json)
    if archive is not None:
        release_quality.verify_archive(archive, proof, tag, candidate=test)
    return proof


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
    if not supported_platform():
        raise update.UpdateError('Онлайн-установка поддерживается только в Windows x64')
    try:
        installed = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
        release.verify_runtime(root)
    except (OSError, ValueError) as exc:
        raise update.UpdateError('Нет сведений о Python/lib. Сначала установите полный Windows-комплект блока Б') from exc
    # Reserve space before network writes, while the bridge remains running.
    need = sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink() and '.updates' not in p.relative_to(root).parts)
    if shutil.disk_usage(root).free < need * 3 + release.MAX_TOTAL * 4 + 16 * 1024 * 1024:
        raise update.UpdateError('Недостаточно свободного места для обновления и копий')
    folder = update.transaction(root) / ('browser-' + ident)
    folder.mkdir()
    archive, checksum = folder / 'update.zip', folder / 'checksum.txt'
    download(info['url'], archive, release.MAX_TOTAL)
    download(info['checksum_url'], checksum, 1024)
    tokens = checksum.read_text(encoding='ascii').split()
    if not tokens or not re.fullmatch('[0-9a-fA-F]{64}', tokens[0]) or hashlib.sha256(archive.read_bytes()).hexdigest() != tokens[0].lower():
        raise update.UpdateError('Контрольная сумма SHA256 не совпадает')
    manifest = release.check(archive, installed)
    try:
        verify_quality(info, archive)
    except (ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        raise update.UpdateError('Свидетельство качества не подтверждено: ' + str(exc)) from exc
    if info.get('version') and (version_key(manifest['version']) != version_key(info['version'])
                               or not newer(info['version'], update.version(root))):
        raise update.UpdateError('Версия пакета не соответствует новому релизу')
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
    executable = sys.executable
    if sys.platform == 'win32' and sys.prefix != sys.base_prefix:
        # CPython 3.12 PC/launcher.c: run the interpreter directly, preserving
        # venv discovery. Popen.pid must identify the actual HTTP process.
        executable = sys._base_executable
        env['__PYVENV_LAUNCHER__'] = sys.executable
    log = (root / '.updates/startup.log').open('ab')
    try:
        return subprocess.Popen([executable, str(root / 'bridge.py'), *spec['args']], cwd=root,
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
    last_report = None

    def record(observed):
        nonlocal last_report
        report = {'expected': {'version': version, 'operation': spec['id'],
                               'pid': spec.get('child_pid')},
                  'ports': spec['ports'], 'worker_pid': os.getpid(), 'observed': observed}
        if report != last_report:
            try:
                update.atomic_json(Path(spec['root']) / '.updates/health.json', report)
                last_report = report
            except OSError:
                pass  # Optional diagnostics cannot decide health or block recovery.

    while time.monotonic() < deadline:
        observed = []
        try:
            for port in spec['ports']:
                entry = {'port': port}
                observed.append(entry)
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/update/health', timeout=2) as response:
                    result = json.load(response)
                entry['result'] = {key: result.get(key) for key in ('version', 'operation', 'pid', 'instance')}
                if (result.get('version') != version or result.get('operation') != spec['id']
                        or (spec.get('child_pid') and result.get('pid') != spec['child_pid'])):
                    raise ValueError('wrong instance')
            record(observed)
            return
        except (OSError, ValueError) as exc:
            entry['error'] = type(exc).__name__
            record(observed)
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
        if 'quality' in spec:
            verify_quality({'quality': spec['quality'], 'version': spec['stable_tag']}, Path(spec['archive']))
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
    def __init__(self, root, select=None):
        self.root = Path(root)
        self.select = select or latest
        self.task = None

    def begin(self, gate, stop, launch_spec, expected_version=None):
        work = update.transaction(self.root)
        ident = uuid.uuid4().hex
        if not update.acquire_lock(self.root, ident):
            return status(self.root)
        progress(self.root, ident, 'downloading', owner=os.getpid(), error='')
        self.task = asyncio.create_task(self._run(ident, gate, stop, launch_spec, expected_version))
        return status(self.root)

    async def _run(self, ident, gate, stop, launch_spec, expected_version):
        closed = False
        child = None
        try:
            info = await asyncio.to_thread(self.select)
            if info is None:
                raise update.UpdateError('Новых обновлений в выбранном канале нет')
            if expected_version is not None and info['version'] != expected_version:
                raise update.UpdateError('Релиз изменился. Повторите проверку и подтвердите новую версию')
            archive, manifest = await asyncio.to_thread(prepare, self.root, ident, info)
            progress(self.root, ident, 'validated', version=manifest['version'])
            if not await gate():
                raise update.UpdateError('Панель занята. Дождитесь окончания действий и повторите')
            closed = True
            folder = archive.parent / 'worker'
            folder.mkdir()
            for name in ('browser_update.py', 'update.py', 'release.py', 'release_quality.py'):
                shutil.copy2(Path(__file__).parent / name, folder / name)
            spec = {**{k: v for k, v in launch_spec.items() if k != 'reopen'}, 'id': ident, 'root': str(self.root), 'parent_pid': os.getpid(),
                    'archive': str(archive), 'version': manifest['version'],
                    **({'quality': info['quality'], 'stable_tag': info['version']} if info.get('quality') else {})}
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
                args = [sys.executable, str(folder / 'browser_update.py'),
                        '--orphan', str(folder / 'job.json'), str(os.getpid())]
                if sys.platform == 'win32':
                    # Popen quotes Windows paths. The CRT execv would split the
                    # Unicode/spaced worker path; exit only after a successful spawn.
                    with (Path(root) / '.updates/startup.log').open('ab') as log:
                        subprocess.Popen(args, cwd=folder, stdin=subprocess.DEVNULL,
                                         stdout=log, stderr=log,
                                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
                    os._exit(0)  # close both HTTP listeners; orphan waits for this exact PID
                else:
                    os.execv(sys.executable, args)
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


def register(app, root, is_loopback, gate, reopen, stop, health_info, launch_spec, busy, settings_path=None):
    from fastapi import Request
    from fastapi.responses import JSONResponse
    from .safety import read_settings_pair, save_settings_pair
    settings_path = Path(settings_path) if settings_path is not None else Path(root) / 'settings.json'
    def select():
        runtime_path = Path(root) / 'runtime.json'
        runtime = json.loads(runtime_path.read_text(encoding='utf-8')) if runtime_path.is_file() else None
        return latest(include_test=test_updates(settings_path), current=update.version(root), runtime=runtime)
    manager = Updater(root, select)
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

    @app.get('/api/update/channel')
    def update_channel(request: Request):
        if not local(request):
            return denied()
        return {'ok': True, 'test_updates': test_updates(settings_path)}

    @app.post('/api/update/channel')
    async def set_update_channel(request: Request):
        if not local(request, True):
            return denied()
        try:
            body = await request.json()
            if not isinstance(body, dict) or set(body) != {'test_updates'} or type(body['test_updates']) is not bool:
                raise ValueError('Требуется test_updates: bool')
            if status(root).get('phase') not in TERMINAL or (Path(root) / '.updates/browser.lock').exists():
                return JSONResponse({'ok': False, 'err': 'Дождитесь завершения обновления'}, status_code=409)
            stored, _, _ = read_settings_pair(settings_path)
            save_settings_pair(settings_path, {**stored, 'test_updates': body['test_updates']}, None)
            return {'ok': True, 'test_updates': body['test_updates']}
        except (ValueError, OSError) as exc:
            return JSONResponse({'ok': False, 'err': str(exc)}, status_code=400)

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
            info = await asyncio.to_thread(select)
            current = update.version(root)
            return {'ok': True, 'current': current, 'available': info,
                    'compatible_installation': supported_platform() and (Path(root) / 'runtime.json').is_file()}
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
        try:
            chosen = (await request.json())['version']
            if not isinstance(chosen, str) or not newer(chosen, update.version(root)):
                raise ValueError()
        except (ValueError, KeyError, TypeError, update.UpdateError):
            return JSONResponse({'ok': False, 'err': 'Сначала проверьте и выберите новую версию'}, status_code=400)
        if not supported_platform():
            return JSONResponse({'ok': False, 'err': 'Нужен Windows x64'}, status_code=409)
        spec = launch_spec()
        if not spec:
            return JSONResponse({'ok': False, 'err': 'Обновление доступно в обычном запуске моста'}, status_code=409)
        # Observe the previous terminal operation before begin replaces its ID.
        # This releases the restarted bridge's admission hold, and refuses busy work.
        if busy():
            return JSONResponse({'ok': False, 'err': 'Панель занята. Дождитесь окончания действий и повторите'}, status_code=409)
        return {'ok': True, **manager.begin(gate, stop, {**spec, 'reopen': reopen}, chosen)}


if __name__ == '__main__':
    if sys.argv[1:2] == ['--orphan']:
        orphan_worker(sys.argv[2], int(sys.argv[3]))
    else:
        worker(sys.argv[1])
