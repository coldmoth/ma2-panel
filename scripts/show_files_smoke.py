"""Repeatable real-browser QA, all application data and simulated MA2 files isolated."""
import argparse
import gzip
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ma2-show-browser-') as temp:
        app = Path(temp)
        for source in ROOT.glob('*.py'):
            shutil.copy2(source, app / source.name)
        shutil.copytree(ROOT / 'static', app / 'static')
        (app / 'shows-ma2').mkdir()
        (app / 'shows-ma2' / 'Mock show.show.gz').write_bytes(gzip.compress(b'isolated mock show', mtime=0))
        cfg = json.loads((ROOT / 'config.example.json').read_text())
        settings = {'bind': '127.0.0.1', 'simple_port': None, 'poll_seconds': 0, 'dmx_seconds': 0,
                    'safety': {'mode': 'full', 'allow_show_load': True, 'allow_show_save': True},
                    'ma2': {'host': '127.0.0.1', 'user': 'Remote', 'load_timeout': 5,
                            'shows_dir': str(app / 'shows-ma2'), 'export_dir': str(app / 'exports')}}
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            settings['port'] = listener.getsockname()[1]
        for name, value in [('config', cfg), ('settings', settings)]:
            (app / (name + '.json')).write_text(json.dumps(value))
        worker = app / '_show_browser_server.py'
        worker.write_text('''import gzip
import sys
from pathlib import Path
from mock import MockMA2
import bridge
folder = Path(__file__).parent / 'shows-ma2'
original = MockMA2._answer
def answer(self, line):
    if line == 'ListShows':
        return '\\n'.join('"' + p.name[:-8] + '"' for p in folder.glob('*.show.gz')) + '\\n[Channel]>'
    if line.startswith('LoadShow'):
        self.shows = [p.name[:-8] for p in folder.glob('*.show.gz')]
    if line == 'SaveShow':
        (folder / (self.show_name + '.show.gz')).write_bytes(gzip.compress(b'new isolated mock show', mtime=0))
    return original(self, line)
MockMA2._answer = answer
sys.argv = ['bridge.py', '--mock', '--config', str(folder.parent / 'config.json'), '--settings', str(folder.parent / 'settings.json')]
bridge.main()
''')
        env = {k: v for k, v in os.environ.items() if k not in ('MA2_PASSWORD', 'MA2_MOCK_REAL', 'PYTHONPATH', 'PYTHONOPTIMIZE')}
        with (output / 'mock.log').open('w') as log:
            process = subprocess.Popen([sys.executable, str(worker)], cwd=app, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                url = 'http://127.0.0.1:' + str(settings['port'])
                deadline = time.monotonic() + 20
                with httpx.Client(timeout=1, trust_env=False) as client:
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError('mock stopped; see ' + str(output / 'mock.log'))
                        try:
                            client.get(url).raise_for_status()
                            break
                        except httpx.HTTPError:
                            if time.monotonic() > deadline:
                                raise TimeoutError('mock startup timed out')
                            time.sleep(.1)
                subprocess.run(['node', str(ROOT / 'scripts/show_files_smoke.cjs'), url, str(output)],
                               check=True, env=env, timeout=120)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
