"""Release gates: a complete, single-version set must precede publication."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest
from ma2panel import release
from scripts.generate_version import generate


def test_release_version_keeps_runtime_lock(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[project]\nversion="3.2.0"\n[tool.ma2panel]\nrelease-version="3.2.5"\n')
    (tmp_path / 'uv.lock').write_bytes(b'unchanged runtime')
    before = release.runtime(tmp_path)
    assert generate(tmp_path) == '3.2.5'
    assert release.identity(tmp_path).startswith('3.2.5+')
    assert release.runtime(tmp_path) == before


def candidate(tmp_path):
    from scripts.release_delivery import ARCHIVES, REQUIRED
    payload = {name: b'payload' for name in REQUIRED}
    payload['VERSION'] = b'3.2.5+abcdef0'
    manifest = {'version': '3.2.5+abcdef0', 'files': {n: {'size': len(d), 'sha256': hashlib.sha256(d).hexdigest()} for n, d in payload.items()}}
    payload['program-manifest.json'] = json.dumps(manifest).encode()
    def packed(path, files):
        with zipfile.ZipFile(path, 'w') as z:
            for name, data in files.items(): z.writestr(name, data)
    update = tmp_path / ARCHIVES[1]
    packed(update, payload)
    packed(tmp_path / ARCHIVES[0], {'ma2-panel/program/' + n: d for n, d in payload.items()} | {'ma2-panel/start.bat': b'launcher', 'ma2-panel/program/python/python.exe': b'MZ', 'ma2-panel/program/lib/fastapi/__init__.py': b'dep', 'ma2-panel/program/runtime.json': b'{}', 'ma2-panel/program/runtime-files.json': b'{}'})
    sidecar = hashlib.sha256(update.read_bytes()).hexdigest() + '  ' + update.name + '\n'
    packed(tmp_path / ARCHIVES[2], {'ma2-panel-update/ma2-panel-update.zip': update.read_bytes(), 'ma2-panel-update/ma2-panel-update.zip.sha256': sidecar.encode(), 'ma2-panel-update/update.py': payload['update.py'], 'ma2-panel-update/release.py': payload['release.py'], 'ma2-panel-update/update-usb.bat': b'updater', 'ma2-panel-update/update-usb.txt': b'instructions'})
    for name in ARCHIVES:
        path = tmp_path / name
        path.with_name(name + '.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + name + '\n')
    (tmp_path / 'build-inputs.json').write_text(json.dumps({'version': manifest['version'], 'commit': 'abcdef0123456789'}))
    return tmp_path


def test_complete_release_set(tmp_path):
    from scripts.release_delivery import validate
    assert len(validate(candidate(tmp_path), 'abcdef0123456789', 'v3.2.5')) == 7


@pytest.mark.parametrize('damage', ['missing', 'checksum', 'commit', 'version', 'mixed'])
def test_reject_incomplete_or_mixed_set(tmp_path, damage):
    from scripts.release_delivery import validate
    root = candidate(tmp_path)
    if damage == 'missing': (root / 'ma2-panel-win.zip').unlink()
    if damage == 'checksum': (root / 'ma2-panel-win.zip').write_bytes(b'corrupt')
    if damage in ('commit', 'version'):
        p = root / 'build-inputs.json'; data = json.loads(p.read_text()); data[damage] = 'wrong'; p.write_text(json.dumps(data))
    if damage == 'mixed':
        p = root / 'ma2-panel-win.zip'
        with zipfile.ZipFile(p) as z: files = {n: z.read(n) for n in z.namelist()}
        files['ma2-panel/program/bridge.py'] = b'another version'
        with zipfile.ZipFile(p, 'w') as z:
            for n, d in files.items(): z.writestr(n, d)
        (root / (p.name + '.sha256')).write_text(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n')
    with pytest.raises((ValueError, FileNotFoundError)):
        validate(root, 'abcdef0123456789', 'v3.2.5')


def test_publication_does_not_edit_existing_release(tmp_path, monkeypatch):
    from scripts import release_delivery as delivery
    root = candidate(tmp_path)
    calls = []
    def gh(*args):
        calls.append(args)
        return '[[{"tag_name":"v3.2.5"}]]'
    monkeypatch.setattr(delivery, 'gh', gh)
    with pytest.raises(ValueError, match='already exists'):
        delivery.publish(root, 'abcdef0123456789', 'v3.2.5', 'unused')
    assert len(calls) == 1 and calls[0][0] == 'api'


@pytest.mark.parametrize('corrupt_upload', [False, True])
def test_publish_only_after_download_verification(tmp_path, monkeypatch, corrupt_upload):
    import shutil
    from scripts import release_delivery as delivery
    root = candidate(tmp_path)
    changes = tmp_path / 'changes.md'; changes.write_text('Complete Windows delivery.')
    assets = delivery.validate(root, 'abcdef0123456789', 'v3.2.5')
    calls = []
    def gh(*args):
        calls.append(args)
        if args[0] == 'api':
            return '[]' if '--slurp' in args or 'matching-refs' in args[-1] else '{"tag_name":"v3.2.4"}'
        if args[:2] == ('release', 'view'):
            return json.dumps({'isDraft': True, 'targetCommitish': 'abcdef0123456789', 'assets': [{'name': p.name} for p in assets]})
        if args[:2] == ('release', 'download'):
            target = Path(args[-1]); target.mkdir()
            for p in assets: shutil.copy2(p, target / p.name)
            if corrupt_upload: (target / 'ma2-panel-win.zip').write_bytes(b'incomplete upload')
        return ''
    monkeypatch.setattr(delivery, 'gh', gh)
    if corrupt_upload:
        with pytest.raises(ValueError, match='Uploaded asset mismatch'):
            delivery.publish(root, 'abcdef0123456789', 'v3.2.5', changes)
    else:
        delivery.publish(root, 'abcdef0123456789', 'v3.2.5', changes)
    edits = [c for c in calls if c[:2] == ('release', 'edit')]
    assert bool(edits) is (not corrupt_upload)
    assert '--draft' in next(c for c in calls if c[:2] == ('release', 'create'))
