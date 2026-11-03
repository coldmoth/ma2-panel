"""Server bootstrap never puts a GitHub credential in process arguments or errors."""
import json

import pytest

from scripts import setup_diagnostic_relay as setup


def test_token_is_checked_and_sent_only_through_stdin(monkeypatch):
    checks, calls = [], []
    token = 'github_pat_synthetic'
    class Github:
        def __init__(self, value):
            assert value == token
        def check_private(self):
            checks.append(True)
    monkeypatch.setattr(setup, 'Github', Github)
    monkeypatch.setattr(setup.subprocess, 'run', lambda argv, **kw: calls.append((argv, kw)))
    setup.install(token)
    assert checks == [True] and len(calls) == 1
    argv, kw = calls[0]
    assert argv[0] == 'ssh' and 'root@132.243.222.221' in argv
    assert token not in repr(argv)
    assert json.loads(kw['input']) == {'repository': 'coldmoth/ma2-panel-diagnostics', 'token': token}
    assert kw['check'] is True and kw['capture_output'] is True


def test_failed_preflight_never_sends_credentials(monkeypatch):
    class Github:
        def __init__(self, value):
            pass
        def check_private(self):
            raise RuntimeError('failure')
    monkeypatch.setattr(setup, 'Github', Github)
    monkeypatch.setattr(setup.subprocess, 'run', lambda *a, **kw: pytest.fail('must not SSH'))
    with pytest.raises(RuntimeError):
        setup.install('synthetic')
