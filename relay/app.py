"""Durable, bounded public admission and serialized private GitHub delivery."""
import asyncio
from contextlib import asynccontextmanager, contextmanager, suppress
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from diagnostic_upload import Github, LIMIT, UNKNOWN, PANEL_VERSION_PATTERN, Uploader, UploadError

MAX_BYTES = 65536
_FIXED_REPLY_LINES = ('[command echo]', '[prompt]>', '[unrecognized line]') + tuple(
    '$' + key + '=[value omitted]' for key in ('USER', 'USERPROFILE', 'USERRIGHTS', 'VERSION', 'SHOWFILE', 'PATH'))

def _reply_valid(text):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if _REPLY.fullmatch(line):
            continue
        # build_report truncates at 1600 characters, including within a fixed line.
        if len(text) == 1600 and index == len(lines) - 1 and any(value.startswith(line) for value in _FIXED_REPLY_LINES):
            continue
        return False
    return True

_COMMAND = re.compile(r'(?:List (?:Executor|Fixture|Group|Sequence|Cue|User|Macro|FixtureType|Attribute|Page|Preset)|ListVar|GetVar|ListShows)(?: +[0-9]+(?:\.[0-9]+)?(?: +Thru +[0-9]+(?:\.[0-9]+)?)?)? *')
_REPLY = re.compile(r'(?:Error #[0-9]{1,4}|\$(?:USER|USERPROFILE|USERRIGHTS|VERSION|SHOWFILE|PATH)=\[value omitted\]|\[command echo\]|\[prompt\]>|row [0-9]{1,4}(?:\.[0-9]{1,4})?; cells=[0-9]+|\[unrecognized line\])')


def _valid_report(report):
    """Accept exactly the automatic vocabulary produced by build/collect_report."""
    required = {'schema', 'mock', 'console_version', 'panel_version', 'counts', 'ma2', 'mode', 'replies', 'truncated'}
    optional = {'cached_replies', 'cached_current', 'cached_available', 'selfcheck', 'description', 'captured_at'}
    if not isinstance(report, dict) or not required <= report.keys() or report.keys() - required - optional:
        return False
    if type(report['schema']) is not int or report['schema'] != 1:
        return False
    if any(type(report[k]) is not bool for k in ('mock', 'truncated')):
        return False
    for key, pattern in [('console_version', r'[0-9]{1,4}(?:\.[0-9]{1,4}){1,5}'), ('panel_version', PANEL_VERSION_PATTERN)]:
        value = report[key]
        if not isinstance(value, str) or (value != UNKNOWN and not re.fullmatch(pattern, value)):
            return False
    counts = report['counts']
    if not isinstance(counts, dict) or set(counts) != {'fixtures', 'groups', 'scenes'} or any(type(n) is not int or not 0 <= n <= 1000000 for n in counts.values()):
        return False
    if report['ma2'] not in ('down', 'tcp', 'login_failed', 'manual_off', 'login_unknown', 'logged_in', UNKNOWN) or report['mode'] not in ('full', 'read', 'test', UNKNOWN):
        return False
    for key in ('replies', 'cached_replies'):
        if key not in report:
            continue
        replies = report[key]
        if not isinstance(replies, list) or len(replies) > 20:
            return False
        for row in replies:
            if not isinstance(row, dict) or set(row) != {'command', 'status', 'reply'}:
                return False
            if not isinstance(row['command'], str) or (row['command'] != UNKNOWN and not _COMMAND.fullmatch(row['command'])):
                return False
            if row['status'] not in ('sent', 'ok', 'error', 'timeout', 'received', 'failed', UNKNOWN):
                return False
            text = row['reply']
            if not isinstance(text, str) or len(text) > 1600 or not _reply_valid(text):
                return False
    for key in ('cached_current', 'cached_available'):
        if key in report and (type(report[key]) is not bool or key == 'cached_current' and report[key] is not False):
            return False
    if 'selfcheck' in report:
        check = report['selfcheck']
        if not isinstance(check, dict) or set(check) not in ({'available', 'current'}, {'available', 'current', 'errors', 'checks'}):
            return False
        if type(check['available']) is not bool or check['current'] is not False:
            return False
        if check['available'] != ('errors' in check):
            return False
        if any(type(check[k]) is not int or not 0 <= check[k] <= 999999 for k in ('errors', 'checks') if k in check):
            return False
    if 'description' in report and (not isinstance(report['description'], str) or len(report['description']) > 1000):
        return False
    if 'captured_at' in report:
        value = report['captured_at']
        if not isinstance(value, str) or len(value) > 40:
            return False
        try:
            if datetime.fromisoformat(value).tzinfo is None:
                return False
        except ValueError:
            return False
    serialized = json.dumps(report, ensure_ascii=False, allow_nan=False)
    serialized.encode('utf-8')  # Reject escaped unpaired surrogates before persistence.
    return len(serialized) <= LIMIT


def _identifier(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, 'Invalid report identifier') from None
    return value


class Receiver:
    def __init__(self, data_dir, credentials_path, github_factory, limits):
        self.directory = Path(data_dir)
        self.credentials_path = Path(credentials_path)
        self.limits = limits
        self.worker_lock = threading.Lock()
        receiver = self
        class BudgetGithub(Github):
            def request(self, method, path, payload=None):
                receiver.reserve_api_request()
                return super().request(method, path, payload)
        self.github_factory = github_factory or BudgetGithub

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.directory / 'reports.sqlite3', timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA synchronous=FULL')
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY, body TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'queued', number INTEGER, accepted REAL NOT NULL,
                    next_attempt REAL NOT NULL DEFAULT 0, last_attempt REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS events (kind TEXT NOT NULL, ip TEXT NOT NULL, at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS events_kind_at ON events(kind, at);
            ''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(reports)')}
            for column in ('next_attempt', 'last_attempt'):
                if column not in columns:
                    db.execute('ALTER TABLE reports ADD COLUMN ' + column + ' REAL NOT NULL DEFAULT 0')
        os.chmod(self.directory / 'reports.sqlite3', 0o600)

    def cleanup(self, db, now):
        db.execute("DELETE FROM events WHERE at <= ? OR (kind='request' AND at <= ?)", (now - 3600, now - 60))

    def request_quota(self):
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.cleanup(db, now)
            n = db.execute("SELECT count(*) FROM events WHERE kind='request' AND at>?", (now - 60,)).fetchone()[0]
            if n >= self.limits['requests_per_minute']:
                raise HTTPException(429, 'Request limit exceeded')
            db.execute("INSERT INTO events VALUES ('request','',?)", (now,))

    @staticmethod
    def receipt(row):
        result = {'report_id': row['report_id'], 'state': row['state']}
        if row['state'] == 'sent':
            result['number'] = row['number']
        return result

    def status(self, identifier):
        with self.connect() as db:
            row = db.execute('SELECT report_id,state,number FROM reports WHERE report_id=?', (identifier,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Unknown report')
        return self.receipt(row)

    def accept(self, identifier, report, ip):
        body = json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False)
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.cleanup(db, now)
            row = db.execute('SELECT * FROM reports WHERE report_id=?', (identifier,)).fetchone()
            if row:
                if row['body'] != body:
                    raise HTTPException(409, 'Identifier already contains a different report')
                return self.receipt(row)
            if db.execute('SELECT count(*) FROM reports').fetchone()[0] >= self.limits['max_reports']:
                raise HTTPException(503, 'Report storage capacity reached')
            total = db.execute("SELECT count(*) FROM events WHERE kind='accept' AND at>?", (now - 60,)).fetchone()[0]
            per_ip = db.execute("SELECT count(*) FROM events WHERE kind='accept' AND ip=? AND at>?", (ip, now - 3600)).fetchone()[0]
            if total >= self.limits['accept_per_minute'] or per_ip >= self.limits['per_ip_hour']:
                raise HTTPException(429, 'New report limit exceeded')
            db.execute('INSERT INTO reports(report_id,body,accepted) VALUES (?,?,?)', (identifier, body, now))
            db.execute("INSERT INTO events VALUES ('accept',?,?)", (ip, now))
        return {'report_id': identifier, 'state': 'queued'}

    def reserve_create(self):
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.cleanup(db, now)
            count = db.execute("SELECT count(*) FROM events WHERE kind='create' AND at>?", (now - 3600,)).fetchone()[0]
            if count >= self.limits['creates_per_hour']:
                # Definitely no POST was made: Uploader may retry this rejected attempt.
                raise UploadError('http')
            db.execute("INSERT INTO events VALUES ('create','',?)", (now,))

    def quota_until(self, kind, limit):
        now = time.time()
        with self.connect() as db:
            count, first = db.execute('SELECT count(*),min(at) FROM events WHERE kind=? AND at>?',
                                      (kind, now - 3600)).fetchone()
        return first + 3600.01 if count >= limit else 0

    def reserve_api_request(self):
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.cleanup(db, now)
            count = db.execute("SELECT count(*) FROM events WHERE kind='github' AND at>?", (now - 3600,)).fetchone()[0]
            if count >= self.limits['github_requests_per_hour']:
                # The denied request has not reached GitHub, including POST.
                raise UploadError('http')
            db.execute("INSERT INTO events VALUES ('github','',?)", (now,))

    def uploader(self, identifier):
        receiver = self
        class MigrationGithub:
            def __init__(self, token):
                self.client = receiver.github_factory(token)
            def check_private(self):
                return self.client.check_private()
            def find(self, rid):
                return self.client.find(rid)
            def create(self, rid, body):
                # Search first even on the initial attempt: it may be a migrated UUID.
                try:
                    found = self.client.find(rid)
                    if found is not None:
                        return found
                    receiver.reserve_create()
                except Exception:
                    # All failures here precede POST. Preserve retryability; the
                    # Uploader's unambiguous HTTP rejection branch persists it.
                    raise UploadError('http') from None
                return self.client.create(rid, body)
        return Uploader(self.directory / 'journals' / identifier / 'upload.json', self.credentials_path,
                        github_factory=MigrationGithub)

    def ready(self):
        try:
            self.uploader('health')._credentials()
            return True
        except UploadError:
            return False

    def work_once(self):
        # One worker/process; the systemd unit runs uvicorn with a single worker.
        with self.worker_lock:
            if not self.ready():
                return
            with self.connect() as db:
                rows = db.execute("SELECT report_id,body FROM reports WHERE state!='sent' AND next_attempt<=? "
                                  "ORDER BY last_attempt,accepted,report_id LIMIT 20", (time.time(),)).fetchall()
            for row in rows:
                try:
                    identifier = row['report_id']
                    uploader = self.uploader(identifier)
                    status = uploader.status()
                    if status.get('error') == 'storage':
                        continue
                    next_attempt = self.quota_until('github', self.limits['github_requests_per_hour'])
                    if status['state'] not in ('pending', 'sent'):
                        next_attempt = max(next_attempt, self.quota_until('create', self.limits['creates_per_hour']))
                    with self.connect() as db:
                        db.execute('UPDATE reports SET last_attempt=?,next_attempt=? WHERE report_id=?',
                                   (time.time(), next_attempt, identifier))
                    if next_attempt and status['state'] != 'sent':
                        continue
                    if status['state'] == 'idle':
                        result = uploader.enqueue(identifier, lambda: json.loads(row['body']))
                        if not result.get('ok'):
                            continue
                    uploader.retry()
                    status = uploader.status()
                    if status.get('error') == 'storage':
                        continue
                    state = status['state'] if status['state'] in ('pending', 'sent') else 'queued'
                    with self.connect() as db:
                        db.execute('UPDATE reports SET state=?,number=? WHERE report_id=?', (state, status.get('number'), identifier))
                except Exception:
                    # Persisted journals decide retry safety; no payloads in logs.
                    continue


def create_app(data_dir, credentials_path, *, github_factory=None, max_reports=5000,
               accept_per_minute=20, per_ip_hour=5, creates_per_hour=30,
               requests_per_minute=120, github_requests_per_hour=1000, worker_interval=60):
    limits = dict(max_reports=max_reports, accept_per_minute=accept_per_minute,
                  per_ip_hour=per_ip_hour, creates_per_hour=creates_per_hour,
                  requests_per_minute=requests_per_minute, github_requests_per_hour=github_requests_per_hour)
    if any(type(v) is not int or v <= 0 for v in limits.values()) or worker_interval <= 0:
        raise ValueError('Limits must be positive')
    receiver = Receiver(data_dir, credentials_path, github_factory, limits)

    async def worker():
        while True:
            try:
                await asyncio.to_thread(receiver.work_once)
            except Exception:
                pass
            await asyncio.sleep(worker_interval)

    @asynccontextmanager
    async def lifespan(app):
        # A damaged/full disk is exposed as HTTP 503, including health.
        try:
            receiver.initialize()
        except (OSError, sqlite3.Error):
            pass
        task = asyncio.create_task(worker())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.relay = receiver

    @app.middleware('http')
    async def bounded_requests(request, call_next):
        try:
            await asyncio.to_thread(receiver.request_quota)
            return await call_next(request)
        except HTTPException as exc:
            return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
        except (OSError, sqlite3.Error):
            return JSONResponse({'detail': 'Storage unavailable'}, status_code=503)

    @app.get('/health')
    def health():
        with receiver.connect() as db:
            db.execute('SELECT count(*) FROM reports').fetchone()
        return {'ok': True, 'delivery_ready': receiver.ready()}

    @app.get('/v1/reports/{identifier}')
    def status(identifier: str):
        return receiver.status(_identifier(identifier))

    @app.put('/v1/reports/{identifier}')
    async def accept(identifier: str, request: Request):
        _identifier(identifier)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BYTES:
                raise HTTPException(413, 'Report too large')
        try:
            def unique_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError()
                    result[key] = value
                return result
            data = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            valid = isinstance(data, dict) and set(data) == {'report'} and _valid_report(data['report'])
        except (ValueError, TypeError, RecursionError, UnicodeError):
            valid = False
        if not valid:
            raise HTTPException(422, 'Invalid report schema')
        return await asyncio.to_thread(receiver.accept, identifier, data['report'], request.client.host if request.client else 'unknown')

    return app


def configured_app():
    """uvicorn --factory relay.app:configured_app (loopback only)."""
    return create_app(os.environ.get('MA2_DIAGNOSTICS_STATE', '/var/lib/ma2-diagnostics'),
                      os.environ.get('MA2_DIAGNOSTICS_CREDENTIALS', '/etc/ma2-diagnostics/github.json'))
