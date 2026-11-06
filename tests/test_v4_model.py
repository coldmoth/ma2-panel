"""Task 2: hall, service fixtures and lossless startup migration."""
import asyncio
import json
import threading

import pytest
from fastapi.testclient import TestClient

from ma2panel import bridge
from test_bridge import CONFIG, FULL, ask, bridge_cfg, until  # noqa: F401
from test_safety import tabs
from ma2panel.migrations import SITE_KEYS, legacy_archive_path
from ma2panel.show_plans import plan_path

HALL = {'w': 20, 'd': 9, 'stage': 'left', 'stageDepth': 3}


def test_hall_save_persists_and_broadcasts(tmp_path):
    with tabs(tmp_path, FULL) as ((a, b), mock, client, path):
        before = json.loads(path.read_text())
        sent = list(mock.received)
        assert ask(a, {'a': 'hall_save', 'hall': HALL})['ok']
        assert until(b, lambda m: 'config' in m)['config']['hall'] == HALL
        assert json.loads(path.read_text()) == {**before, 'hall': HALL, 'scene_order_version': 1}
        assert mock.received == sent
        log = client.get('/api/log').json()[0]
        assert log['a'] == 'hall_save' and log['ok'] and log['what'] == {'hall': HALL}


def test_hall_save_rejects_invalid_values(bridge_cfg):
    bad = [None, [], {}, {**HALL, 'extra': 1}]
    for key in ('w', 'd', 'stageDepth'):
        bad.extend({**HALL, key: v} for v in (None, True, '3', 0, 1.9, 81, float('nan'), float('inf')))
    bad.extend({**HALL, 'stage': v} for v in ('front', [], None))
    bad.extend({**HALL, 'stage': stage, 'stageDepth': depth}
               for stage, depth in [('top', 9), ('bottom', 10), ('left', 20), ('right', 21)])
    with bridge_cfg() as (ws, mock, path):
        before = path.read_bytes()
        sent = list(mock.received)
        for hall in bad:
            assert not ask(ws, {'a': 'hall_save', 'hall': hall})['ok'], hall
        assert path.read_bytes() == before and mock.received == sent


def test_hall_orientation_limits(bridge_cfg):
    with bridge_cfg() as (ws, _, path):
        for stage in ('left', 'right', 'top', 'bottom'):
            hall = {**HALL, 'stage': stage, 'stageDepth': 2.5}
            assert ask(ws, {'a': 'hall_save', 'hall': hall})['ok']
            assert json.loads(path.read_text())['hall'] == hall


def test_fixture_flag_updates_zone_and_journal(tmp_path):
    with tabs(tmp_path, FULL) as ((a, b), mock, client, path):
        sent = list(mock.received)
        for service in (True, False):
            assert ask(a, {'a': 'fixture_flag', 'id': 12, 'service': service})['ok']
            config = until(b, lambda m: 'config' in m)['config']
            assert next(f for f in config['fixtures'] if f['id'] == 12)['service'] is service
            assert next(f for f in json.loads(path.read_text())['fixtures'] if f['id'] == 12)['service'] is service
            # Read the current status from a fresh panel; the zone must reflect the flag.
            with client.websocket_connect('/ws') as panel:
                status = until(panel, lambda m: 'status' in m)['status']
                assert (12 in status['highlight']['available']) is (not service)
            entry = client.get('/api/log').json()[0]
            assert entry['a'] == 'fixture_flag' and entry['ok']
            assert entry['what'] == {'id': 12, 'service': service}
        assert mock.received == sent


def test_fixture_flag_rejects_unknown_id_and_non_bool(bridge_cfg):
    with bridge_cfg() as (ws, _, path):
        before = path.read_bytes()
        for change in ({'id': 99999, 'service': True}, {'id': True, 'service': True},
                       {'id': '12', 'service': True}, *({'id': 12, 'service': v} for v in (None, 0, 1, 'true', []))):
            assert not ask(ws, {'a': 'fixture_flag', **change})['ok']
        assert path.read_bytes() == before


@pytest.mark.parametrize('action', [{'a': 'hall_save', 'hall': HALL},
                                    {'a': 'fixture_flag', 'id': 12, 'service': True}])
def test_model_save_failure_keeps_memory_and_disk(bridge_cfg, monkeypatch, action):
    with bridge_cfg() as (ws, _, path):
        before = path.read_bytes()
        def fail(*args):
            raise OSError('disk full')
        monkeypatch.setattr(bridge, 'save_config', fail)
        assert not ask(ws, action)['ok']
        assert path.read_bytes() == before
        # A later layout save serialises the in-memory config.
        monkeypatch.undo()
        assert ask(ws, {'a': 'layout_save', 'pos': [{'id': 12, 'x': .2, 'y': .3}]})['ok']
        saved = json.loads(path.read_text())
        original = json.loads(before)
        assert saved.get('hall') == original.get('hall')
        assert [f.get('service') for f in saved['fixtures']] == [f.get('service') for f in original['fixtures']]


@pytest.mark.parametrize('action', [{'a': 'hall_save', 'hall': HALL},
                                    {'a': 'fixture_flag', 'id': 12, 'service': True}])
def test_model_changes_wait_for_action_lock(tmp_path, monkeypatch, action):
    entered, release = threading.Event(), threading.Event()
    original = bridge.MA2Link.send
    async def delayed(link, cmd, *args, **kwargs):
        if cmd == 'Go Executor 1.101':
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.01)
        return await original(link, cmd, *args, **kwargs)
    monkeypatch.setattr(bridge.MA2Link, 'send', delayed)
    with tabs(tmp_path, FULL) as ((a, b), _, client, path):
        before = path.read_bytes()
        a.send_json({'a': 'scene_go', 'id': 'pianist'})
        assert entered.wait(3)
        b.send_json(action)
        try:
            # This request is a barrier: the event loop has processed the queued action.
            assert client.get('/api/idle').json()['idle'] is False
            assert path.read_bytes() == before
        finally:
            release.set()
        assert until(a, lambda m: 'ok' in m)['ok']
        assert until(b, lambda m: 'ok' in m)['ok']
        assert path.read_bytes() != before


@pytest.mark.parametrize('show', ['Hall / test', None, ''])
def test_startup_migrates_without_clearing_or_repeating(tmp_path, show):
    cfg = json.loads(open(CONFIG).read())
    cfg.pop('version', None)
    cfg['show'] = show
    cfg['hall'] = HALL
    cfg['custom'] = {'keep': [1, 2]}
    cfg['ma2']['export_dir'] = str(tmp_path)
    path = tmp_path / 'config.json'
    raw = json.dumps(cfg, ensure_ascii=False).encode()
    path.write_bytes(raw)
    archive = legacy_archive_path(path, cfg)
    with TestClient(bridge.create_app(cfg, True, str(path), FULL)):
        assert json.loads(path.read_text()) == {**{k: v for k, v in json.loads(raw).items() if k not in SITE_KEYS}, 'version': 5}
        assert archive.read_bytes() == raw
        expected_settings = {k: v for k, v in json.loads(raw).items() if k in SITE_KEYS}
        expected_settings['ma2'].pop('password', None)
        assert json.loads((tmp_path / 'settings.json').read_text()) == expected_settings
        backups = list((tmp_path / 'backups').glob('*.json'))
        assert len(backups) == (1 if show else 2)
        assert all(p.read_bytes() == raw for p in backups)
    snapshot = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*.json')}
    with TestClient(bridge.create_app(json.loads(path.read_text()), True, str(path), FULL)):
        assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*.json')} == snapshot


def test_empty_v4_workspace_starts(bridge_cfg):
    def empty(cfg):
        cfg.update(version=4, fixtures=[], groups=[], scenes=[], presets=[], pages={})
    with bridge_cfg(empty) as (ws, mock, path):
        assert json.loads(path.read_text())['fixtures'] == []
        assert json.loads(path.read_text())['version'] == 5
        backups = {p.name: p.read_bytes() for p in (path.parent / 'backups').glob('*.json')}
        assert any(name.startswith('config-v4-') for name in backups)
        assert ask(ws, {'a': 'hall_save', 'hall': HALL})['ok']
        assert mock.received == ['login "panel" ""', 'ListVar']
        assert {p.name: p.read_bytes() for p in (path.parent / 'backups').glob('*.json')} == backups
