import json
import os
import pytest
from ma2panel import safety
from test_diag import site  # noqa: F401


def test_secret_replace_failure_rolls_back_pair(site, monkeypatch):
    with site(password='old-test-secret') as s:
        before = s.path.read_bytes()
        old_secret = (s.folder / 'secret.env').read_bytes()
        original = os.replace
        failed = False
        def fail(source, target):
            nonlocal failed
            if str(target).endswith('secret.env') and not failed:
                failed = True
                raise OSError('injected replace failure')
            return original(source, target)
        monkeypatch.setattr(os, 'replace', fail)
        response = s.client.post('/api/settings', json={'settings': {'ma2': {'host': '192.0.2.7'}}, 'password': 'new-test-secret'})
        assert response.status_code == 500
        assert s.path.read_bytes() == before
        assert (s.folder / 'secret.env').read_bytes() == old_secret


@pytest.mark.parametrize('boundary', ['settings.json', 'secret.env'])
@pytest.mark.parametrize('exists', [False, True])
def test_restart_recovers_interrupted_pair(tmp_path, monkeypatch, boundary, exists):
    path = tmp_path / 'settings.json'
    secret = tmp_path / 'secret.env'
    if exists:
        path.write_text('{"old": true}')
        secret.write_text('MA2_PASSWORD=old-test\n')
    before = {p: p.read_bytes() if p.exists() else None for p in (path, secret)}
    original = os.replace
    class Crash(BaseException): pass
    def crash(source, target):
        result = original(source, target)
        if str(target).endswith(boundary): raise Crash()
        return result
    monkeypatch.setattr(os, 'replace', crash)
    with pytest.raises(Crash):
        safety.save_settings_pair(path, {'ma2': {'host': '192.0.2.7'}}, 'new-test')
    monkeypatch.setattr(os, 'replace', original)
    # Either loader recovers the pair before returning data.
    safety.load_settings(path)
    for p, data in before.items():
        assert (p.read_bytes() if p.exists() else None) == data
    safety.save_settings_pair(path, {'new': True}, 'retry-test')
    assert safety.load_settings(path) == {'new': True}
    assert safety.load_secret(tmp_path) == 'retry-test'


@pytest.mark.parametrize('failure', ['temp', 'write', 'settings', 'secret', 'rollback'])
def test_pair_io_failures_are_old_or_recoverable(tmp_path, monkeypatch, failure):
    path = tmp_path / 'settings.json'
    path.write_text('{"old": true}')
    (tmp_path / 'secret.env').write_text('MA2_PASSWORD=old-test\n')
    original = os.replace
    def replace(source, target):
        if failure == 'settings' and str(target).endswith('settings.json'): raise OSError('settings')
        if failure in ('secret', 'rollback') and str(target).endswith('secret.env'): raise OSError('secret')
        return original(source, target)
    with monkeypatch.context() as m:
        m.setattr(os, 'replace', replace)
        if failure == 'temp':
            m.setattr(safety.tempfile, 'NamedTemporaryFile', lambda **kw: (_ for _ in ()).throw(OSError('temp')))
        if failure == 'write':
            m.setattr(os, 'fsync', lambda fd: (_ for _ in ()).throw(OSError('write')))
        with pytest.raises(OSError):
            safety.save_settings_pair(path, {'new': True}, 'new-test')
    assert safety.load_settings(path) == {'old': True}
    assert safety.load_secret(tmp_path) == 'old-test'
    assert not (tmp_path / '.settings-transaction.json').exists()


def test_settings_api_recovers_before_reading_either_file(site, monkeypatch):
    with site(password='old-test-secret') as s:
        before = json.loads(s.path.read_text())
        original = os.replace
        class Crash(BaseException): pass
        def crash(source, target):
            result = original(source, target)
            if target == s.path: raise Crash()
            return result
        with monkeypatch.context() as m:
            m.setattr(os, 'replace', crash)
            with pytest.raises(Crash):
                safety.save_settings_pair(s.path, {'new': True}, 'new-test-secret')
        result = s.client.get('/api/settings').json()
        assert result['settings'] == before
        assert result['password_set']


def test_api_exposes_pending_recovery_and_next_read_restores_pair(site, monkeypatch):
    with site(password='old-test-secret') as s:
        before = json.loads(s.path.read_text())
        original = os.replace
        def fail(source, target):
            if str(target).endswith('secret.env'): raise OSError('persistent secret failure')
            return original(source, target)
        with monkeypatch.context() as m:
            m.setattr(os, 'replace', fail)
            response = s.client.post('/api/settings', json={'settings': {'new': True}, 'password': 'new-test-secret'})
        assert response.status_code == 500
        assert response.json()['recovery_pending'] is True
        assert 'восстановлена' in response.json()['err']
        assert s.client.get('/api/settings').json()['settings'] == before
        assert safety.load_secret(s.folder) == 'old-test-secret'
