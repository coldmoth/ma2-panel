from test_bridge import ask, bridge_cfg, until  # noqa: F401


def offer(ws, request='r1'):
    ask(ws, {'a':'select_fixtures','ids':[12]})
    ws.send_json({'a':'scene_slot_find','request':request})
    terminal = None
    acknowledged = False
    while not (acknowledged and terminal):
        msg = ws.receive_json()
        if msg.get('a') == 'scene_slot_find' and 'ok' in msg:
            assert msg['ok'], msg
            acknowledged = True
        if msg.get('scene_slot',{}).get('state') in ('ready','error'):
            terminal = msg['scene_slot']
    return terminal



def test_find_is_read_only_then_confirmed_write(bridge_cfg):
    with bridge_cfg() as (ws,mock,path):
        candidate = offer(ws)
        assert candidate['state'] == 'ready'
        assert candidate['exec'] == '1.1'
        assert not any(c.startswith(('Store','Delete','Label')) for c in mock.received)
        assert ask(ws, {'a':'scene_create','label':'Новая','page':1,'exec':'1.1','confirm':'1.1','token':candidate['token']})['ok']
        assert 'Store Executor 1.1 Cue 1 /Source=Output /Use=Allforselected' in mock.received
        assert not ask(ws, {'a':'scene_create','label':'Повтор','page':1,'exec':'1.1','confirm':'1.1','token':candidate['token']})['ok']


def test_place_occupied_after_offer_never_overwrites(bridge_cfg):
    with bridge_cfg() as (ws,mock,path):
        candidate = offer(ws)
        mock.rows['1.1']='Другой оператор'
        before=len(mock.received)
        reply=ask(ws, {'a':'scene_create','label':'Новая','page':1,'exec':'1.1','confirm':'1.1','token':candidate['token']})
        assert not reply['ok']
        assert not any(c.startswith(('Store','Delete','Label')) for c in mock.received[before:])


def test_cancel_invalidates_ready_offer(bridge_cfg):
    with bridge_cfg() as (ws,mock,path):
        candidate=offer(ws)
        assert ask(ws,{'a':'scene_slot_cancel','request':'r1'})['ok']
        assert not ask(ws,{'a':'scene_create','label':'Нет','page':1,'exec':'1.1','confirm':'1.1','token':candidate['token']})['ok']


def test_readonly_mode_cannot_search(bridge_cfg):
    with bridge_cfg(settings={'safety':{'mode':'test'}}) as (ws,mock,path):
        before=len(mock.received)
        assert not ask(ws,{'a':'scene_slot_find','request':'r'})['ok']
        assert not any(c.startswith('List Executor') for c in mock.received[before:])


def test_offer_cannot_be_used_by_another_socket(tmp_path):
    from test_safety import tabs
    with tabs(tmp_path, {'safety':{'mode':'full'}}) as ((a,b),mock,client,path):
        candidate=offer(a)
        create={'a':'scene_create','label':'Новая','page':1,'exec':'1.1','confirm':'1.1','token':candidate['token']}
        assert not ask(b,create)['ok']
        assert ask(a,create)['ok']


def test_plan_binding_change_invalidates_offer(bridge_cfg):
    with bridge_cfg(lambda cfg: cfg.pop("show", None)) as (ws,mock,path):
        candidate=offer(ws)
        assert ask(ws,{'a':'show_bind','name':'Mock show'})['ok']
        before=len(mock.received)
        assert not ask(ws,{'a':'scene_create','label':'Нет','page':1,'exec':'1.1','confirm':'1.1','token':candidate['token']})['ok']
        assert not any(c.startswith(('Store','Delete','Label')) for c in mock.received[before:])


def test_disabled_store_feature_cannot_search(bridge_cfg):
    with bridge_cfg(settings={'safety':{'mode':'full'},'features':{'store':False}}) as (ws,mock,path):
        before=len(mock.received)
        assert not ask(ws,{'a':'scene_slot_find','request':'r'})['ok']
        assert not any(c.startswith('List Executor') for c in mock.received[before:])


def test_unrecognised_slot_reply_stops_search(bridge_cfg,monkeypatch):
    from ma2panel.mock import MockMA2
    original=MockMA2._reply
    def reply(self,text):
        if text=='List Executor 1.1':
            return 'Ответ без данных о месте\r\n[Channel]>'
        return original(self,text)
    monkeypatch.setattr(MockMA2,'_reply',reply)
    with bridge_cfg() as (ws,mock,path):
        result=offer(ws)
        assert result['state']=='error'
        assert [c for c in mock.received if c.startswith('List Executor')] == ['List Executor 1.1']
        assert not any(c.startswith(('Store','Delete','Label')) for c in mock.received)


def test_expired_offer_cannot_write(bridge_cfg,monkeypatch):
    from ma2panel import bridge
    from types import SimpleNamespace
    clock=bridge.time
    with bridge_cfg() as (ws,mock,path):
        candidate=offer(ws)
        monkeypatch.setattr(bridge,'time',SimpleNamespace(**{**{k:getattr(clock,k) for k in dir(clock) if not k.startswith("__")}, "monotonic":lambda:clock.monotonic()+61}))
        before=len(mock.received)
        assert not ask(ws,{'a':'scene_create','label':'Нет','page':1,'exec':'1.1','confirm':'1.1','token':candidate['token']})['ok']
        assert not any(c.startswith(('Store','Delete','Label')) for c in mock.received[before:])


def test_search_cancellation_does_not_wait_for_telnet(bridge_cfg):
    import time
    with bridge_cfg() as (ws,mock,path):
        mock.late=.12
        ws.send_json({'a':'scene_slot_find','request':'cancel-in-flight'})
        until(ws,lambda m:m.get('scene_slot',{}).get('state')=='searching')
        deadline=time.monotonic()+1
        while 'List Executor 1.1' not in mock.received and time.monotonic()<deadline:
            time.sleep(.005)
        assert 'List Executor 1.1' in mock.received
        assert ask(ws,{'a':'scene_slot_cancel','request':'cancel-in-flight'})['ok']
        time.sleep(.18)
        assert [c for c in mock.received if c.startswith('List Executor')]==['List Executor 1.1']
        assert not any(c.startswith(('Store','Delete','Label')) for c in mock.received)


def test_slot_timeout_never_continues_or_writes(bridge_cfg):
    with bridge_cfg(settings={'safety':{'mode':'full'},'ma2':{'timeout':.05}}) as (ws,mock,path):
        mock.mute=True
        result=offer(ws)
        assert result['state']=='error'
        assert [c for c in mock.received if c.startswith('List Executor')]==['List Executor 1.1']
        assert not any(c.startswith(('Store','Delete','Label')) for c in mock.received)
