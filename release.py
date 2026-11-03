import hashlib
import json
import re
import stat
import subprocess
import tomllib
import zipfile
from pathlib import Path

DOCS = ('SETUP.md', 'USAGE.md', 'RELEASE-3.0.md', 'RELEASE-3.1.md', 'pre-hall-3.1.md', 'phase1-windows-smoke.md', 'browser-preflight.md', 'audit-step3-executors.md', 'audit-step5-programmer.md', 'audit-step6-blackout.md', 'audit-step7-scenes.md', 'update-usb.txt', 'spec.md', 'CODEMAP.md', 'code-index.md', 'hall-test-plan.md', 'outgoing-commands.md', 'ma2-syntax.md', 'archive/spec-history.md', 'superpowers/specs/2026-10-30-tablet-ui-design.md')
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024


class RuntimeMismatch(ValueError, RuntimeError):
    pass


def _path(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError('invalid path')
    parts = name.split('/')
    for part in parts:
        if not part or part in ('.', '..') or part.endswith(('.', ' ')):
            raise ValueError('invalid path')
        if any(ord(c) < 32 or ord(c) == 127 for c in part):
            raise ValueError('control character')
        if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', part.split('.')[0], re.I):
            raise ValueError('reserved name')
    if len(parts) > 1:
        if parts[0] not in ('static', 'docs'):
            raise ValueError('invalid location')
    elif not (name.endswith(('.py', '.bat')) or name in ('VERSION', 'README-RU.md', 'CHANGELOG.md', 'program-manifest.json')):
        raise ValueError('invalid location')
    return parts


def _names(names):
    seen = set()
    parents = set()
    for name in names:
        parts = _path(name)
        key = name.casefold()
        prefixes = {'/'.join(parts[:i]).casefold() for i in range(1, len(parts))}
        if key in seen or key in parents or prefixes & seen:
            raise ValueError('path collision')
        seen.add(key)
        parents.update(prefixes)


def payload(root):
    root = Path(root)
    if root.is_symlink():
        raise ValueError('symlink')
    result = {}

    def add(source, dest):
        relative = source.relative_to(root)
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError('symlink')
        if dest in result:
            raise ValueError('duplicate destination')
        result[dest] = source.read_bytes()

    for source in sorted(root.glob('*.py')):
        add(source, source.name)
    static = root / 'static'
    if static.is_symlink():
        raise ValueError('symlink')
    if static.exists():
        def walk(directory):
            for source in sorted(directory.iterdir()):
                if source.is_symlink():
                    raise ValueError('symlink')
                if source.name == '__pycache__':
                    continue
                if source.is_dir():
                    walk(source)
                elif source.is_file():
                    add(source, source.relative_to(root).as_posix())
        walk(static)
    if (root / 'win').is_symlink():
        raise ValueError('symlink')
    for source in sorted((root / 'win').glob('*.bat')):
        add(source, source.name)
    add(root / 'README.md', 'README-RU.md')
    result['README-RU.md'] = result['README-RU.md'].replace(b'](LICENSE)', b'](docs/LICENSE.txt)')
    add(root / 'CHANGELOG.md', 'CHANGELOG.md')
    add(root / 'LICENSE', 'docs/LICENSE.txt')
    for doc in DOCS:
        add(root / 'docs' / doc, 'docs/' + doc)
        if doc == 'RELEASE-3.1.md':
            result['docs/' + doc] = result['docs/' + doc].replace(b'](../LICENSE)', b'](LICENSE.txt)')
        elif doc == 'browser-preflight.md':
            result['docs/' + doc] = result['docs/' + doc].replace(
                b'](../.github/workflows/ci.yml)',
                b'](https://github.com/coldmoth/ma2-panel/blob/main/.github/workflows/ci.yml)')
    _names(result)
    return result


def identity(root):
    root = Path(root)
    version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    try:
        commit = subprocess.run(['git', '-C', str(root), 'rev-parse', '--short', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(['git', '-C', str(root), 'status', '--porcelain'], check=True, capture_output=True, text=True).stdout.strip()
        suffix = commit + ('-dirty' if dirty else '')
        if not commit:
            suffix = 'nogit'
    except (OSError, subprocess.SubprocessError):
        suffix = 'nogit'
    return str(version) + '+' + suffix


def runtime(root):
    return {'python': '3.12', 'lock_sha256': hashlib.sha256((Path(root) / 'uv.lock').read_bytes()).hexdigest()}


def _json(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')) + '\n').encode('utf-8')


def build(root, version=None):
    files = payload(root)
    version = identity(root) if version is None else version
    if not isinstance(version, str) or not version.strip():
        raise ValueError('empty version')
    files['VERSION'] = version.encode('utf-8')
    manifest = {'schema': 1, 'version': version, 'runtime': runtime(root), 'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)} for name, data in files.items()}}
    files['program-manifest.json'] = _json(manifest)
    return files


def write_zip(files, archive):
    _names(files)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as out:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            out.writestr(info, files[name])


def write_tree(files, target):
    _names(files)
    target = Path(target)
    for name in sorted(files):
        dest = target / name
        for item in (target, *(target / Path(*Path(name).parts[:i]) for i in range(1, len(Path(name).parts) + 1))):
            if item.is_symlink():
                raise ValueError('symlink target')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(files[name])


def write_windows_launcher(bundle):
    """Stable outer entry point; updates keep operating inside program/."""
    target = Path(bundle) / 'start.bat'
    target.write_bytes(('''@echo off
setlocal
if not exist "%~dp0program\\start.bat" (
  echo program\\start.bat not found. Extract the WHOLE ma2-panel folder.
  pause
  exit /b 1
)
call "%~dp0program\\start.bat" %*
exit /b %errorlevel%
''').replace('\n', '\r\n').encode('ascii'))


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def check(archive, installed_runtime=None):
    try:
        return _check(archive, installed_runtime)
    except (zipfile.BadZipFile, UnicodeError, KeyError, TypeError, OverflowError, NotImplementedError, EOFError) as exc:
        raise ValueError('invalid package') from exc


def _check(archive, installed_runtime):
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > 3000 or sum(i.file_size for i in entries) > MAX_TOTAL:
            raise ValueError('package too large')
        _names([i.filename for i in entries])
        for info in entries:
            mode = info.external_attr >> 16
            if info.file_size > MAX_FILE or info.is_dir() or stat.S_ISLNK(mode) or info.flag_bits & 1:
                raise ValueError('invalid member')
        data = {i.filename: source.read(i) for i in entries}
    manifest = json.loads(data['program-manifest.json'], object_pairs_hook=_object)
    if not isinstance(manifest, dict) or set(manifest) != {'schema', 'version', 'runtime', 'files'}:
        raise ValueError('invalid manifest')
    if type(manifest['schema']) is not int or manifest['schema'] != 1:
        raise ValueError('invalid schema')
    version = manifest['version']
    if not isinstance(version, str) or not version.strip() or data['VERSION'].decode('utf-8') != version:
        raise ValueError('version mismatch')
    rt = manifest['runtime']
    if not isinstance(rt, dict) or set(rt) != {'python', 'lock_sha256'} or rt['python'] != '3.12' or not isinstance(rt['lock_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', rt['lock_sha256']):
        raise ValueError('invalid runtime')
    records = manifest['files']
    if not isinstance(records, dict) or set(records) != set(data) - {'program-manifest.json'}:
        raise ValueError('member mismatch')
    if not {'bridge.py', 'update.py', 'VERSION'} <= set(records):
        raise ValueError('missing required files')
    for name, record in records.items():
        if not isinstance(record, dict) or set(record) != {'sha256', 'size'}:
            raise ValueError('invalid file record')
        if type(record['size']) is not int or record['size'] < 0 or not isinstance(record['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', record['sha256']):
            raise ValueError('invalid file metadata')
        if record['size'] != len(data[name]) or record['sha256'] != hashlib.sha256(data[name]).hexdigest():
            raise ValueError('content mismatch')
    if installed_runtime is not None and installed_runtime != rt:
        raise RuntimeMismatch('incompatible runtime')
    return manifest


def _runtime_files(root):
    files = {}
    for prefix in ('python', 'lib'):
        folder = Path(root) / prefix
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError('Нет проверенного Python/lib')
        for path in folder.rglob('*'):
            if path.is_symlink():
                raise ValueError('Ссылка в Python/lib')
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not files:
        raise ValueError('Пустой Python/lib')
    return files


def record_runtime(root):
    (Path(root) / 'runtime-files.json').write_bytes(_json(_runtime_files(root)))


def verify_runtime(root):
    import sys
    if sys.version_info[:2] != (3, 12):
        raise ValueError('Нужен Python 3.12 из Windows-комплекта')
    expected = json.loads((Path(root) / 'runtime-files.json').read_text(encoding='utf-8'))
    if expected != _runtime_files(Path(root)):
        raise ValueError('Python/lib изменён или повреждён; установите полный комплект')
