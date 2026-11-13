"""Install the pinned real 3.3.0 ZIP, upgrade to a different candidate, recover/rollback.

All writes and mock connections belong to temporary installations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.first_run_zip import clean_environment, request
from ma2panel import release

PREVIOUS_SHA256='b4d2ce6414e65f7654875af988e846b4883f4d798b5f4831aa9a757065196280'
PREVIOUS_URL='https://github.com/coldmoth/ma2-panel/releases/download/v3.3.0/ma2-panel-update.zip'
BOOT=r'''
import socket,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
if (root/'ma2panel/bridge.py').exists():
    import ma2panel.bridge as bridge
else:
    from ma2panel import bridge
allowed=set(); original=bridge.start_mock
async def start(*a,**k):
    mock=await original(*a,**k);allowed.add(mock.port);return mock
bridge.start_mock=start
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
        if args[1][0]!='127.0.0.1' or args[1][1] not in allowed:
            raise OSError('Lifecycle permits only this installation own mock')
sys.addaudithook(guard)
sys.argv=[str(root/'bridge.py'),'--mock','--config',str(root/'config.json'),'--settings',str(root/'settings.json')]
bridge.main()
'''


def previous_zip(path):
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(PREVIOUS_URL,timeout=30) as response:
            data=response.read(16*1024*1024)
        if hashlib.sha256(data).hexdigest()!=PREVIOUS_SHA256: raise ValueError('Previous ZIP hash mismatch')
        path.write_bytes(data)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=PREVIOUS_SHA256: raise ValueError('Previous ZIP hash mismatch')
    return path


def boot(root, executable, output):
    settings=json.loads((root/'settings.json').read_text(encoding='utf-8'))
    with output.open('wb') as log:
        process=subprocess.Popen([str(executable),'-c',BOOT,str(root)],cwd=root,env=clean_environment(),stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+30
            for port in (settings['port'],settings['simple_port']):
                while True:
                    if process.poll() is not None: raise RuntimeError('Installed process exited; see '+str(output))
                    try:
                        base=f'http://127.0.0.1:{port}'
                        health=request(base,'/api/update/health')
                        setup=request(f"http://127.0.0.1:{settings['port']}",'/api/setup')
                        if setup['ma2']['ready']: break
                    except OSError: pass
                    if time.monotonic()>deadline: raise TimeoutError('Installed process readiness; see '+str(output))
                    time.sleep(.1)
                assert health['pid']==process.pid
                assert health['version']==(root/'VERSION').read_text().strip()
                assert setup['mock'] is True
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)


def invoke(root, executable, code, *args, expected=0):
    result=subprocess.run([str(executable),'-c',"import sys;sys.path.insert(0,sys.argv[1]);"+code,str(root),*map(str,args)],cwd=root,env=clean_environment(),capture_output=True,timeout=90)
    if result.returncode!=expected: raise RuntimeError(result.stdout.decode('utf-8','replace')+result.stderr.decode('utf-8','replace'))


def exercise(previous, candidate, output, runtime=None):
    previous_zip(previous)
    old,new=release.check(previous),release.check(candidate)
    assert old['version'].startswith('3.3.0+') and new['version']!=old['version']
    module = 'ma2panel/bridge.py' if 'ma2panel/bridge.py' in old['files'] else 'bridge.py'
    target = 'ma2panel/bridge.py' if 'ma2panel/bridge.py' in new['files'] else 'bridge.py'
    assert old['files'][module]['sha256']!=new['files'][target]['sha256'], 'Same code is not an inter-version test'
    assert old['runtime']==new['runtime'], 'Upgrade needs an explicit runtime migration; do not fake compatibility'
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ma2 lifecycle зал ') as temp:
        root=Path(temp)/'program'; root.mkdir()
        with zipfile.ZipFile(previous) as archive: archive.extractall(root)
        executable=sys.executable
        if runtime:
            for name in ('python','lib','runtime.json','runtime-files.json'):
                source=runtime/name
                if source.is_dir(): shutil.copytree(source,root/name)
                else: shutil.copy2(source,root/name)
            executable=root/'python/python.exe'
        else: (root/'runtime.json').write_text(json.dumps(old['runtime']))
        with socket.socket() as a,socket.socket() as b:
            a.bind(('127.0.0.1',0));b.bind(('127.0.0.1',0));ports=[a.getsockname()[1],b.getsockname()[1]]
        cfg=json.loads((ROOT/'ma2panel/resources/config.example.json').read_text())
        cfg.update(version=5,show='Mock show',fixtures=[{'id':1,'type':'Dimmer','label':'QA','x':.25,'y':.75}],groups=[{'id':'local','label':'QA group','fixtures':[1]}],ma2groups=[{'n':1,'name':'QA MA2','ids':[1]}],scenes=[{'id':'look','exec':'1.101','label':'QA look'}])
        settings=json.loads((ROOT/'ma2panel/resources/settings.example.json').read_text())
        settings.update(port=ports[0],simple_port=ports[1],poll_seconds=0,dmx_seconds=0)
        settings['ma2']['export_dir']=str(root/'exports')
        data={'config.json':json.dumps(cfg).encode(),'settings.json':json.dumps(settings).encode(),'secret.env':b'MA2_PASSWORD=isolated-qa',
              'shows/QA.json':json.dumps(cfg).encode(),'rdm-search.json':b'corrupt journal must survive exactly'}
        for name,body in data.items():
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
        boot(root,executable,output/'previous.log')
        protected={n:(root/n).read_bytes() for n in data}
        def preserved():
            for n,body in protected.items(): assert (root/n).read_bytes()==body,n
        # Use the REAL previous updater, including its manifest parser.
        invoke(root,executable,'import update;from pathlib import Path;update.backup_user_data(Path(sys.argv[1]));update.install(sys.argv[2],sys.argv[1])',candidate)
        preserved();boot(root,executable,output/'candidate.log');preserved()
        assert (root/target).read_bytes()!=zipfile.ZipFile(previous).read(module)
        invoke(root,executable,"import update;update.prepare_bridge=lambda *a,**k:None;update.rollback(sys.argv[1],confirm=lambda _: 'y')")
        preserved();boot(root,executable,output/'rollback.log')
        with zipfile.ZipFile(previous) as archive: assert (root/'bridge.py').read_bytes()==archive.read('bridge.py')
        # Abrupt process death after a real target removal, bypassing try/except recovery.
        crash=r'''
import os,update
from pathlib import Path
root=Path(sys.argv[1]);original=update.remove
def remove(path):
    original(path)
    if Path(path)==root/'bridge.py': os._exit(91)
update.remove=remove
update.install(sys.argv[2],root)
'''
        invoke(root,executable,crash,candidate,expected=91)
        assert not (root/'bridge.py').exists()
        subprocess.run([str(executable),str(root/'.updates/recovery.py'),'--recover',str(root)],cwd=root,env=clean_environment(),check=True,timeout=30)
        preserved();boot(root,executable,output/'recovered.log')
        with zipfile.ZipFile(previous) as archive: assert (root/'bridge.py').read_bytes()==archive.read('bridge.py')
    result={'previous':old['version'],'previous_sha256':PREVIOUS_SHA256,'candidate':new['version'],'candidate_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),'upgrade':'success','rollback':'success','interrupted_recovery':'success','runtime':'embedded-windows' if runtime else 'host-python'}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--previous',type=Path,default=Path('dist/cache/previous-3.3.0.zip'))
    p.add_argument('--candidate',type=Path,default=Path('dist/update/ma2-panel-update.zip'));p.add_argument('--runtime',type=Path)
    p.add_argument('--output',type=Path,default=Path('test-results/release-lifecycle'));a=p.parse_args()
    exercise(a.previous.resolve(),a.candidate.resolve(),a.output.resolve(),a.runtime.resolve() if a.runtime else None)


if __name__=='__main__': main()
