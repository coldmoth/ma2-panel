"""Isolated real socket mock → Lua/ListVar → backend → WebSocket, no browser."""
import json
import time
from pathlib import Path
from fastapi.testclient import TestClient
from ma2panel import bridge
from test_bridge import ask, until
from test_dmx_recovery_regression import profile, RGB


def test_four_universes_external_changes_partial_error_and_reconnect(tmp_path, monkeypatch):
    cfg = json.loads(Path('tests/config.test.json').read_text())
    fixtures = [{'id': i, 'type': kind, 'address': f'{i}.001', 'label': str(i), 'name': str(i)} for i, kind in
                [(1, '3 RGB'), (2, '2 Dimmer'), (3, '4 Shutter'), (4, '5 Unknown')]]
    cfg.update(fixtures=fixtures, groups=[], scenes=[], dmx_map={})
    cfg['ma2']['export_dir'] = str(tmp_path / 'importexport')
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(cfg))
    original = bridge.start_mock
    async def start(*args, **kw):
        mock = await original(*args, **kw)
        mock.fixture_types = {3: profile(RGB), 2: profile('<ChannelType attribute="DIM" coarse="1"/>'),
            4: profile('<ChannelType attribute="DIM" coarse="1"/><ChannelType attribute="SHUTTER1" coarse="2">'
                       '<ChannelSet name="Closed" from_dmx="0" to_dmx="31"/>'
                       '<ChannelSet name="Open" from_dmx="128" to_dmx="255"/></ChannelType>'),
            5: profile('<ChannelType attribute="COLORCMY1" coarse="1"/>')}
        mock.export_text = '<MA>' + ''.join(f'<Fixture fixture_id="{f["id"]}" name="{f["label"]}" type="{f["type"]}"><Patch>{f["address"]}</Patch></Fixture>' for f in fixtures) + '</MA>'
        mock.dmx = {1: 51, 2: 255, 3: 0, 4: 0, 513: 51, 1025: 255, 1026: 0, 1537: 255}
        return mock
    monkeypatch.setattr(bridge, 'start_mock', start)
    monkeypatch.delenv('MA2_MOCK_REAL', raising=False)
    app = bridge.create_app(cfg, True, str(config), settings={
        'safety': {'mode': 'full', 'allow_fixture_read': True}, 'dmx_seconds': .01,
        'poll_seconds': 0, 'simple_port': None}, settings_path=tmp_path / 'settings.json')
    with TestClient(app) as client, client.websocket_connect('/ws') as ws:
        mock = app.state.mock
        latest = {}
        def output(predicate):
            def matches(msg):
                if 'live' in msg:
                    latest.clear(); latest.update(msg['live'])
                return predicate(latest)
            return until(ws, matches)
        until(ws, lambda m: m.get('status', {}).get('ma2') == 'logged_in' and not m['status'].get('recovering'))
        output(lambda live: all(str(i) in live for i in (1, 2, 3)))
        assert latest['1'] == {'dim': 20.0, 'rgb': [100.0, 0.0, 0.0]}
        assert latest['2']['dim'] == 20 and latest['3']['dim'] == 0 and '4' not in latest
        mock.dmx.update({1: 204, 2: 0, 4: 255, 1026: 255})
        output(lambda live: live.get('1', {}).get('dim') == 80 and live.get('3', {}).get('dim') == 100)
        assert latest['1']['rgb'] == [0, 0, 100]
        mock.dmx[513] = -1
        output(lambda live: '2' not in live and live.get('1', {}).get('dim') == 80)
        mock.paused = True
        for writer in list(mock._writers):
            writer._loop.call_soon_threadsafe(writer.close)
        until(ws, lambda m: m.get('status', {}).get('ma2') == 'down')
        assert not ask(ws, {'a': 'dim', 'v': 99})['ok']
        before = len(mock.received)
        mock.dmx[513] = 128
        mock.paused = False
        until(ws, lambda m: m.get('status', {}).get('ma2') == 'logged_in' and not m['status'].get('recovering'))
        output(lambda live: live.get('2', {}).get('dim') == 50.2)
        assert not any(line.startswith('At 99') for line in mock.received[before:])
        diag = client.get('/api/diag').json()['export']['dmx_read']
        assert diag['connected'] and diag['last_success']
        assert all(not line.startswith(('At ', 'Assign ', 'Goto ', 'Store ', 'Off ')) for line in mock.received)
