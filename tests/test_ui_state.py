"""UI state must survive DOM rebuilds without pretending to be desk feedback."""
from test_bridge import ask, bridge_cfg, until  # noqa: F401


def test_master_is_shared_sent_value(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        ws.send_json({"a": "master", "v": 99})
        msg = until(ws, lambda m: "shown" in m)
        assert msg.get("master") == 99
        assert "Master 2.1 At 99" in mock.received
        ws.send_json({"a": "link_drop"})
        assert until(ws, lambda m: "master" in m)["master"] is None


def test_saved_data_does_not_mean_fresh_read(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        ws.send_json({"a": "show_identify"})
        msg = until(ws, lambda m: "status" in m)
        assert msg["status"].get("read_freshness") == {"fixtures": False, "ma2": False, "scenes": False}


def test_master_error_keeps_last_sent(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        ws.send_json({'a': 'master', 'v': 42})
        assert until(ws, lambda m: 'master' in m)['master'] == 42
        assert not ask(ws, {'a': 'master', 'v': 101})['ok']
        assert ask(ws, {'a': 'select_fixtures', 'ids': [12]})['ok']
        ws.send_json({'a': 'dim', 'v': 10})
        assert until(ws, lambda m: 'master' in m)['master'] == 42


def test_nudge_explicit_step_reaches_console(bridge_cfg):
    with bridge_cfg() as (ws, mock, path):
        assert ask(ws, {'a': 'select_fixtures', 'ids': [12]})['ok']
        before = len(mock.received)
        assert ask(ws, {'a': 'nudge', 'attr': 'pan', 'dir': 1, 'step': 1})['ok']
        assert 'Attribute "Pan" At + 1' in mock.received[before:]
        assert 'Attribute "Pan" At + 2' not in mock.received[before:]


def test_rewrite_preserves_scene_id_and_position(bridge_cfg):
    def edit(cfg):
        cfg['scene_order_version'] = 1
        cfg['scenes'] = [{'id':'first','exec':'1.110','label':'First'}, {'id':'pianist','exec':'1.101','label':'Piano'}, {'id':'last','exec':'1.111','label':'Last'}]
    with bridge_cfg(edit=edit) as (ws, mock, path):
        assert ask(ws, {'a':'select_fixtures','ids':[12]})['ok']
        assert ask(ws, {'a':'scene_create','label':'Новое','page':1,'exec':'1.101','confirm':'1.101','replace':True})['ok']
        import json
        scenes = json.loads(path.read_text())['scenes']
        assert [s['id'] for s in scenes] == ['first','pianist','last']
        assert scenes[1]['label'] == 'Новое'


def test_failed_rewrite_remains_visible_as_unconfirmed(bridge_cfg, monkeypatch):
    from ma2panel.mock import MockMA2
    original=MockMA2._reply
    def reply(self,text):
        if text == 'Copy Cue 1 Executor 1.1 At Cue 1 Executor 1.101 /CueOnly /Overwrite':
            return 'Error #72: COMMAND NOT EXECUTED\r\n[Channel]>'
        return original(self,text)
    monkeypatch.setattr(MockMA2,'_reply',reply)
    with bridge_cfg() as (ws,mock,path):
        assert ask(ws, {'a':'select_fixtures','ids':[12]})['ok']
        result=ask(ws,{'a':'scene_create','label':'Новое','page':1,'exec':'1.101','confirm':'1.101','replace':True})
        assert not result['ok']
        import json
        scene=next(sc for sc in json.loads(path.read_text())['scenes'] if sc['id']=='pianist')
        assert scene.get('write_error')
        assert 'повторно не отправлено' in result['err']
        before_go=len(mock.received)
        assert not ask(ws,{'a':'scene_go','id':'pianist'})['ok']
        assert not any(c.startswith(('Go Executor','Goto Cue')) for c in mock.received[before_go:])
        assert len([c for c in mock.received if c.startswith('Store Executor')]) == 1


def test_desk_show_change_invalidates_shared_master(tmp_path):
    from test_safety import tabs
    with tabs(tmp_path,{'safety':{'mode':'full'}}) as ((a,b),mock,client,path):
        a.send_json({'a':'master','v':42})
        assert until(b,lambda m:'master' in m)['master']==42
        mock.show_name='Demo'
        assert ask(a,{'a':'show_identify'})['ok']
        assert not ask(a,{'a':'select_fixtures','ids':[12]})['ok']
        a.send_json({'a':'dim','v':10})
        assert until(b,lambda m:'master' in m)['master'] is None


def test_sent_value_snapshots_have_monotonic_revisions(bridge_cfg):
    with bridge_cfg() as (ws,mock,path):
        ws.send_json({'a':'master','v':40})
        first=until(ws,lambda m:'master' in m)
        assert isinstance(first.get('values_revision'),int)
        ws.send_json({'a':'master','v':70})
        second=until(ws,lambda m:'master' in m)
        assert second['values_revision'] > first['values_revision']
        assert second['master']==70
