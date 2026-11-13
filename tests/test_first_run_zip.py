import shutil
import sys
import socket
from pathlib import Path

import pytest
from ma2panel import release
from scripts.first_run_zip import check_program


@pytest.mark.parametrize('scenario', ['pristine','missing-config','broken-config','missing-settings','broken-settings'])
def test_delivered_defaults_without_replacing_configuration(tmp_path, scenario):
    if scenario in ('pristine','missing-settings'):
        try:
            for port in (8080,8090):
                with socket.socket() as sock: sock.bind(('127.0.0.1',port))
        except OSError:
            pytest.skip('Default ports occupied; untouched Windows ZIP CI gate must run independently')
    source=Path(__file__).resolve().parents[1]
    program=tmp_path/'program'
    release.write_tree(release.build(source),program)
    # This is the builder's exact delivery step, not a smoke-specific seed.
    for name in ('config','settings'):
        shutil.copy2(source/'ma2panel/resources'/f'{name}.example.json',program/f'{name}.json')
        assert (program/f'{name}.json').read_bytes()==(source/'ma2panel/resources'/f'{name}.example.json').read_bytes()
    check_program(program,sys.executable,tmp_path/'evidence',scenario)
    if scenario=='broken-config': assert (program/'config.json').read_bytes()==b'{broken'
    if scenario=='broken-settings': assert (program/'settings.json').read_bytes()==b'{broken'


def test_guard_allows_only_stdlib_private_socketpair_and_blocks_application_connections(tmp_path):
    import json
    import subprocess
    from scripts.first_run_zip import GUARDED
    entry = tmp_path / 'entry.py'
    entry.write_text('''import socket,sys
left,right=socket._fallback_socketpair(socket.AF_INET)
left.sendall(b"self-pipe");assert right.recv(9)==b"self-pipe"
left.close();right.close()
with socket.socket() as server, socket.socket() as client:
    server.bind(("127.0.0.1",0));server.listen()
    try: client.connect(server.getsockname())
    except OSError as error: assert "First-run ZIP acceptance blocks" in str(error)
    else: raise AssertionError("Application loopback connection escaped the guard")
with socket.socket() as client:
    try: sys.audit("socket.connect",client,("127.0.0.1",30000))
    except OSError as error: assert "First-run ZIP acceptance blocks" in str(error)
    else: raise AssertionError("MA2 address escaped the guard")
''')
    record = tmp_path / 'connects.jsonl'
    result = subprocess.run([sys.executable,'-c',GUARDED,str(record),str(entry)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    attempts = [json.loads(line) for line in record.read_text().splitlines()]
    assert len(attempts) == 2 and attempts[-1] == ['127.0.0.1',30000]


def test_host_venv_launcher_preserves_pid_check_without_replacing_embedded_python(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import first_run_zip as first
    host, base, embedded = (tmp_path/name for name in ('venv-python.exe','base-python.exe','embedded-python.exe'))
    monkeypatch.setattr(first, 'sys', SimpleNamespace(platform='win32',prefix='venv',base_prefix='base',executable=str(host),_base_executable=str(base)),raising=False)
    calls = []
    class Captured(Exception): pass
    def capture(args, **kwargs):
        calls.append((args,kwargs['env']))
        raise Captured
    monkeypatch.setattr(first.subprocess, 'Popen', capture)
    program = tmp_path/'program'; program.mkdir()
    for executable in (host, embedded):
        with pytest.raises(Captured):
            first.check_program(program, executable, tmp_path/'evidence', 'broken-settings')
    assert calls[0][0][0] == str(base)
    assert calls[0][1]['__PYVENV_LAUNCHER__'] == str(host)
    assert calls[1][0][0] == str(embedded)
    assert '__PYVENV_LAUNCHER__' not in calls[1][1]
