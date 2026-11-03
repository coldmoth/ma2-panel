"""Privacy-limited diagnostic reports and durable, single-destination uploads."""
import ast
import asyncio
import contextlib
import http.client
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import uuid

REPOSITORY = 'coldmoth/ma2-panel-diagnostics'
BASE = '/repos/' + REPOSITORY
UNKNOWN = 'неизвестно'
PANEL_VERSION_PATTERN = (r'(?:[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}(?:rc[0-9]{1,4})?'
                         r'(?:\+(?:[0-9a-f]{7,40}(?:-dirty)?|nogit))?'
                         r'|20[0-9]{2}-[01][0-9]-[0-3][0-9]_[0-2][0-9][0-5][0-9] [0-9a-f]{7,40}(?:\+dirty)?)')
LIMIT = 48000
RETRY_SECONDS = 60
_LOCK = threading.Lock()
_ERRORS = {
    'config': 'Загрузка не настроена.', 'storage': 'Ошибка хранения отчёта.',
    'invalid': 'Некорректный идентификатор отчёта.', 'collection': 'Не удалось собрать отчёт.',
    'size': 'Отчёт слишком большой.', 'busy': 'Загрузка уже выполняется.',
    'private': 'Нужен закрытый репозиторий с включёнными Issues.',
    'network': 'Ошибка связи с сервисом диагностики.', 'http': 'GitHub отклонил запрос.',
    'response': 'Некорректный ответ GitHub.', 'pending': 'Результат отправки пока неизвестен.',
    'relay_http': 'Сервис диагностики временно не принимает отчёт.',
    'relay_response': 'Некорректная квитанция сервиса диагностики.',
    'relay_conflict': 'Сервис уже получил другой снимок с этим номером. Нужна проверка владельцем.',
    'relay_limit': 'Сервис диагностики перегружен. Мост повторит попытку позже.',
    'legacy_config': 'Старая отправка в GitHub не завершена. Владельцу нужно восстановить прежний доступ для проверки; новый отчёт не создаётся.'
}


class UploadError(Exception):
    def __init__(self, code, ambiguous=False):
        self.code = code if code in _ERRORS else 'response'
        self.ambiguous = bool(ambiguous)
        super().__init__(self.code)


def _uuid(value):
    if not isinstance(value, str):
        raise UploadError('invalid')
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError):
        raise UploadError('invalid') from None
    return value


def marker(report_id):
    return '<!-- ma2-diagnostics:' + _uuid(report_id) + ' -->'


def _number(data):
    n = data.get('number') if isinstance(data, dict) else None
    if type(n) is not int or n <= 0:
        raise UploadError('response', ambiguous=True)
    return n


def build_report(diag, cfg, private=(), mock=False):
    diag = diag if isinstance(diag, dict) else {}
    cfg = cfg if isinstance(cfg, dict) else {}
    secrets = tuple(p for p in private if isinstance(p, str) and p)
    def clean(value):
        text = value[:8192] if isinstance(value, str) else ''
        for p in sorted(secrets, key=len, reverse=True):
            text = text.replace(p, '_')
        return text
    def choice(value, allowed):
        return value if isinstance(value, str) and value in allowed and clean(value) == value else UNKNOWN
    login = diag.get('login_vars')
    version = clean(login.get('VERSION')) if isinstance(login, dict) else ''
    if not re.fullmatch(r'[0-9]{1,4}(?:\.[0-9]{1,4}){1,5}', version):
        version = UNKNOWN
    panel = clean(diag.get('version'))
    if not re.fullmatch(PANEL_VERSION_PATTERN, panel):
        panel = UNKNOWN
    commands = ('List Executor', 'List Fixture', 'List Group', 'List Sequence',
                'List Cue', 'List User', 'ListVar', 'GetVar', 'List Macro',
                'List FixtureType', 'List Attribute', 'List Page', 'List Preset', 'ListShows')

    raw = diag.get('raw')
    raw = raw if isinstance(raw, list) else []
    report = {'schema': 1, 'mock': bool(mock), 'console_version': version,
              'panel_version': panel,
              'counts': {k: len(cfg[k]) if isinstance(cfg.get(k), (list, dict)) else 0
                         for k in ('fixtures', 'groups', 'scenes')},
              'ma2': choice(diag.get('ma2'), ('down', 'tcp', 'login_failed', 'manual_off', 'login_unknown', 'logged_in')),
              'mode': choice(diag.get('mode'), ('full', 'read', 'test')),
              'replies': [], 'truncated': len(raw) > 20}
    for item in raw[-20:]:
        if not isinstance(item, dict):
            report['truncated'] = True
            continue
        cmd = clean(item.get('cmd', item.get('command')))
        command = next((c for c in commands if re.fullmatch(re.escape(c) + r'(?: +[0-9]+(?:\.[0-9]+)?(?: +Thru +[0-9]+(?:\.[0-9]+)?)?)? *', cmd)), UNKNOWN)
        original = item.get('reply')
        text = clean(original)
        if isinstance(original, str) and len(original) > 8192:
            report['truncated'] = True
        lines = []
        for line in text.splitlines()[:60]:
            # Recognize positions in the protocol, never retain vocabulary from name columns.
            # Cached captures can contain names no longer present in the current configuration.
            error = re.fullmatch(r'\s*Error\s+#([0-9]{1,4})(?:\b.*)?', line)
            variable = re.fullmatch(r'\s*(?:Global\s*:\s*)?\$(USER|USERPROFILE|USERRIGHTS|VERSION|SHOWFILE|PATH)\s*[=:].*', line)
            row = re.fullmatch(r'\s*([0-9]{1,4}(?:\.[0-9]{1,4})?)\s+(.+)', line)
            if error:
                lines.append('Error #' + error[1])
            elif variable and command == 'ListVar':
                lines.append('$' + variable[1] + '=[value omitted]')
            elif command != UNKNOWN and line.strip() == 'Executing : ' + cmd.strip():
                lines.append('[command echo]')
            elif re.fullmatch(r'\s*\[[^\]\r\n]*\]>\s*', line):
                lines.append('[prompt]>')
            elif row and command.startswith('List '):
                cells = len(re.findall(r'"[^"\r\n]*"|\S+', row[2]))
                lines.append('row ' + row[1] + '; cells=' + str(cells))
            elif line.strip():
                lines.append('[unrecognized line]')
        reply = '\n'.join(lines)[:1600]
        report['replies'].append({'command': command,
            'status': choice(item.get('status'), ('sent', 'ok', 'error', 'timeout', 'received', 'failed')),
            'reply': reply})
    while len(json.dumps(report, ensure_ascii=False)) > LIMIT:
        report['replies'].pop(0)
        report['truncated'] = True
    return report



def collect_report(diag, cfg, private=(), mock=False, root=None):
    """Reuse startup captures as explicitly historical evidence; never run a probe."""
    report = build_report(diag, cfg, private, mock=mock)
    report.update(cached_replies=[], cached_current=False, cached_available=False,
                  selfcheck={'available': False, 'current': False})
    if root is None:
        return report
    try:
        with (Path(root) / 'selfcheck-report.txt').open('rb') as stream:
            summary = stream.read(4096).decode('utf-8', errors='replace')
        found = re.search(r'^Ошибок: ([0-9]{1,6}) из ([0-9]{1,6})$', summary, re.M)
        if found:
            report['selfcheck'].update(available=True, errors=int(found[1]), checks=int(found[2]))
    except OSError:
        pass
    try:
        files = sorted((Path(root) / 'field-data' / 'auto').glob('*.txt'))
        if not files:
            return report
        with files[-1].open('rb') as stream:
            data = stream.read(65537)
        report['cached_available'] = True
        if len(data) > 65536:
            report['truncated'] = True
        # capture_replies writes one repr(string) line for each ### command.
        rows = []
        chunks = re.split(r'^### (.+?)  \(ok=(True|False)\)\s*$', data[:65536].decode('utf-8', errors='replace'), flags=re.M)
        for i in range(1, len(chunks), 3):
            if len(rows) >= 20:
                report['truncated'] = True
                break
            try:
                reply = ast.literal_eval(chunks[i + 2].strip().splitlines()[0])
            except (ValueError, SyntaxError, IndexError, MemoryError, RecursionError):
                report['truncated'] = True
                continue
            if isinstance(reply, str):
                rows.append({'cmd': chunks[i], 'status': 'sent' if chunks[i + 1] == 'True' else 'error', 'reply': reply})
        report['cached_replies'] = build_report({'raw': rows}, {}, private)['replies']
    except OSError:
        report['cached_available'] = False
    while len(json.dumps(report, ensure_ascii=False)) > LIMIT:
        key = 'cached_replies' if report['cached_replies'] else 'replies'
        report[key].pop(0)
        report['truncated'] = True
    return report


class Github:
    def __init__(self, token):
        self.token = token

    def request(self, method, path, payload=None):
        if (method not in ('GET', 'POST') or not isinstance(path, str)
                or not (path == BASE or path.startswith(BASE + '/') or path.startswith(BASE + '?'))
                or any(c.isspace() or ord(c) < 32 for c in path)
                or '#' in path or '\\' in path or '..' in path):
            raise UploadError('response')
        conn = None
        posting = method == 'POST'
        try:
            conn = http.client.HTTPSConnection('api.github.com', timeout=10)
            headers = {'Authorization': 'Bearer ' + self.token,
                       'User-Agent': 'ma2-panel-diagnostics',
                       'Accept': 'application/vnd.github+json',
                       'X-GitHub-Api-Version': '2022-11-28'}
            body = None
            if payload is not None:
                body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
                headers['Content-Type'] = 'application/json'
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            status = response.status
            if not 200 <= status < 300:
                raise UploadError('http', posting and status not in (401, 403, 404, 410, 422))
            data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise UploadError('response', posting)
            try:
                return json.loads(data)
            except (ValueError, UnicodeError):
                raise UploadError('response', posting) from None
        except UploadError:
            raise
        except Exception:
            raise UploadError('network', posting) from None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def check_private(self):
        data = self.request('GET', BASE)
        if not isinstance(data, dict) or data.get('private') is not True or data.get('has_issues') is not True or data.get('archived', False) is not False:
            raise UploadError('private')

    def find(self, report_id):
        tag = marker(report_id)
        page = 1
        # A page of 100 maximum-size reports exceeds the bounded 2 MiB response.
        page_size = 20
        while True:
            rows = self.request('GET', BASE + '/issues?state=all&per_page=' + str(page_size) + '&page=' + str(page))
            if not isinstance(rows, list) or len(rows) > page_size:
                raise UploadError('response')
            for row in rows:
                if not isinstance(row, dict):
                    raise UploadError('response')
                if 'pull_request' in row:
                    continue
                body = row.get('body')
                if body is not None and not isinstance(body, str):
                    raise UploadError('response')
                if body and tag in body:
                    _number(row)
                    return row
            if len(rows) < page_size:
                return None
            page += 1

    def create(self, report_id, body):
        tag = marker(report_id)
        data = self.request('POST', BASE + '/issues', {
            'title': 'MA2 diagnostics ' + report_id,
            'body': tag + '\n\n```json\n' + body + '\n```'})
        _number(data)
        return data


class Uploader:
    def __init__(self, path, config_path, github_factory=None):
        self.path = Path(path)
        self.config_path = Path(config_path)
        self.github_factory = github_factory
        self._wake = asyncio.Event()

    def _credentials(self):
        try:
            with self.config_path.open('rb') as stream:
                raw = stream.read(8193)
            if len(raw) > 8192:
                raise ValueError()
            data = json.loads(raw)
            token = data['token']
            if data['repository'] != REPOSITORY or not isinstance(token, str) or not token or len(token.encode('utf-8')) > 512 or any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in token):
                raise ValueError()
            return token
        except Exception:
            raise UploadError('config') from None

    def _load(self):
        try:
            try:
                raw = self.path.read_bytes()
            except FileNotFoundError:
                return {'current': None, 'reports': {}}
            data = json.loads(raw)
            if not isinstance(data, dict) or not isinstance(data['reports'], dict):
                raise ValueError()
            for rid, row in data['reports'].items():
                _uuid(rid)
                if not isinstance(row, dict) or row.get('report_id') != rid or row.get('state') not in ('queued', 'prepared', 'pending', 'rejected', 'accepted', 'sent') or not isinstance(row.get('body'), str) or len(row['body']) > LIMIT:
                    raise ValueError()
                if row.get('transport') not in (None, 'github', 'relay'):
                    raise ValueError()
                if 'auto_send' in row and type(row['auto_send']) is not bool:
                    raise ValueError()
                json.loads(row['body'])
                if row['state'] == 'sent':
                    _number(row)
            if data.get('current') is not None and data['current'] not in data['reports']:
                raise ValueError()
            return data
        except Exception:
            raise UploadError('storage') from None

    def _save(self, state):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        temp = None
        try:
            fd, temp = tempfile.mkstemp(prefix='.upload-', dir=self.path.parent)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                os.chmod(temp, 0o600)
                json.dump(state, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
            temp = None
            if os.name != 'nt':
                fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            if temp is not None:
                os.unlink(temp)

    @contextlib.contextmanager
    def _process_lock(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(str(self.path) + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
        locked = False
        try:
            try:
                if os.name == 'nt':
                    import msvcrt
                    if os.fstat(fd).st_size == 0:
                        os.write(fd, b'0')
                    os.lseek(fd, 0, 0)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                raise UploadError('busy') from None
            yield
        finally:
            if locked:
                if os.name == 'nt':
                    os.lseek(fd, 0, 0)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _result(self, configured, row=None, error=None):
        result = {'ok': error is None, 'configured': configured, 'repository': REPOSITORY,
                  'state': row['state'] if row else 'idle'}
        if self._uses_relay(row):
            result['transport'] = 'relay'
        if row:
            result['report_id'] = row['report_id']
            result['automatic'] = bool(row.get('auto_send'))
            if row['state'] == 'sent':
                number = _number(row)
                result.update(number=number, url='https://github.com/' + REPOSITORY + '/issues/' + str(number))
        if error:
            result.update(error=error, err=_ERRORS.get(error, _ERRORS['response']))
        elif row and row['state'] != 'sent' and row.get('last_error') in _ERRORS:
            result.update(error=row['last_error'], err=_ERRORS[row['last_error']])
        return result

    def enqueue(self, report_id, collect):
        """Persist explicit consent and a snapshot without making any network request."""
        with _LOCK:
            configured, token = False, None
            try:
                _uuid(report_id)
                try:
                    token = self._credentials()
                    configured = True
                except UploadError:
                    pass
                with self._process_lock():
                    state = self._load()
                    current = state['reports'].get(state.get('current'))
                    configured = configured or self._uses_relay(current)
                    if current and current['state'] != 'sent' and current['report_id'] != report_id:
                        return self._result(configured, current, 'busy')
                    row = state['reports'].get(report_id)
                    if row and row['state'] == 'sent':
                        return self._result(configured, row)
                    if row is None:
                        try:
                            body = json.dumps(collect(), ensure_ascii=False, allow_nan=False)
                        except Exception:
                            return self._result(configured, error='collection')
                        if len(body) > LIMIT:
                            return self._result(configured, error='size')
                        if token and token in body:
                            return self._result(configured, error='collection')
                        row = {'report_id': report_id, 'state': 'queued', 'body': body}
                    state['reports'][report_id] = dict(row, auto_send=True)
                    state['current'] = report_id
                    self._save(state)
                    return self._result(configured, state['reports'][report_id])
            except UploadError as exc:
                return self._result(configured, error=exc.code)
            except Exception:
                return self._result(configured, error='storage')

    def retry(self):
        """Deliver only explicitly queued reports; uncertain POSTs remain GET-only."""
        with _LOCK:
            configured = False
            try:
                with self._process_lock():
                    state = self._load()
                    row = state['reports'].get(state.get('current'))
                    if not row or not row.get('auto_send') or row['state'] == 'sent':
                        return None
                    if self._uses_relay(row):
                        configured = True
                        result = self._submit_relay(row['report_id'], lambda: None)
                    else:
                        token = self._direct_credentials(row)
                        configured = True
                        result = self._submit(row['report_id'], lambda: None, token)
                    state = self._load()
                    updated = state['reports'][row['report_id']]
                    if result.get('error'):
                        updated['last_error'] = result['error']
                    else:
                        updated.pop('last_error', None)
                    self._save(state)
                    return result
            except UploadError as exc:
                return self._result(configured, error=exc.code)
            except Exception:
                return self._result(configured, error='storage')

    def wake(self):
        # Called by the API on the event loop, never by the worker thread.
        self._wake.set()

    async def run(self):
        while True:
            self._wake.clear()
            await asyncio.to_thread(self.retry)
            try:
                await asyncio.wait_for(self._wake.wait(), RETRY_SECONDS)
            except TimeoutError:
                pass

    def status(self):
        configured = False
        try:
            self._credentials()
            configured = True
        except UploadError:
            pass
        try:
            state = self._load()
            row = state['reports'].get(state.get('current'))
            configured = configured or self._uses_relay(row)
            if not configured and self.github_factory is None and row and row['state'] == 'pending':
                return self._result(False, row, 'legacy_config')
            return self._result(configured, row)
        except UploadError:
            return self._result(configured, error='storage')

    def submit(self, report_id, collect):
        with _LOCK:
            configured = False
            try:
                _uuid(report_id)
                with self._process_lock():
                    state = self._load()
                    row = state['reports'].get(report_id)
                    if self._uses_relay(row):
                        configured = True
                        return self._submit_relay(report_id, collect)
                    token = self._direct_credentials(row)
                    configured = True
                    return self._submit(report_id, collect, token)
            except UploadError as exc:
                return self._result(configured, error=exc.code)
            except Exception:
                return self._result(configured, error='storage')

    def _uses_relay(self, row=None):
        # An old ambiguous GitHub POST must remain GET-only on that transport.
        return (self.github_factory is None and
                (not row or row.get('transport') != 'github' and
                 (row.get('transport') == 'relay' or row.get('state') != 'pending')))

    def _direct_credentials(self, row):
        try:
            return self._credentials()
        except UploadError:
            if self.github_factory is None and row and row['state'] == 'pending':
                raise UploadError('legacy_config') from None
            raise

    def _submit_relay(self, rid, collect):
        from diagnostic_relay import Relay
        state = self._load()
        current = state['reports'].get(state.get('current'))
        if current and current['state'] != 'sent' and current['report_id'] != rid:
            return self._result(True, current, 'busy')
        row = state['reports'].get(rid)
        if row and row['state'] == 'sent':
            return self._result(True, row)
        if row is None:
            try:
                body = json.dumps(collect(), ensure_ascii=False, allow_nan=False)
            except Exception:
                return self._result(True, error='collection')
            if len(body) > LIMIT:
                return self._result(True, error='size')
            row = {'report_id': rid, 'body': body, 'state': 'queued'}
        # Pin transport before the request. Retrying PUT after a lost reply is safe.
        row = dict(row, transport='relay')
        state['reports'][rid] = row
        state['current'] = rid
        self._save(state)
        try:
            receipt = Relay().put(rid, json.loads(row['body']))
        except UploadError as exc:
            return self._result(True, row, exc.code)
        updated = dict(row, state='sent' if receipt['state'] == 'sent' else 'accepted')
        if receipt['state'] == 'sent':
            updated['number'] = _number(receipt)
        state['reports'][rid] = updated
        self._save(state)
        return self._result(True, updated)

    def _submit(self, rid, collect, token):
        state = self._load()
        current = state['reports'].get(state.get('current'))
        if current and (current['state'] == 'pending' or current.get('auto_send') and current['state'] != 'sent') and current['report_id'] != rid:
            return self._result(True, current, 'pending')
        row = state['reports'].get(rid)
        if row and row['state'] == 'sent':
            return self._result(True, row)
        if row and token in row['body']:
            return self._result(True, row, 'collection')
        client = (self.github_factory or Github)(token)
        if row and row['state'] == 'pending':
            try:
                client.check_private()
                found = client.find(rid)
                if found is None:
                    return self._result(True, row, 'pending')
                number = _number(found)
                updated = dict(row, state='sent', number=number)
                state['reports'][rid] = updated
                self._save(state)
                return self._result(True, updated)
            except UploadError as exc:
                return self._result(True, row, exc.code)
            except Exception:
                return self._result(True, row, 'storage')
        if row is None:
            try:
                body = json.dumps(collect(), ensure_ascii=False, allow_nan=False)
            except Exception:
                return self._result(True, error='collection')
            if len(body) > LIMIT:
                return self._result(True, error='size')
            if token in body:
                return self._result(True, error='collection')
            row = {'report_id': rid, 'body': body, 'state': 'prepared'}
            state['reports'][rid] = row
        state['current'] = rid
        try:
            self._save(state)
        except Exception:
            return self._result(True, error='storage')
        try:
            client.check_private()
        except UploadError as exc:
            return self._result(True, row, exc.code)
        except Exception:
            return self._result(True, row, 'network')
        pending = dict(row, state='pending')
        state['reports'][rid] = pending
        try:
            self._save(state)
        except Exception:
            return self._result(True, row, 'storage')
        try:
            created = client.create(rid, row['body'])
            number = _number(created)
        except UploadError as exc:
            if not exc.ambiguous and exc.code == 'http':
                rejected = dict(row, state='rejected')
                state['reports'][rid] = rejected
                try:
                    self._save(state)
                except Exception:
                    return self._result(True, pending, 'storage')
                return self._result(True, rejected, exc.code)
            return self._result(True, pending, exc.code)
        except Exception:
            return self._result(True, pending, 'network')
        sent = dict(row, state='sent', number=number)
        state['reports'][rid] = sent
        try:
            self._save(state)
        except Exception:
            return self._result(True, pending, 'storage')
        return self._result(True, sent)
