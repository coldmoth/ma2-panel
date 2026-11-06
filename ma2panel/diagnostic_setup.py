"""One-time, interactive setup of the hall PC's restricted diagnostic token."""
import argparse
import csv
import getpass
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile

from . import diagnostic_upload as upload


def _protect(path):
    if os.name != 'nt':
        os.chmod(path, 0o600)
        return
    # NTFS ACLs, not chmod: remove inherited grants before the token is written.
    identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, text=True, check=True)
    sid = next(csv.reader(io.StringIO(identity.stdout)))[1]
    if not __import__('re').fullmatch(r'S-1-(?:\d+-)*\d+', sid):
        raise OSError('identity')
    subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', f'*{sid}:(F)'],
                   capture_output=True, check=True)


def configure(path, token):
    """Validate destination before replacing credentials; never print the token."""
    if (not isinstance(token, str) or not token or len(token.encode('utf-8')) > 512
            or any(not 33 <= ord(c) <= 126 for c in token)):
        raise upload.UploadError('config')
    upload.Github(token).check_private()
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.diagnostic-token-', dir=path.parent)
    try:
        # On Windows close the handle before adjusting ACLs; there is no secret in the file yet.
        os.close(fd)
        _protect(temporary)
        with open(temporary, 'w', encoding='utf-8') as stream:
            json.dump({'repository': upload.REPOSITORY, 'token': token}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(description='Настройка отправки диагностики в закрытый GitHub-репозиторий')
    parser.add_argument('--settings', type=Path, default=Path(__file__).resolve().parent.parent / 'settings.json')
    args = parser.parse_args()
    print('Получатель: ' + upload.REPOSITORY)
    print('Нужен fine-grained токен: только этот репозиторий, Issues read/write, Metadata read.')
    try:
        token = getpass.getpass('Токен GitHub (ввод скрыт): ')
        configure(args.settings.parent / 'diagnostic-upload.json', token)
    except (Exception, KeyboardInterrupt):
        print('Настройка не выполнена. Проверьте токен, закрытый репозиторий, доступ в интернет и права на папку. Старый доступ сохранён.')
        return 1
    print('Доступ сохранён. Обновите состояние отправки на странице диагностики через localhost.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
