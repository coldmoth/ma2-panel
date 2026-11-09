"""Exercise the shipped Windows artifact, never a user installation or real MA2."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def legacy_transition():
    """Install the published v3.2.4 update on its full v3.2.0 runtime baseline."""
    archive = ROOT / 'dist/cache/published-v3.2.0-win.zip'
    if not archive.exists():
        with urllib.request.urlopen('https://github.com/coldmoth/ma2-panel/releases/download/v3.2.0/ma2-panel-win.zip', timeout=60) as response:
            archive.write_bytes(response.read())
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == 'ebe01bdf8eabf9245830aeb61bce05f2dd49a14b0868f8f20b055919a94c487e'
    patch = ROOT / 'dist/cache/published-v3.2.4-update.zip'
    if not patch.exists():
        with urllib.request.urlopen('https://github.com/coldmoth/ma2-panel/releases/download/v3.2.4/ma2-panel-update.zip', timeout=60) as response:
            patch.write_bytes(response.read())
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == 'bc8736d591d8c7dcef33d644e785b2a8b1b4538ff269fa3a6773719709ecf783'
    with tempfile.TemporaryDirectory(prefix='ma2 legacy переход ') as temp:
        folder = Path(temp)
        with zipfile.ZipFile(archive) as packed:
            packed.extractall(folder)
        root = folder / 'ma2-panel/program'
        python = root / 'python/python.exe'
        installed = subprocess.run([str(python), '-c',
            'import pathlib,sys,update; update.install(pathlib.Path(sys.argv[1]), pathlib.Path.cwd())', str(patch)],
            cwd=root, capture_output=True, timeout=120)
        assert installed.returncode == 0, installed.stdout + installed.stderr
        original_version = (root / 'VERSION').read_bytes()
        assert original_version.startswith(b'3.2.4+')
        # Synthetic operator data; never connect the bridge to a console.
        protected = {'config.json': (root / 'config.json').read_bytes(),
                     'settings.json': (root / 'settings.json').read_bytes(),
                     'secret.env': b'MA2_PASSWORD=ci-synthetic',
                     'shows/operator.json': b'{"show":"operator"}',
                     'backups/keep.txt': b'operator backup',
                     'diag/keep.txt': b'operator diagnostic',
                     'rdm-search.json': b'{"state":"pending"}'}
        for name, data in protected.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        target = ROOT / 'dist/update/ma2-panel-update.zip'
        # Establish the known compatibility boundary before testing the migration path.
        rejection = subprocess.run([str(python), '-c', 'import sys,update; update.validate_zip(sys.argv[1])', str(target)],
                                   cwd=root, capture_output=True, timeout=30)
        assert rejection.returncode != 0 and b'invalid location' in rejection.stderr, rejection.stderr
        usb = folder / 'external updater'
        with zipfile.ZipFile(ROOT / 'dist/ma2-panel-update-usb.zip') as packed:
            packed.extractall(usb)
        staged = usb / 'ma2-panel-update'
        updater = staged / 'update.py'
        for command in ([str(python), str(updater), '--root', str(root), str(staged / 'ma2-panel-update.zip')],
                        [str(python), str(updater), '--root', str(root), '--rollback']):
            result = subprocess.run(command, cwd=folder, input=b'y\n', capture_output=True, timeout=120)
            assert result.returncode == 0, result.stdout + result.stderr
            if '--rollback' not in command:
                check = subprocess.run([str(python), '-c', 'from ma2panel import bridge,mock; assert mock.SAMPLE.is_file()'],
                                       cwd=root, capture_output=True, timeout=30)
                assert check.returncode == 0, check.stderr
            for name, data in protected.items():
                assert (root / name).read_bytes() == data, name
        assert (root / 'VERSION').read_bytes() == original_version
        assert not (root / 'ma2panel').exists()
        result = subprocess.run([str(python), str(root / 'bridge.py'), '--help'], cwd=folder,
                                capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
    print('Published v3.2.4 on v3.2.0 runtime: legacy rejection, external USB migration, rollback and user data passed')


def main():
    if os.name != 'nt':
        raise SystemExit('This acceptance check requires Windows x64')
    archive = ROOT / 'dist/ma2-panel-win.zip'
    expected = Path(str(archive) + '.sha256').read_text(encoding='ascii').split()[0]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
    with tempfile.TemporaryDirectory(prefix='ma2 delivered зал ') as temp:
        folder = Path(temp)
        with zipfile.ZipFile(archive) as source:
            assert source.testzip() is None
            source.extractall(folder)
        bundle = folder / 'ma2-panel'
        program = bundle / 'program'
        python = program / 'python/python.exe'
        update_zip = folder / 'update.zip'
        shutil.copy2(ROOT / 'dist/update/ma2-panel-update.zip', update_zip)
        code = r'''
import hashlib,json,pathlib,sys,zipfile
import fastapi,uvicorn,websockets,segno,pydantic_core
import release,update
from ma2panel import bridge,mock
assert mock.SAMPLE.is_file() and mock.REAL_EXPORT.is_file() and mock.TYPE_LIST.is_file()
root=pathlib.Path.cwd()
release.verify_runtime(root)
archive=pathlib.Path(sys.argv[1])
manifest=release.check(archive,json.loads((root/'runtime.json').read_text()))
with zipfile.ZipFile(archive) as packed:
    for name in packed.namelist():
        assert (root/name).read_bytes()==packed.read(name),name
original=(root/'VERSION').read_bytes()
protected={}
for name in update.USER_DATA:
    path=root/name
    if path.is_file(): protected[name]=path.read_bytes()
for name,data in {'shows/operator.json':b'{"plan":"user"}',
                  'secret.env':b'MA2_PASSWORD=ci-synthetic',
                  'rdm-search.json':b'{"state":"pending","target":{"id":42}}'}.items():
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);protected[name]=data
with zipfile.ZipFile(archive) as packed: files={n:packed.read(n) for n in packed.namelist()}
files.pop('program-manifest.json')
files['VERSION']=b'ci-only-next'
manifest['version']='ci-only-next'
manifest['files']={n:{'size':len(d),'sha256':hashlib.sha256(d).hexdigest()} for n,d in files.items()}
files['program-manifest.json']=release._json(manifest)
candidate=root.parent/'candidate.zip';release.write_zip(files,candidate)
update.backup_user_data(root)
update.install(candidate,root)
assert (root/'VERSION').read_bytes()==b'ci-only-next'
update.prepare_bridge=lambda *a,**kw:None
update.rollback(root,confirm=lambda _: 'y')
assert (root/'VERSION').read_bytes()==original
for name,data in protected.items(): assert (root/name).read_bytes()==data,name
release.verify_runtime(root)
print('Delivered runtime imports, payload identity, update, rollback and user/RDM data passed')
'''
        subprocess.run([str(python), '-c', code, str(update_zip)], cwd=program, check=True, timeout=120)
        # BAT arguments and ERRORLEVEL are exercised by cmd.exe, not emulated.
        result = subprocess.run(f'cmd.exe /d /s /c ""{bundle / "start.bat"}" --help"',
                                cwd=folder, input=b'', capture_output=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        result = subprocess.run(f'cmd.exe /d /s /c ""{program / "selfcheck.bat"}" http://127.0.0.1:1"',
                                cwd=folder, input=b'', capture_output=True, timeout=30)
        assert result.returncode == 1, result.stdout + result.stderr
        assert (program / 'selfcheck-report.txt').is_file()
    legacy_transition()
    print('Delivered ZIP SHA256, embedded runtime, Unicode paths and BAT exit codes passed')


if __name__ == '__main__':
    main()
