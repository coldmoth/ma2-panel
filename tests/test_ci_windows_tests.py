"""Exercise the CI watchdog with real children, without starting MA2."""
import json
import sys
import time

from scripts import ci_windows_tests


def assert_process_stopped(pid):
    import os
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if handle:
            try:
                assert kernel.WaitForSingleObject(handle, 0) == 0, f'process {pid} still running'
            finally:
                kernel.CloseHandle(handle)
        else:
            assert ctypes.get_last_error() == 87, f'cannot verify process {pid}'
    else:
        # An exited orphan can briefly remain a zombie; it cannot run any code.
        import subprocess
        with subprocess.Popen(['ps', '-o', 'stat=', '-p', str(pid)], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) as probe:
            result, _ = probe.communicate(timeout=2)
        assert not result.strip() or result.strip().startswith('Z'), f'process {pid} still running'


def test_watchdog_preserves_output_and_failure(tmp_path):
    result = ci_windows_tests.run([sys.executable, '-u', '-c',
                           'import sys; print("current test", flush=True); sys.exit(7)'],
                          tmp_path, timeout=10)
    assert result == 7
    assert 'current test' in (tmp_path / 'pytest.log').read_text()
    state = json.loads((tmp_path / 'result.json').read_text())
    assert state['reason'] == 'exit'
    assert state['returncode'] == 7


def test_watchdog_allows_success_to_reach_next_step(tmp_path):
    assert ci_windows_tests.run([sys.executable, '-c', 'print("passed")'], tmp_path, timeout=10) == 0
    assert json.loads((tmp_path / 'result.json').read_text())['returncode'] == 0


def test_watchdog_bounds_hang_and_kills_descendants(tmp_path, monkeypatch):
    marker = tmp_path / 'leaked-child'
    child = f'import time; from pathlib import Path; time.sleep(3); Path({str(marker)!r}).touch()'
    pids = tmp_path / 'pids.json'
    parent = f'import subprocess,sys,time,os,json; from pathlib import Path; p=subprocess.Popen([sys.executable,"-c",{child!r}]); Path({str(pids)!r}).write_text(json.dumps([os.getpid(),p.pid])); print("stalled test",flush=True); time.sleep(60)'
    original_run = ci_windows_tests.subprocess.run
    diagnostic_checks = []

    def slow_snapshot(command, **kwargs):
        if command[0] in ('ps', 'powershell'):
            # A real slow diagnostic must only start after the child tree is dead.
            for pid in json.loads(pids.read_text()):
                assert_process_stopped(pid)
            diagnostic_checks.append(True)
            time.sleep(3)
            raise ci_windows_tests.subprocess.TimeoutExpired(command, kwargs['timeout'])
        return original_run(command, **kwargs)

    monkeypatch.setattr(ci_windows_tests.subprocess, 'run', slow_snapshot)
    start = time.monotonic()
    assert ci_windows_tests.run([sys.executable, '-u', '-c', parent], tmp_path, timeout=1) == 124
    assert time.monotonic() - start < 15
    state = json.loads((tmp_path / 'result.json').read_text())
    assert state['reason'] == 'watchdog_timeout'
    assert diagnostic_checks == [True]
    for pid in json.loads(pids.read_text()):
        assert_process_stopped(pid)
    assert state['stopped_elapsed_seconds'] < 3
    assert (tmp_path / 'processes.log').is_file()
    assert 'stalled test' in (tmp_path / 'pytest.log').read_text()
    time.sleep(2.5)
    assert not marker.exists(), 'watchdog left a descendant running'


def test_watchdog_deadline_survives_blocked_console(tmp_path):
    import os
    import signal
    import subprocess

    # Do not drain the supervisor's stdout until it exits: a blocking relay must
    # not be able to suspend the deadline or leak the pytest child.
    child = 'import sys,time;sys.stdout.write("x"*2097152);sys.stdout.flush();time.sleep(30)'
    code = f'''import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('watchdog',{ci_windows_tests.__file__!r})
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
sys.exit(m.run([sys.executable,'-u','-c',{child!r}],Path({str(tmp_path)!r}),timeout=1))
'''
    process = subprocess.Popen([sys.executable, '-u', '-c', code],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=os.name != 'nt')
    result = None
    try:
        try:
            result = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    finally:
        if process.poll() is None:
            if os.name == 'nt':
                with (tmp_path / 'probe-cleanup.log').open('wb') as cleanup:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   stdout=cleanup, stderr=subprocess.STDOUT, timeout=10)
            else:
                # run() gives its child a separate session; kill that group too.
                state = json.loads((tmp_path / 'result.json').read_text())
                for pid in (state['pid'], process.pid):
                    try:
                        os.killpg(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            if process.poll() is None:
                process.kill()
        stdout, stderr = process.communicate(timeout=5)
    assert result == 124, 'blocked console prevented watchdog deadline'
    assert not stdout and not stderr
    assert json.loads((tmp_path / 'result.json').read_text())['reason'] == 'watchdog_timeout'
    assert (tmp_path / 'pytest.log').stat().st_size == 2097152
