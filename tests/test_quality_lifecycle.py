import json
from pathlib import Path

from ma2panel.commands import load_config
from ma2panel import data_transfer
from ma2panel import release
from ma2panel import update


def test_real_panel_groups_scenes_layout_survive_update_rollback_and_move(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1]
    root = tmp_path / 'installed'; root.mkdir()
    release.write_tree(release.build(source, version='old-candidate'), root)
    (root / 'runtime.json').write_text(json.dumps(release.runtime(source)))
    cfg = json.loads((source / 'ma2panel/resources/config.example.json').read_text())
    cfg.update(show='QA-show', fixtures=[{'id': 1, 'label': 'Прибор', 'type': 'Dimmer', 'x': .25, 'y': .75}],
               groups=[{'id': 'local', 'label': 'Локальная группа', 'fixtures': [1]}],
               scenes=[{'id': 'look', 'exec': '1.101', 'label': 'Сцена'}])
    protected = {'config.json': json.dumps(cfg, ensure_ascii=False).encode(),
                 'settings.json': b'{"custom-site-setting":42}', 'secret.env': b'MA2_PASSWORD=synthetic',
                 'shows/QA-show.json': json.dumps(cfg).encode(), 'rdm-search.json': b'unknown target: keep every byte'}
    for name, data in protected.items():
        p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
    candidate = tmp_path / 'candidate.zip'
    release.write_zip(release.build(source, version='new-candidate'), candidate)
    update.backup_user_data(root)
    update.install(candidate, root)
    for name, data in protected.items(): assert (root / name).read_bytes() == data
    monkeypatch.setattr(update, 'prepare_bridge', lambda *a, **kw: None)
    update.rollback(root, confirm=lambda _: 'y')
    for name, data in protected.items(): assert (root / name).read_bytes() == data
    archive = tmp_path / 'private-transfer.zip'
    data_transfer.backup(root, archive, confirmed_stopped=True)
    moved = tmp_path / 'reinstalled'; moved.mkdir()
    data_transfer.restore(archive, moved, confirmed_stopped=True, confirm=True)
    for name, data in protected.items(): assert (moved / name).read_bytes() == data
    loaded = load_config(str(moved / 'config.json'))
    for key in ('groups', 'scenes'):
        assert loaded[key] == cfg[key]
    assert [(f['x'], f['y']) for f in loaded['fixtures']] == [(.25, .75)]
