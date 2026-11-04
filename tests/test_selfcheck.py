"""CLI checks use an isolated script copy and loopback-only synthetic endpoints."""
import json
import shutil
import socket
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest
from websockets.datastructures import Headers
from websockets.http11 import Response
from websockets.sync.server import serve


@contextmanager
def endpoint(*, logged_in=True, simple=False):
    requests = []
    def http(connection, request):
        requests.append(request.path)
        if request.path == '/ws' and not simple:
            return None
        if simple:
            return Response(404, 'Not Found', Headers(), b'no API on simple port')
        body = (json.dumps({'version': 'test', 'ma2': 'logged_in' if logged_in else 'offline',
                            'user': 'mock', 'show': {'name': 'mock'}, 'mode': 'test'}).encode()
                if request.path == '/api/diag' else b'x' * 101)
        return Response(200, 'OK', Headers(), body)
    def ws(connection):
        connection.send(json.dumps({'config': {'fixtures': [
            {'id': 1, 'address': '1.001', 'moves': True}]}}))
        for message in connection:
            action = json.loads(message)['a']
            requests.append(action)
            connection.send(json.dumps({'a': action, 'ok': True, 'names': ['mock'], 'total': 1,
                                        'groups': [{'name': 'mock'}], 'colors': [1]}))
    with serve(ws, '127.0.0.1', 0, process_request=http) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.socket.getsockname()[1]}', requests
        finally:
            server.shutdown()
            thread.join(timeout=5)


def run_check(tmp_path, url, *, blocked_report=False):
    script = tmp_path / 'selfcheck.py'
    shutil.copy2(Path(__file__).resolve().parents[1] / 'selfcheck.py', script)
    if blocked_report:
        (tmp_path / 'selfcheck-report.txt').mkdir()
    return subprocess.run([sys.executable, str(script), url], cwd=tmp_path,
                          capture_output=True, text=True, timeout=20)


def test_unreachable_cli_returns_failure_and_report(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        url = f'http://127.0.0.1:{sock.getsockname()[1]}'
        result = run_check(tmp_path, url)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'Ошибок: 1 из 1' in (tmp_path / 'selfcheck-report.txt').read_text()


@pytest.mark.parametrize('logged_in', [True, False])
def test_cli_mock_on_explicit_nondefault_port(tmp_path, logged_in):
    with endpoint(logged_in=logged_in) as (url, requests):
        result = run_check(tmp_path, url + '/')
    assert result.returncode == (0 if logged_in else 1), result.stdout + result.stderr
    assert '/api/diag' in requests and 'fixtures_fetch' in requests
    report = (tmp_path / 'selfcheck-report.txt').read_text()
    assert ('Ошибок: 0 из' in report) == logged_in


def test_simple_port_is_not_reported_as_success(tmp_path):
    with endpoint(simple=True) as (url, requests):
        result = run_check(tmp_path, url)
    assert result.returncode == 1, result.stdout + result.stderr
    assert requests == ['/api/diag']
    assert 'HTTPError' in (tmp_path / 'selfcheck-report.txt').read_text()


def test_report_write_failure_is_nonzero(tmp_path):
    with endpoint() as (url, _):
        result = run_check(tmp_path, url, blocked_report=True)
    assert result.returncode != 0
    assert result.stderr
