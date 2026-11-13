"""Explicit private backup/restore; source kept, legacy paths unchanged. Stop bridge first."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile
import unicodedata

from .update import USER_DATA, sync_directory

ROOTS = frozenset((*USER_DATA, 'backups', 'previous', '.updates', '.settings-transaction.json'))
DIRECTORIES = {'shows', 'diag', 'field-data', 'backups', 'previous', '.updates'}
MAX_FILE, MAX_TOTAL, MAX_FILES = 64 * 1024 * 1024, 512 * 1024 * 1024, 10000


def _linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def _files(path):
    if _linked(path): raise ValueError('Ссылка или junction в данных.')
    if path.is_dir():
        for child in sorted(path.iterdir()): yield from _files(child)
    elif path.exists(): yield path


def _private(folder):
    os.chmod(folder, 0o700)
    if os.name == 'nt':
        import csv
        import io
        import subprocess
        result = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, text=True, check=True)
        sid = next(csv.reader(io.StringIO(result.stdout)))[1]
        if not re.fullmatch(r'S-1-(?:\d+-)*\d+', sid):
            raise ValueError('Не удалось ограничить доступ к копии.')
        subprocess.run(['icacls', str(folder), '/inheritance:r', '/grant:r', f'*{sid}:(OI)(CI)F'], capture_output=True, check=True)


def _root(path):
    path = Path(path).absolute()
    if any(_linked(p) for p in (path, *path.parents)):
        raise ValueError('Символические ссылки не разрешены.')
    return path


def _name(name):
    p = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or p.is_absolute() or p.as_posix() != name
            or any(n in ('', '.', '..') or n.endswith(('.', ' ')) or any(ord(c) < 32 or ord(c) == 127 or c in '<>"|?*' for c in n)
                   or re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', n, re.I) for n in p.parts)
            or p.parts[0] not in ROOTS
            or (p.parts[0] in DIRECTORIES) != (len(p.parts) > 1)):
        raise ValueError('Недопустимый путь в архиве.')
    return p


def _settled(root):
    if (root / '.data-transfer.lock').exists():
        raise ValueError('Предыдущий перенос не завершён. Сохраните архив и источник; восстановите в новую пустую установку.')
    if (root / '.settings-transaction.json').exists():
        raise ValueError('Сначала завершите восстановление настроек.')
    active = root / '.updates/active.json'
    if active.exists():
        try:
            tx = json.loads(active.read_text(encoding='utf-8'))
            phase = tx['phase']
        except (ValueError, KeyError, TypeError):
            raise ValueError('Неизвестное состояние recovery; источник сохранён.') from None
        settled = phase in ('recovered', 'rolled_back') or phase == 'installed' and not tx.get('operation')
        if phase == 'installed' and tx.get('operation'):
            try:
                browser = json.loads((root / '.updates/browser-state.json').read_text(encoding='utf-8'))
                settled = browser.get('id') == tx['operation'] and browser.get('phase') == 'completed'
            except (OSError, ValueError, TypeError):
                settled = False
        if not settled:
            raise ValueError('Сначала завершите recovery/rollback обновления.')
    if (root / '.updates/browser.lock').exists():
        raise ValueError('Обновление занято; не переносите активную установку.')


def backup(source, archive, *, confirmed_stopped=False):
    if not confirmed_stopped:
        raise ValueError('Подтвердите остановку моста: --confirm-stopped.')
    source, archive = _root(source), _root(archive)
    if not source.is_dir() or archive.exists() or archive.is_relative_to(source):
        raise ValueError('Нужна исходная установка и новый архив вне неё.')
    _settled(source)
    files = {}
    total = 0
    for top in sorted(ROOTS):
        entry = source / top
        if _linked(entry):
            raise ValueError('Символическая ссылка в данных.')
        paths = _files(entry)
        for path in paths:
            if _linked(path):
                raise ValueError('Символическая ссылка в данных.')
            if path.is_dir():
                continue
            if not path.is_file() or path.stat().st_size > MAX_FILE:
                raise ValueError('Неподдерживаемый файл или превышен размер.')
            name = path.relative_to(source).as_posix(); _name(name)
            data = path.read_bytes(); total += len(data)
            if total > MAX_TOTAL or len(files) >= MAX_FILES:
                raise ValueError('Превышен размер копии.')
            files[name] = data
    if not files: raise ValueError('В исходном каталоге нет пользовательских данных.')
    manifest = {'schema': 1, 'private': True, 'files': {n: {'size': len(d), 'sha256': hashlib.sha256(d).hexdigest()} for n, d in files.items()}}
    # A private subdirectory protects credentials on Windows as well as POSIX.
    with tempfile.TemporaryDirectory(prefix='ma2-private-', dir=archive.parent) as temp:
        folder = Path(temp); _private(folder)
        staged = folder / 'data.zip'
        with zipfile.ZipFile(staged, 'w', zipfile.ZIP_DEFLATED) as z:
            for name, data in files.items(): z.writestr(name, data)
            z.writestr('transfer-manifest.json', json.dumps(manifest, ensure_ascii=False))
        inspect(staged)
        with staged.open('rb') as stream: os.fsync(stream.fileno())
        os.chmod(staged, 0o600)
        # Atomic no-overwrite publication; failure leaves no partial destination.
        os.link(staged, archive)
        sync_directory(archive.parent)
    return manifest


def inspect(archive):
    with zipfile.ZipFile(_root(archive)) as z:
        items = z.infolist()
        names = [i.filename for i in items]
        if len(names) > MAX_FILES + 1 or len(set(unicodedata.normalize('NFC', n).casefold() for n in names)) != len(names):
            raise ValueError('Дублирующиеся или слишком многочисленные файлы.')
        total = 0
        for item in items:
            if item.filename != 'transfer-manifest.json': _name(item.filename)
            if item.is_dir() or stat.S_ISLNK(item.external_attr >> 16) or item.file_size > MAX_FILE:
                raise ValueError('Недопустимый файл архива.')
            total += item.file_size
        if total > MAX_TOTAL or 'transfer-manifest.json' not in names:
            raise ValueError('Нет манифеста или превышен размер.')
        manifest = json.loads(z.read('transfer-manifest.json'))
        if not isinstance(manifest, dict) or manifest.get('schema') != 1 or not isinstance(manifest.get('files'), dict) or not manifest['files'] or set(manifest['files']) != set(names) - {'transfer-manifest.json'}:
            raise ValueError('Состав не соответствует манифесту.')
        for name, expected in manifest['files'].items():
            data = z.read(name)
            if expected != {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}:
                raise ValueError('Контрольная сумма не совпала.')
        # Detect file/directory collisions before extraction.
        keys = {n.casefold() for n in manifest['files']}
        if any('/'.join(PurePosixPath(n).parts[:i]).casefold() in keys
               for n in keys for i in range(1, len(PurePosixPath(n).parts))):
            raise ValueError('Конфликт файлов и каталогов.')
        return manifest


def restore(archive, destination, *, confirmed_stopped=False, confirm=False):
    if not confirmed_stopped or not confirm:
        raise ValueError('Сначала preview, остановка моста и явное --confirm.')
    destination = _root(destination)
    if not destination.is_dir(): raise ValueError('Нужен существующий каталог новой установки.')
    manifest = inspect(archive)
    tops = sorted({PurePosixPath(n).parts[0] for n in manifest['files']})
    if any((destination / top).exists() or _linked(destination / top) for top in tops):
        raise ValueError('Конфликт данных: используйте отдельную установку, не заменяйте файлы.')
    lock = destination / '.data-transfer.lock'
    published = []
    lock_stream = lock.open('x')
    try:
        try:
            with tempfile.TemporaryDirectory(prefix='ma2-restore-', dir=destination.parent) as temp:
                stage = Path(temp); _private(stage)
                with zipfile.ZipFile(archive) as z:
                    for name in manifest['files']:
                        path = stage / name; path.parent.mkdir(parents=True, exist_ok=True)
                        data = z.read(name)
                        if manifest['files'][name] != {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}:
                            raise ValueError('Архив изменился после preview.')
                        path.write_bytes(data); os.chmod(path, 0o600)
                for top in tops:
                    os.replace(stage / top, destination / top); published.append(top)
                sync_directory(destination)
        except BaseException:
            for top in reversed(published):
                path = destination / top
                if path.is_dir(): shutil.rmtree(path)
                else: path.unlink()
            raise
    finally:
        lock_stream.close()
        lock.unlink(missing_ok=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('backup', 'preview', 'restore'))
    parser.add_argument('source', type=Path); parser.add_argument('destination', nargs='?', type=Path)
    parser.add_argument('--confirm-stopped', action='store_true'); parser.add_argument('--confirm', action='store_true')
    args = parser.parse_args()
    if args.operation != 'preview' and args.destination is None: parser.error('Требуется destination.')
    try:
        result = inspect(args.source) if args.operation == 'preview' else backup(args.source, args.destination, confirmed_stopped=args.confirm_stopped) if args.operation == 'backup' else restore(args.source, args.destination, confirmed_stopped=args.confirm_stopped, confirm=args.confirm)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, zipfile.BadZipFile, KeyError, TypeError) as error:
        parser.exit(1, f'Перенос не выполнен: {error}\n')


if __name__ == '__main__': main()
