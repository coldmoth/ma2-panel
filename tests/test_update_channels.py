"""Channel selection uses SemVer precedence, not GitHub publication order."""
import json

import pytest
from ma2panel import browser_update as bu, update


@pytest.mark.parametrize('older,newer', [
    ('3.3.2-beta.2', '3.3.2-beta.10'), ('3.3.2-beta.10', '3.3.2-rc.1'),
    ('3.3.2rc2+abc', 'v3.3.2-rc.10'), ('3.3.2-rc.10', '3.3.2'),
    ('3.3.2', '3.3.3-beta.1'), ('3.3.2-1', '3.3.2-alpha'),
    ('3.3.2-alpha', '3.3.2-alpha.1'), ('3.3.2b2', '3.3.2-beta.3'),
])
def test_precedence(older, newer):
    assert bu.newer(newer, older)
    assert not bu.newer(older, newer)


@pytest.mark.parametrize('a,b', [('3.3.2rc2+abc', 'v3.3.2-rc.2+def'),
                                ('3.3.2b2', '3.3.2-beta.2'), ('3.3.2+a', '3.3.2+b')])
def test_build_and_legacy_spellings(a, b):
    assert bu.version_key(a) == bu.version_key(b)
    assert not bu.newer(a, b)


@pytest.mark.parametrize('value', ['3.3', '03.3.2', '3.3.2-rc.01', '3.3.2-',
                                  '3.3.2-rc..1', '3.3.2+x..y', '3.3.2+', '3.3.2 rc1'])
def test_invalid_semver(value):
    with pytest.raises(update.UpdateError):
        bu.version_key(value)


def metadata(tag, *, draft=False):
    test = '-' in tag
    names = ['ma2-panel-update.zip', 'ma2-panel-update.zip.sha256',
             'quality.json' if test else 'stable-quality.json']
    return {'tag_name': tag, 'draft': draft, 'prerelease': test, 'body': tag,
            'assets': [{'name': name, 'browser_download_url':
                        f'https://github.com/{bu.REPO}/releases/download/{tag}/{name}'} for name in names]}


def transport(monkeypatch, records, *, runtime=None):
    calls = []
    def fetch(url):
        calls.append(url)
        if '/releases?' in url:
            return records if 'page=1' == url.split('&')[-1] else []
        if url == bu.API:
            return metadata('v3.3.2')
        if '/commits/' in url:
            return {'sha': 'a' * 40}
        return {'source_sha': 'a' * 40, 'runtime': runtime}
    monkeypatch.setattr(bu, 'fetch_json', fetch)
    monkeypatch.setattr(bu.release_quality, 'authenticate', lambda report, *a: report)
    monkeypatch.setattr(bu.release_quality, 'authenticate_candidate', lambda report, *a: report, raising=False)
    return calls


def test_opt_in_picks_highest_and_ignores_drafts_unsupported_and_downgrade(monkeypatch):
    records = [metadata('v3.3.3-rc.2'), metadata('v9.0.0-rc.1', draft=True),
               metadata('v3.3.3-beta.20'), metadata('v3.3.3-rc.10'), metadata('v3.3.2'),
               metadata('v9.0.0-alpha.1')]
    transport(monkeypatch, records)
    assert bu.latest(include_test=True, current='3.3.2')['version'] == 'v3.3.3-rc.10'
    assert bu.latest(include_test=True, current='3.3.3') is None


def test_stable_uses_existing_endpoint_and_never_downgrades(monkeypatch):
    calls = transport(monkeypatch, [metadata('v3.3.3-rc.1')])
    assert bu.latest(current='3.3.1')['version'] == 'v3.3.2'
    assert calls[0] == bu.API
    assert not any('/releases?' in u for u in calls)
    assert bu.latest(current='3.3.3-rc.1') is None


def test_incompatible_runtime_is_not_offered(monkeypatch):
    transport(monkeypatch, [metadata('v3.3.3-rc.1')], runtime={'python': '3.13'})
    assert bu.latest(include_test=True, current='3.3.2', runtime={'python': '3.12'}) is None


def test_pagination_is_not_silently_truncated(monkeypatch):
    record = metadata('v3.3.3-rc.1')
    calls = transport(monkeypatch, [record] * 100)
    assert bu.latest(include_test=True, current='3.3.2')['version'] == record['tag_name']
    assert any('page=2' in url for url in calls)


def test_preferences_default_off_and_use_custom_settings_path(tmp_path):
    other = tmp_path / 'private-settings.json'
    assert bu.test_updates(other) is False
    other.write_text(json.dumps({'test_updates': True}))
    assert bu.test_updates(other) is True
    other.write_text(json.dumps({'test_updates': 'yes'}))
    assert bu.test_updates(other) is False


def test_channel_api_preserves_private_data_and_does_not_start_update(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    settings = tmp_path / 'private' / 'settings.json'
    settings.parent.mkdir()
    settings.write_text(json.dumps({'custom': {'keep': 1}, 'ma2': {'host': '127.0.0.1'}}))
    secret = settings.parent / 'secret.env'
    secret.write_bytes(b'MA2_PASSWORD=synthetic-test-only\n')
    monkeypatch.setattr(bu, 'latest', lambda *a, **k: pytest.fail('no automatic check'))
    bu.register(app, tmp_path, lambda r: r.client.host == '127.0.0.1', None, None, None,
                lambda: {}, lambda: {}, lambda: False, settings_path=settings)
    with TestClient(app, base_url='http://localhost', client=('127.0.0.1', 123)) as client:
        assert client.get('/api/update/channel').json()['test_updates'] is False
        assert client.post('/api/update/channel', json={'test_updates': True}).status_code == 403
        result = client.post('/api/update/channel', headers={'X-Update': '1'}, json={'test_updates': True})
        assert result.status_code == 200, result.text
        assert client.get('/api/update/channel').json()['test_updates'] is True
        assert json.loads(settings.read_text())['custom'] == {'keep': 1}
        assert secret.read_bytes() == b'MA2_PASSWORD=synthetic-test-only\n'
        assert not (tmp_path / '.updates').exists()
        for bad in ('yes', None, 1):
            assert client.post('/api/update/channel', headers={'X-Update': '1'}, json={'test_updates': bad}).status_code == 400
        bu.progress(tmp_path, 'a' * 32, 'installing')
        assert client.post('/api/update/channel', headers={'X-Update': '1'}, json={'test_updates': False}).status_code == 409
        assert bu.test_updates(settings) is True


def test_next_update_observes_previous_completion_before_replacing_operation(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    (tmp_path / 'VERSION').write_text('3.3.1+old')
    bu.progress(tmp_path, 'a' * 32, 'completed')
    observed = []
    def busy():
        observed.append(bu.status(tmp_path)['id'])
        return False
    bu.register(app, tmp_path, lambda _: True, None, None, None, lambda: {},
                lambda: {'ports': [8080]}, busy)
    def begin(*args):
        assert observed == ['a' * 32], 'Old terminal hold must be observed before begin'
        return {'phase': 'downloading'}
    monkeypatch.setattr(app.state.updater, 'begin', begin)
    monkeypatch.setattr(bu, 'supported_platform', lambda: True)
    with TestClient(app, base_url='http://localhost') as client:
        response = client.post('/api/update/start', headers={'X-Update': '1'}, json={'version': 'v3.3.2-rc.1'})
        assert response.status_code == 200, response.text
        assert observed == ['a' * 32]
