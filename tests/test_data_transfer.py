import json
from pathlib import Path
import zipfile
import hashlib

import pytest

from ma2panel import data_transfer as transfer


def source(tmp_path):
    root = tmp_path / 'old'; root.mkdir()
    for name, data in {'config.json': b'{"version":5}', 'settings.json': b'{"custom":true}',
                       'secret.env': b'MA2_PASSWORD=synthetic', 'shows/зал.json': b'\x00plan',
                       'rdm-search.json': b'broken journal: keep it', 'backups/config.json': b'older',
                       '.updates/active.json': b'{"phase":"rolled_back"}',
                       'previous/rollback.json': b'previous metadata'}.items():
        p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
    return root


def test_transfer_keeps_every_byte_and_source(tmp_path):
    root = source(tmp_path)
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    archive = tmp_path / 'private.zip'
    transfer.backup(root, archive, confirmed_stopped=True)
    preview = transfer.inspect(archive)
    assert set(preview['files']) == set(before)
    target = tmp_path / 'new'; target.mkdir()
    (target / 'VERSION').write_text('new program')
    transfer.restore(archive, target, confirmed_stopped=True, confirm=True)
    for name, data in before.items():
        assert (target / name).read_bytes() == data
        assert (root / name).read_bytes() == data
    assert (target / 'VERSION').read_text() == 'new program'


def test_requires_confirmation_and_refuses_conflicting_data_without_writes(tmp_path):
    root = source(tmp_path); archive = tmp_path / 'data.zip'
    with pytest.raises(ValueError): transfer.backup(root, archive)
    transfer.backup(root, archive, confirmed_stopped=True)
    target = tmp_path / 'new'; target.mkdir(); (target / 'config.json').write_bytes(b'keep me')
    with pytest.raises(ValueError): transfer.restore(archive, target, confirmed_stopped=True, confirm=True)
    assert [p.name for p in target.iterdir()] == ['config.json']
    assert (target / 'config.json').read_bytes() == b'keep me'


@pytest.mark.parametrize('phase', ['applying', 'restoring', 'installed'])
def test_pending_recovery_is_not_moved_as_success(tmp_path, phase):
    root = source(tmp_path)
    (root / '.updates/active.json').write_text(json.dumps({'phase': phase, 'operation': 'pending'}))
    with pytest.raises(ValueError): transfer.backup(root, tmp_path / 'data.zip', confirmed_stopped=True)
    assert not (tmp_path / 'data.zip').exists()


def test_symlink_and_corrupt_archive_refused(tmp_path):
    root = source(tmp_path); archive = tmp_path / 'data.zip'
    (root / 'shows/leak').symlink_to(tmp_path / 'outside')
    with pytest.raises(ValueError): transfer.backup(root, archive, confirmed_stopped=True)
    (root / 'shows/leak').unlink()
    transfer.backup(root, archive, confirmed_stopped=True)
    with zipfile.ZipFile(archive, 'a') as z: z.writestr('config.json', 'tampered')
    with pytest.raises(ValueError): transfer.inspect(archive)


def test_interrupted_restore_is_not_backed_up_as_complete(tmp_path):
    root = source(tmp_path); (root / '.data-transfer.lock').write_text('interrupted')
    with pytest.raises(ValueError, match='перенос'):
        transfer.backup(root, tmp_path / 'data.zip', confirmed_stopped=True)
    assert not (tmp_path / 'data.zip').exists()


def test_restore_failure_rolls_back_only_its_files(tmp_path, monkeypatch):
    root = source(tmp_path); archive = tmp_path / 'data.zip'
    transfer.backup(root, archive, confirmed_stopped=True)
    target = tmp_path / 'new'; target.mkdir(); (target / 'VERSION').write_text('keep')
    original = transfer.os.replace
    count = 0
    def fail(source, dest):
        nonlocal count
        count += 1
        if count == 2: raise OSError('disk failed')
        return original(source, dest)
    monkeypatch.setattr(transfer.os, 'replace', fail)
    with pytest.raises(OSError): transfer.restore(archive, target, confirmed_stopped=True, confirm=True)
    assert [p.name for p in target.iterdir()] == ['VERSION']


@pytest.mark.parametrize('names', [['config.json/nested'], ['shows/a?.json'], ['shows/é.json', 'shows/é.json']])
def test_archive_paths_are_portable_and_have_no_aliases(tmp_path, names):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for name in names: z.writestr(name, b'data')
        z.writestr('transfer-manifest.json', json.dumps({'schema': 1, 'files': {n: {'size': 4, 'sha256': hashlib.sha256(b'data').hexdigest()} for n in names}}))
    with pytest.raises(ValueError): transfer.inspect(archive)


@pytest.mark.parametrize('manifest', [[], {'schema': 1, 'files': []}, {'schema': 1, 'files': {}}])
def test_malformed_or_empty_manifest_is_not_a_success(tmp_path, manifest):
    archive = tmp_path / 'empty.zip'
    with zipfile.ZipFile(archive, 'w') as z: z.writestr('transfer-manifest.json', json.dumps(manifest))
    with pytest.raises(ValueError): transfer.inspect(archive)


def test_backup_flush_uses_a_writable_handle_on_windows(tmp_path, monkeypatch):
    import errno
    root = tmp_path / 'source'; root.mkdir()
    (root / 'config.json').write_text('{"private-data":true}')
    archive = tmp_path / 'backup.zip'
    original_open, original_fsync = Path.open, transfer.os.fsync
    handles, flushed = {}, []
    def tracked_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        if path.name == 'data.zip': handles[stream.fileno()] = stream
        return stream
    def windows_flush(fd):
        stream = handles.get(fd)
        if stream is not None and not stream.closed:
            if not stream.writable(): raise OSError(errno.EBADF, 'Windows FlushFileBuffers requires write access')
            flushed.append(fd)
        return original_fsync(fd)
    monkeypatch.setattr(Path, 'open', tracked_open)
    monkeypatch.setattr(transfer.os, 'fsync', windows_flush)
    transfer.backup(root, archive, confirmed_stopped=True)
    assert flushed and transfer.inspect(archive)['files']['config.json']
