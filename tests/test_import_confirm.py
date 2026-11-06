"""Regression: ambiguous fixture re-patch requires confirmation (audit 12, plan step 13)."""
import pytest
from ma2panel.fixtures import merge_fixtures


def test_merge_ambiguous_needs_confirmation():
    """Two vanished fixtures match new one by name+type: merge must not guess, needs explicit choice."""
    old = [
        {"id": 5, "label": "Левый", "name": "PAR L", "type": "par", "x": 0.2, "y": 0.3},
        {"id": 6, "label": "Правый", "name": "PAR L", "type": "par", "x": 0.8, "y": 0.3}
    ]
    found = [{"id": 31, "name": "PAR L", "type": "par", "address": "1.400"}]
    result = merge_fixtures(old, found)
    # Ambiguous case: all three present, vanished marked missing, new one has candidates
    assert {f["id"] for f in result} == {5, 6, 31}, "ambiguous case leaves all fixtures"
    missing = [f for f in result if f.get("missing")]
    assert len(missing) == 2 and {m["id"] for m in missing} == {5, 6}, "vanished fixtures marked missing"
    new_fix = [f for f in result if f["id"] == 31][0]
    assert "ambiguous_candidates" in new_fix, "new fixture must carry candidates for UI"
    candidates = new_fix["ambiguous_candidates"]
    assert len(candidates) == 2
    assert {"old_id": 5, "label": "Левый"} in candidates
    assert {"old_id": 6, "label": "Правый"} in candidates


def test_merge_unambiguous_still_works():
    """One vanished fixture matches: auto-merge as before."""
    old = [{"id": 5, "label": "Левый", "name": "PAR L", "type": "par", "x": 0.2, "y": 0.3, "flip_pan": True}]
    found = [{"id": 31, "name": "PAR L", "type": "par", "address": "1.400"}]
    result = merge_fixtures(old, found)
    assert result == [{"id": 31, "label": "Левый", "name": "PAR L", "type": "par", "x": 0.2, "y": 0.3,
                       "flip_pan": True, "params": [], "address": "1.400", "repatched_from": 5}]


def test_merge_no_match_creates_new():
    """No vanished match: create new fixture."""
    old = [{"id": 5, "label": "Старый", "name": "OLD", "type": "old"}]
    found = [{"id": 31, "name": "NEW", "type": "new", "address": "1.500"}]
    result = merge_fixtures(old, found)
    assert len(result) == 2
    missing = [f for f in result if f.get("missing")]
    assert len(missing) == 1 and missing[0]["id"] == 5
    new_fix = [f for f in result if f["id"] == 31][0]
    assert new_fix["label"] == "NEW" and "repatched_from" not in new_fix


def test_two_new_one_old_requires_confirmation():
    old = [{"id": 5, "name": "PAR", "type": "par", "x": 0.3}]
    found = [{"id": i, "name": "PAR", "type": "par", "address": "1.1"} for i in (31, 32)]
    result = merge_fixtures(old, found)
    assert all(f.get("ambiguous_candidates") for f in result if f["id"] in (31, 32))
    assert next(f for f in result if f["id"] == 5)["missing"]


def test_confirm_string_keys_and_explicit_new():
    old = [{"id": i, "name": "PAR", "type": "par", "x": i / 10} for i in (5, 6)]
    found = [{"id": i, "name": "PAR", "type": "par", "address": "1.1"} for i in (31, 32)]
    result = merge_fixtures(old, found, choices={"31": 6, "32": None})
    assert next(f for f in result if f["id"] == 31)["x"] == 0.6
    assert "x" not in next(f for f in result if f["id"] == 32)
    assert next(f for f in result if f["id"] == 5)["missing"]
    assert not any("ambiguous_candidates" in f for f in result)


@pytest.mark.parametrize("choices", [{"31": 5, "32": 5}, {"31": 5}, {"31": True, "32": None}, {"31": 99, "32": None}, {"31": None, "32": None, "33": None}])
def test_confirm_rejects_invalid_choices(choices):
    old = [{"id": i, "name": "PAR", "type": "par"} for i in (5, 6)]
    found = [{"id": i, "name": "PAR", "type": "par", "address": "1.1"} for i in (31, 32)]
    with pytest.raises(ValueError):
        merge_fixtures(old, found, choices=choices)


from contextlib import contextmanager
import json
from pathlib import Path
from fastapi.testclient import TestClient
from ma2panel import bridge
from test_bridge import ask, ready


@contextmanager
def import_client(tmp_path, monkeypatch):
    cfg = json.loads(Path('tests/config.test.json').read_text())
    cfg['fixtures'] = [{'id': i, 'label': str(i), 'name': 'PAR', 'type': 'par', 'x': i / 10} for i in (5, 6)]
    cfg['groups'] = [{'id': 'g', 'label': 'Group', 'fixtures': [6]}]
    cfg['show'] = 'Demo'
    cfg['ma2']['export_dir'] = str(tmp_path)
    monkeypatch.setattr(bridge, 'is_loopback', lambda request: True)
    path = tmp_path / 'config.json'
    app = bridge.create_app(cfg, True, str(path), {'safety': {'mode': 'full'}, 'poll_seconds': 0})
    with TestClient(app) as client, client.websocket_connect('/ws') as ws:
        ready(ws)
        app.state.mock.show_name = 'Demo'
        assert ask(ws, {'a': 'show_identify'})['ok']
        yield client, ws, path


XML = '<MA><Fixture id="31" name="PAR"><FixtureType name="par"/></Fixture></MA>'


def test_http_prepare_and_ws_confirm_persists_choice_and_broadcasts(tmp_path, monkeypatch):
    with import_client(tmp_path, monkeypatch) as (client, ws, path):
        result = client.post('/api/fixtures/import_file', content=XML).json()
        assert result.get('ambiguous'), result
        assert not path.exists(), 'prepare must not write config'
        before = list(client.app.state.mock.received)
        ws.send_json({'a': 'import_confirm_merge', 'request_token': result['request_token'], 'choices': {'31': 6}})
        messages = []
        while not any('ok' in m for m in messages):
            messages.append(ws.receive_json())
        assert messages[-1]['ok'], messages[-1]
        assert any('config' in m and any(f.get('x') == 0.6 and f['id'] == 31 for f in m['config']['fixtures']) for m in messages)
        saved = json.loads(path.read_text())
        assert next(f for f in saved['fixtures'] if f['id'] == 31)['x'] == 0.6
        assert saved['groups'][0]['fixtures'] == [31]
        assert before == client.app.state.mock.received
        assert not ask(ws, {'a': 'import_confirm_merge', 'request_token': result['request_token'], 'choices': {'31': 6}})['ok']


def test_all_new_confirmation_and_invalid_token(tmp_path, monkeypatch):
    with import_client(tmp_path, monkeypatch) as (client, ws, path):
        result = client.post('/api/fixtures/import_file', content=XML).json()
        assert result.get('ambiguous'), result
        assert not ask(ws, {'a': 'import_confirm_merge', 'request_token': 'wrong', 'choices': {'31': 6}})['ok']
        assert not path.exists()
        assert ask(ws, {'a': 'import_confirm_merge', 'request_token': result['request_token'], 'choices': {'31': None}})['ok']
        assert 'x' not in next(f for f in json.loads(path.read_text())['fixtures'] if f['id'] == 31)


def test_pending_import_rejected_after_plan_edit(tmp_path, monkeypatch):
    with import_client(tmp_path, monkeypatch) as (client, ws, path):
        result = client.post('/api/fixtures/import_file', content=XML).json()
        assert result.get('ambiguous'), result
        assert ask(ws, {'a': 'layout_save', 'pos': [{'id': 5, 'x': 0.1, 'y': 0.2}]})['ok']
        before = path.read_bytes()
        assert not ask(ws, {'a': 'import_confirm_merge', 'request_token': result['request_token'], 'choices': {'31': 6}})['ok']
        assert path.read_bytes() == before


def test_http_confirm_is_loopback_only_and_checks_same_token(tmp_path, monkeypatch):
    with import_client(tmp_path, monkeypatch) as (client, ws, path):
        result = client.post('/api/fixtures/import_file', content=XML).json()
        assert result.get('ambiguous'), result
        monkeypatch.setattr(bridge, 'is_loopback', lambda request: False)
        body = {'request_token': result['request_token'], 'choices': {'31': 6}}
        assert client.post('/api/fixtures/import_confirm', json=body).status_code == 403
        assert not path.exists()
        monkeypatch.setattr(bridge, 'is_loopback', lambda request: True)
        assert not client.post('/api/fixtures/import_confirm', json={**body, 'request_token': 'wrong'}).json()['ok']
        before = list(client.app.state.mock.received)
        assert client.post('/api/fixtures/import_confirm', json=body).json()['ok']
        assert before == client.app.state.mock.received
        assert next(f for f in json.loads(path.read_text())['fixtures'] if f['id'] == 31)['x'] == 0.6


def test_pending_replaced_by_new_prepare(tmp_path, monkeypatch):
    with import_client(tmp_path, monkeypatch) as (client, ws, path):
        one = client.post('/api/fixtures/import_file', content=XML).json()
        two = client.post('/api/fixtures/import_file', content=XML).json()
        assert one.get('request_token') != two.get('request_token')
        assert not ask(ws, {'a': 'import_confirm_merge', 'request_token': one['request_token'], 'choices': {'31': 6}})['ok']
        assert ask(ws, {'a': 'import_confirm_merge', 'request_token': two['request_token'], 'choices': {'31': 6}})['ok']


def test_pending_rejected_even_when_edit_is_reverted(tmp_path, monkeypatch):
    with import_client(tmp_path, monkeypatch) as (client, ws, path):
        # Materialize initial normalized plan first, then prepare against it.
        assert ask(ws, {'a': 'layout_save', 'pos': [{'id': 5, 'x': 0.5, 'y': 0.2}]})['ok']
        result = client.post('/api/fixtures/import_file', content=XML).json()
        assert ask(ws, {'a': 'layout_save', 'pos': [{'id': 5, 'x': 0.1, 'y': 0.2}]})['ok']
        assert ask(ws, {'a': 'layout_save', 'pos': [{'id': 5, 'x': 0.5, 'y': 0.2}]})['ok']
        before = path.read_bytes()
        assert not ask(ws, {'a': 'import_confirm_merge', 'request_token': result['request_token'], 'choices': {'31': 6}})['ok']
        assert path.read_bytes() == before


def test_confirm_retains_report_for_fixtures_without_ids(tmp_path, monkeypatch):
    with import_client(tmp_path, monkeypatch) as (client, ws, path):
        xml = XML.replace('</MA>', '<Fixture name="Без номера" channel_id="8"/></MA>')
        prepared = client.post('/api/fixtures/import_file', content=xml).json()
        assert prepared['no_id'] == ['Без номера']
        done = ask(ws, {'a': 'import_confirm_merge', 'request_token': prepared['request_token'], 'choices': {'31': 6}})
        assert done['ok'] and done['no_id'] == ['Без номера']
        assert done['source'] == 'file'
