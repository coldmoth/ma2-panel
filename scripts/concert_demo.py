"""Demo-only adapter around bridge.main and MockMA2; never loaded by the real launcher."""
import gzip
import json
from pathlib import Path
import sys
import time
from xml.etree import ElementTree as ET


FLAGS = ('allow_master', 'allow_page_change', 'allow_fixture_read', 'allow_highlight',
         'allow_show_load', 'allow_show_save', 'allow_group_store', 'allow_patch', 'allow_rdm')
TYPES = {1: ('1 Demo Head', 12), 2: ('2 Demo RGB', 8), 3: ('3 Demo Dimmer', 1)}


def demo_data(config, settings, app, ports):
    names = ['Вход зрителей', 'Общий тёплый', 'Ведущий', 'Солист', 'Хор', 'Оркестр',
             'Танец — синий', 'Танец — красный', 'Пауза', 'Поклоны', 'Уборка зала', 'Рабочий свет']
    fixtures = []
    address = 1
    for i in range(1, 61):
        typ = 1 if i <= 40 else 2 if i <= 56 else 3
        name, footprint = TYPES[typ]
        fixtures.append(dict(id=i, label=f'Прибор {i}' + (' — дальний край оркестровой площадки с длинным именем' if i == 55 else ''),
                             type=name, moves=typ == 1, color='none' if typ == 3 else 'rgb',
                             address=f'{(address-1)//512+1}.{(address-1)%512+1:03}', channels=footprint, footprint=footprint,
                             params=['Dimmer'] + (['ColorRGB1', 'ColorRGB2', 'ColorRGB3'] if typ != 3 else []) +
                             (['Pan', 'Tilt', 'Zoom', 'Focus', 'Strobe'] if typ == 1 else []),
                             x=((i-1) % 10+1)/11, y=((i-1)//10+1)/7))
        address += footprint
    # The test panel and its exported console Patch share the same fixture identity.
    for fixture in fixtures:
        fixture['name'] = fixture['label']
    maps = {name: {'dim': 1, 'has': []} if n == 3 else
            {'dim': 1, 'r': 2, 'g': 3, 'b': 4, 'has': ['zoom', 'focus', 'strobe'] if n == 1 else [],
             **({'strobe': {'attr': 'Strobe', 'open': 0, 'from': 10, 'to': 100}} if n == 1 else {})}
            for n, (name, _) in TYPES.items()}
    config.update(show='Mock show', scene_order_version=1, hall={'w': 18, 'd': 14, 'stage': 'top', 'stageDepth': 4},
                  fixtures=fixtures, dmx_map=maps,
                  groups=[{'id': 'front', 'label': 'Фронт', 'fixtures': [1, 2, 3]},
                          {'id': 'back', 'label': 'Контровой', 'fixtures': [55, 56, 57]}],
                  ma2groups=[{'n': n, 'name': name, 'ids': [n, n+1]} for n, name in [(1, 'Фронт MA2'), (2, 'Контровой MA2')]],
                  ma2presets={'colors': [{'n': n, 'name': name} for n, name in [(1, 'Красный'), (2, 'Синий')]],
                              'positions': [{'n': 1, 'name': 'Центр сцены'}]},
                  presets=[{'id': 'demo-center', 'label': 'Центр', 'pos': {str(i): {'pan': 50, 'tilt': 50} for i in range(1, 41)}}],
                  scenes=[{'id': f's{i}', 'exec': f'1.{100+i}', 'label': names[(i-1) % 12]+(f' · {1+(i-1)//12}' if i>12 else '')} for i in range(1, 37)])
    settings.update(bind='127.0.0.1', port=ports[0], simple_port=ports[1], poll_seconds=1, dmx_seconds=0)
    settings['safety'].update(mode='full', **dict.fromkeys(FLAGS, True))
    settings['features'] = dict.fromkeys(('dim', 'color', 'move', 'zoom', 'focus', 'strobe', 'scenes', 'store'), True)
    settings['ma2'].update(host='127.0.0.1', export_dir=str(app/'exports'), shows_dir=str(app/'demo-shows'))
    for folder in ('exports', 'demo-shows', 'tests'):
        (app/folder).mkdir(exist_ok=True)
    # These are deliberately synthetic gzip files, never an actual grandMA2 show.
    for name in ('Mock show', 'Demo'):
        (app/'demo-shows'/f'{name}.show.gz').write_bytes(gzip.compress(f'DEMO ONLY: {name}'.encode()))
    (app/'tests/list_fixturetype_3.9.60.txt').write_text(
        f'{"No. LongName":<60}{"DMXFootprint":<16}Instances\n'+''.join(
            f'{f"FixtureType {n} {name}":<60}{footprint:<16}1\n' for n, (name, footprint) in TYPES.items()))
    return config, settings


def seed_mock(mock, config, app):
    mock.show_name = config['show']
    mock.rows = {s['exec']: s['label'] for s in config['scenes']}
    mock.groups = {g['n']: g['name'] for g in config['ma2groups']}
    mock.presets = {4: {p['n']: p['name'] for p in config['ma2presets']['colors']},
                    2: {p['n']: p['name'] for p in config['ma2presets']['positions']}}
    mock.running = {config['scenes'][2]['exec']} if len(config['scenes']) > 2 else set()
    root = ET.Element('MA', xmlns='urn:ma')
    for fixture in config['fixtures']:
        node = ET.SubElement(root, 'Fixture', fixture_id=str(fixture['id']), name=fixture['label'])
        ET.SubElement(node, 'FixtureType', name=fixture['type'])
        # Absolute addresses keep the existing mock's patch-update mechanism usable.
        u, a = map(int, fixture['address'].split('.'))
        ET.SubElement(node, 'Address').text = str((u-1)*512+a)
        for channel in range(fixture['footprint']):
            ET.SubElement(node, 'Channel', index=str(channel))
        for attr in fixture['params']:
            ET.SubElement(node, 'Attribute', name=attr)
    mock.export_text = ET.tostring(root, encoding='unicode')
    for no in TYPES:
        attrs = ['DIM'] if no == 3 else ['DIM', 'COLORRGB1', 'COLORRGB2', 'COLORRGB3'] + (['PAN', 'TILT', 'ZOOM', 'FOCUS', 'STROBE'] if no == 1 else [])
        root = ET.Element('FixtureType'); module = ET.SubElement(root, 'Module')
        for channel, attr in enumerate(attrs, 1):
            node = ET.SubElement(module, 'ChannelType', attribute=attr, coarse=str(channel))
            if attr == 'STROBE':
                ET.SubElement(node, 'ChannelSet', name='Open', **{'from': '0', 'to': '0'})
                ET.SubElement(node, 'ChannelSet', name='Strobe', **{'from': '26', 'to': '255'})
        mock.fixture_types[no] = ET.tostring(root, encoding='unicode')
    mock.rdm_devices = [{'uid': f'43500000{i:04X}', 'address': 1+(i-1)*12, 'footprint': 12, 'label': f'Demo RDM {i}'} for i in range(1, 5)]
    def save_show():
        (app/'demo-shows'/f'{mock.show_name}.show.gz').write_bytes(gzip.compress(f'DEMO ONLY {time.time_ns()}'.encode()))
    mock.on_save = save_show


def network_guard(allowed_ports):
    """Audit hook: even edited demo settings may only dial this process's mock server."""
    def check(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo'):
            host, port = (args[1][:2] if event == 'socket.connect' else args[:2])
            if host != '127.0.0.1' or port not in allowed_ports:
                raise OSError('Изолированное демо: соединение разрешено только с собственным MockMA2')
        elif event in ('socket.sendto', 'subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.exec'):
            raise OSError('Изолированное демо: внешняя сеть и запуск внешних программ отключены')
    return check


def main():
    if '--mock' not in sys.argv or '--probe' in sys.argv or '--check' in sys.argv:
        raise SystemExit('concert_demo запускается только из concert_mock.py с --mock')
    from ma2panel import bridge
    from fastapi.responses import JSONResponse
    app_dir = Path(__file__).resolve().parent
    config_path = Path(sys.argv[sys.argv.index('--config')+1]).resolve()
    settings_path = Path(sys.argv[sys.argv.index('--settings')+1]).resolve()
    if config_path.parent != app_dir or settings_path.parent != app_dir or not (app_dir/'.concert-demo').is_file():
        raise SystemExit('Требуется отдельный каталог демо, без пользовательских config/settings')
    marker = json.loads((app_dir/'.concert-demo').read_text())
    settings = json.loads(settings_path.read_text())
    # Network-facing listeners stay local across a settings save/restart.
    settings.update(bind='127.0.0.1', port=marker['ports'][0], simple_port=marker['ports'][1])
    settings_path.write_text(json.dumps(settings, ensure_ascii=False))
    allowed_ports = set()
    sys.addaudithook(network_guard(allowed_ports))
    original_start = bridge.start_mock
    async def start(port, user, export_dir):
        mock = await original_start(port, user, export_dir)
        allowed_ports.add(mock.port)
        seed_mock(mock, json.loads(config_path.read_text()), app_dir)
        return mock
    bridge.start_mock = start
    original_create = bridge.create_app
    def create(*args, **kwargs):
        if not (kwargs.get('mock') if 'mock' in kwargs else args[1]):
            raise RuntimeError('Демо требует MockMA2')
        app = original_create(*args, **kwargs)
        async def get_demo(request):
            mock = app.state.mock
            return JSONResponse({'demo': True, 'id': marker['id'], 'paused': mock.paused, 'next_fault': mock.fault_once,
                                 'fixtures': 60, 'executors': len(mock.rows), 'mock_port': mock.port,
                                 'network': 'Только собственный MockMA2 на loopback; оборудование недоступно'})
        async def set_demo(request):
            origin = request.headers.get('origin')
            if not bridge.is_loopback(request) or request.headers.get('x-concert-demo') != '1' or (origin and origin != str(request.base_url).rstrip('/')):
                return JSONResponse({'ok': False}, status_code=403)
            try:
                mode = (await request.json())['state']
                if mode not in ('connected', 'disconnected', 'delay', 'error', 'unknown'):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                return JSONResponse({'ok': False, 'err': 'Неизвестное состояние демо'}, status_code=400)
            mock = app.state.mock
            mock.paused = mode == 'disconnected'
            mock.fault_once = mode if mode in ('delay', 'error', 'unknown') else None
            if mock.paused:
                mock.drop()
            return JSONResponse({'ok': True, 'state': mode})
        async def restart_demo(request):
            origin = request.headers.get('origin')
            if not bridge.is_loopback(request) or request.headers.get('x-stop') != '1' or (origin and origin != str(request.base_url).rstrip('/')):
                return JSONResponse({'ok': False}, status_code=403)
            if app.state.active_actions:
                return JSONResponse({'ok': False, 'err': 'Дождитесь окончания действия в демо'}, status_code=409)
            # Only the isolated fake process: the real restart/update gate is deliberately untouched.
            # Its idle WS worker check otherwise prevents a design reviewer from applying demo settings.
            app.state.exit_code = 3
            app.state.server.should_exit = True
            return JSONResponse({'ok': True})
        # Insert before the existing static mount. No real bridge route is replaced.
        from starlette.routing import Route
        app.router.routes.insert(0, Route('/api/restart', restart_demo, methods=['POST']))
        app.router.routes.insert(0, Route('/api/demo', get_demo, methods=['GET']))
        app.router.routes.insert(0, Route('/api/demo', set_demo, methods=['POST']))
        return app
    bridge.create_app = create
    bridge.main()


if __name__ == '__main__':
    main()
