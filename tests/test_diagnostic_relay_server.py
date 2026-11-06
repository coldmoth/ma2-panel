import json
import uuid

from fastapi.testclient import TestClient
import pytest

from ma2panel.diagnostic_upload import UploadError, build_report, collect_report
from scripts.relay.app import create_app


def rid():
    return str(uuid.uuid4())


def report():
    return dict(collect_report({}, {}), description='Synthetic report')


def app(tmp_path, **kw):
    return create_app(tmp_path / 'state', tmp_path / 'credentials.json', worker_interval=3600, **kw)


def put(client, identifier=None, body=None):
    return client.put('/v1/reports/' + (identifier or rid()), json={'report': report() if body is None else body})


def test_durable_idempotent_private_and_conflict(tmp_path):
    identifier = rid()
    with TestClient(app(tmp_path)) as c:
        assert c.get('/health').json() == {'ok': True, 'delivery_ready': False}
        assert put(c, identifier).json() == {'report_id': identifier, 'state': 'queued'}
        assert put(c, identifier).status_code == 200
        assert put(c, identifier, dict(report(), description='changed')).status_code == 409
        assert c.get('/v1/reports/' + identifier).json() == {'report_id': identifier, 'state': 'queued'}
        assert c.get('/v1/reports/' + rid()).status_code == 404
    with TestClient(app(tmp_path)) as c:
        assert put(c, identifier).json()['state'] == 'queued'


@pytest.mark.parametrize('change', [
    {'secret': 'oops'}, {'schema': True}, {'mock': 'yes'}, {'counts': {'fixtures': -1, 'groups': 0, 'scenes': 0}},
    {'ma2': 'anything'}, {'console_version': 'private name'}, {'description': 'x' * 1001},
    {'replies': [{'command': 'Delete Show', 'status': 'ok', 'reply': 'raw secret'}]},
    {'replies': [{'command': 'List Fixture', 'status': 'ok', 'reply': 'name=private'}]},
    {'selfcheck': {'available': False, 'current': False, 'secret': 'private'}},
])
def test_strict_schema(tmp_path, change):
    with TestClient(app(tmp_path)) as c:
        assert put(c, body=dict(report(), **change)).status_code == 422


def test_body_limit_uuid_and_envelope(tmp_path):
    with TestClient(app(tmp_path)) as c:
        assert c.put('/v1/reports/' + rid(), content=b'x' * 65537).status_code == 413
        assert put(c, rid().upper()).status_code == 422
        assert c.put('/v1/reports/' + rid(), json={'report': report(), 'extra': 1}).status_code == 422
        assert put(c, body=build_report({}, {})).status_code == 200


def test_new_quotas_retry_bypasses_and_survives_restart(tmp_path):
    identifier = rid()
    with TestClient(app(tmp_path, per_ip_hour=1)) as c:
        assert put(c, identifier).status_code == 200
        assert put(c).status_code == 429
        assert put(c, identifier).status_code == 200
    with TestClient(app(tmp_path, per_ip_hour=1)) as c:
        assert put(c).status_code == 429
        assert put(c, identifier).status_code == 200


@pytest.mark.parametrize('limits,code', [({'max_reports': 1}, 503), ({'accept_per_minute': 1}, 429)])
def test_capacity_global_admission(tmp_path, limits, code):
    with TestClient(app(tmp_path, **limits)) as c:
        identifier = rid()
        assert put(c, identifier).status_code == 200
        assert put(c).status_code == code
        assert put(c, identifier).status_code == 200


def test_all_requests_bounded_even_idempotent(tmp_path):
    with TestClient(app(tmp_path, requests_per_minute=2)) as c:
        identifier = rid()
        assert put(c, identifier).status_code == 200
        assert put(c, identifier).status_code == 200
        assert put(c, identifier).status_code == 429


class FakeGithub:
    def __init__(self):
        self.created = []
        self.found = {}
        self.uncertain = set()
        self.checked = 0
    def check_private(self):
        self.checked += 1
    def find(self, identifier):
        return self.found.get(identifier)
    def create(self, identifier, body):
        self.created.append(identifier)
        if identifier in self.uncertain:
            raise UploadError('network', ambiguous=True)
        return {'number': 42}


def configured(tmp_path):
    (tmp_path / 'credentials.json').write_text(json.dumps({'repository': 'coldmoth/ma2-panel-diagnostics', 'token': 'synthetic-token'}))


def test_worker_pending_does_not_starve_and_restart_get_only(tmp_path):
    configured(tmp_path)
    github = FakeGithub()
    first, second = rid(), rid()
    github.uncertain.add(first)
    server = app(tmp_path, github_factory=lambda token: github)
    with TestClient(server) as c:
        assert c.get('/health').json()['delivery_ready'] is True
        put(c, first)
        put(c, second)
        server.state.relay.work_once()
        assert c.get('/v1/reports/' + first).json()['state'] == 'pending'
        assert c.get('/v1/reports/' + second).json() == {'report_id': second, 'state': 'sent', 'number': 42}
    server = app(tmp_path, github_factory=lambda token: github)
    with TestClient(server) as c:
        server.state.relay.work_once()
        assert github.created.count(first) == 1
        github.found[first] = {'number': 77}
        server.state.relay.work_once()
        assert c.get('/v1/reports/' + first).json()['number'] == 77


def test_migration_marker_found_without_post_and_creation_quota(tmp_path):
    configured(tmp_path)
    github = FakeGithub()
    existing, first, second = rid(), rid(), rid()
    github.found[existing] = {'number': 10}
    server = app(tmp_path, github_factory=lambda token: github, creates_per_hour=1)
    with TestClient(server) as c:
        for identifier in (existing, first, second):
            put(c, identifier)
        server.state.relay.work_once()
        assert c.get('/v1/reports/' + existing).json()['number'] == 10
        assert github.created == [first]
        assert c.get('/v1/reports/' + second).json()['state'] == 'queued'
    server = app(tmp_path, github_factory=lambda token: github, creates_per_hour=1)
    with TestClient(server) as c:
        server.state.relay.work_once()
        assert github.created == [first]


def test_storage_error_503(tmp_path, monkeypatch):
    server = app(tmp_path)
    with TestClient(server) as c:
        def broken():
            import sqlite3
            raise sqlite3.OperationalError('disk full')
        monkeypatch.setattr(server.state.relay, 'connect', broken)
        assert put(c).status_code == 503
        assert c.get('/v1/reports/' + rid()).status_code == 503
        assert c.get('/health').status_code == 503


def test_journal_sent_survives_missing_sqlite_status_update(tmp_path, monkeypatch):
    configured(tmp_path)
    github = FakeGithub()
    server = app(tmp_path, github_factory=lambda token: github)
    identifier = rid()
    with TestClient(server) as c:
        put(c, identifier)
        uploader = server.state.relay.uploader(identifier)
        uploader.enqueue(identifier, report)
        assert uploader.retry()['state'] == 'sent'
        assert c.get('/v1/reports/' + identifier).json()['state'] == 'queued'
    server = app(tmp_path, github_factory=lambda token: github)
    with TestClient(server) as c:
        server.state.relay.work_once()
        assert c.get('/v1/reports/' + identifier).json()['state'] == 'sent'
        assert github.created == [identifier]


def test_missing_credentials_never_calls_github(tmp_path):
    def forbidden(token):
        raise AssertionError('External client must not be instantiated')
    server = app(tmp_path, github_factory=forbidden)
    with TestClient(server) as c:
        identifier = rid()
        put(c, identifier)
        server.state.relay.work_once()
        assert c.get('/v1/reports/' + identifier).json()['state'] == 'queued'


def test_surrogate_is_invalid_and_real_truncated_reply_accepted(tmp_path):
    # build_report cuts at 1600 characters, potentially inside the last line.
    source = {'raw': [{'cmd': 'ListVar', 'status': 'ok',
                       'reply': '\n'.join('$USERPROFILE=private' for _ in range(60))}]}
    generated = build_report(source, {})
    assert len(generated['replies'][0]['reply']) == 1600
    with TestClient(app(tmp_path)) as c:
        assert c.put('/v1/reports/' + rid(), content=json.dumps({'report': dict(report(), description='\ud800')})).status_code == 422
        assert put(c, body=generated).status_code == 200


def test_precreate_lookup_failure_is_retryable_without_uncertain_post(tmp_path):
    configured(tmp_path)
    github = FakeGithub()
    original_find = github.find
    github.find = lambda identifier: (_ for _ in ()).throw(UploadError('network'))
    server = app(tmp_path, github_factory=lambda token: github)
    with TestClient(server) as c:
        identifier = rid()
        put(c, identifier)
        server.state.relay.work_once()
        assert c.get('/v1/reports/' + identifier).json()['state'] == 'queued'
        assert not github.created
        github.find = original_find
        server.state.relay.work_once()
        assert c.get('/v1/reports/' + identifier).json()['state'] == 'sent'


def test_creation_quota_defers_reads_but_pending_can_reconcile(tmp_path):
    configured(tmp_path)
    github = FakeGithub()
    pending, deferred = rid(), rid()
    github.uncertain.add(pending)
    server = app(tmp_path, github_factory=lambda token: github, creates_per_hour=1)
    with TestClient(server) as c:
        put(c, pending)
        put(c, deferred)
        server.state.relay.work_once()
        assert github.checked == 1  # Deferred queue must not read GitHub.
        assert c.get('/v1/reports/' + deferred).json()['state'] == 'queued'
    github.found[pending] = {'number': 99}
    server = app(tmp_path, github_factory=lambda token: github, creates_per_hour=1)
    with TestClient(server) as c:
        server.state.relay.work_once()
        assert github.checked == 2
        assert c.get('/v1/reports/' + pending).json()['number'] == 99
        server.state.relay.work_once()
        assert github.checked == 2
        with server.state.relay.connect() as db:
            assert db.execute('SELECT next_attempt FROM reports WHERE report_id=?', (deferred,)).fetchone()[0] > 0


def test_actual_paginated_github_requests_have_persistent_budget(tmp_path, monkeypatch):
    from ma2panel.diagnostic_upload import Github
    calls = []
    monkeypatch.setattr(Github, 'request', lambda *args, **kwargs: calls.append(args) or {})
    server = app(tmp_path, github_requests_per_hour=2)
    with TestClient(server):
        client = server.state.relay.github_factory('synthetic')
        client.request('GET', '/repos/coldmoth/ma2-panel-diagnostics')
        client.request('GET', '/repos/coldmoth/ma2-panel-diagnostics/issues?page=2')
        with pytest.raises(UploadError):
            client.request('GET', '/repos/coldmoth/ma2-panel-diagnostics/issues?page=3')
    server = app(tmp_path, github_requests_per_hour=2)
    with TestClient(server):
        with pytest.raises(UploadError):
            server.state.relay.github_factory('synthetic').request('GET', '/repos/coldmoth/ma2-panel-diagnostics')
    assert len(calls) == 2
