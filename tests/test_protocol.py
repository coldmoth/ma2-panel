"""Request correlation, stale edits and truthful transport outcomes."""
import json
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from bridge import create_app, MA2Link
from test_bridge import bridge_cfg, ask, ready, until, CONFIG, FULL


def test_request_errors_are_correlated(bridge_cfg):
    with bridge_cfg() as (ws, _, _):
        for action in ({"a": "not_an_action"}, {"a": "select_fixtures", "ids": [999]}):
            r = ask(ws, {**action, "request_id": "error-1" + action["a"]})
            assert r["request_id"] == "error-1" + action["a"]
            assert r["outcome"] == "failed"
        r = ask(ws, {"a": "clear", "request_id": []})
        assert not r["ok"] and "request_id" in r["err"]


def test_same_request_is_not_replayed(bridge_cfg):
    with bridge_cfg() as (ws, mock, _):
        action = {"a": "scene_go", "id": "pianist", "request_id": "once"}
        r = ask(ws, action)
        assert r["outcome"] == "completed"
        before = len(mock.received)
        r = ask(ws, action)
        assert not r["ok"] and r["request_id"] == "once"
        assert len(mock.received) == before


@pytest.mark.parametrize("clients", [2, 5])
def test_stale_shared_plan_edits_rejected(tmp_path, clients):
    cfg = json.loads(open(CONFIG).read())
    cfg["ma2"]["export_dir"] = str(tmp_path)
    with TestClient(create_app(cfg, True, str(tmp_path / "c.json"), FULL)) as client, ExitStack() as stack:
        sockets = [stack.enter_context(client.websocket_connect("/ws")) for _ in range(clients)]
        snapshots = [until(ws, lambda m: "config" in m)["config"] for ws in sockets]
        token = snapshots[0]["revision"]
        r = ask(sockets[0], {"a": "group_save", "label": "Первый", "ids": [12], "request_id": "write1", "config_revision": token})
        assert r["ok"]
        for i, ws in enumerate(sockets[1:]):
            r = ask(ws, {"a": "group_save", "label": "Устарел", "ids": [12], "request_id": f"stale{i}", "config_revision": token})
            assert not r["ok"] and r["conflict"]
        assert not any(g["label"] == "Устарел" for g in json.loads((tmp_path / "c.json").read_text())["groups"])


@pytest.mark.parametrize("failure,outcome", [("error", "partial"), ("unknown", "unknown")])
def test_multiline_failure_stops_and_reports_evidence(bridge_cfg, monkeypatch, failure, outcome):
    with bridge_cfg(lambda c: c["scenes"].append({"id": "second", "exec": "1.102", "label": "Second"})) as (ws, _, _):
        original = MA2Link.send
        calls = []
        async def injected(self, cmd, *args, **kwargs):
            if cmd.startswith("Off Executor"):
                calls.append(cmd)
                if len(calls) == 2:
                    self._result(cmd, failure, "injected")
                    return False, "injected"
            return await original(self, cmd, *args, **kwargs)
        monkeypatch.setattr(MA2Link, "send", injected)
        r = ask(ws, {"a": "blackout", "request_id": "blackout1"})
        assert not r["ok"] and r["outcome"] == outcome
        assert len(calls) == 2


def test_legacy_stale_session_cannot_overwrite(tmp_path):
    cfg = json.loads(open(CONFIG).read())
    cfg["ma2"]["export_dir"] = str(tmp_path)
    with TestClient(create_app(cfg, True, str(tmp_path / "c.json"), FULL)) as client:
        with client.websocket_connect('/ws') as first, client.websocket_connect('/ws') as stale:
            ready(first); ready(stale)
            assert ask(first, {"a": "group_save", "label": "Fresh", "ids": [12]})['ok']
            assert not ask(stale, {"a": "group_save", "label": "Stale", "ids": [12]})['ok']


def test_slider_terminal_reply_is_after_actual_send(bridge_cfg):
    with bridge_cfg() as (ws, mock, _):
        assert ask(ws, {"a": "select_fixtures", "ids": [12]})['ok']
        ws.send_json({"a": "dim", "v": 42, "request_id": "slider"})
        r = until(ws, lambda m: m.get('request_id') == 'slider' and 'ok' in m)
        assert r['outcome'] == 'completed' and 'At 42' in mock.received


def test_disconnect_does_not_replay_on_new_socket(tmp_path):
    cfg = json.loads(open(CONFIG).read()); cfg['ma2']['export_dir'] = str(tmp_path)
    app = create_app(cfg, True, str(tmp_path / 'c.json'), FULL)
    with TestClient(app) as client:
        with client.websocket_connect('/ws') as first:
            ready(first)
            assert ask(first, {"a": "scene_go", "id": "pianist", "request_id": "old-socket"})['ok']
        before = app.state.mock.received.count('Go Executor 1.101')
        with client.websocket_connect('/ws') as second:
            ready(second)
            ask(second, {"a": "clear", "request_id": "barrier"})
            assert app.state.mock.received.count('Go Executor 1.101') == before


def test_fade_failure_stops_further_ticks(bridge_cfg, monkeypatch):
    with bridge_cfg(settings={**FULL, 'rate_hz': 10}) as (ws, mock, _):
        ask(ws, {"a": "select_fixtures", "ids": [12]})
        ws.send_json({"a": "dim", "v": 20, "request_id": "initial"})
        assert until(ws, lambda m: m.get('request_id') == 'initial').get('ok')
        original = MA2Link.send
        values = []
        async def injected(self, cmd, *args, **kwargs):
            if cmd.startswith('At '):
                values.append(cmd)
                self._result(cmd, 'unknown', 'injected timeout')
                return False, 'injected timeout'
            return await original(self, cmd, *args, **kwargs)
        monkeypatch.setattr(MA2Link, 'send', injected)
        ws.send_json({"a": "dim", "v": 80, "fade": .4, "request_id": "fade"})
        r = until(ws, lambda m: m.get('request_id') == 'fade' and 'ok' in m)
        assert not r['ok'] and r['outcome'] == 'unknown'
        # Flush other work; a failed first stage must not leave later value intents behind.
        ask(ws, {"a": "clear", "request_id": "after-fade"})
        assert len(values) == 1


def test_revision_identity_changes_on_restart(tmp_path):
    revisions = []
    for _ in range(2):
        cfg = json.loads(open(CONFIG).read()); cfg['ma2']['export_dir'] = str(tmp_path)
        with TestClient(create_app(cfg, True, str(tmp_path / 'c.json'), FULL)) as client:
            with client.websocket_connect('/ws') as ws:
                revisions.append(until(ws, lambda m: 'config' in m)['config']['revision'])
    assert revisions[0] != revisions[1]


def test_modern_config_write_requires_revision(bridge_cfg):
    with bridge_cfg() as (ws, _, _):
        r = ask(ws, {'a': 'group_save', 'label': 'Missing revision', 'ids': [12], 'request_id': 'missing-rev'})
        assert not r['ok'] and r['conflict'] and r['outcome'] == 'failed'


def test_disconnect_drops_unsent_slider(tmp_path):
    cfg = json.loads(open(CONFIG).read()); cfg['ma2']['export_dir'] = str(tmp_path)
    app = create_app(cfg, True, str(tmp_path / 'c.json'), {**FULL, 'rate_hz': 1})
    with TestClient(app) as client:
        with client.websocket_connect('/ws') as first:
            ready(first)
            ask(first, {'a': 'select_fixtures', 'ids': [12]})
            first.send_json({'a': 'dim', 'v': 71, 'request_id': 'unsent'})
            until(first, lambda m: any(op['a'] == 'dim' for op in m.get('status', {}).get('operations', [])))
        with client.websocket_connect('/ws') as second:
            ready(second)
            assert ask(second, {'a': 'clear', 'request_id': 'flush-old'})['ok']
            assert 'At 71' not in app.state.mock.received


def test_concurrent_saves_have_one_winner(tmp_path):
    cfg = json.loads(open(CONFIG).read()); cfg['ma2']['export_dir'] = str(tmp_path)
    with TestClient(create_app(cfg, True, str(tmp_path / 'c.json'), FULL)) as client:
        with client.websocket_connect('/ws') as first, client.websocket_connect('/ws') as second:
            revision = until(first, lambda m: 'config' in m)['config']['revision']
            until(second, lambda m: 'config' in m)
            for ws, rid in ((first, 'a'), (second, 'b')):
                ws.send_json({'a': 'group_save', 'label': rid, 'ids': [12], 'request_id': rid, 'config_revision': revision})
            replies = [until(ws, lambda m: 'ok' in m) for ws in (first, second)]
            assert sorted(r['ok'] for r in replies) == [False, True]
            loser = next(r for r in replies if not r['ok'])
            assert loser['conflict']
            assert loser['outcome'] == 'failed'


def test_waiting_conflict_does_not_claim_another_clients_mutation(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace
    import bridge
    captured = []
    monkeypatch.setattr(bridge, 'register_api', lambda app, context, gate: captured.append(context))
    cfg = json.loads(open(CONFIG).read()); cfg['ma2']['export_dir'] = str(tmp_path)
    create_app(cfg, True, str(tmp_path / 'c.json'), FULL)
    c = captured[0]
    class Socket:
        client = SimpleNamespace(host='test')
        def __init__(self): self.messages = []
        async def send_json(self, message): self.messages.append(message)
    async def run():
        ws = Socket(); c.clients.add(ws)
        revision = c.revision_token()
        c.sessions[ws] = {'selection': [], 'base': None, 'requests': set(), 'legacy_revision': revision}
        await c.action_lock.acquire()
        task = asyncio.create_task(c.perform_action(ws, json.dumps({'a':'group_save', 'label':'loser', 'ids':[12],
                                                                  'request_id':'loser', 'config_revision':revision})))
        for _ in range(100):
            await asyncio.sleep(0)
            if c.action_lock._waiters:
                break
        assert c.action_lock._waiters  # request has captured its initial snapshot and now waits
        cfg['groups'].append({'id':'winner', 'label':'winner', 'fixtures':[12]})
        c.action_lock.release()
        await task
        reply = next(m for m in ws.messages if 'ok' in m)
        assert reply['conflict'] and reply['outcome'] == 'failed'
        assert c.sessions[ws]['legacy_revision'] == revision
    asyncio.run(run())


@pytest.mark.parametrize('invalid_action', [[1], {'nested': 'action'}, None, 7])
def test_invalid_action_type_keeps_correlated_validation_error(bridge_cfg, invalid_action):
    with bridge_cfg() as (ws, _, _):
        r = ask(ws, {'a': invalid_action, 'request_id': 'invalid-action'})
        assert not r['ok'] and r['outcome'] == 'failed'
        assert r['request_id'] == 'invalid-action'
        assert r['a'] is None
        assert r['err'] == 'нужен объект с полем a'
