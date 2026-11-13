"""First launch of an untouched delivered ZIP. Does not seed mock settings/config."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

# Run the actual entry point with shipped defaults. Reject outbound connects before
# the OS can reach onPC, including loopback:30000. Only the stdlib private self-pipe
# may connect to its own listener. No app/settings patches.
GUARDED = r'''
import json,runpy,socket,sys
from pathlib import Path
record=Path(sys.argv[1]); entry=sys.argv[2]; sys.argv=[entry]
sys.path.insert(0,str(Path(entry).parent))
def guard(event,args):
    if event=='socket.connect':
        # Windows asyncio builds its private self-pipe with the stdlib TCP fallback.
        frame = sys._getframe(1)
        fallback = getattr(socket, '_fallback_socketpair', None)
        if fallback is not None and frame.f_code is fallback.__code__:
            listener, client = frame.f_locals.get('lsock'), frame.f_locals.get('csock')
            if (listener is not None and client is args[0]
                    and args[1][0] in ('127.0.0.1', '::1') and args[1][1] != 30000
                    and tuple(args[1][:2]) == tuple(listener.getsockname()[:2])
                    and frame.f_locals.get('port') == args[1][1]):
                return
        with record.open('a',encoding='utf-8') as stream: stream.write(json.dumps(list(args[1]))+'\n')
        raise OSError('First-run ZIP acceptance blocks every outbound connection')
sys.addaudithook(guard)
runpy.run_path(entry,run_name='__main__')
'''


def clean_environment():
    keys = ('PATH', 'HOME', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'LOCALAPPDATA')
    return {**{k: os.environ[k] for k in keys if k in os.environ}, 'PYTHONUTF8': '1', 'PYTHONNOUSERSITE': '1'}


def request(base, path, data=None):
    req = urllib.request.Request(base + path, data=None if data is None else json.dumps(data).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=2) as r:
        return json.load(r)


def check_program(program, executable, evidence, scenario='pristine'):
    evidence.mkdir(parents=True, exist_ok=True)
    config, settings = program/'config.json', program/'settings.json'
    if scenario == 'pristine':
        assert config.is_file() and settings.is_file()
        assert json.loads(config.read_text(encoding='utf-8'))['fixtures'] == []
        assert json.loads(settings.read_text(encoding='utf-8'))['safety']['mode'] == 'test'
        assert not any((program/n).exists() for n in ('secret.env','shows','rdm-search.json'))
    elif scenario.startswith('missing-'): (program/(scenario[8:]+'.json')).unlink()
    elif scenario.startswith('broken-'): (program/(scenario[7:]+'.json')).write_bytes(b'{broken')
    else: raise ValueError('Unknown first-run scenario')
    fail = scenario in ('missing-config','broken-config','broken-settings')
    if not fail:
        for port in (8080,8090):
            with socket.socket() as sock: sock.bind(('127.0.0.1',port))
    record = evidence/'outbound.jsonl'
    launch_executable, launch_env = str(executable), clean_environment()
    if (sys.platform == 'win32' and sys.prefix != sys.base_prefix
            and Path(executable).resolve() == Path(sys.executable).resolve()):
        # Match the existing updater launcher: the venv redirector has a separate PID.
        launch_executable = sys._base_executable
        launch_env['__PYVENV_LAUNCHER__'] = sys.executable
    with (evidence/'bridge.log').open('wb') as log:
        process = subprocess.Popen([launch_executable, '-c', GUARDED, str(record), str(program/'bridge.py')],
                                   cwd=program, env=launch_env, stdout=log, stderr=subprocess.STDOUT)
        try:
            if fail:
                assert process.wait(timeout=15) != 0
                assert not record.exists(), 'invalid config must fail before any outbound attempt'
                text = (evidence/'bridge.log').read_text(encoding='utf-8')
                assert 'JSON' in text or 'конфига' in text
                return
            deadline = time.monotonic()+30
            while True:
                if process.poll() is not None:
                    log_path = evidence/'bridge.log'
                    details = log_path.read_text(encoding='utf-8', errors='replace')[-6000:]
                    raise RuntimeError(f'First-run exited ({process.returncode}); see {log_path}:\n{details}')
                try:
                    health = request('http://127.0.0.1:8080','/api/update/health')
                    if health.get('pid') != process.pid: raise RuntimeError('Default port belongs to another process')
                    info = request('http://127.0.0.1:8080','/api/setup')
                    break
                except OSError:
                    if time.monotonic()>deadline: raise TimeoutError('First-run startup')
                    time.sleep(.1)
            assert info['ok'] and info['mock'] is False and not info['ma2']['ready']
            body = request('http://127.0.0.1:8080','/api/settings')
            assert body['settings'].get('safety',{}).get('mode', body['defaults']['safety']['mode']) == 'test'
            if scenario == 'pristine':
                body['settings']['ma2']['user'] = 'FirstRunQA'
                saved = request('http://127.0.0.1:8080','/api/settings', {'settings': body['settings']})
                assert saved['ok']
                stored = json.loads(settings.read_text(encoding='utf-8'))
                assert stored['ma2']['user'] == 'FirstRunQA' and stored['safety']['mode'] == 'test'
            # No application connection reached the OS; blocked attempts remain evidence.
            attempts = [json.loads(line) for line in record.read_text().splitlines()] if record.exists() else []
            assert all(a[0] == '127.0.0.1' and a[1] == 30000 for a in attempts), attempts
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,default=Path('dist/ma2-panel-win.zip'))
    p.add_argument('--output',type=Path,default=Path('test-results/first-run-zip'));args=p.parse_args()
    if os.name != 'nt': raise SystemExit('Untouched embedded-runtime ZIP check requires Windows')
    for port in (8080,8090):
        with socket.socket() as s: s.bind(('127.0.0.1',port))
    for scenario in ('pristine','missing-config','broken-config','missing-settings','broken-settings'):
        with tempfile.TemporaryDirectory(prefix='ma2 first run зал ') as folder:
            with zipfile.ZipFile(args.archive) as archive:
                assert archive.testzip() is None; archive.extractall(folder)
            program=Path(folder)/'ma2-panel/program'
            check_program(program,program/'python/python.exe',args.output.resolve()/scenario,scenario)
    print('Untouched ZIP, safe test mode, settings wizard API and missing/corrupt inputs passed; outbound sockets blocked')


if __name__=='__main__': main()
