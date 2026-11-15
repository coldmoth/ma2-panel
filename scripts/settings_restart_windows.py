"""Native Windows restart acceptance: real delivered BAT + embedded Python, isolated --mock."""
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.name != 'nt' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise SystemExit('Requires native Windows x64')
    output = ROOT / 'test-results/settings-restart'
    output.mkdir(parents=True, exist_ok=True)
    bundle = ROOT / 'dist/ma2-panel-win/ma2-panel'
    report = {'platform': platform.platform(), 'commit': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'ma2': 'mock only'}
    with tempfile.TemporaryDirectory(prefix='ma2-restart-') as temp:
        home = Path(temp) / 'panel space зал'
        shutil.copytree(bundle, home)
        app = home / 'program'
        python = app / 'python/python.exe'
        report['runtime'] = json.loads(subprocess.check_output([str(python), '-c',
            'import json,sys,struct; print(json.dumps({"executable":sys.executable,"version":sys.version,"bits":struct.calcsize("P")*8}))'], text=True))
        assert report['runtime']['bits'] == 64
        settings = json.loads((app / 'settings.json').read_text(encoding='utf-8-sig'))
        ports = []
        sockets = []
        try:
            for _ in range(4):
                sock = socket.socket()
                sock.bind(('127.0.0.1', 0))
                sockets.append(sock)
                ports.append(sock.getsockname()[1])
        finally:
            for sock in sockets:
                sock.close()
        settings.update(bind='127.0.0.1', port=ports[0], simple_port=ports[3], poll_seconds=2,
                        dmx_seconds=0, rate_hz=5)
        settings['ma2']['export_dir'] = str(app)
        (app / 'settings.json').write_text(json.dumps(settings), encoding='utf-8')
        env = {k: v for k, v in os.environ.items() if k not in
               {'MA2_PASSWORD', 'MA2_MOCK_REAL', 'PYTHONPATH', 'PYTHONOPTIMIZE'}}
        env['PYTHONUTF8'] = '1'
        arguments = ['--mock', '--config', str(app / 'config.json'), '--settings', str(app / 'settings.json')]
        command = 'cmd.exe /d /s /c ""' + str(home / 'start.bat') + '" ' + subprocess.list2cmdline(arguments) + ' <NUL"'
        with (output / 'launcher.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen(command, cwd=home, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                with httpx.Client(timeout=2, trust_env=False) as client:
                    deadline = time.monotonic() + 30
                    url = f'http://127.0.0.1:{ports[0]}'
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError(f'start.bat exited: {process.returncode}')
                        try:
                            health = client.get(url + '/api/update/health')
                            health.raise_for_status()
                            break
                        except httpx.TransportError:
                            if time.monotonic() >= deadline:
                                raise TimeoutError('Windows launcher did not become ready')
                            time.sleep(.1)
                    report['before'] = health.json()
                    # Keep a real port occupied for the final startup-failure scenario.
                    with socket.socket() as occupied:
                        occupied.bind(('127.0.0.1', ports[2]))
                        occupied.listen()
                        subprocess.run(['node', str(ROOT / 'scripts/settings_restart_browser.cjs'),
                                        url, str(ports[1]), str(ports[2]), str(ports[3]), str(output)],
                                       cwd=ROOT, env=env, check=True, timeout=120)
                    assert process.wait(timeout=15) is not None
                    report.update(json.loads((output / 'browser.json').read_text()))
                    assert len({item['pid'] for item in report['processes']}) == 3
                    assert len({item['instance'] for item in report['processes']}) == 3
                    assert not (app / 'bridge.pid').exists()
                    report['result'] = 'PASS'
            finally:
                if process.poll() is None:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=10)
                    process.wait(timeout=10)
                for name in ('bridge.log',):
                    if (app / name).exists():
                        shutil.copy2(app / name, output / name)
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS: native Windows x64 / embedded Python / real start.bat / browser confirmed 3 processes / port change / startup error')


if __name__ == '__main__':
    main()
