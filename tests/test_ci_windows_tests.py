"""Exercise the CI watchdog with real children, without starting MA2."""
import json
import sys
import time

from scripts import ci_windows_tests


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


def test_watchdog_bounds_hang_and_kills_descendants(tmp_path):
    marker = tmp_path / 'leaked-child'
    child = f'import time; from pathlib import Path; time.sleep(3); Path({str(marker)!r}).touch()'
    parent = f'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{child!r}]); print("stalled test",flush=True); time.sleep(60)'
    start = time.monotonic()
    assert ci_windows_tests.run([sys.executable, '-u', '-c', parent], tmp_path, timeout=1) == 124
    assert time.monotonic() - start < 15
    state = json.loads((tmp_path / 'result.json').read_text())
    assert state['reason'] == 'watchdog_timeout'
    assert (tmp_path / 'processes.log').is_file()
    assert 'stalled test' in (tmp_path / 'pytest.log').read_text()
    time.sleep(2.5)
    assert not marker.exists(), 'watchdog left a descendant running'
