"""Build the delivered Windows x64 bundle on Windows, Linux or macOS."""
import hashlib
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import release

PYTHON = '3.12.10'
# Fixed input fetched from python.org; a cache entry must match before extraction.
PYTHON_SHA256 = '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'


def write_bundle(tree, archive):
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as out:
        for path in sorted(Path(tree).rglob('*')):
            if path.is_symlink():
                raise ValueError('symlink in bundle')
            if not path.is_file():
                continue
            info = zipfile.ZipInfo(path.relative_to(tree).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            out.writestr(info, path.read_bytes())
    digest = hashlib.sha256(Path(archive).read_bytes()).hexdigest()
    Path(str(archive) + '.sha256').write_text(f'{digest}  {Path(archive).name}\n', encoding='ascii')


def main():
    cache = ROOT / 'dist/cache'
    cache.mkdir(parents=True, exist_ok=True)
    embedded = cache / f'python-{PYTHON}-embed-amd64.zip'
    if not embedded.exists():
        with urllib.request.urlopen(f'https://www.python.org/ftp/python/{PYTHON}/{embedded.name}', timeout=60) as response:
            data = response.read(32 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != PYTHON_SHA256:
            raise ValueError('embedded Python SHA256 mismatch')
        embedded.write_bytes(data)
    if hashlib.sha256(embedded.read_bytes()).hexdigest() != PYTHON_SHA256:
        raise ValueError('cached embedded Python SHA256 mismatch; remove invalid cache entry')
    tree = ROOT / 'dist/ma2-panel-win'
    shutil.rmtree(tree, ignore_errors=True)
    bundle = tree / 'ma2-panel'
    program = bundle / 'program'
    (program / 'python').mkdir(parents=True)
    with zipfile.ZipFile(embedded) as source:
        source.extractall(program / 'python')  # Fixed archive, verified against pinned digest.
    (program / 'python/python312._pth').write_bytes(b'python312.zip\r\n.\r\n..\r\n..\\lib\r\nimport site\r\n')
    requirements = cache / 'req.txt'
    subprocess.run(['uv', 'export', '--locked', '--no-dev', '--no-emit-project', '--output-file', str(requirements)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['uv', 'pip', 'install', '--target', str(program / 'lib'), '--python-platform', 'windows',
                    '--python-version', '3.12', '--only-binary', ':all:', '--no-deps', '--require-hashes',
                    '--requirement', str(requirements)], cwd=ROOT, check=True)
    shutil.rmtree(program / 'lib/bin', ignore_errors=True)
    subprocess.run([sys.executable, str(ROOT / 'scripts/package_release.py'), '--tree', str(program)], cwd=ROOT, check=True)
    shutil.copy2(ROOT / 'secret.env.example', program)
    for name in ('config', 'settings'):
        shutil.copy2(ROOT / f'{name}.example.json', program / f'{name}.json')
    release.write_windows_launcher(bundle)
    for path in program.rglob('__pycache__'):
        shutil.rmtree(path)
    release.record_runtime(program)
    write_bundle(tree, ROOT / 'dist/ma2-panel-win.zip')
    usb = ROOT / 'dist/usb'
    shutil.rmtree(usb, ignore_errors=True)
    folder = usb / 'ma2-panel-update'
    folder.mkdir(parents=True)
    for source in ('dist/update/ma2-panel-update.zip', 'dist/update/ma2-panel-update.zip.sha256',
                   'update.py', 'release.py', 'win/update-usb.bat', 'docs/update-usb.txt'):
        shutil.copy2(ROOT / source, folder / Path(source).name)
    write_bundle(usb, ROOT / 'dist/ma2-panel-update-usb.zip')
    print('Built Windows x64 and USB ZIPs with SHA256 sidecars')


if __name__ == '__main__':
    main()
