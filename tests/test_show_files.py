"""Real HTTP/filesystem boundaries; only MA2's Telnet peer is simulated."""
import gzip
import time
from pathlib import Path

import pytest

from test_safety import tabs

HEADERS = {'X-Show-Files': '1'}
SETTINGS = {'safety': {'mode': 'full', 'allow_show_load': True, 'allow_show_save': True},
            'dmx_seconds': 0, 'ma2': {'load_timeout': .6}}
DATA = gzip.compress(b'MA2 opaque fixture for transport tests', mtime=0)


def post(client, path, **kwargs):
    client.headers['host'] = '127.0.0.1'
    return client.post('/api/show-files' + path, headers=HEADERS, **kwargs)


def finish(client, oid):
    for _ in range(200):
        result = client.get('/api/show-files/' + oid).json()
        if result.get('state') in ('ready', 'done', 'failed', 'unknown'):
            return result
        time.sleep(.02)
    pytest.fail('operation did not terminate')


def options(tmp_path):
    folder = tmp_path / 'ma2' / 'shows'
    folder.mkdir(parents=True)
    return {**SETTINGS, 'ma2': {**SETTINGS['ma2'], 'shows_dir': str(folder)}}, folder


def test_upload_waits_for_confirmation_preserves_existing_and_deduplicates(tmp_path):
    settings, folder = options(tmp_path)
    old = folder / 'Demo.show.gz'
    old.write_bytes(DATA)
    with tabs(tmp_path, settings) as ((ws, _), mock, client, config):
        before = config.read_bytes()
        r = post(client, '/upload?name=Demo.show.gz', content=DATA)
        assert r.status_code == 200, r.text
        offer = r.json()
        assert offer['state'] == 'confirm' and offer['original'] == 'Demo.show.gz'
        assert old.read_bytes() == DATA and list(folder.iterdir()) == [old]
        assert not any(x.startswith('LoadShow') for x in mock.received)
        # The peer lists only shows it can actually see on this isolated disk.
        original = mock._reply
        def reply(line):
            if line == 'ListShows':
                return '\n'.join('"' + p.name[:-8] + '"' for p in folder.glob('*.show.gz')) + '\n[Channel]>'
            if line.startswith('LoadShow'):
                mock.shows = [p.name[:-8] for p in folder.glob('*.show.gz')]
            return original(line)
        mock._reply = reply
        assert not post(client, '/' + offer['id'] + '/confirm', json={}).json()['ok']
        body = {'confirm_name': offer['name'], 'ack_unsaved': True}
        assert post(client, '/' + offer['id'] + '/confirm', json=body).json()['ok']
        done = finish(client, offer['id'])
        assert done['state'] == 'done', done
        post(client, '/' + offer['id'] + '/confirm', json=body)
        assert sum(x.startswith('LoadShow') for x in mock.received) == 1
        assert old.read_bytes() == DATA
        assert (folder / (offer['name'] + '.show.gz')).read_bytes() == DATA
        assert config.read_bytes() != before  # switches only after actual show identity confirmation


@pytest.mark.parametrize('name,data', [('plan.json', b'{}'), ('x.show.gz', b'bad'),
    ('x.show.gz', DATA[:-3]), ('x.show.gz', DATA[:-8] + b'12345678'),
    ('../x.show.gz', DATA), ('C:\\x.show.gz', DATA), ('x.show.gz', b'')])
def test_invalid_upload_changes_no_files_or_ma2(tmp_path, name, data):
    from urllib.parse import quote
    settings, folder = options(tmp_path)
    with tabs(tmp_path, settings) as (_, mock, client, config):
        before = config.read_bytes()
        result = post(client, '/upload?name=' + quote(name, safe=''), content=data)
        assert result.status_code == 400, result.text
        assert not list(folder.iterdir()) and config.read_bytes() == before
        assert not any(x.startswith(('LoadShow', 'SaveShow', 'SelectDrive')) for x in mock.received)


def test_download_is_snapshot_and_never_saves(tmp_path):
    settings, folder = options(tmp_path)
    source = folder / 'Mock show.show.gz'
    source.write_bytes(DATA)
    with tabs(tmp_path, settings) as (_, mock, client, _):
        r = post(client, '/prepare', json={'kind': 'download'})
        assert r.status_code == 200, r.text
        offer = r.json()
        assert offer['name'] == 'Mock show' and offer['state'] == 'confirm'
        post(client, '/' + offer['id'] + '/confirm', json={'confirm_name': offer['name']})
        ready = finish(client, offer['id'])
        assert ready['state'] == 'ready', ready
        source.write_bytes(gzip.compress(b'changed'))
        response = client.get('/api/show-files/' + offer['id'] + '/download')
        assert response.content == DATA
        assert 'attachment' in response.headers['content-disposition']
        assert 'content-encoding' not in response.headers
        assert not any(x.startswith('SaveShow') for x in mock.received)


def test_unknown_save_never_returns_old_file_or_repeats(tmp_path, monkeypatch):
    settings, folder = options(tmp_path)
    source = folder / 'Mock show.show.gz'
    source.write_bytes(DATA)
    with tabs(tmp_path, settings) as (_, mock, client, _):
        from ma2panel import show_transfer
        monkeypatch.setattr(show_transfer, 'FILE_WAIT', .15)
        offer = post(client, '/prepare', json={'kind': 'save'}).json()
        assert offer.get('state') == 'confirm', offer
        body = {'confirm_name': offer['name'], 'ack_overwrite': True}
        post(client, '/' + offer['id'] + '/confirm', json=body)
        result = finish(client, offer['id'])
        assert result['state'] == 'unknown', result
        assert client.get('/api/show-files/' + offer['id'] + '/download').status_code == 409
        post(client, '/' + offer['id'] + '/confirm', json=body)
        assert mock.received.count('SaveShow') == 1
        assert source.read_bytes() == DATA
        assert any(p.read_bytes() == DATA for p in (tmp_path / 'backups').glob('show-*'))


def test_stale_offer_and_foreign_origin_send_no_write(tmp_path):
    settings, folder = options(tmp_path)
    (folder / 'Mock show.show.gz').write_bytes(DATA)
    with tabs(tmp_path, settings) as (_, mock, client, _):
        offer = post(client, '/prepare', json={'kind': 'save'}).json()
        assert offer.get('id'), offer
        mock.show_name = 'Demo'
        response = post(client, '/' + offer['id'] + '/confirm', json={'confirm_name': offer['name'], 'ack_overwrite': True})
        assert response.status_code == 200
        result = finish(client, offer['id'])
        assert result['state'] == 'failed', result
        bad = client.post('/api/show-files/prepare', headers={**HEADERS, 'Origin': 'https://evil.example'}, json={'kind': 'save'})
        assert bad.status_code == 403
        assert client.post('/api/show-files/upload?name=x.show.gz', content=DATA).status_code == 403
        assert not any(x.startswith(('LoadShow', 'SaveShow')) for x in mock.received)


def test_save_observes_new_valid_file_and_keeps_backup(tmp_path, monkeypatch):
    settings, folder = options(tmp_path)
    source = folder / 'Mock show.show.gz'
    source.write_bytes(DATA)
    updated = gzip.compress(b'new MA2 contents', mtime=0)
    with tabs(tmp_path, settings) as (_, mock, client, _):
        from ma2panel import show_transfer
        monkeypatch.setattr(show_transfer, 'STABLE_SECONDS', .02)
        original = mock._reply
        def reply(line):
            if line == 'SaveShow':
                source.write_bytes(updated)
            return original(line)
        mock._reply = reply
        offer = post(client, '/prepare', json={'kind': 'save'}).json()
        post(client, '/' + offer['id'] + '/confirm', json={'confirm_name': offer['name'], 'ack_overwrite': True})
        result = finish(client, offer['id'])
        assert result['state'] == 'ready', result
        assert client.get('/api/show-files/' + offer['id'] + '/download').content == updated
        assert mock.received.index('SelectDrive 1') < mock.received.index('SaveShow')
        assert (tmp_path / 'backups' / ('show-' + offer['id'] + '.show.gz')).read_bytes() == DATA


def test_archive_bomb_and_size_limit_reject_before_ma2(tmp_path, monkeypatch):
    from ma2panel import show_files
    settings, folder = options(tmp_path)
    with tabs(tmp_path, settings) as (_, mock, client, _):
        monkeypatch.setattr(show_files, 'MAX_EXPANDED', 64)
        response = post(client, '/upload?name=bomb.show.gz', content=gzip.compress(b'x' * 1000))
        assert response.status_code == 400
        monkeypatch.setattr(show_files, 'MAX_FILE', 8)
        assert post(client, '/upload?name=x.show.gz', content=DATA).status_code == 400
        assert not list(folder.iterdir()) and not any(x.startswith('LoadShow') for x in mock.received)


def test_snapshot_refuses_symlinks_collision_and_changed_source(tmp_path, monkeypatch):
    from ma2panel import show_files
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.write_bytes(DATA)
    target.write_bytes(b'valuable')
    with pytest.raises(FileExistsError):
        show_files.snapshot(source, target)
    assert target.read_bytes() == b'valuable'
    alias = tmp_path / 'alias'
    alias.symlink_to(source)
    with pytest.raises(ValueError):
        show_files.snapshot(alias, tmp_path / 'new')
    original = show_files.regular
    calls = 0
    def changing(path):
        nonlocal calls
        if Path(path) == source:
            calls += 1
            if calls == 2:
                source.write_bytes(gzip.compress(b'changed'))
        return original(path)
    monkeypatch.setattr(show_files, 'regular', changing)
    with pytest.raises(ValueError):
        show_files.snapshot(source, tmp_path / 'new')
    assert not (tmp_path / 'new').exists()


def test_unknown_id_and_expired_offer_never_replay(tmp_path, monkeypatch):
    settings, folder = options(tmp_path)
    (folder / 'Mock show.show.gz').write_bytes(DATA)
    with tabs(tmp_path, settings) as (_, mock, client, _):
        offer = post(client, '/prepare', json={'kind': 'save'}).json()
        from ma2panel import show_transfer
        monkeypatch.setattr(show_transfer, 'OFFER_TTL', -1)
        body = {'confirm_name': offer['name'], 'ack_overwrite': True}
        assert post(client, '/' + offer['id'] + '/confirm', json=body).status_code == 400
        assert post(client, '/old-run-id/confirm', json=body).status_code == 404
        assert not any(x.startswith('SaveShow') for x in mock.received)


def test_transport_timeout_after_save_does_not_repeat(tmp_path, monkeypatch):
    settings, folder = options(tmp_path)
    settings['ma2']['timeout'] = .05
    (folder / 'Mock show.show.gz').write_bytes(DATA)
    with tabs(tmp_path, settings) as (_, mock, client, _):
        original = mock._reply
        mock._reply = lambda line: '' if line == 'SaveShow' else original(line)
        offer = post(client, '/prepare', json={'kind': 'save'}).json()
        body = {'confirm_name': offer['name'], 'ack_overwrite': True}
        post(client, '/' + offer['id'] + '/confirm', json=body)
        assert finish(client, offer['id'])['state'] == 'unknown'
        post(client, '/' + offer['id'] + '/confirm', json=body)
        assert mock.received.count('SaveShow') == 1


def test_unparseable_list_does_not_load_empty_show(tmp_path):
    settings, folder = options(tmp_path)
    with tabs(tmp_path, settings) as (_, mock, client, _):
        offer = post(client, '/upload?name=x.show.gz', content=DATA).json()
        original = mock._reply
        mock._reply = lambda line: '???\n[Channel]>' if line == 'ListShows' else original(line)
        post(client, '/' + offer['id'] + '/confirm', json={'confirm_name': offer['name'], 'ack_unsaved': True})
        result = finish(client, offer['id'])
        assert result['state'] == 'failed' and 'ListShows' in result['reason'], result
        assert not any(x.startswith('LoadShow') for x in mock.received)
        assert (folder / (offer['name'] + '.show.gz')).read_bytes() == DATA


def test_post_shutdown_cleans_temporary_files(tmp_path):
    settings, folder = options(tmp_path)
    with tabs(tmp_path, settings) as (_, _, client, _):
        assert post(client, '/upload?name=x.show.gz', content=DATA).status_code == 200
        workspace = Path(client.app.state.show_files_workspace.name)
        assert workspace.exists()
    assert not workspace.exists()


def test_bad_deflate_reports_validation_error(tmp_path):
    settings, _ = options(tmp_path)
    with tabs(tmp_path, settings) as (_, _, client, _):
        # Valid gzip header, invalid deflate block (BTYPE=3).
        data = bytes.fromhex('1f8b0800000000000003') + b'\x07' + b'\0' * 8
        assert post(client, '/upload?name=x.show.gz', content=data).status_code == 400


def test_busy_file_save_blocks_second_client_and_halt_leaves_unknown(tmp_path, monkeypatch):
    from test_bridge import ask
    from ma2panel import show_transfer
    monkeypatch.setattr(show_transfer, 'FILE_WAIT', 1)
    settings, folder = options(tmp_path)
    (folder / 'Mock show.show.gz').write_bytes(DATA)
    with tabs(tmp_path, settings) as ((ws, _), mock, client, _):
        offer = post(client, '/prepare', json={'kind': 'save'}).json()
        post(client, '/' + offer['id'] + '/confirm', json={'confirm_name': offer['name'], 'ack_overwrite': True})
        # A separate panel action must fail promptly, not queue an unnoticed second SaveShow.
        for _ in range(100):
            if 'SaveShow' in mock.received:
                break
            time.sleep(.005)
        assert 'SaveShow' in mock.received
        assert not ask(ws, {'a': 'select_fixtures', 'ids': [12]})['ok']
        result = ask(ws, {'a': 'show_save'})
        assert not result['ok'], result
        assert ask(ws, {'a': 'halt'})['ok']
        assert finish(client, offer['id'])['state'] == 'unknown'
        assert mock.received.count('SaveShow') <= 1


def test_temporary_quota_and_disk_full_leave_no_partial_upload(tmp_path, monkeypatch):
    from ma2panel import show_transfer
    settings, folder = options(tmp_path)
    with tabs(tmp_path, settings) as (_, mock, client, _):
        monkeypatch.setattr(show_transfer, 'MAX_TEMP_BYTES', 1, raising=False)
        response = post(client, '/upload?name=x.show.gz', content=DATA)
        assert response.status_code == 400
        assert not list(Path(client.app.state.show_files_workspace.name).iterdir())
        assert not list(folder.iterdir())


def test_permissions_missing_directory_and_symlink_are_fail_closed(tmp_path):
    settings, folder = options(tmp_path)
    source = folder / 'Mock show.show.gz'
    source.symlink_to(tmp_path / 'missing')
    settings['safety'] = {'mode': 'full'}
    with tabs(tmp_path, settings) as (_, mock, client, _):
        assert post(client, '/upload?name=x.show.gz', content=DATA).status_code == 400
        assert post(client, '/prepare', json={'kind': 'save'}).status_code == 400
        assert post(client, '/prepare', json={'kind': 'download'}).status_code == 400
        assert source.is_symlink()
        assert not any(x.startswith(('LoadShow', 'SaveShow')) for x in mock.received)


def test_failed_backup_never_sends_save(tmp_path, monkeypatch):
    import errno
    from ma2panel import show_files
    settings, folder = options(tmp_path)
    source = folder / 'Mock show.show.gz'
    source.write_bytes(DATA)
    with tabs(tmp_path, settings) as (_, mock, client, _):
        offer = post(client, '/prepare', json={'kind': 'save'}).json()
        original = show_files.snapshot
        def no_space(src, target):
            if Path(target).parent.name == 'backups':
                raise OSError(errno.ENOSPC, 'disk full')
            return original(src, target)
        monkeypatch.setattr(show_files, 'snapshot', no_space)
        post(client, '/' + offer['id'] + '/confirm', json={'confirm_name': offer['name'], 'ack_overwrite': True})
        assert finish(client, offer['id'])['state'] == 'failed'
        assert source.read_bytes() == DATA and 'SaveShow' not in mock.received


def test_mock_rejects_show_directory_outside_its_config(tmp_path):
    import tempfile
    with tempfile.TemporaryDirectory() as external:
        settings = {**SETTINGS, 'ma2': {**SETTINGS['ma2'], 'shows_dir': external}}
        with tabs(tmp_path, settings) as (_, mock, client, _):
            assert post(client, '/upload?name=x.show.gz', content=DATA).status_code == 400
            assert not list(Path(external).iterdir())


def test_unexpected_show_after_sent_load_is_unknown(tmp_path):
    settings, folder = options(tmp_path)
    with tabs(tmp_path, settings) as (_, mock, client, _):
        offer = post(client, '/upload?name=x.show.gz', content=DATA).json()
        mock.shows.append(offer['name'])
        original = mock._reply
        def reply(line):
            result = original(line)
            if line.startswith('LoadShow'):
                mock.show_name = 'Externally changed'
            return result
        mock._reply = reply
        post(client, '/' + offer['id'] + '/confirm', json={'confirm_name': offer['name'], 'ack_unsaved': True})
        result = finish(client, offer['id'])
        assert result['state'] == 'unknown', result


def test_file_disappears_after_listing_never_sends_load(tmp_path):
    settings, folder = options(tmp_path)
    with tabs(tmp_path, settings) as (_, mock, client, _):
        offer = post(client, '/upload?name=x.show.gz', content=DATA).json()
        original = mock._reply
        def reply(line):
            if line == 'ListShows':
                (folder / (offer['name'] + '.show.gz')).unlink()
                return '"' + offer['name'] + '"\n[Channel]>'
            return original(line)
        mock._reply = reply
        post(client, '/' + offer['id'] + '/confirm', json={'confirm_name': offer['name'], 'ack_unsaved': True})
        assert finish(client, offer['id'])['state'] == 'failed'
        assert not any(x.startswith('LoadShow') for x in mock.received)


@pytest.mark.parametrize('kind', ['load', 'save'])
@pytest.mark.parametrize('control', ['reconnect', 'halt_resume'])
def test_connection_or_stop_during_disk_invalidates_consent(tmp_path, monkeypatch, kind, control):
    import threading
    from ma2panel import show_files
    from test_bridge import ask
    settings, folder = options(tmp_path)
    (folder / 'Mock show.show.gz').write_bytes(DATA)
    entered, release = threading.Event(), threading.Event()
    original = show_files.publish if kind == 'load' else show_files.snapshot
    def delayed(*args):
        if kind == 'load' or Path(args[1]).parent.name == 'backups':
            entered.set()
            assert release.wait(10), 'disk test timed out'
        return original(*args)
    with tabs(tmp_path, settings) as ((ws, _), mock, client, _):
        if kind == 'load':
            offer = post(client, '/upload?name=x.show.gz', content=DATA).json()
            mock.shows.append(offer['name'])
        else:
            offer = post(client, '/prepare', json={'kind': 'save'}).json()
        monkeypatch.setattr(show_files, 'publish' if kind == 'load' else 'snapshot', delayed)
        try:
            post(client, '/' + offer['id'] + '/confirm', json={'confirm_name': offer['name'], 'ack_unsaved': True, 'ack_overwrite': True})
            assert entered.wait(3)
            for action in (('link_drop', 'link_connect') if control == 'reconnect' else ('halt', 'resume')):
                assert ask(ws, {'a': action})['ok']
            if control == 'reconnect':
                for _ in range(800):
                    if sum(x.startswith('login') for x in mock.received) >= 2:
                        time.sleep(.05)
                        break
                    time.sleep(.005)
                assert sum(x.startswith('login') for x in mock.received) >= 2
        finally:
            release.set()
        result = finish(client, offer['id'])
        assert not any(x.startswith(('SaveShow', 'LoadShow')) for x in mock.received), result
        assert result['state'] == 'failed', result


@pytest.mark.parametrize('event', ['reconnect', 'halt_resume'])
def test_expected_generation_is_rechecked_after_late_reply_drain(event):
    import asyncio
    from ma2panel.link import MA2Link
    async def scenario():
        link = MA2Link('127.0.0.1', 1, 'panel', '', lambda state: None)
        link.state, link._stale = 'logged_in', True
        writes = []
        async def drain():
            if event == 'reconnect':
                link._gen += 1
            else:
                link.halted = True
                link.halted = False
            return True
        async def exchange(command, timeout):
            writes.append(command)
            return 'OK\n[Channel]>', True
        link._drain, link._exchange = drain, exchange
        ok, _ = await link.send('SaveShow', gen=0)
        assert not ok and not writes
    asyncio.run(scenario())


def test_disconnected_upload_removes_partial_bytes(tmp_path):
    from starlette.requests import Request
    settings, folder = options(tmp_path)
    with tabs(tmp_path, settings) as (_, mock, client, _):
        events = iter([{'type': 'http.request', 'body': DATA[:10], 'more_body': True},
                       {'type': 'http.disconnect'}])
        async def receive():
            return next(events)
        request = Request({'type': 'http', 'method': 'POST', 'path': '/api/show-files/upload',
                           'scheme': 'http', 'query_string': b'name=x.show.gz',
                           'headers': [(b'host', b'127.0.0.1'), (b'x-show-files', b'1')]}, receive)
        endpoint = next(r.endpoint for r in client.app.routes if getattr(r, 'path', '') == '/api/show-files/upload')
        response = client.portal.call(endpoint, request)
        assert response.status_code == 400
        assert not list(Path(client.app.state.show_files_workspace.name).iterdir())
        assert not list(folder.iterdir())
        assert not any(x.startswith(('LoadShow', 'SaveShow')) for x in mock.received)
