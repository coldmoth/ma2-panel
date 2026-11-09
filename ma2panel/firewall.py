"""Apply narrowly scoped Windows rules using the saved panel ports."""
import json
from pathlib import Path
import subprocess


def apply(root):
    root = Path(root)
    path = root / 'settings.json'
    settings = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    port, simple = settings.get('port', 8080), settings.get('simple_port', 8090)
    if any(type(value) is not int or not 1 <= value <= 65535 for value in (port, simple) if value is not None) or port is None or port == simple:
        raise ValueError('Недопустимые порты панели')
    for name, value, profile in (('MA2 panel', port, 'private,domain'), ('MA2 simple panel', simple, 'private')):
        prefix = ['netsh', 'advfirewall', 'firewall']
        subprocess.run([*prefix, 'delete', 'rule', f'name={name}'], check=False, capture_output=True)
        if value is not None:
            subprocess.run([*prefix, 'add', 'rule', f'name={name}', 'dir=in', 'action=allow',
                            f'program={root / "python/python.exe"}', 'protocol=TCP', f'localport={value}',
                            'remoteip=LocalSubnet', f'profile={profile}', 'enable=yes'], check=True)


def main():
    apply(Path(__file__).resolve().parent.parent)


if __name__ == '__main__':
    main()
