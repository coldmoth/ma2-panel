"""Lossless, restartable migration of plans and site settings to schema v5.

Settings are replaced before the config version marker. If that last replacement
fails, a retry preserves the already migrated settings and repeats safely.
"""
import copy
import json
import re
import shutil
import time
from pathlib import Path

from fixtures import save_config
from safety import validate_settings

SITE_KEYS = ('port', 'rate_hz', 'ma2', 'master')


def _read(path, default=None):
    if not path.exists() and default is not None:
        return copy.deepcopy(default)
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError(f'{path.name}: требуется объект JSON')
    return value


def merge_settings(legacy, current):
    """Current site settings win at each leaf, without discarding legacy siblings."""
    result = copy.deepcopy(legacy)
    for key, value in current.items():
        result[key] = (merge_settings(result[key], value)
                       if isinstance(result.get(key), dict) and isinstance(value, dict)
                       else copy.deepcopy(value))
    return result


def _backup(path, folder, label):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'{label}-{time.strftime("%Y%m%d-%H%M%S")}.json'
    index = 1
    while target.exists():
        target = folder / f'{label}-{time.strftime("%Y%m%d-%H%M%S")}-{index}.json'
        index += 1
    shutil.copy2(path, target)


def legacy_archive_path(config_path, cfg):
    """Raw unnamed legacy snapshots are backups, not owner-checked show plans."""
    version = cfg.get('version', 3)
    if type(version) is not int or version >= 4:
        return None
    folder = Path(config_path).parent
    name = cfg.get('show')
    if not isinstance(name, str) or not name.strip():
        return folder / 'backups' / 'unnamed-plan-v3.json'
    from show_plans import plan_path
    return plan_path(folder / 'shows', name, write=True)


def migrate_config(config_path, settings_path, *, archive_path=None):
    """Return ``(config, settings)`` after validated, backed-up v1..v4 migration.

    Missing config version is the historical v3 layout. v5 is read-only;
    unsupported versions fail before creating backups. ``archive_path`` preserves
    the exact pre-v4 plan; another show's archive is never overwritten.
    """
    config_path, settings_path = Path(config_path), Path(settings_path)
    if config_path.resolve() == settings_path.resolve():
        raise ValueError('config и settings должны быть разными файлами')
    cfg = _read(config_path)
    settings = _read(settings_path, {})
    version = cfg.get('version', 3)
    if type(version) is not int or not 1 <= version <= 5:
        raise ValueError('неподдерживаемая версия config.json')
    for key in ('fixtures', 'groups', 'scenes', 'presets'):
        if key in cfg and not isinstance(cfg[key], list):
            raise ValueError(f'config.{key}: требуется список')
    if version == 5:
        return cfg, settings

    legacy_site = {key: copy.deepcopy(cfg[key]) for key in SITE_KEYS if key in cfg}
    if 'ma2' in legacy_site:
        if not isinstance(legacy_site['ma2'], dict):
            raise ValueError('config.ma2: требуется объект')
        if legacy_site['ma2'].get('password'):
            raise ValueError('Пароль нельзя хранить в config: используйте secret.env')
        legacy_site['ma2'].pop('password', None)
    migrated_settings = merge_settings(legacy_site, settings)
    try:
        validate_settings({**migrated_settings, **({"port": 8080} if migrated_settings.get("port") == 0 else {})})
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    if 'master' in migrated_settings:
        master = migrated_settings['master']
        if (not isinstance(master, dict) or not isinstance(master.get('cmd'), str)
                or not re.fullmatch(r'Master \d+\.\d+ At \{v\}', master['cmd'])):
            raise ValueError('master.cmd: требуется Master N.N At {v}')
    migrated_cfg = {key: value for key, value in cfg.items() if key not in SITE_KEYS}
    migrated_cfg['version'] = 5

    archive = Path(archive_path) if archive_path is not None and version < 4 else None
    if archive is not None:
        if archive.resolve() in (config_path.resolve(), settings_path.resolve()):
            raise ValueError('архив плана должен быть отдельным файлом')
        if archive.exists() and _read(archive).get('show') != cfg.get('show'):
            raise ValueError('архив принадлежит другому шоу')

    # All validation above happens before any disk mutation.
    backups = config_path.parent / 'backups'
    _backup(config_path, backups, f'config-v{version}')
    if settings_path.exists():
        _backup(settings_path, backups, f'settings-v{version}')
    if archive is not None:
        if archive.exists():
            _backup(archive, backups, f'show-v{version}')
        archive.parent.mkdir(parents=True, exist_ok=True)
        # Atomic byte-for-byte archive: no new representation of the original.
        import os
        import tempfile
        with tempfile.NamedTemporaryFile(dir=archive.parent, suffix='.tmp', delete=False) as tmp:
            tmp_name = tmp.name
        try:
            shutil.copy2(config_path, tmp_name)
            os.replace(tmp_name, archive)
        finally:
            Path(tmp_name).unlink(missing_ok=True)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    save_config(str(settings_path), migrated_settings)
    save_config(str(config_path), migrated_cfg)
    return migrated_cfg, migrated_settings
