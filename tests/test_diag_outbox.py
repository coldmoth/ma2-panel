"""A user-requested report survives offline/restart and needs no browser to deliver."""
import asyncio
import json
import time

import pytest

import diagnostic_upload as upload
from test_diag import site
from test_diag_upload import FakeGithub, RID, RID2, TOKEN, configure, store


def test_enqueue_is_local_durable_and_immutable_without_credentials(tmp_path):
    uploader, fake = store(tmp_path)
    uploader.config_path.unlink()
    result = uploader.enqueue(RID, lambda: {'description': 'Голова дёрнулась'})
    assert result['state'] == 'queued' and result['ok'] and not result['configured']
    assert not fake.creates
    assert uploader.enqueue(RID, lambda: pytest.fail('immutable'))['report_id'] == RID
    assert json.loads(uploader._load()['reports'][RID]['body'])['description'] == 'Голова дёрнулась'
    assert uploader.enqueue(RID2, lambda: pytest.fail('one outstanding report'))['report_id'] == RID


def test_offline_queue_retries_original_snapshot_after_restart(tmp_path):
    uploader, fake = store(tmp_path)
    check = fake.check_private
    fake.check_private = lambda: (_ for _ in ()).throw(upload.UploadError('network'))
    uploader.enqueue(RID, lambda: {'snapshot': 1})
    assert uploader.retry()['state'] == 'queued'
    assert not fake.creates
    fake.check_private = check
    restarted = upload.Uploader(uploader.path, uploader.config_path, lambda _: fake)
    assert restarted.retry()['number'] == 17
    assert json.loads(fake.creates[0][1]) == {'snapshot': 1}
    restarted.retry()
    assert len(fake.creates) == 1


def test_background_lost_post_only_reconciles_and_blocks_other_uuid(tmp_path):
    uploader, fake = store(tmp_path)
    fake.lose_reply = True
    uploader.enqueue(RID, lambda: {})
    assert uploader.retry()['state'] == 'pending'
    saved = fake.issues[:]
    fake.issues.clear()
    assert uploader.retry()['state'] == 'pending'
    assert uploader.enqueue(RID2, lambda: pytest.fail())['report_id'] == RID
    fake.issues = saved
    assert uploader.retry()['state'] == 'sent'
    assert len(fake.creates) == 1


def test_worker_does_not_send_legacy_prepared_reports(tmp_path):
    uploader, fake = store(tmp_path)
    fake.check_private = lambda: (_ for _ in ()).throw(upload.UploadError('network'))
    uploader.submit(RID, lambda: {})
    fake.check_private = lambda: pytest.fail('legacy send was not queued')
    uploader.retry()
    assert not fake.creates


def test_enqueue_disk_failure_and_token_never_reach_remote(tmp_path, monkeypatch):
    uploader, fake = store(tmp_path)
    assert not uploader.enqueue(RID, lambda: {'description': TOKEN})['ok']
    monkeypatch.setattr(uploader, '_save', lambda _: (_ for _ in ()).throw(OSError('private path')))
    result = uploader.enqueue(RID, lambda: {})
    assert not result['ok'] and 'private path' not in json.dumps(result)
    uploader.retry()
    assert not fake.creates


def test_run_starts_from_saved_queue_without_browser(tmp_path):
    uploader, fake = store(tmp_path)
    uploader.enqueue(RID, lambda: {})
    restarted = upload.Uploader(uploader.path, uploader.config_path, lambda _: fake)
    async def run():
        task = asyncio.create_task(restarted.run())
        try:
            async with asyncio.timeout(2):
                while restarted.status()['state'] != 'sent':
                    await asyncio.sleep(.01)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(run())
    assert len(fake.creates) == 1


def test_api_queue_is_passive_masks_description_and_worker_delivers(site, monkeypatch):
    import diagnostic_relay
    fake = FakeGithub()
    fake.put = lambda rid, report: dict(fake.create(rid, json.dumps(report)), state='sent')
    monkeypatch.setattr(diagnostic_relay, 'Relay', lambda: fake)
    with site(password='SecretPassword', settings={'poll_seconds': 0}) as s:
        configure(s.folder)
        before = list(s.link.raw)
        headers = {'X-Diag-Upload': '1', 'Host': 'localhost', 'Origin': 'http://localhost'}
        response = s.client.post('/api/diag/queue', json={'report_id': RID, 'description': 'Голова: SecretPassword'}, headers=headers)
        assert response.status_code == 200 and response.json()['report_id'] == RID
        deadline = time.monotonic() + 3
        while s.client.get('/api/diag/upload').json()['state'] != 'sent':
            assert time.monotonic() < deadline
            time.sleep(.01)
        body = json.loads(fake.creates[0][1])
        assert 'SecretPassword' not in fake.creates[0][1]
        assert body['description'].startswith('Голова:') and body['captured_at'].endswith('+00:00')
        assert list(s.link.raw) == before


@pytest.mark.parametrize('description', [None, 42, [], 'x' * 1001])
def test_queue_rejects_bad_descriptions(site, description):
    with site() as s:
        r = s.client.post('/api/diag/queue', json={'report_id': RID, 'description': description},
                          headers={'X-Diag-Upload': '1', 'Host': 'localhost'})
        assert r.status_code == 400


def test_queue_access_stays_local_and_same_origin(site):
    with site() as s:
        for headers in ({}, {'X-Diag-Upload': '1', 'Host': 'localhost', 'Origin': 'https://evil.example'},
                        {'X-Diag-Upload': '1', 'Host': 'evil.example'}):
            assert s.client.post('/api/diag/queue', json={'report_id': RID}, headers=headers).status_code == 403
    with site(local=False) as s:
        assert s.client.post('/api/diag/queue', json={'report_id': RID}, headers={'X-Diag-Upload': '1', 'Host': 'localhost'}).status_code == 403
