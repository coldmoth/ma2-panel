"""Explicit, local-network application updates; uses only the Python stdlib."""
import hashlib
import functools
import errno
import json
import os
import uuid
import re
import shutil
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


class UpdateError(Exception):
    pass


def allowed(name):
    if '\\' in name or ':' in name:
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        return False
    if name == 'program-manifest.json' or name == 'CHANGELOG.md':
        return True
    if path.parts[0] in ('static', 'docs'):
        return True
    return len(path.parts) == 1 and (name in ('VERSION', 'README-RU.md') or path.suffix in ('.py', '.bat'))


def validate_zip(archive):
    with zipfile.ZipFile(archive) as candidate:
        for item in candidate.infolist():
            # Windows zipfile normalizes backslashes; NUL names are truncated.
            # Reject changed raw names before either legacy or manifest validation.
            if item.orig_filename != item.filename:
                raise UpdateError(f'Недопустимый файл обновления: {item.orig_filename!r}')
        if 'program-manifest.json' in candidate.namelist():
            import release
            try:
                return release.check(archive)['version']
            except ValueError as exc:
                raise UpdateError(str(exc)) from exc
    with zipfile.ZipFile(archive) as z:
        names = set()
        for item in z.infolist():
            name = item.filename.rstrip('/')
            mode = item.external_attr >> 16
            if not allowed(name) or stat.S_ISLNK(mode):
                raise UpdateError(f'Недопустимый файл обновления: {item.filename}')
            key = name.casefold()
            if key in names:
                raise UpdateError(f'Повторный файл: {name}')
            names.add(key)
        for required in ('bridge.py', 'VERSION'):
            if required not in z.namelist() or z.getinfo(required).is_dir():
                raise UpdateError(f'В обновлении отсутствует {required}')
        # Read now, so damaged archives fail before the bridge is stopped.
        if z.testzip() is not None:
            raise UpdateError('Повреждён архив обновления')
        return z.read('VERSION').decode('utf-8-sig').strip()


def normalize_url(value):
    value = value.strip()
    if '://' not in value:
        value = 'http://' + value
    if urllib.parse.urlsplit(value).path in ('', '/'):
        value = value.rstrip('/') + '/ma2-panel-update.zip'
    if urllib.parse.urlsplit(value).scheme not in ('http', 'https'):
        raise UpdateError('Нужен адрес HTTP или HTTPS')
    return value


def download(url, directory):
    archive = Path(directory) / 'update.zip'
    with urllib.request.urlopen(url, timeout=15) as response:
        archive.write_bytes(response.read())
    with urllib.request.urlopen(url + '.sha256', timeout=15) as response:
        tokens = response.read().decode('ascii').split()
    digest = tokens[0] if tokens else ''
    if not re.fullmatch(r'[0-9a-fA-F]{64}', digest) or hashlib.sha256(archive.read_bytes()).hexdigest() != digest.lower():
        raise UpdateError('Контрольная сумма SHA256 не совпадает')
    return archive


def settings(root):
    path = Path(root) / 'settings.json'
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}


def version(root):
    path = Path(root) / 'VERSION'
    return path.read_text(encoding='utf-8-sig').strip() if path.exists() else 'неизвестно'


def idle(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/update/idle', timeout=3) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise UpdateError(f'Не удалось проверить состояние моста: {exc}') from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None


def prepare_bridge(port, old, new, confirm=input, wait_seconds=15):
    state = idle(port)
    if state is not None and state.get('idle') is not True:
        print('Идёт передача команд на пульт: обновление отменено. Повторите, когда панель не используется.')
        return 2
    print(f'{old} -> {new}')
    if confirm('Остановить мост и обновить? (y/n) ').strip().lower() not in ('y', 'д'):
        return -1
    state = idle(port)  # confirmation may have taken arbitrarily long
    if state is not None:
        request = urllib.request.Request(f'http://127.0.0.1:{port}/api/update/quiesce', data=b'', headers={'X-Update': '1'}, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=3):
                pass
        except urllib.error.HTTPError as exc:
            print(f'Мост не разрешил остановку (HTTP {exc.code}); для старой версии сначала запустите stop.bat.')
            return 2
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass  # Check process termination even if the response was lost.
        deadline = time.monotonic() + wait_seconds
        while (process_alive(state['pid']) if type(state.get('pid')) is int else idle(port) is not None):
            if time.monotonic() >= deadline:
                print('Мост не остановился: обновление отменено.')
                return 2
            time.sleep(0.2)
    return 0


def local_archive(path, directory):
    """An update zip from a USB stick; a .sha256 next to it is checked when present."""
    archive = Path(directory) / 'update.zip'
    shutil.copy2(path, archive)
    sidecar = Path(str(path) + '.sha256')
    if sidecar.exists():
        tokens = sidecar.read_text(encoding='ascii').split()
        if not tokens or hashlib.sha256(archive.read_bytes()).hexdigest() != tokens[0].lower():
            raise UpdateError('Контрольная сумма SHA256 не совпадает')
    return archive


USER_DATA = ('config.json', 'settings.json', 'secret.env', 'highlight.json', 'rdm-search.json', 'update_url.txt', 'shows', 'diagnostic-upload.json', 'diag', 'field-data')


def backup_user_data(root):
    """Copies this panel's own data before an update; MA2 files are never touched. Returns the folder."""
    folder = root / 'backups' / f"before-update-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    folder.mkdir(parents=True, exist_ok=False, mode=0o700)
    if os.name == 'nt':
        import csv
        import io
        import subprocess
        identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, text=True, check=True)
        sid = next(csv.reader(io.StringIO(identity.stdout)))[1]
        if not re.fullmatch(r'S-1-(?:\d+-)*\d+', sid):
            raise UpdateError('Не удалось ограничить доступ к копии данных')
        subprocess.run(['icacls', str(folder), '/inheritance:r', '/grant:r', f'*{sid}:(OI)(CI)F'],
                       capture_output=True, check=True)
    else:
        os.chmod(folder, 0o700)
    for name in USER_DATA:
        source = root / name
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, folder / name)
        elif source.is_file():
            shutil.copy2(source, folder / name)
    sync_tree(folder)
    sync_directory(folder.parent)
    return folder


def remove(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def sync_directory(path):
    if sys.platform != 'win32':
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def sync_tree(path):
    path = Path(path)
    if path.is_symlink():
        raise UpdateError('Символическая ссылка при фиксации файлов')
    if path.is_dir():
        for item in path.iterdir():
            sync_tree(item)
        sync_directory(path)
    else:
        with path.open('r+b') as stream:
            os.fsync(stream.fileno())


def durable_replace(source, target):
    source, target = Path(source), Path(target)
    if sys.platform == 'win32':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.MoveFileExW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        if not kernel.MoveFileExW(str(source), str(target), 0x1 | 0x8):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.replace(source, target)
        sync_directory(target.parent)
        if source.parent != target.parent:
            sync_directory(source.parent)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    durable_replace(temp, path)


def copy_entry(source, target):
    if source.is_symlink() or (source.is_dir() and any(p.is_symlink() for p in source.rglob('*'))):
        raise UpdateError('Символическая ссылка в программе')
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)
    sync_tree(target)
    sync_directory(target.parent)


def safe_targets(names):
    if not isinstance(names, list) or len(names) != len(set(names)):
        raise UpdateError('Повреждён список файлов транзакции')
    for name in names:
        if not isinstance(name, str) or '/' in name or not allowed(name):
            raise UpdateError('Недопустимая цель транзакции')
    return names


def snapshot_meta(folder, targets, present):
    hashes = {}
    for path in folder.rglob('*'):
        if path.is_symlink():
            raise UpdateError('Символическая ссылка в снимке')
        if path.is_file():
            hashes[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'targets': sorted(targets), 'present': sorted(present), 'hashes': hashes}


def check_snapshot(folder, meta):
    targets = safe_targets(meta['targets'])
    present = safe_targets(meta['present'])
    if not set(present) <= set(targets):
        raise UpdateError('Повреждён снимок программы')
    actual = snapshot_meta(folder, targets, present)
    # Metadata lives beside the snapshot, never inside its checked file set.
    if actual['hashes'] != meta['hashes'] or sorted(p.name for p in folder.iterdir()) != sorted(present):
        raise UpdateError('Контрольная сумма снимка программы не совпадает')
    return targets, present


def restore_snapshot(root, folder, meta):
    targets, present = check_snapshot(folder, meta)
    if any((root / name).is_symlink() for name in targets):
        raise UpdateError('Символическая ссылка в папке приложения')
    for name in targets:
        remove(root / name)
        if name in present:
            copy_entry(folder / name, root / name)
    sync_directory(root)  # removals of snapshot-absent targets must also be durable


def transaction(root):
    work = root / '.updates'
    if work.is_symlink():
        raise UpdateError('Символическая ссылка в каталоге обновления')
    work.mkdir(exist_ok=True)
    sync_directory(root)
    return work


def process_alive(pid):
    if type(pid) is not int or pid <= 0:
        return False
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # access denied does not prove death
        try:
            return kernel.WaitForSingleObject(handle, 0) != 0
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def recover(root):
    """Restore an interrupted replacement before the bridge opens any interfaces."""
    root = Path(root)
    work = transaction(root)
    active = work / 'active.json'
    if not active.exists():
        return
    try:
        tx = json.loads(active.read_text(encoding='utf-8'))
        if not re.fullmatch(r'[0-9a-f]{32}', tx['id']):
            raise ValueError('id')
        if tx['phase'] in ('recovered', 'rolled_back'):
            return
        if tx['phase'] == 'installed':
            state_path = work / 'browser-state.json'
            state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
            pending = (tx.get('operation') and tx.get('operation') == state.get('id')
                       and state.get('phase') not in ('completed', 'rolled_back', 'failed', 'idle'))
            if not pending or process_alive(state.get('owner')):
                return
            # Installed is not committed until the browser worker records successful health.
            tx['phase'] = 'applying'
        if tx['phase'] not in ('applying', 'restoring'):
            raise ValueError('phase')
        folder = work / tx['id']
        if folder.is_symlink() or (folder / 'backup').is_symlink():
            raise ValueError('symlink')
        restore_snapshot(root, folder / 'backup', tx['snapshot'])
        if tx.get('publishing'):
            previous = root / 'previous'
            if (folder / 'older-previous').exists():
                remove(previous)
                durable_replace(folder / 'older-previous', previous)
            elif not tx.get('previous_existed'):
                remove(previous)
        tx['phase'] = 'recovered'
        atomic_json(active, tx)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise UpdateError(f'Не удалось восстановить прерванное обновление: {exc}') from exc


def install(archive, root, operation=None):
    root = Path(root)
    validate_zip(archive)
    recover(root)
    work = transaction(root)
    ident = uuid.uuid4().hex
    folder = work / ident
    bootstrap = work / 'recovery.py.tmp'
    shutil.copy2(Path(__file__), bootstrap)
    sync_tree(bootstrap)
    durable_replace(bootstrap, work / 'recovery.py')
    stage = folder / 'stage'
    stage.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        z.extractall(stage)
    sync_tree(stage)
    sync_directory(folder)
    targets = {p.name for p in stage.iterdir()}
    current = root / 'program-manifest.json'
    if current.exists():
        previous_manifest = json.loads(current.read_text(encoding='utf-8'))
        targets.update(PurePosixPath(name).parts[0] for name in previous_manifest['files'])
        targets.add('program-manifest.json')
    targets = safe_targets(sorted(targets))
    previous = root / 'previous'
    if previous.is_symlink() or any((root / name).is_symlink() for name in targets):
        raise UpdateError('Символическая ссылка в папке приложения')
    backup = folder / 'backup'
    backup.mkdir()
    present = [name for name in targets if (root / name).exists()]
    for name in present:
        copy_entry(root / name, backup / name)
    sync_directory(folder)  # persist the backup directory entry before the journal
    meta = snapshot_meta(backup, targets, present)
    tx = {'id': ident, 'phase': 'applying', 'snapshot': meta, 'operation': operation}
    atomic_json(work / 'active.json', tx)
    try:
        for name in targets:
            remove(root / name)
        for source in stage.iterdir():
            copy_entry(source, root / source.name)
        # Prepare the next rollback separately. Retain earlier backups indefinitely.
        rollback_folder = folder / 'next-previous'
        shutil.copytree(backup, rollback_folder / 'program')
        sync_tree(rollback_folder)
        sync_directory(folder)
        atomic_json(rollback_folder / 'rollback.json', meta)
        # Compatibility: expose old VERSION/modules at previous/<name> for CLI/tools.
        for name in present:
            copy_entry(backup / name, rollback_folder / name)
        tx.update(publishing=True, previous_existed=previous.exists())
        atomic_json(work / 'active.json', tx)
        if previous.exists():
            durable_replace(previous, folder / 'older-previous')
        durable_replace(rollback_folder, previous)
        tx['phase'] = 'installed'
        atomic_json(work / 'active.json', tx)
    except Exception:
        recover(root)
        if (folder / 'older-previous').exists():
            remove(previous)
            durable_replace(folder / 'older-previous', previous)
        raise


def acquire_lock(root, ident):
    """Publish an already populated owner directory atomically (also survives pre-status crashes)."""
    work = transaction(Path(root))
    prepared = work / ('lock-' + uuid.uuid4().hex)
    prepared.mkdir()
    atomic_json(prepared / 'owner.json', {'id': ident, 'owner': os.getpid()})
    try:
        os.rename(prepared, work / 'browser.lock')
        sync_directory(work)
        return True
    except OSError as exc:
        remove(prepared)
        if exc.errno in (errno.EEXIST, errno.ENOTEMPTY) or (work / 'browser.lock').exists():
            return False
        raise


def serialized(function):
    @functools.wraps(function)
    def call(root, *args, **kwargs):
        root = Path(root)
        work = transaction(root)
        ident = uuid.uuid4().hex
        if not acquire_lock(root, ident):
            raise UpdateError('Уже идёт обновление или откат; проверьте статус на ПК')
        old = version(root)
        atomic_json(work / 'browser-state.json', {'id': ident, 'phase': 'manual', 'owner': os.getpid()})
        phase, error = 'idle', ''
        try:
            result = function(root, *args, **kwargs)
            phase = 'completed' if result == 0 and version(root) != old else 'idle'
            return result
        except BaseException as exc:
            phase, error = 'failed', str(exc)
            raise
        finally:
            atomic_json(work / 'browser-state.json', {'id': ident, 'phase': phase, 'owner': os.getpid(), 'error': error})
            remove(work / 'browser.lock')
    return call


@serialized

def rollback(root, confirm=input):
    root = Path(root)
    recover(root)
    previous = root / 'previous'
    if not previous.is_dir() or previous.is_symlink():
        raise UpdateError('Предыдущая версия отсутствует')
    try:
        meta = json.loads((previous / 'rollback.json').read_text(encoding='utf-8'))
        check_snapshot(previous / 'program', meta)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise UpdateError('Нет проверенного манифеста отката; нужен прежний комплект') from exc
    old, new = version(root), version(previous)
    result = prepare_bridge(settings(root).get('port', 8080), old, new, confirm)
    if result:
        return max(result, 0)
    work = transaction(root)
    ident = uuid.uuid4().hex
    folder = work / ident
    shutil.copytree(previous / 'program', folder / 'backup')
    sync_tree(folder)
    sync_directory(work)
    tx = {'id': ident, 'phase': 'restoring', 'snapshot': meta}
    atomic_json(work / 'active.json', tx)
    restore_snapshot(root, folder / 'backup', meta)
    tx['phase'] = 'rolled_back'
    atomic_json(work / 'active.json', tx)
    print(f'Восстановлено: {old} -> {new}. Запустите start.bat.')
    return 0


@serialized
def run(root, url=None, confirm=input):
    root = Path(root)
    cfg = settings(root)
    saved = root / 'update_url.txt'  # the updater's own file: settings.json is never written by an update
    remembered = saved.read_text(encoding='utf-8').strip() if saved.exists() else ''
    entered = url is not None or not remembered
    beside = root / 'ma2-panel-update.zip'  # copied here from a USB stick
    if url is None and beside.is_file():
        url, entered = str(beside), False
    local = url is not None and Path(url).is_file()
    if not local:
        url = normalize_url(url or remembered or confirm('Адрес Mac, например 192.168.0.20:8765: '))
    with tempfile.TemporaryDirectory() as temp:
        archive = local_archive(url, temp) if local else download(url, temp)
        new = validate_zip(archive)
        with zipfile.ZipFile(archive) as package:
            if 'program-manifest.json' in package.namelist():
                import release
                try:
                    installed = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
                    release.verify_runtime(root)
                    release.check(archive, installed)
                except (OSError, ValueError) as exc:
                    raise UpdateError('Несовместимый или неподтверждённый Python/lib; нужен полный комплект') from exc
        old = version(root)
        result = prepare_bridge(cfg.get('port', 8080), old, new, confirm)
        if result:
            return max(result, 0)
        print(f'Данные панели сохранены в {backup_user_data(root)}')
        install(archive, root)
    if entered and not local:
        saved.write_text(url + '\n', encoding='utf-8')
    message = f'Обновлено: {old} -> {new}. Запустите start.bat.'
    print(message)
    with (root / 'update.log').open('a', encoding='utf-8') as log:
        log.write(message + '\n')
    return 0


def main():
    # Pipes/BAT and isolated embedded Python may default to cp1252 on Windows.
    # Keep Russian diagnostics intact and tolerate unpaired filesystem surrogates.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    try:
        if sys.argv[1:2] == ['--recover'] and len(sys.argv) == 3:
            recover(Path(sys.argv[2]))
            return 0
        import argparse
        parser = argparse.ArgumentParser(description='Обновление панели')
        parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent,
                            help='папка установленной программы (с python/ и start.bat)')
        parser.add_argument('--rollback', action='store_true')
        parser.add_argument('source', nargs='?')
        args = parser.parse_args()
        root = args.root.resolve()
        if not root.is_dir():
            raise UpdateError('Папка установки не найдена')
        return rollback(root) if args.rollback else run(root, args.source)
    except Exception as exc:
        print(f'Обновление не выполнено: {exc}')
        return 1


if __name__ == '__main__':
    # Embedded Windows Python's _pth can omit the external script directory.
    # Always pair this updater with release.py from the same staging folder.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
