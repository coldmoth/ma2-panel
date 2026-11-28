"""Tests for layout_templates backup, HALL_TRIAL updater compatibility, and StatusRelay LUMA redirects."""
from urllib.request import urlopen
from zipfile import ZipFile, ZipInfo

from ma2panel import browser_update as bu
from ma2panel import update


def _archive(path, extra=None):
    with ZipFile(path, 'w') as z:
        for name, value in {'bridge.py': 'new', 'VERSION': 'v2', 'static/new.txt': 'new', **(extra or {})}.items():
            info = ZipInfo(name)
            info.filename = name
            z.writestr(info, value)
    return path


def test_backup_preserves_layout_templates_and_luma_hall_trial_update_rollback(tmp_path, monkeypatch):
    root = tmp_path / 'luma_app'
    (root / 'ma2panel').mkdir(parents=True)
    (root / 'static' / 'luma').mkdir(parents=True)
    (root / 'layout_templates').mkdir()
    (root / 'bridge.py').write_text('v1')
    (root / 'VERSION').write_text('3.4.0-beta.1')
    (root / 'ma2panel' / 'HALL_TRIAL').write_text('Controlled LUMA hall trial\n')
    (root / 'static' / 'luma' / 'index.html').write_text('<h1>LUMA beta 1</h1>')
    (root / 'layout_templates' / 'layout-abc.xml').write_text('<MA><Group name="Hall"/></MA>')

    backup = update.backup_user_data(root)
    assert (backup / 'layout_templates' / 'layout-abc.xml').read_text() == '<MA><Group name="Hall"/></MA>'

    pkg = _archive(tmp_path / 'luma-beta2.zip', {
        'VERSION': '3.4.0-beta.2',
        'ma2panel/HALL_TRIAL': 'Controlled LUMA hall trial\n',
        'static/luma/index.html': '<h1>LUMA beta 2</h1>',
    })
    update.install(pkg, root)
    assert (root / 'ma2panel' / 'HALL_TRIAL').is_file()
    assert (root / 'static' / 'luma' / 'index.html').read_text() == '<h1>LUMA beta 2</h1>'
    assert (root / 'layout_templates' / 'layout-abc.xml').read_text() == '<MA><Group name="Hall"/></MA>'

    monkeypatch.setattr(update, 'idle', lambda _: None)
    assert update.rollback(root, confirm=lambda _: 'y') == 0
    assert (root / 'ma2panel' / 'HALL_TRIAL').is_file()
    assert (root / 'static' / 'luma' / 'index.html').read_text() == '<h1>LUMA beta 1</h1>'
    assert (root / 'layout_templates' / 'layout-abc.xml').read_text() == '<MA><Group name="Hall"/></MA>'


def test_status_relay_serves_luma_path_and_redirects_by_hall_trial(tmp_path):
    bu.progress(tmp_path, '5' * 32, 'installing')
    relay = bu.StatusRelay(tmp_path, 0)
    try:
        relay.start()
        # Classic installation: /luma/ serves progress page and redirects to /settings.html
        with urlopen(f'http://127.0.0.1:{relay.port}/luma/') as resp:
            body = resp.read().decode('utf-8')
            assert resp.status == 200 and "location.href='/settings.html'" in body
        # HALL_TRIAL installation: / and /luma/ redirect to / (LUMA)
        (tmp_path / 'ma2panel').mkdir()
        (tmp_path / 'ma2panel' / 'HALL_TRIAL').write_text('Controlled LUMA hall trial\n')
        for path in ('/', '/luma/'):
            with urlopen(f'http://127.0.0.1:{relay.port}{path}') as resp:
                body = resp.read().decode('utf-8')
                assert resp.status == 200 and "location.href='/'" in body
    finally:
        relay.stop()
