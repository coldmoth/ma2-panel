"""Exercise production migration, including interrupted two-file writes."""
import json
from pathlib import Path

import pytest

from migrations import migrate_config


def workspace(tmp_path, version=4, settings=None, **extra):
    cfg = {'version': version, 'fixtures': [], 'groups': [], 'scenes': [], 'presets': [], **extra}
    cp, sp = tmp_path / 'config.json', tmp_path / 'settings.json'
    cp.write_text(json.dumps(cfg), encoding='utf-8')
    if settings is not None:
        sp.write_text(json.dumps(settings), encoding='utf-8')
    return cp, sp


def snapshot(tmp_path):
    return {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_moves_settings_and_merges_nested_without_losing_plan(tmp_path):
    cp, sp = workspace(tmp_path, settings={'port': 9091, 'ma2': {'host': 'site', 'timeout': 3}},
                       port=8080, rate_hz=10, ma2={'host': 'old', 'port': 30000, 'password': ''},
                       master={'cmd': 'Master 2.7 At {v}'}, attrs={'pan': {'min': -270}}, custom={'keep': 1})
    raw_cfg, raw_settings = cp.read_bytes(), sp.read_bytes()
    cfg, settings = migrate_config(cp, sp)
    assert cfg['version'] == 5
    assert not {'port', 'rate_hz', 'ma2', 'master'} & cfg.keys()
    assert cfg['attrs'] == {'pan': {'min': -270}} and cfg['custom'] == {'keep': 1}
    assert settings == {'port': 9091, 'rate_hz': 10, 'ma2': {'host': 'site', 'timeout': 3, 'port': 30000},
                        'master': {'cmd': 'Master 2.7 At {v}'}}
    assert json.loads(cp.read_text()) == cfg and json.loads(sp.read_text()) == settings
    backup_bytes = [p.read_bytes() for p in (tmp_path / 'backups').glob('*.json')]
    assert raw_cfg in backup_bytes and raw_settings in backup_bytes
    before = snapshot(tmp_path)
    assert migrate_config(cp, sp) == (cfg, settings)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('version', [1, 2, 3, None])
def test_legacy_reaches_v5_in_one_pass_and_archives_original(tmp_path, version):
    cp, sp = workspace(tmp_path, port=8080, custom=['keep'])
    legacy = json.loads(cp.read_text())
    if version is None:
        legacy.pop('version')
    else:
        legacy['version'] = version
    cp.write_text(json.dumps(legacy))
    original = cp.read_bytes()
    archive = tmp_path / 'shows' / 'legacy.json'
    cfg, settings = migrate_config(cp, sp, archive_path=archive)
    assert cfg['version'] == 5 and cfg['custom'] == ['keep'] and settings['port'] == 8080
    assert archive.read_bytes() == original
    before = snapshot(tmp_path)
    migrate_config(cp, sp, archive_path=archive)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('version', [True, 0, -1, 6, '4', 4.0])
def test_unknown_version_fails_without_any_write(tmp_path, version):
    cp, sp = workspace(tmp_path, version=version)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match='верс'):
        migrate_config(cp, sp, archive_path=tmp_path / 'shows' / 'legacy.json')
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('extra,settings', [({'rate_hz': 0}, {}), ({'port': 8090}, {}),
    ({'ma2': {'password': 'DO-NOT-STORE'}}, {}), ({}, {'rate_hz': 'bad'}),
    ({'master': {'cmd': 42}}, {}), ({'fixtures': {}}, {})])
def test_invalid_data_fails_before_backup_or_write(tmp_path, extra, settings):
    cp, sp = workspace(tmp_path, settings=settings, **extra)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        migrate_config(cp, sp, archive_path=tmp_path / 'shows' / 'legacy.json')
    assert snapshot(tmp_path) == before
    assert not (tmp_path / 'backups').exists()


def test_interrupted_config_write_can_retry_without_losing_settings(tmp_path, monkeypatch):
    import migrations
    cp, sp = workspace(tmp_path, settings={'ma2': {'host': 'site'}}, port=8080,
                       ma2={'host': 'legacy', 'port': 30000})
    original = cp.read_bytes()
    save = migrations.save_config
    def fail_config(path, value):
        if Path(path) == cp:
            raise OSError('interrupted')
        save(path, value)
    monkeypatch.setattr(migrations, 'save_config', fail_config)
    with pytest.raises(OSError, match='interrupted'):
        migrate_config(cp, sp)
    assert cp.read_bytes() == original
    assert json.loads(sp.read_text()) == {'port': 8080, 'ma2': {'host': 'site', 'port': 30000}}
    monkeypatch.setattr(migrations, 'save_config', save)
    cfg, settings = migrate_config(cp, sp)
    assert cfg['version'] == 5 and settings['ma2']['host'] == 'site'


def test_existing_archive_kept_with_backup_before_replacement(tmp_path):
    cp, sp = workspace(tmp_path, version=3, show='Hall')
    archive = tmp_path / 'shows' / 'legacy.json'
    archive.parent.mkdir()
    old = json.dumps({'show': 'Hall', 'custom': 'old'}).encode()
    archive.write_bytes(old)
    original = cp.read_bytes()
    migrate_config(cp, sp, archive_path=archive)
    assert archive.read_bytes() == original
    assert old in [p.read_bytes() for p in (tmp_path / 'backups').glob('*.json')]


def test_archive_for_another_show_refuses_before_write(tmp_path):
    cp, sp = workspace(tmp_path, version=3, show='Hall')
    archive = tmp_path / 'shows' / 'legacy.json'
    archive.parent.mkdir()
    archive.write_text(json.dumps({'show': 'Other'}))
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match='шоу'):
        migrate_config(cp, sp, archive_path=archive)
    assert snapshot(tmp_path) == before


def test_settings_write_failure_leaves_both_original_files(tmp_path, monkeypatch):
    import migrations
    cp, sp = workspace(tmp_path, settings={'port': 9091}, rate_hz=10)
    original_cfg, original_settings = cp.read_bytes(), sp.read_bytes()
    def fail_write(path, value):
        raise OSError('read-only settings')
    monkeypatch.setattr(migrations, 'save_config', fail_write)
    with pytest.raises(OSError, match='read-only'):
        migrate_config(cp, sp)
    assert cp.read_bytes() == original_cfg and sp.read_bytes() == original_settings


@pytest.mark.parametrize('target,value', [('config', []), ('settings', []), ('settings', {'ma2': []})])
def test_bad_top_level_or_nested_settings_does_not_modify_files(tmp_path, target, value):
    cp, sp = workspace(tmp_path, settings={})
    (cp if target == 'config' else sp).write_text(json.dumps(value))
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        migrate_config(cp, sp)
    assert snapshot(tmp_path) == before


def test_migrated_export_path_with_password_word_can_be_loaded(tmp_path):
    from safety import load_settings
    config, settings = workspace(tmp_path, ma2={'export_dir': 'C:/password-tests/importexport'})
    migrate_config(config, settings)
    assert load_settings(settings)['ma2']['export_dir'] == 'C:/password-tests/importexport'
