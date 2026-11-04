"""Bound Windows regressions independently of the Actions step cancellation.

124 means this watchdog expired; any other test exit code is preserved.
Logs live under test-results/windows, including pytest temporary worker logs.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TESTS = ('test_release.py', 'test_update.py', 'test_browser_update.py',
         'test_selfcheck.py', 'test_rdm_search.py', 'test_ci_windows_tests.py')


def run(command, output, timeout=240):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    state = {'command': command, 'timeout_seconds': timeout, 'reason': 'starting'}

    def record():
        (output / 'result.json').write_text(json.dumps(state, indent=2), encoding='utf-8')

    record()
    started = time.monotonic()
    with (output / 'pytest.log').open('wb') as log, (output / 'pytest.log').open('rb') as reader:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=os.name != 'nt')
        state.update(pid=child.pid, reason='running')
        record()

        def relay():
            data = reader.read(1024 * 1024)
            if data:
                print(data.decode('utf-8', errors='replace'), end='', flush=True)

        try:
            while child.poll() is None and time.monotonic() - started < timeout:
                relay()
                time.sleep(0.1)
            if child.poll() is None:
                state['reason'] = 'watchdog_timeout'
                record()
                print(f'pytest watchdog expired (PID {child.pid}); see {output}', flush=True)
                with (output / 'processes.log').open('wb') as snapshot:
                    if os.name == 'nt':
                        # Names/PIDs only: do not collect other processes' command-line secrets.
                        inspect = ['powershell', '-NoProfile', '-Command',
                                   'Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name | Format-Table -AutoSize']
                    else:
                        inspect = ['ps', '-eo', 'pid,ppid,pgid,comm']
                    try:
                        subprocess.run(inspect, stdout=snapshot, stderr=subprocess.STDOUT, timeout=10)
                    except (OSError, subprocess.TimeoutExpired) as error:
                        snapshot.write(str(error).encode('utf-8'))
                returncode = 124
            else:
                state['reason'] = 'exit'
                returncode = child.returncode
        finally:
            if child.poll() is None:
                with (output / 'cleanup.log').open('wb') as cleanup:
                    try:
                        if os.name == 'nt':
                            result = subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'],
                                                    stdout=cleanup, stderr=subprocess.STDOUT, timeout=10)
                            state['taskkill_returncode'] = result.returncode
                        else:
                            os.killpg(child.pid, signal.SIGKILL)
                    except (OSError, subprocess.TimeoutExpired) as error:
                        cleanup.write(str(error).encode('utf-8'))
                    finally:
                        if child.poll() is None:
                            child.kill()
                        child.wait(timeout=5)
                if state['reason'] == 'running':
                    state['reason'] = 'interrupted'
            relay()
            state.update(returncode=child.returncode, elapsed_seconds=round(time.monotonic() - started, 2))
            record()
    return returncode


def main():
    output = ROOT / 'test-results/windows'
    command = [sys.executable, '-u', '-m', 'pytest',
               *(str(ROOT / 'tests' / name) for name in TESTS),
               '-o', 'addopts=--tb=short', '-o', 'faulthandler_timeout=60',
               '-vv', '-s', '--durations=15',
               f'--basetemp={output / "tmp"}', f'--junitxml={output / "pytest.xml"}']
    result = run(command, output)
    if result == 124:
        print(f'::error::Windows regression watchdog expired; logs: {output}', flush=True)
    return result


if __name__ == '__main__':
    sys.exit(main())
