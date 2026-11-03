"""Outbound diagnostics: privacy, durable sends, and no console side effects."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import diagnostic_upload as upload
from test_diag import site

RID = 'f0e1d2c3-4567-4890-abcd-0123456789ab'
RID2 = 'a0e1d2c3-4567-4890-abcd-0123456789ab'
TOKEN = 'github_pat_PRIVATE_TOKEN'


@pytest.mark.parametrize('version', ['3.1.0rc1', '3.1.0', '3.1.0rc1+abc1234-dirty',
                                     '3.1.0+nogit', '2026-11-02_1200 abc1234+dirty'])
def test_project_version_survives_report_and_receiver_validation(version):
    from relay.app import _valid_report
    report = upload.build_report({'version': version}, {}, mock=True)
    assert report['panel_version'] == version
    assert _valid_report(report)


@pytest.mark.parametrize('version', ['3.1.0+private-show-name', '3.1.0+abc1234/path', 'private', '3.1.0\n'])
def test_version_allowlist_still_hides_private_values(version):
    from relay.app import _valid_report
    report = upload.build_report({'version': version}, {})
    assert report['panel_version'] == upload.UNKNOWN
    assert not _valid_report(dict(report, panel_version=version))


def configure(tmp_path):
    path = tmp_path / 'diagnostic-upload.json'
    path.write_text(json.dumps({'repository': upload.REPOSITORY, 'token': TOKEN}))
    return path


class FakeGithub:
    def __init__(self):
        self.creates = []
        self.issues = []
        self.private = True
        self.lose_reply = False
        self.lookups = 0

    def check_private(self):
        if not self.private:
            raise upload.UploadError('private')

    def find(self, report_id):
        self.lookups += 1
        return next((i for i in self.issues if i['report_id'] == report_id), None)

    def create(self, report_id, body):
        self.creates.append((report_id, body))
        issue = {'number': 17, 'report_id': report_id}
        self.issues.append(issue)
        if self.lose_reply:
            raise upload.UploadError('network', ambiguous=True)
        return issue


def store(tmp_path, fake=None):
    fake = fake or FakeGithub()
    return upload.Uploader(tmp_path / 'diag' / 'upload-state.json', configure(tmp_path), lambda token: fake), fake


def test_report_excludes_private_data_and_unknown_fields():
    private = ['SecretShow', 'PrivateOperator', 'TopSecret99', '192.168.5.9', r'C:\Users\Alice', '123456789']
    diag = {'version': '2026-11-02_1200 abc1234+dirty', 'ma2': 'logged_in', 'mode': 'full',
            'login_vars': {'VERSION': '3.9.60.68', 'USER': private[1], 'USERPROFILE': private[1], 'SHOWFILE': private[0], 'PATH': private[4]},
            'host': private[3], 'login_reply': ' '.join(private), 'unknown': private,
            'raw': [{'cmd': 'List Executor 1.1 Thru 1.250', 'status': 'sent',
                     'reply': 'Executing : List Executor 1.1 Thru 1.250\n1.101 "SecretShow" Running\nError #9\n' + '\n'.join(private)}]}
    cfg = {'fixtures': [{'id': 5, 'label': private[0], 'type': private[1], 'address': 12, 'channels': 8}],
           'groups': [{'name': private[0]}], 'scenes': [], 'password': private[2]}
    report = upload.build_report(diag, cfg, private, mock=True)
    body = json.dumps(report, ensure_ascii=False)
    assert not any(p in body for p in private)
    assert report['console_version'] == '3.9.60.68'
    assert report['mock'] is True
    assert report['counts']['fixtures'] == 1
    assert report['replies'][0]['command'] == 'List Executor'
    assert 'row 1.101' in body and '#9' in body
    assert 'неизвестно' in json.dumps(upload.build_report({}, {}, [], mock=False), ensure_ascii=False)


def test_report_is_bounded_and_handles_bad_types():
    diag = {'version': 'evil secret value', 'raw': [{'cmd': 'login "secret" "p"', 'status': 'oops', 'reply': 'secret' * 100000}] * 500,
            'export': {'type_reads': {'bad': {'spec': float('nan')}}}}
    body = json.dumps(upload.build_report(diag, {'fixtures': [None, {}] * 5000}, ['p']), ensure_ascii=False, allow_nan=False)
    assert len(body) <= 48000 and 'secret' not in body and 'evil' not in body


def test_sent_id_is_immutable_and_survives_restart(tmp_path):
    uploader, fake = store(tmp_path)
    first = uploader.submit(RID, lambda: {'schema': 1, 'value': 42})
    assert first['state'] == 'sent' and first['number'] == 17
    again = upload.Uploader(uploader.path, uploader.config_path, lambda _: fake).submit(RID, lambda: pytest.fail('must use saved snapshot'))
    assert again['number'] == 17 and len(fake.creates) == 1
    assert TOKEN not in uploader.path.read_text()
    assert 'body' not in first and 'token' not in json.dumps(uploader.status())


def test_lost_reply_reconciles_without_second_post_after_restart(tmp_path):
    uploader, fake = store(tmp_path)
    fake.lose_reply = True
    assert uploader.submit(RID, lambda: {'schema': 1})['state'] == 'pending'
    restarted = upload.Uploader(uploader.path, uploader.config_path, lambda _: fake)
    assert restarted.submit(RID, lambda: pytest.fail())['number'] == 17
    assert len(fake.creates) == 1 and fake.lookups == 1


def test_unknown_result_not_found_blocks_new_reports_and_repost(tmp_path):
    uploader, fake = store(tmp_path)
    fake.lose_reply = True
    uploader.submit(RID, lambda: {})
    fake.issues.clear()  # eventual visibility / cannot prove POST failed
    assert uploader.submit(RID, lambda: {})['state'] == 'pending'
    assert uploader.submit(RID2, lambda: pytest.fail())['report_id'] == RID
    assert len(fake.creates) == 1


def test_concurrent_same_id_creates_only_once(tmp_path):
    uploader, fake = store(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: uploader.submit(RID, lambda: {}), range(2)))
    assert all(r['number'] == 17 for r in results) and len(fake.creates) == 1


def test_disk_failure_before_post_never_creates(tmp_path, monkeypatch):
    uploader, fake = store(tmp_path)
    monkeypatch.setattr(uploader, '_save', lambda _: (_ for _ in ()).throw(OSError('PRIVATE_PATH')))
    result = uploader.submit(RID, lambda: {})
    assert result['ok'] is False and not fake.creates
    assert 'PRIVATE_PATH' not in json.dumps(result)


def test_public_repository_and_unconfigured_fail_closed(tmp_path):
    uploader, fake = store(tmp_path)
    fake.private = False
    assert uploader.submit(RID, lambda: {})['ok'] is False and not fake.creates
    uploader.config_path.unlink()
    assert uploader.status()['configured'] is False
    assert uploader.submit(RID, lambda: {})['ok'] is False


def test_invalid_uuid_and_wrong_destination_rejected(tmp_path):
    uploader, fake = store(tmp_path)
    for rid in ['../escape', 'x', None, 12]:
        assert uploader.submit(rid, lambda: {})['ok'] is False
    uploader.config_path.write_text(json.dumps({'repository': 'other/public', 'token': TOKEN}))
    assert uploader.submit(RID, lambda: {})['ok'] is False and not fake.creates


def test_github_paginates_all_issues_and_matches_marker_not_title(monkeypatch):
    client = upload.Github(TOKEN)
    calls = []
    def request(method, path, payload=None):
        calls.append((method, path))
        assert 'per_page=20&' in path
        if path.endswith('&page=1'):
            return [{'number': i + 1, 'body': 'unrelated'} for i in range(20)]
        return [{'number': 987, 'body': upload.marker(RID)}]
    monkeypatch.setattr(client, 'request', request)
    assert client.find(RID)['number'] == 987
    assert len(calls) == 2 and all(m == 'GET' for m, _ in calls)


def test_github_preflight_rejects_public_and_disabled_issues(monkeypatch):
    client = upload.Github(TOKEN)
    for data in [{'private': False, 'has_issues': True}, {'private': True, 'has_issues': False}, {}]:
        monkeypatch.setattr(client, 'request', lambda *a: data)
        with pytest.raises(upload.UploadError):
            client.check_private()


def test_api_upload_is_local_protected_and_passive(site, monkeypatch):
    import diagnostic_relay
    fake = FakeGithub()
    fake.put = lambda rid, report: dict(fake.create(rid, json.dumps(report)), state='sent')
    monkeypatch.setattr(diagnostic_relay, 'Relay', lambda: fake)
    with site(settings={'poll_seconds': 0}) as s:
        configure(s.folder)
        before = list(s.link.raw)
        assert s.client.post('/api/diag/send', json={'report_id': RID}).status_code == 403
        assert s.client.post('/api/diag/send', json={'report_id': RID}, headers={'X-Diag-Upload': '1', 'Origin': 'https://evil.example'}).status_code == 403
        r = s.client.post('/api/diag/send', json={'report_id': RID}, headers={'X-Diag-Upload': '1', 'Host': 'localhost', 'Origin': 'http://localhost'})
        assert r.json()['number'] == 17
        assert list(s.link.raw) == before
        assert TOKEN not in r.text and TOKEN not in s.client.get('/api/diag/upload').text
    with site(local=False) as s:
        assert s.client.post('/api/diag/send', json={'report_id': RID}, headers={'X-Diag-Upload': '1'}).status_code == 403
        assert s.client.get('/api/diag/upload').status_code == 403


def test_pending_errors_are_retryable_in_ui_and_have_safe_message(tmp_path):
    uploader, fake = store(tmp_path)
    fake.lose_reply = True
    result = uploader.submit(RID, lambda: {})
    assert result['ok'] is False and result['state'] == 'pending'
    assert result['err'] and TOKEN not in result['err']


def test_corrupt_journal_never_resets_and_does_not_create(tmp_path):
    uploader, fake = store(tmp_path)
    uploader.path.parent.mkdir(parents=True)
    uploader.path.write_text('{broken')
    assert uploader.submit(RID, lambda: {})['ok'] is False
    assert not fake.creates and uploader.path.read_text() == '{broken'


def test_definite_rejection_reuses_original_body(tmp_path):
    uploader, fake = store(tmp_path)
    create = fake.create
    fake.create = lambda *args: (_ for _ in ()).throw(upload.UploadError('http'))
    assert uploader.submit(RID, lambda: {'old': 1})['state'] == 'rejected'
    fake.create = create
    assert uploader.submit(RID, lambda: pytest.fail())['state'] == 'sent'
    assert json.loads(fake.creates[0][1]) == {'old': 1}


def test_save_failure_after_remote_create_recovers_by_get_only(tmp_path, monkeypatch):
    uploader, fake = store(tmp_path)
    save = uploader._save
    def fail_sent(state):
        if state['reports'][RID]['state'] == 'sent':
            raise OSError('private local path')
        save(state)
    monkeypatch.setattr(uploader, '_save', fail_sent)
    assert uploader.submit(RID, lambda: {})['state'] == 'pending'
    restarted = upload.Uploader(uploader.path, uploader.config_path, lambda _: fake)
    assert restarted.submit(RID, lambda: pytest.fail())['state'] == 'sent'
    assert len(fake.creates) == 1


def test_cached_replies_are_bounded_sanitized_and_not_current(tmp_path):
    folder = tmp_path / 'field-data' / 'auto'
    folder.mkdir(parents=True)
    (folder / '20260101.txt').write_text('## test\n### List Executor 1.1 Thru 1.100  (ok=True)\n' + repr('1.101 SecretShow Running\r\nError #9') + '\n')
    report = upload.collect_report({}, {}, ['SecretShow'], mock=False, root=tmp_path)
    assert report['cached_replies'] and report['cached_current'] is False
    assert 'SecretShow' not in json.dumps(report) and 'row 1.101' in json.dumps(report)
    assert report['console_version'] == 'неизвестно'  # no inference from cached replies


def test_supported_real_states_and_no_fake_evidence():
    for state in ['down', 'tcp', 'login_failed', 'manual_off', 'login_unknown', 'logged_in']:
        assert upload.build_report({'ma2': state, 'mode': 'test'}, {}, [])['ma2'] == state
    assert upload.build_report({'mode': 'test'}, {}, [])['mode'] == 'test'


def test_setup_validates_before_writing_and_protects_credentials(tmp_path, monkeypatch):
    import diagnostic_setup
    fake = FakeGithub()
    monkeypatch.setattr(upload, 'Github', lambda _: fake)
    path = tmp_path / 'diagnostic-upload.json'
    diagnostic_setup.configure(path, TOKEN)
    assert json.loads(path.read_text())['token'] == TOKEN
    if __import__('os').name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600
    fake.private = False
    before = path.read_bytes()
    with pytest.raises(upload.UploadError):
        diagnostic_setup.configure(path, 'new_token')
    assert path.read_bytes() == before


def test_upload_rejects_foreign_host_and_malformed_origin(site):
    with site() as s:
        for headers in [
            {'Host': 'evil.example', 'Origin': 'http://evil.example'},
            {'Host': 'localhost', 'Origin': 'http://['},
            {'Host': 'localhost', 'Origin': 'null'},
        ]:
            r = s.client.post('/api/diag/send', headers={'X-Diag-Upload': '1', **headers}, json={'report_id': RID})
            assert r.status_code == 403


def test_saved_selfcheck_summary_is_reused_without_running_it(tmp_path):
    (tmp_path / 'selfcheck-report.txt').write_text('2026-01-01\nОшибок: 2 из 19\nPrivateOperator SecretShow /Users/private\n')
    report = upload.collect_report({}, {}, [], mock=True, root=tmp_path)
    assert report['selfcheck'] == {'available': True, 'errors': 2, 'checks': 19, 'current': False}
    assert 'SecretShow' not in json.dumps(report)


@pytest.mark.parametrize('name', ['Running Group', 'List Executor', 'Permission denied', 'Status Type'])
def test_free_text_is_removed_even_if_it_looks_like_protocol_vocabulary(tmp_path, name):
    reply = '1.101 ' + name + '\n' + name + '\nError #9: ' + name + '\n[Group]>'
    diag = {'raw': [{'cmd': 'List Executor 1.1 Thru 1.100', 'status': 'sent', 'reply': reply}]}
    report = upload.build_report(diag, {}, [])
    assert name not in report['replies'][0]['reply']
    folder = tmp_path / 'field-data' / 'auto'
    folder.mkdir(parents=True)
    (folder / 'capture.txt').write_text('### List Executor 1.1 Thru 1.100  (ok=True)\n' + repr(reply) + '\n')
    cached = upload.collect_report({}, {}, [], root=tmp_path)
    assert name not in cached['cached_replies'][0]['reply']
    assert '#9' in report['replies'][0]['reply']
