"""Exercise the shipped Windows artifact, never a user installation or real MA2."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


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
    print('Delivered ZIP SHA256, embedded runtime, Unicode paths and BAT exit codes passed')


if __name__ == '__main__':
    main()
