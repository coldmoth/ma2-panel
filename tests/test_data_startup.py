"""Schema migration is used before deriving runtime connection settings."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
import bridge
from test_bridge import ask, ready


def test_migrated_ma2_survives_partial_runtime_override(tmp_path):
    cfg = json.loads(Path('tests/config.test.json').read_text())
    cfg['ma2'].update(export_dir=str(tmp_path), user='LocalOperator')
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(cfg))
    app = bridge.create_app(cfg, True, str(path), {'poll_seconds': 0, 'ma2': {'timeout': 0.5}})
    with TestClient(app) as client, client.websocket_connect('/ws') as ws:
        ready(ws)
        assert app.state.mock.user == 'LocalOperator'
        assert 'ma2' not in json.loads(path.read_text())
        assert json.loads((tmp_path / 'settings.json').read_text())['ma2']['export_dir'] == str(tmp_path)


def test_fresh_templates_start_and_master_uses_site_setting(tmp_path):
    cfg = json.loads(Path('config.example.json').read_text())
    settings = json.loads(Path('settings.example.json').read_text())
    settings.update(poll_seconds=0, safety={'mode': 'full'}, master={'cmd': 'Master 2.2 At {v}'})
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(cfg))
    settings_path = tmp_path / 'settings.json'
    settings_path.write_text(json.dumps(settings))
    before = path.read_bytes(), settings_path.read_bytes()
    with TestClient(bridge.create_app(cfg, True, str(path), settings, settings_path=settings_path)) as client, client.websocket_connect('/ws') as ws:
        ready(ws)
        ws.send_json({'a': 'master', 'v': 50})
        assert ask(ws, {'a': 'clear'})['ok']  # flush throttle
        assert 'Master 2.2 At 50' in client.app.state.mock.received
        assert before == (path.read_bytes(), settings_path.read_bytes())
        assert not (tmp_path / 'backups').exists()


import pytest


@pytest.mark.parametrize('show', [None, ''])
def test_unnamed_startup_retries_after_interrupted_migration(tmp_path, monkeypatch, show):
    import migrations
    cfg = json.loads(Path('tests/config.test.json').read_text())
    cfg['version'] = 3
    if show is None:
        cfg.pop('show', None)
    else:
        cfg['show'] = show
    cfg['ma2']['export_dir'] = str(tmp_path)
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(cfg))
    original = path.read_bytes()
    save = migrations.save_config
    def fail_config_write(target, value):
        if Path(target) == path:
            raise OSError('interrupted config replacement')
        return save(target, value)
    monkeypatch.setattr(migrations, 'save_config', fail_config_write)
    with pytest.raises(OSError, match='interrupted'):
        bridge.create_app(cfg, True, str(path), {'poll_seconds': 0})
    assert path.read_bytes() == original
    monkeypatch.setattr(migrations, 'save_config', save)
    with TestClient(bridge.create_app(cfg, True, str(path), {'poll_seconds': 0})):
        assert json.loads(path.read_text())['version'] == 5
        assert original in [p.read_bytes() for p in (tmp_path / 'backups').glob('*.json')]
