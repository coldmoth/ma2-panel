"""Real published v3.3.0 + embedded Python, existing HTTP/UI updater, mock only.

Only GitHub transport is fixture-backed (including deliberately synthetic CI
receipts). Synthetic fixtures are NEVER published. This is not hardware acceptance
or evidence that a stable release currently exists on GitHub.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ma2panel import release, release_quality, browser_update
from scripts.first_run_zip import clean_environment

OLD_SHA = '0dc535cb5143f5acb368ebc8a5a13cd8fceef9eef737d5616a6acb0f07163cbb'
REPO = 'coldmoth/ma2-panel'
API = f'https://api.github.com/repos/{REPO}'
# External harness, not installed application code. Propagates only the fixture
# transport into detached workers/restarts. Every non-loopback network is denied.
HOOK = r'''
import io,json,os,runpy,socket,subprocess,sys,urllib.request
from pathlib import Path
root,transport,pids,entry=map(Path,sys.argv[1:5]); args=sys.argv[5:]
original_open=urllib.request.urlopen; original_build=urllib.request.build_opener
class Opener:
    def open(self,request,*a,**k):
        url=request.full_url if hasattr(request,'full_url') else str(request)
        if url.startswith('https://'):
            records=json.loads(transport.read_text(encoding='utf-8'))
            if url not in records: raise OSError('Unmapped GitHub fixture '+url)
            record=records[url]
            return io.BytesIO(Path(record['file']).read_bytes() if 'file' in record else json.dumps(record['json']).encode())
        return original_open(request,*a,**k)
urllib.request.build_opener=lambda *a,**k: Opener()
# urlopen handles updater health locally; remote uses the same fixture transport.
urllib.request.urlopen=lambda request,*a,**k: Opener().open(request,*a,**k) if str(getattr(request,'full_url',request)).startswith('https://') else original_open(request,*a,**k)
# original urlopen builds an opener once; initialize it before installing wrappers.
urllib.request._opener=original_build()
popen=subprocess.Popen
def child(command,*a,**k):
    if isinstance(command,(tuple,list)) and len(command)>1 and Path(str(command[1])).name in ('bridge.py','browser_update.py'):
        command=[command[0],'-c',HOOK,str(root),str(transport),str(pids),*command[1:]]
    process=popen(command,*a,**k)
    with pids.open('a') as stream: stream.write(str(process.pid)+'\n')
    return process
subprocess.Popen=child
# The harness text is passed via argv code, so children can propagate it.
HOOK=Path(str(transport)+'.hook').read_text(encoding='utf-8')
def guard(event,args):
    if event=='socket.connect' and args[1][0] not in ('127.0.0.1','::1'):
        raise OSError('Acceptance blocks non-loopback connections')
sys.addaudithook(guard)
if json.loads(transport.read_text(encoding='utf-8')).get('_host_smoke'):
    sys.path.insert(0,str(root))
    from ma2panel import browser_update
    browser_update.supported_platform=lambda:True
sys.path.insert(0,str(root));sys.argv=[str(entry),*args]
runpy.run_path(str(entry),run_name='__main__')
'''


def free_ports():
    sockets = [socket.socket() for _ in range(2)]
    try:
        for s in sockets: s.bind(('127.0.0.1', 0))
        return [s.getsockname()[1] for s in sockets]
    finally:
        for s in sockets: s.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, default=Path('dist/update/ma2-panel-update.zip'))
    parser.add_argument('--output', type=Path, default=Path('test-results/update-channels'))
    parser.add_argument('--host-runtime', action='store_true', help='Local smoke only; not Windows acceptance')
    args = parser.parse_args()
    if os.name != 'nt' and not args.host_runtime:
        raise SystemExit('Windows x64 acceptance requires the shipped embedded runtime')
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    cache = ROOT / 'dist/cache/published-v3.3.0-win.zip'; cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        with urllib.request.urlopen(f'https://github.com/{REPO}/releases/download/v3.3.0/ma2-panel-win.zip', timeout=45) as response:
            cache.write_bytes(response.read(32 * 1024 * 1024))
    assert hashlib.sha256(cache.read_bytes()).hexdigest() == OLD_SHA
    candidate = args.candidate.resolve(); manifest = release.check(candidate)
    stable_candidate = browser_update.version_key(manifest['version'])[3]
    sha = zipfile.ZipFile(candidate).read('source_identity.py').decode().removeprefix('# source-sha: ').strip()
    with tempfile.TemporaryDirectory(prefix='ma2 online зал ') as folder:
        temp = Path(folder)
        with zipfile.ZipFile(cache) as archive: archive.extractall(temp)
        root = temp / 'ma2-panel/program'
        executable = Path(sys.executable) if args.host_runtime else root / 'python/python.exe'
        old_version = (root / 'VERSION').read_text().strip()
        assert old_version.startswith('3.3.0+')
        # Exercise the exact stable candidate if provided; otherwise construct a
        # synthetic bootstrap. The other channel uses a matching-version fixture.
        if stable_candidate:
            stable, stable_version = candidate, manifest['version']
            major, minor, patch = browser_update.version_key(stable_version)[:3]
            rc_version = f'{major}.{minor}.{patch+1}-rc.1+fixture'
            test_archive = temp / 'next-rc.zip'
            release.write_zip(release.build(ROOT, version=rc_version), test_archive)
        else:
            stable = temp / 'stable.zip'; stable_version = '3.3.1+fixture'
            release.write_zip(release.build(ROOT, version=stable_version), stable)
            test_archive, rc_version = candidate, manifest['version']
        stable_tag = 'v' + stable_version.split('+')[0]
        rc_tag = 'v' + rc_version.split('+')[0]
        routes = {'_host_smoke': args.host_runtime}
        proof = {'schema': 1, 'source_sha': sha, 'candidate_run': 42, 'candidate_attempt': 1,
                 'checks': dict.fromkeys(release_quality.REQUIRED, 'success'), 'blockers': [],
                 'runtime': manifest['runtime'], 'assets': {'ma2-panel-update.zip': hashlib.sha256(test_archive.read_bytes()).hexdigest()}}
        check = {'name': 'Candidate quality evidence', 'head_sha': sha, 'conclusion': 'success',
                 'app': {'slug': 'github-actions'}, 'external_id': 'candidate:42:1',
                 'details_url': f'https://github.com/{REPO}/actions/runs/42/attempts/1',
                 'output': {'summary': release_quality.fingerprint(proof)}}
        routes[f'{API}/actions/runs/42/attempts/1'] = {'json': {'head_sha': sha, 'conclusion': 'success',
                 'event': 'workflow_dispatch', 'path': '.github/workflows/ci.yml', 'repository': {'full_name': REPO}}}
        routes[f'{API}/commits/{sha}/check-runs?check_name=Candidate%20quality%20evidence&filter=all&per_page=100'] = {'json': {'total_count': 1, 'check_runs': [check]}}
        records = []
        for tag, archive, test in ((stable_tag, stable, False), (rc_tag, test_archive, True)):
            prefix = f'https://github.com/{REPO}/releases/download/{tag}/'
            checksum = temp / (tag + '.sha256'); checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest())
            names = {'ma2-panel-update.zip': {'file': str(archive)}, 'ma2-panel-update.zip.sha256': {'file': str(checksum)}}
            if test: names['quality.json'] = {'json': proof}
            records.append({'tag_name': tag, 'draft': False, 'prerelease': test, 'body': 'Fixture-backed browser update acceptance',
                            'assets': [{'name': name, 'browser_download_url': prefix + name} for name in names]})
            routes.update({prefix + name: record for name, record in names.items()})
            routes[f'{API}/commits/{tag}'] = {'json': {'sha': sha}}
        routes[f'{API}/releases/latest'] = {'json': records[0]}
        routes[f'{API}/releases?per_page=100&page=1'] = {'json': records}
        transport = temp / 'transport.json'; transport.write_text(json.dumps(routes), encoding='utf-8')
        Path(str(transport) + '.hook').write_text(HOOK, encoding='utf-8')
        ports = free_ports()
        cfg = json.loads((ROOT / 'ma2panel/resources/config.example.json').read_text())
        cfg.update(version=5, show='Mock show', fixtures=[{'id': 1, 'type': 'Dimmer', 'label': 'QA', 'x': .25, 'y': .75}],
                   groups=[{'id': 'local', 'label': 'QA group', 'fixtures': [1]}], ma2groups=[], scenes=[])
        settings = json.loads((ROOT / 'ma2panel/resources/settings.example.json').read_text())
        settings.update(port=ports[0], simple_port=ports[1], poll_seconds=0, dmx_seconds=0)
        protected = {'config.json': json.dumps(cfg).encode(), 'settings.json': json.dumps(settings).encode(),
                     'secret.env': b'MA2_PASSWORD=synthetic-ci-only\n', 'shows/QA.json': json.dumps(cfg).encode(),
                     'backups/keep.txt': b'backup sentinel', 'diag/keep.txt': b'diagnostic sentinel',
                     'bridge.log': b'operator log sentinel\n', 'rdm-search.json': b'journal sentinel'}
        for name, data in protected.items():
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        pids = temp / 'pids.txt'
        command = [str(executable), '-c', HOOK, str(root), str(transport), str(pids), str(root / 'bridge.py'),
                   '--mock', '--config', str(root / 'config.json'), '--settings', str(root / 'settings.json')]
        with (output / 'bridge.log').open('wb') as log:
            process = subprocess.Popen(command, cwd=root, env=clean_environment(), stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 35
                base = f'http://127.0.0.1:{ports[0]}'
                while True:
                    if process.poll() is not None: raise RuntimeError('Old client exited; see bridge.log')
                    try:
                        with urllib.request.urlopen(base + '/api/update/health', timeout=1) as response:
                            assert json.load(response)['version'] == old_version
                        break
                    except OSError:
                        if time.monotonic() > deadline: raise TimeoutError('Old client startup')
                        time.sleep(.2)
                # Snapshot startup migrations before testing the update itself.
                before = {name: (root / name).read_bytes() for name in protected}
                browser = subprocess.Popen(['node', str(ROOT / 'scripts/update_channels_browser.cjs'), base, str(output),
                                            old_version, stable_version, rc_version], cwd=ROOT)
                until = time.monotonic() + 130
                try:
                    while browser.poll() is None:
                        process.poll()  # Reap the old parent on Unix; a zombie is still kill(pid,0)-alive.
                        if time.monotonic() > until: raise TimeoutError('Browser scenario')
                        time.sleep(.1)
                    if browser.returncode: raise RuntimeError('Browser scenario failed; see failure.txt')
                finally:
                    if browser.poll() is None: browser.kill(); browser.wait(timeout=5)
                for name, data in before.items():
                    actual = (root / name).read_bytes()
                    if name == 'settings.json':
                        assert json.loads(actual) == {**json.loads(data), 'test_updates': True}
                    elif name == 'bridge.log': assert actual.startswith(data)
                    else: assert actual == data, name
                assert (root / 'previous').is_dir() and (root / '.updates').is_dir()
                result = {'published_old': old_version, 'published_old_sha256': OLD_SHA,
                          'stable_target': stable_version, 'rc_target': rc_version, 'candidate': manifest['version'],
                          'stable_is_fixture': not stable_candidate, 'rc_is_fixture': stable_candidate,
                          'runtime': 'host-smoke' if args.host_runtime else 'published-v3.3.0-embedded-windows-x64',
                          'transport': 'fixture GitHub; synthetic CI evidence; no public stable asserted',
                          'old_button_upgrade': 'success', 'rc_button_upgrade': 'success',
                          'preference_after_restart': True, 'private_data': 'preserved', 'rollback_snapshot': 'present'}
                (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
                print(json.dumps(result))
            finally:
                if process.poll() is None: process.terminate(); process.wait(timeout=10)
                for pid in set(pids.read_text().splitlines() if pids.exists() else []):
                    try:
                        if os.name == 'nt': subprocess.run(['taskkill', '/PID', pid, '/T', '/F'], capture_output=True, timeout=10)
                        else: os.kill(int(pid), 15)
                    except (OSError, subprocess.TimeoutExpired): pass
                if (root / '.updates').exists():
                    shutil.copytree(root / '.updates', output / 'updates', ignore=shutil.ignore_patterns('*.zip'), dirs_exist_ok=True)


if __name__ == '__main__': main()
