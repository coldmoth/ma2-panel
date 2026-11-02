"""Explicit, local-network application updates; uses only the Python stdlib."""
import hashlib
import json
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
    if path.parts[0] in ('static', 'docs'):
        return True
    return len(path.parts) == 1 and (name in ('VERSION', 'README-RU.md') or path.suffix in ('.py', '.bat'))


def validate_zip(archive):
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
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/idle', timeout=3) as response:
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
    if state is not None:
        request = urllib.request.Request(f'http://127.0.0.1:{port}/api/stop', data=b'', headers={'X-Stop': '1'}, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=3):
                pass
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass  # The process may exit before writing its response.
        deadline = time.monotonic() + wait_seconds
        while idle(port) is not None:
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


USER_DATA = ('config.json', 'settings.json', 'secret.env', 'highlight.json', 'update_url.txt', 'shows')


def backup_user_data(root):
    """Copies this panel's own data before an update; MA2 files are never touched. Returns the folder."""
    folder = root / 'backups' / f"before-update-{time.strftime('%Y%m%d-%H%M%S')}"
    folder.mkdir(parents=True, exist_ok=True)
    for name in USER_DATA:
        source = root / name
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, folder / name)
        elif source.is_file():
            shutil.copy2(source, folder / name)
    return folder


def remove(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def install(archive, root):
    root = Path(root)
    validate_zip(archive)
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp)
        with zipfile.ZipFile(archive) as z:
            z.extractall(stage)
        targets = sorted(p.name for p in stage.iterdir())
        # static and docs are replaced as complete folders when present.
        for name in targets:
            if (root / name).is_symlink():
                raise UpdateError(f'Символическая ссылка в папке приложения: {name}')
        previous = root / 'previous'
        remove(previous)
        previous.mkdir()
        moved, installed = [], []
        try:
            for name in targets:
                if (root / name).exists():
                    shutil.move(str(root / name), str(previous / name))
                    moved.append(name)
            for name in targets:
                installed.append(name)
                source = stage / name
                if source.is_dir():
                    shutil.copytree(source, root / name)
                else:
                    shutil.copy2(source, root / name)
        except Exception:
            for name in installed:
                remove(root / name)
            for name in moved:
                shutil.move(str(previous / name), str(root / name))
            raise


def rollback(root, confirm=input):
    root = Path(root)
    previous = root / 'previous'
    if not previous.is_dir() or previous.is_symlink():
        raise UpdateError('Предыдущая версия отсутствует')
    entries = list(previous.rglob('*'))
    if any(p.is_symlink() or not allowed(p.relative_to(previous).as_posix()) for p in entries):
        raise UpdateError('Недопустимые файлы в previous')
    if any((root / p.relative_to(previous)).is_symlink() for p in entries):
        raise UpdateError('Символическая ссылка в папке приложения')
    old, new = version(root), version(previous)
    result = prepare_bridge(settings(root).get('port', 8080), old, new, confirm)
    if result:
        return max(result, 0)
    for source in previous.iterdir():
        target = root / source.name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
    print(f'Восстановлено: {old} -> {new}. Запустите start.bat.')
    return 0


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
    try:
        root = Path(__file__).resolve().parent
        return rollback(root) if sys.argv[1:] == ['--rollback'] else run(root, sys.argv[1] if len(sys.argv) > 1 else None)
    except Exception as exc:
        print(f'Обновление не выполнено: {exc}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
