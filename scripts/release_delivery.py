"""Verify the tested delivery set, then publish through an unpublished GitHub draft."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

from ma2panel import release

ARCHIVES = ('ma2-panel-win.zip', 'ma2-panel-update.zip', 'ma2-panel-update-usb.zip')
REQUIRED = ('bridge.py', 'start.bat', 'update.py', 'release.py', 'browser_update.py',
            'ma2panel/__init__.py', 'ma2panel/__main__.py', 'ma2panel/bridge.py',
            'ma2panel/onboarding.py', 'ma2panel/resources/config.example.json',
            'ma2panel/resources/settings.example.json', 'ma2panel/resources/secret.env.example',
            'static/index.html', 'static/setup.html', 'static/setup.js', 'static/setup.css', 'static/simple.html',
            'ma2panel/resources/mock/sample_export.xml', 'ma2panel/resources/mock/real_export_3.9.60.xml',
            'ma2panel/resources/mock/list_fixturetype_3.9.60.txt', 'selfcheck.bat', 'rollback.bat')


def validate(folder, commit, tag):
    folder = Path(folder)
    if not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise ValueError('Expected a stable vX.Y.Z tag')
    inputs = json.loads((folder / 'build-inputs.json').read_text(encoding='utf-8'))
    if inputs['commit'] != commit or inputs['version'] != tag[1:] + '+' + commit[:7]:
        raise ValueError('Build commit/version differs from release (or dirty source tree)')
    assets = [folder / 'build-inputs.json']
    for name in ARCHIVES:
        archive = folder / name
        sidecar = folder / (name + '.sha256')
        if sidecar.read_text(encoding='ascii').split() != [hashlib.sha256(archive.read_bytes()).hexdigest(), name]:
            raise ValueError('SHA256 mismatch: ' + name)
        with zipfile.ZipFile(archive) as packed:
            if packed.testzip() is not None or len(packed.namelist()) != len(set(packed.namelist())):
                raise ValueError('Corrupt or duplicate ZIP entries: ' + name)
        assets.extend((archive, sidecar))
    with zipfile.ZipFile(folder / ARCHIVES[1]) as update:
        files = {n: update.read(n) for n in update.namelist()}
        manifest = json.loads(files['program-manifest.json'])
        if manifest['version'] != inputs['version']:
            raise ValueError('Payload version mismatch')
        for name in REQUIRED:
            if name not in files:
                raise ValueError('Missing program entry: ' + name)
        if set(files) != set(manifest['files']) | {'program-manifest.json'}:
            raise ValueError('Manifest file set mismatch')
        for name, info in manifest['files'].items():
            if info != {'size': len(files[name]), 'sha256': hashlib.sha256(files[name]).hexdigest()}:
                raise ValueError('Manifest mismatch: ' + name)
    with zipfile.ZipFile(folder / ARCHIVES[0]) as full:
        for name, data in files.items():
            if full.read('ma2-panel/program/' + name) != data:
                raise ValueError('Full/update payload mismatch: ' + name)
        for name in ('start.bat', 'program/python/python.exe', 'program/lib/fastapi/__init__.py',
                     'program/runtime.json', 'program/runtime-files.json'):
            full.getinfo('ma2-panel/' + name)
    with zipfile.ZipFile(folder / ARCHIVES[2]) as usb:
        for name in (ARCHIVES[1], ARCHIVES[1] + '.sha256'):
            if usb.read('ma2-panel-update/' + name) != (folder / name).read_bytes():
                raise ValueError('USB/update archive mismatch')
        for name in ('update.py', 'release.py'):
            if usb.read('ma2-panel-update/' + name) != files[name]:
                raise ValueError('USB updater differs from release')
        for name in ('update-usb.bat', 'update-usb.txt'):
            usb.getinfo('ma2-panel-update/' + name)
    return assets


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True).strip()


def notes(tag, changes):
    base = f'https://github.com/coldmoth/ma2-panel/releases/download/{tag}/'
    return f'''## Скачать для Windows
[ma2-panel-win.zip]({base}ma2-panel-win.zip) — полное приложение с Python и зависимостями.

## Установка
Распакуйте весь ZIP в папку с правом записи. Запустите внешний **start.bat**, оставьте окно открытым и пройдите мастер настройки. Отдельно устанавливать Python не нужно.

## Изменения
{changes.strip()}

## Обновление
**С v3.2.0–v3.2.4:** остановите приложение, распакуйте [ma2-panel-update-usb.zip]({base}ma2-panel-update-usb.zip) отдельно от установки, запустите **update-usb.bat** и выберите установленную папку **program**. Старый встроенный updater не принимает этот выпуск. Не заменяйте файлы updater вручную.

**С v3.2.5 и совместимых новых версий:** используйте [ma2-panel-update.zip]({base}ma2-panel-update.zip). Настройки, пароли, шоу и backups сохраняются. Сохраните **previous/** и **.updates/** для отката; следуйте инструкции USB-комплекта. На новый компьютер устанавливайте полный ZIP.

## Требования
Windows 10/11 x64, современный браузер и grandMA2 onPC 3.9 с настроенным Telnet Remote. Используйте доверенную локальную сеть.

## Ограничения проверки
Интерфейс на русском языке. Полная аппаратная приёмка новой интеграции не завершена: в этой сессии использовался mock. Исторический onPC 3.9.63.11 проверял команды и пустые Cue без физических приборов. Crossfade реального света, HTP/LTP/Programmer и сложные профили требуют проверки на целевой MA2; подробности — docs/RELEASE-3.3.md и docs/hardware-acceptance.md в репозитории. Каждый из трёх ZIP сопровождается SHA256.
'''


def publish(folder, commit, tag, changes):
    assets = validate(folder, commit, tag)
    # Refuse existing releases, including drafts. Never replace published assets.
    existing = json.loads(gh('api', '--paginate', '--slurp', 'repos/{owner}/{repo}/releases?per_page=100'))
    if any(r['tag_name'] == tag for page in existing for r in page):
        raise ValueError('Release already exists; refusing to modify it')
    latest = json.loads(gh('api', 'repos/{owner}/{repo}/releases/latest'))['tag_name']
    if tuple(map(int, tag[1:].split('.'))) <= tuple(map(int, latest.removeprefix('v').split('.'))):
        raise ValueError('Version must be newer than the latest release')
    refs = json.loads(gh('api', 'repos/{owner}/{repo}/git/matching-refs/tags/' + tag))
    if any(r['ref'] == 'refs/tags/' + tag for r in refs):
        tagged = json.loads(gh('api', 'repos/{owner}/{repo}/commits/' + tag))['sha']
        if tagged != commit:
            raise ValueError('Existing tag points to a different commit')
    with tempfile.TemporaryDirectory(prefix='ma2-publish-') as temp:
        temp = Path(temp)
        body = temp / 'notes.md'
        body.write_text(notes(tag, Path(changes).read_text(encoding='utf-8')), encoding='utf-8')
        gh('release', 'create', tag, *(str(p) for p in assets), '--target', commit,
           '--draft', '--title', 'ma2-panel ' + tag, '--notes-file', str(body))
        info = json.loads(gh('release', 'view', tag, '--json', 'assets,isDraft,targetCommitish'))
        if not info['isDraft'] or info['targetCommitish'] != commit or sorted(a['name'] for a in info['assets']) != sorted(p.name for p in assets):
            raise ValueError('Draft release assets/commit mismatch; left unpublished')
        downloaded = temp / 'download'
        gh('release', 'download', tag, '--dir', str(downloaded))
        for path in assets:
            if (downloaded / path.name).read_bytes() != path.read_bytes():
                raise ValueError('Uploaded asset mismatch; draft left unpublished')
        validate(downloaded, commit, tag)
        gh('release', 'edit', tag, '--draft=false', '--latest')
    print('Published complete verified release: ' + tag)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--changes', default='docs/release-changes.md')
    args = parser.parse_args()
    if args.publish:
        publish(args.folder, args.commit, args.tag, args.changes)
    else:
        validate(args.folder, args.commit, args.tag)
        print('All three ZIPs, SHA256, commit and payload identity verified')


if __name__ == '__main__':
    main()
