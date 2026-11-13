"""Offline release selection and transport tests; no GitHub or MA2 requests."""
import hashlib
import json
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest

from ma2panel import browser_update as bu
from ma2panel import release
from ma2panel import update
from test_browser_update import install_runtime, package


def metadata():
    prefix = f'https://github.com/{bu.REPO}/releases/download/v3.2.0/'
    return {'tag_name': 'v3.2.0', 'draft': False, 'prerelease': False, 'body': 'Changes <script>ignored</script>',
            'assets': [{'name': n, 'browser_download_url': prefix + n}
                       for n in ('ma2-panel-update.zip', 'ma2-panel-update.zip.sha256')]}


@pytest.mark.parametrize('current,expected', [('3.1.0+abc', True), ('3.2.0+abc', False),
                                           ('3.3.0', False), ('3.2.0rc1+abc', True)])
def test_only_newer_stable_release(current, expected):
    assert bu.newer('v3.2.0', current) is expected


@pytest.mark.parametrize('data', [None, [], {}, {'assets': None},
                                {**metadata(), 'assets': [None]},
                                {**metadata(), 'prerelease': True},
                                {**metadata(), 'tag_name': 'v3.2.0-rc.1'},
                                {**metadata(), 'tag_name': 'v3.3.0'}])
def test_malformed_or_nonstable_release_is_refused(monkeypatch, data):
    monkeypatch.setattr(bu, 'fetch_json', lambda _: data)
    with pytest.raises(update.UpdateError):
        bu.latest()


def test_notes_are_plain_data(monkeypatch):
    data = metadata()
    data['assets'].append({'name': 'stable-quality.json', 'browser_download_url': f'https://github.com/{bu.REPO}/releases/download/v3.2.0/stable-quality.json'})
    monkeypatch.setattr(bu.release_quality, 'authenticate', lambda *a: {'source_sha': 'a' * 40})
    monkeypatch.setattr(bu, 'fetch_json', lambda u: data if u == bu.API else {'sha': 'a' * 40})
    info = bu.latest()
    assert info['notes'] == metadata()['body']


@pytest.mark.parametrize('url', ['http://github.com/a', 'https://evil.invalid/a',
                               'https://github.com@evil.invalid/a', 'https://github.com:444/a'])
def test_redirect_cannot_leave_trusted_https(url):
    handler = bu.GitHubRedirect()
    request = urllib.request.Request(bu.API)
    with pytest.raises(update.UpdateError):
        handler.redirect_request(request, None, 302, 'Found', {}, url)


@pytest.mark.parametrize('error', [TimeoutError('timeout'), urllib.error.URLError('offline'),
                                 urllib.error.HTTPError(bu.API, 500, 'error', {}, None)])
def test_network_errors_are_bounded_and_do_not_change_installation(tmp_path, monkeypatch, error):
    (tmp_path / 'VERSION').write_text('3.1.0')
    monkeypatch.setattr(bu, '_open', lambda *a, **k: (_ for _ in ()).throw(error))
    with pytest.raises((update.UpdateError, OSError)):
        bu.latest()
    assert (tmp_path / 'VERSION').read_text() == '3.1.0'
    assert not (tmp_path / '.updates').exists()


@pytest.mark.parametrize('failure', ['space', 'download', 'zip', 'version'])
def test_prepare_failures_keep_running_program(tmp_path, monkeypatch, failure):
    archive, runtime = package(tmp_path)
    install_runtime(tmp_path)
    (tmp_path / 'runtime.json').write_text(json.dumps(runtime))
    (tmp_path / 'VERSION').write_text('3.1.0')
    monkeypatch.setattr(bu, 'supported_platform', lambda: True)
    if failure == 'space':
        monkeypatch.setattr(bu.shutil, 'disk_usage', lambda _: SimpleNamespace(free=0))
    payload = b'broken ZIP' if failure == 'zip' else archive.read_bytes()
    def download(url, path, limit):
        if failure == 'download':
            raise OSError('connection lost')
        path.write_bytes(payload if url.endswith('.zip') else hashlib.sha256(payload).hexdigest().encode())
    monkeypatch.setattr(bu, 'download', download)
    with pytest.raises((ValueError, OSError, update.UpdateError)):
        bu.prepare(tmp_path, 'a' * 32, {'url': 'a.zip', 'checksum_url': 'a.sha256', 'version': 'v3.2.0'})
    assert (tmp_path / 'VERSION').read_text() == '3.1.0'
    assert not (tmp_path / 'previous').exists()


def test_online_install_refuses_wrong_platform_before_download(tmp_path, monkeypatch):
    monkeypatch.setattr(bu, 'supported_platform', lambda: False)
    monkeypatch.setattr(bu, 'download', lambda *a: pytest.fail('must not download'))
    with pytest.raises(update.UpdateError, match='Windows x64'):
        bu.prepare(tmp_path, 'b' * 32, {})


def test_changed_release_requires_new_confirmation(tmp_path, monkeypatch):
    import asyncio
    async def scenario():
        monkeypatch.setattr(bu, 'latest', lambda: {'version': 'v3.3.0'})
        monkeypatch.setattr(bu, 'prepare', lambda *a: pytest.fail('unconfirmed package must not download'))
        manager = bu.Updater(tmp_path)
        manager.begin(None, None, {}, 'v3.2.0')
        await manager.task
        assert bu.status(tmp_path)['phase'] == 'failed'
        assert 'подтвердите' in bu.status(tmp_path)['error']
        assert not (tmp_path / '.updates/browser.lock').exists()
    asyncio.run(scenario())


def test_busy_after_download_does_not_stop_or_install(tmp_path, monkeypatch):
    import asyncio
    async def scenario():
        monkeypatch.setattr(bu, 'latest', lambda: {'version': 'v3.2.0'})
        monkeypatch.setattr(bu, 'prepare', lambda *a: (tmp_path / 'ma2panel.update.zip', {'version': '3.2.0'}))
        async def busy(): return False
        manager = bu.Updater(tmp_path)
        manager.begin(busy, lambda: pytest.fail('busy bridge must remain running'), {}, 'v3.2.0')
        await manager.task
        assert bu.status(tmp_path)['phase'] == 'failed'
        assert 'занята' in bu.status(tmp_path)['error']
        assert not (tmp_path / 'previous').exists()
    asyncio.run(scenario())
