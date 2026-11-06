"""On-site administration never sends settings to the console; diagnostics redact secrets."""
import io
import json
import logging
import re
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ma2panel import bridge
from ma2panel.safety import READ


@pytest.fixture
def site(tmp_path, monkeypatch):
    (tmp_path / 'static').symlink_to(bridge.HERE / 'static', target_is_directory=True)
    monkeypatch.setattr(bridge, 'HERE', tmp_path)
    real_link = bridge.MA2Link
    links = []

    def capture(*args, **kwargs):
        link = real_link(*args, **kwargs)
        links.append(link)
        return link

    monkeypatch.setattr(bridge, 'MA2Link', capture)
    monkeypatch.delenv('MA2_PASSWORD', raising=False)
    real_mock = bridge.start_mock

    async def echo_mock(*args, **kwargs):
        mock = await real_mock(*args, **kwargs)
        mock.echo = True
        return mock

    monkeypatch.setattr(bridge, 'start_mock', echo_mock)

    @contextmanager
    def start(local=True, password='', settings=None):
        monkeypatch.setattr(bridge, 'is_loopback', lambda request: local)
        cfg = json.loads(Path('tests/config.test.json').read_text())
        cfg['ma2']['export_dir'] = str(tmp_path)
        config = tmp_path / 'config.json'
        config.write_text(json.dumps(cfg))
        path = tmp_path / 'settings.json'
        settings = settings if settings is not None else {'unknown': {'keep': [1, 2]}}
        path.write_text(json.dumps(settings))
        if password:
            (tmp_path / 'secret.env').write_text('MA2_PASSWORD=' + password + '\n')
        app = bridge.create_app(cfg, True, str(config), settings=settings, password=password, settings_path=path)
        app.state.server = SimpleNamespace(should_exit=False)
        with TestClient(app) as client:
            deadline = time.monotonic() + 3
            while client.get('/api/diag').json()['ma2'] != 'logged_in':
                assert time.monotonic() < deadline
                time.sleep(.02)
            yield SimpleNamespace(client=client, app=app, path=path, folder=tmp_path, link=links[-1], mock=app.state.mock)
    return start


def test_loopback_is_strict():
    for host in ['127.0.0.1', '::1', 'testclient', '192.168.0.2', '127.0.0.2']:
        request = SimpleNamespace(client=SimpleNamespace(host=host))
        assert bridge.is_loopback(request) == (host in ('127.0.0.1', '::1'))
    assert not bridge.is_loopback(SimpleNamespace(client=None))


def test_settings_and_restart_forbidden_remotely(site):
    with site(local=False) as s:
        assert s.client.get('/api/settings').status_code == 403
        assert s.client.post('/api/settings', json={'settings': {}}).status_code == 403
        assert s.client.post('/api/restart', headers={'X-Stop': '1'}).status_code == 403
        assert s.client.get('/api/diag').status_code == 200


@pytest.mark.parametrize('settings', [
    [], {'outer': [{'PASSWORD_hint': 'no'}]}, {'safety': {'mode': 'bad'}},
    {'ma2': {'prompt_regex': '['}}, {'ma2': {'login_ok_regex': 5}}, {'ma2': {'exec_empty_regex': '('}},
    {'ma2': {'port': '30000'}}, {'ma2': {'port': 65536}}, {'port': 0}, {'port': True},
    {'bind': 'localhost'}, {'bind': 123}, {'bind': '999.1.1.1'},
    {'rate_hz': 11}, {'rate_hz': True}, {'attrs': []}, {'attrs': {'zoom': 'bad'}},
    {'attrs': {'zoom': {'cmd': 'At {v}'}}}, {'attrs': {'zoom': {'cmd': 'Attribute "Bad Name" At {v}'}}},
    {'attrs': {'zoom': {'rel_cmd': 'Attribute "Zoom" At 1'}}}, {'features': {'zoom': 1}},
    {'ma2': []}, {'safety': []}, {'safety': {'allowed_fixtures': ['x']}},
])
def test_invalid_settings_have_no_side_effects(site, settings):
    with site() as s:
        before = s.path.read_bytes(), list(s.mock.received)
        backups = {p.name: p.read_bytes() for p in (s.folder / 'backups').glob('*.json')}
        r = s.client.post('/api/settings', json={'settings': settings, 'password': 'must-not-save'})
        assert r.status_code == 400, r.text
        assert r.json()['ok'] is False and r.json()['err']
        assert (s.path.read_bytes(), s.mock.received) == before
        assert not (s.folder / 'secret.env').exists()
        assert {p.name: p.read_bytes() for p in (s.folder / 'backups').glob('*.json')} == backups


def test_save_backup_unknown_keys_secret_and_no_console_traffic(site):
    with site() as s:
        data = s.client.get('/api/settings').json()
        assert data['path'] == str(s.path)
        assert data['defaults']['safety']['mode'] == 'test'
        assert 'zoom' in data['config_attrs']
        assert data['password_set'] is False
        proposed = data['settings']
        proposed.update({'ma2': {'host': '10.0.0.2', 'port': 30001, 'prompt_regex': r'\]>\s*$'},
                         'safety': {'mode': 'store', 'allowed_fixtures': [12]},
                         'attrs': {'zoom': {'cmd': 'Attribute "Zoom" At {v}'}},
                         'features': {'color': 'Не проверено', 'zoom': True}})
        old = s.path.read_bytes()
        backups = {p.name for p in (s.folder / 'backups').glob('*.json')}
        before = list(s.mock.received)
        assert s.client.post('/api/settings', json={'settings': proposed}).json() == {'ok': True, 'restart_needed': True}
        assert json.loads(s.path.read_text()) == proposed
        assert json.loads(s.path.read_text())['unknown'] == {'keep': [1, 2]}
        added = [p for p in (s.folder / 'backups').glob('*.json') if p.name not in backups]
        assert len(added) == 1 and added[0].read_bytes() == old
        assert not (s.folder / 'secret.env').exists()
        assert s.mock.received == before
        # The running bridge still has its original mode and host.
        assert s.client.get('/api/diag').json()['mode'] == 'test'
        assert s.client.get('/api/diag').json()['host'] == '127.0.0.1:30000'
        r = s.client.post('/api/settings', json={'settings': proposed, 'password': 'new-secret'})
        assert r.status_code == 200
        assert (s.folder / 'secret.env').read_text() == 'MA2_PASSWORD=new-secret\n'
        assert s.client.get('/api/settings').json()['password_set'] is True
        secret_bytes = (s.folder / 'secret.env').read_bytes()
        s.client.post('/api/settings', json={'settings': proposed})
        assert (s.folder / 'secret.env').read_bytes() == secret_bytes
        assert len({p.name for p in (s.folder / 'backups').glob('*.json')} - backups) == 3
        s.client.post('/api/settings', json={'settings': proposed, 'clear_password': True})
        assert (s.folder / 'secret.env').read_text() == 'MA2_PASSWORD=\n'
        assert s.client.get('/api/settings').json()['password_set'] is False
        assert s.mock.received == before


def test_bad_password_payload_is_not_written(site):
    with site() as s:
        for payload in [{'password': []}, {'password': 'a\nBAD=2'}, {'clear_password': 'true'}]:
            assert s.client.post('/api/settings', json={'settings': {}, **payload}).status_code == 400
        assert not (s.folder / 'secret.env').exists()


def test_restart_header_idle_and_exit_code(site):
    with site() as s:
        assert s.client.post('/api/restart').status_code == 403
        s.app.state.last_send = time.monotonic()
        response = s.client.post('/api/restart', headers={'X-Stop': '1'})
        assert response.status_code == 409 and response.json()['err'] == 'идёт передача команд'
        assert not s.app.state.server.should_exit
        s.app.state.last_send = -1e9
        assert s.client.post('/api/restart', headers={'X-Stop': '1'}).json()['ok']
        assert s.app.state.exit_code == 3 and s.app.state.server.should_exit


def test_diag_masks_login_and_logs_gives_ordered_hints_and_cleans_handler(site):
    baseline = list(bridge.log.handlers)
    with site(password='private-password') as s:
        assert any('private-password' in line for line in s.mock.received)  # real login echo
        bridge.log.warning('login failed private-password')
        bridge.log.error('РЕЗУЛЬТАТ НЕИЗВЕСТЕН private-password')
        data = s.client.get('/api/diag').json()
        assert 'private-password' not in json.dumps(data)
        assert '***' in data['login_reply']
        assert data['errors'][0]['level'] == 'ERROR'
        assert ']> вовремя' in data['errors'][0]['hint']
        assert 'Настройках' in data['errors'][1]['hint']
        for i in range(105):
            bridge.log.warning('не распознан %d', i)
        errors = s.client.get('/api/diag').json()['errors']
        assert len(errors) == 100 and errors[0]['msg'].endswith('104')
    assert bridge.log.handlers == baseline


@pytest.mark.parametrize('message,expected', [
    ('вход не подтверждён', 'login_ok_regex'), ('нет приглашения', 'prompt_regex'),
    ('ЗАБЛОКИРОВАНО защитой: прибор 5', 'allowed_fixtures'), ('сцена 1.101 не разрешена', 'allowed_scenes'),
    ('команда не в списке разрешённых', 'сопоставлении'), ('ma2 link: refused', 'Telnet'),
    ('поздний ответ', 'timeout'), ('ответ не распознан', 'сырые'), ('другая ошибка', ''),
])
def test_diagnostic_advice(site, message, expected):
    with site() as s:
        bridge.log.warning(message)
        hint = s.client.get('/api/diag').json()['errors'][0]['hint']
        assert expected in hint
        if not expected:
            assert hint == ''


def test_probe_only_read_commands_and_halt(site):
    with site(local=False) as s:
        before = len(s.mock.received)
        data = s.client.post('/api/probe').json()
        assert data['ok'] and [r['cmd'] for r in data['results']] == bridge.PROBE_COMMANDS
        assert all(r['ok'] and r['reply'] for r in data['results'])
        sent = s.mock.received[before:]
        assert sent == bridge.PROBE_COMMANDS
        assert all(any(re.fullmatch(pattern, line) for pattern in READ) for line in sent)
        assert 'List Group' in (s.folder / 'probe.txt').read_text()
        s.link.halted = True
        assert not s.client.post('/api/probe').json()['ok']
        assert s.mock.received[before:] == sent
        s.link.halted = False
        s.link.state = 'down'
        assert s.client.post('/api/probe').json() == {'ok': False, 'err': 'нет связи с пультом'}


def test_zip_has_artifacts_but_no_passwords_or_secret_file(site):
    secret = 'never-export-this'
    with site(password=secret) as s:
        # Legacy misplaced secrets must be removed recursively even from lists.
        s.path.write_text(json.dumps({'ma2': {'password': secret}, 'nested': [{'some_PASSWORD': secret, 'keep': 3}]}))
        assert s.client.get('/api/settings').json()['settings'] == {'ma2': {}, 'nested': [{'keep': 3}]}
        for name in ['bridge.log', 'bridge.log.1', 'bridge.log.2', 'bridge.log.3', 'update.log']:
            (s.folder / name).write_text('echo ' + secret)
        (s.folder / 'VERSION').write_text('1.2.3\n')
        s.client.post('/api/probe')
        bridge.log.warning('login failed %s', secret)
        response = s.client.get('/api/diag.zip')
        assert response.headers['content-type'] == 'application/zip'
        assert 'attachment; filename="ma2-diag-' in response.headers['content-disposition']
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert set(archive.namelist()) == {'bridge.log', 'bridge.log.1', 'bridge.log.2', 'bridge.log.3',
                'settings.json', 'config.json', 'diag.json', 'journal.json', 'probe.txt', 'update.log', 'VERSION'}
            for name in archive.namelist():
                assert secret not in archive.read(name).decode()
            settings = json.loads(archive.read('settings.json'))
            assert settings == {'ma2': {}, 'nested': [{'keep': 3}]}
            assert json.loads(archive.read('diag.json'))['version'] == '1.2.3'
            config = json.loads(archive.read('config.json'))
            assert config['version'] == 5 and 'ma2' not in config


def test_pages_served(site):
    with site() as s:
        for path in ['/settings.html', '/settings.js', '/diag.html', '/diag.js']:
            assert s.client.get(path).status_code == 200
        assert 'settings.html' in s.client.get('/app.js').text  # Площадка links settings and diagnostics


def test_missing_settings_file_and_secret_are_empty(site):
    with site() as s:
        s.path.unlink()
        backups = {p.name: p.read_bytes() for p in (s.folder / 'backups').glob('*.json')}
        data = s.client.get('/api/settings').json()
        assert data['settings'] == {} and data['password_set'] is False
        assert s.client.post('/api/settings', json={'settings': {}}).json()['ok']
        assert {p.name: p.read_bytes() for p in (s.folder / 'backups').glob('*.json')} == backups


def test_restart_refuses_in_progress_probe(site):
    from concurrent.futures import ThreadPoolExecutor
    with site() as s, ThreadPoolExecutor() as pool:
        s.mock.late = .1
        future = pool.submit(s.client.post, '/api/probe')
        deadline = time.monotonic() + 2
        while not any(line.startswith('List ') for line in s.mock.received):
            assert time.monotonic() < deadline
            time.sleep(.01)
        s.app.state.last_send = -1e9  # the action lock alone must block restart
        assert not s.client.get('/api/idle').json()['idle']
        assert s.client.post('/api/restart', headers={'X-Stop': '1'}).status_code == 409
        assert not s.app.state.server.should_exit
        assert future.result(timeout=4).json()['ok']


def test_main_exits_with_restart_code(tmp_path, monkeypatch):
    cfg = json.loads(Path('tests/config.test.json').read_text())
    cfg['ma2'].pop('password', None)
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(cfg))
    settings_path = tmp_path / 'custom.json'
    settings_path.write_text(json.dumps({'port': 0, 'simple_port': None}))
    monkeypatch.setattr(bridge, 'HERE', tmp_path)
    monkeypatch.setattr('sys.argv', ['bridge.py', '--config', str(config), '--settings', str(settings_path)])
    calls = []

    def create(*args, **kwargs):
        calls.append(kwargs['settings_path'])
        return SimpleNamespace(state=SimpleNamespace(exit_code=3))

    monkeypatch.setattr(bridge, 'create_app', create)
    monkeypatch.setattr(bridge.uvicorn, 'Config', lambda app, **kwargs: None)
    async def serve():
        pass

    monkeypatch.setattr(bridge.uvicorn, 'Server', lambda config: SimpleNamespace(serve=serve))
    with pytest.raises(SystemExit) as exc:
        bridge.main()
    assert exc.value.code == 3 and calls == [str(settings_path)]
    assert not (tmp_path / 'bridge.pid').exists()
