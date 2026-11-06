"""Owner-only: hidden token input, validated locally and installed via SSH stdin."""
import getpass
import json
from pathlib import Path
import shlex
import subprocess
import sys

from ma2panel.diagnostic_upload import Github, REPOSITORY


REMOTE = '''
import grp, json, os, pathlib, tempfile
data = json.load(__import__('sys').stdin)
if set(data) != {'repository', 'token'} or data['repository'] != 'coldmoth/ma2-panel-diagnostics':
    raise SystemExit(1)
folder = pathlib.Path('/etc/ma2-diagnostics')
gid = grp.getgrnam('ma2-diagnostics').gr_gid
folder.mkdir(mode=0o750, exist_ok=True)
os.chown(folder, 0, gid)
os.chmod(folder, 0o750)
fd, name = tempfile.mkstemp(prefix='.github-', dir=folder)
try:
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o640)
        os.fchown(stream.fileno(), 0, gid)
        json.dump(data, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(name, folder / 'github.json')
    fd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
finally:
    if os.path.exists(name):
        os.unlink(name)
'''


def install(token):
    if (not isinstance(token, str) or not token or len(token.encode('utf-8')) > 512
            or any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in token)):
        raise ValueError('Invalid credential')
    Github(token).check_private()
    subprocess.run([
        'ssh', '-i', str(Path.home() / '.ssh' / 'ma2_diagnostics_ed25519'),
        '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
        'root@132.243.222.221', 'python3 -c ' + shlex.quote(REMOTE),
    ], input=json.dumps({'repository': REPOSITORY, 'token': token}).encode('utf-8'),
        capture_output=True, check=True, timeout=30)


def main():
    print('Однократная настройка сервера diag.shmyrev52.ru.')
    print('Нужен ограниченный токен: только ma2-panel-diagnostics, Issues read/write и Metadata read.')
    try:
        token = getpass.getpass('Токен GitHub (ввод скрыт): ')
        install(token)
        subprocess.run([
            'ssh', '-i', str(Path.home() / '.ssh' / 'ma2_diagnostics_ed25519'),
            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
            'root@132.243.222.221', 'systemctl restart ma2-diagnostics',
        ], capture_output=True, check=True, timeout=30)
    except (Exception, KeyboardInterrupt):
        print('Настройка не завершена. Проверьте права токена, SSH-доступ и наличие сервиса на сервере.')
        return 1
    print('Доступ установлен на сервере. Пользовательским ПК токен не нужен.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
