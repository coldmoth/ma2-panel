"""New installs use the relay, preserve receipts, and never replay legacy GitHub POSTs."""
import json

import pytest

from ma2panel import diagnostic_upload as upload
from test_diag_upload import RID, RID2, TOKEN, FakeGithub, configure


class FakeRelay:
    def __init__(self):
        self.requests = []
        self.state = 'queued'
        self.offline = False

    def put(self, rid, report):
        self.requests.append((rid, report))
        if self.offline:
            raise upload.UploadError('network')
        return dict(report_id=rid, state=self.state, **({'number': 23} if self.state == 'sent' else {}))


@pytest.fixture
def relay_store(tmp_path, monkeypatch):
    from ma2panel import diagnostic_relay
    relay = FakeRelay()
    monkeypatch.setattr(diagnostic_relay, 'Relay', lambda: relay)
    path = tmp_path / 'diag' / 'upload-state.json'
    return upload.Uploader(path, tmp_path / 'missing.json'), relay


def test_new_install_no_github_credentials(relay_store):
    uploader, relay = relay_store
    assert uploader.status()['configured'] is True
    assert uploader.enqueue(RID, lambda: {'description': 'Тест'})['state'] == 'queued'
    result = uploader.retry()
    assert result['state'] == 'accepted' and result['transport'] == 'relay'
    assert 'number' not in result
    relay.state = 'sent'
    restarted = upload.Uploader(uploader.path, uploader.config_path)
    assert restarted.retry()['number'] == 23
    assert relay.requests[0] == relay.requests[1] == (RID, {'description': 'Тест'})
    assert restarted.retry() is None


def test_lost_put_response_retries_original_uuid_and_snapshot(relay_store):
    uploader, relay = relay_store
    uploader.enqueue(RID, lambda: {'description': 'original'})
    relay.offline = True
    assert uploader.retry()['error'] == 'network'
    assert uploader.enqueue(RID2, lambda: pytest.fail('must keep original'))['report_id'] == RID
    relay.offline = False
    assert uploader.retry()['state'] == 'accepted'
    assert relay.requests[0] == relay.requests[1]


def test_legacy_ambiguous_post_never_reaches_relay(tmp_path, monkeypatch, relay_store):
    from ma2panel import diagnostic_relay
    monkeypatch.setattr(diagnostic_relay, 'Relay', lambda: pytest.fail('legacy pending must not migrate'))
    cfg = configure(tmp_path)
    fake = FakeGithub()
    fake.lose_reply = True
    uploader = upload.Uploader(tmp_path / 'diag' / 'upload-state.json', cfg, lambda _: fake)
    uploader.enqueue(RID, lambda: {'snapshot': 1})
    assert uploader.retry()['state'] == 'pending'
    monkeypatch.setattr(upload, 'Github', lambda _: fake)
    restarted = upload.Uploader(uploader.path, cfg)
    assert restarted.retry()['state'] == 'sent'
    assert len(fake.creates) == 1


def test_legacy_pending_without_credentials_stays_pending(tmp_path, relay_store):
    uploader, _ = relay_store
    uploader.path.parent.mkdir(parents=True)
    uploader.path.write_text(json.dumps({'current': RID, 'reports': {
        RID: {'report_id': RID, 'state': 'pending', 'auto_send': True, 'body': '{}'}}}))
    result = uploader.retry()
    assert result['error'] == 'legacy_config'
    assert uploader.status()['state'] == 'pending'
    assert uploader.status()['error'] == 'legacy_config'


def test_unsent_legacy_queue_migrates_but_needs_existing_consent(relay_store):
    uploader, relay = relay_store
    uploader.path.parent.mkdir(parents=True)
    row = {'report_id': RID, 'state': 'prepared', 'body': '{}'}
    uploader.path.write_text(json.dumps({'current': RID, 'reports': {RID: row}}))
    assert uploader.retry() is None and not relay.requests
    uploader.enqueue(RID, lambda: pytest.fail('immutable'))
    assert uploader.retry()['state'] == 'accepted'


def test_no_remote_put_if_transport_cannot_be_persisted(relay_store, monkeypatch):
    uploader, relay = relay_store
    uploader.enqueue(RID, lambda: {})
    monkeypatch.setattr(uploader, '_save', lambda _: (_ for _ in ()).throw(OSError()))
    assert uploader.retry()['error'] == 'storage'
    assert not relay.requests


@pytest.mark.parametrize('status,payload', [
    (302, {}), (200, {'report_id': RID2, 'state': 'sent', 'number': 5}),
    (200, {'report_id': RID, 'state': 'sent', 'number': True}),
    (200, {'report_id': RID, 'state': 'queued', 'description': 'private'}),
    (200, {'report_id': RID, 'state': 'other'}),
])
def test_relay_rejects_redirects_and_bad_receipts(monkeypatch, status, payload):
    from ma2panel import diagnostic_relay
    class Connection:
        def __init__(self, host, **kwargs):
            assert host == 'diag.shmyrev52.ru'
        def request(self, method, path, body=None, headers=None):
            assert method == 'PUT' and path == '/v1/reports/' + RID
        def getresponse(self):
            return self
        def read(self, n):
            return json.dumps(payload).encode()
        def close(self):
            pass
    Connection.status = status
    monkeypatch.setattr(diagnostic_relay.http.client, 'HTTPSConnection', Connection)
    with pytest.raises(upload.UploadError):
        diagnostic_relay.Relay().put(RID, {})


def test_relay_request_uses_fixed_https_host_and_bounded_response(monkeypatch):
    from ma2panel import diagnostic_relay
    class Connection:
        status = 200
        def __init__(self, host, **kwargs):
            assert host == 'diag.shmyrev52.ru' and kwargs['timeout'] == 10
        def request(self, method, path, body=None, headers=None):
            assert json.loads(body) == {'report': {'description': 'Тест'}}
            assert 'Authorization' not in headers
        def getresponse(self):
            return self
        def read(self, n):
            assert n <= 8193
            return b'x' * n
        def close(self):
            pass
    monkeypatch.setattr(diagnostic_relay.http.client, 'HTTPSConnection', Connection)
    with pytest.raises(upload.UploadError):
        diagnostic_relay.Relay().put(RID, {'description': 'Тест'})
