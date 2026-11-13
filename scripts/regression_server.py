"""Test-only hooks in an isolated copy. Never packaged as a production endpoint."""
import json
from pathlib import Path
import sys


def main():
    from ma2panel import bridge
    from concert_demo import seed_mock, network_guard
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    root = Path(__file__).resolve().parent
    marker = root / '.quality-test'
    if '--mock' not in sys.argv or not marker.is_file():
        raise SystemExit('Only an isolated quality-test copy with --mock is permitted')
    config_path = Path(sys.argv[sys.argv.index('--config') + 1]).resolve()
    settings_path = Path(sys.argv[sys.argv.index('--settings') + 1]).resolve()
    if config_path.parent != root or settings_path.parent != root:
        raise SystemExit('Config/settings must belong to this isolated copy')
    identity = json.loads(marker.read_text())
    allowed = set(); sys.addaudithook(network_guard(allowed))
    original_start, original_create = bridge.start_mock, bridge.create_app
    async def start(*args, **kwargs):
        mock = await original_start(*args, **kwargs); allowed.add(mock.port)
        # Console fixture profiles do not disappear when the panel saves its own plan.
        cfg = json.loads((root / '.quality-console.json').read_text(encoding='utf-8'))
        if identity['profile'] in ('synthetic', 'field-start'):
            from ma2panel.mock_console import GROUPS
            seed_mock(mock, cfg, root)
            mock.groups = {n: g[0] for n, g in GROUPS.items()}
            mock.configure_simulation(cfg)
            mock.strict_console = True
            if identity['profile'] == 'field-start':
                mock.running.clear()
                mock.sim_active.clear()
                from xml.etree import ElementTree as ET
                # Like the real V2 export: Patch has channels, no attribute names.
                patch = ET.fromstring(mock.export_text)
                for fixture in patch:
                    for node in list(fixture):
                        if node.tag.rsplit('}', 1)[-1] == 'Attribute':
                            fixture.remove(node)
                mock.export_text = ET.tostring(patch, encoding='unicode')
        if identity['profile'] == 'field-v2':
            mock.show_name = 'big room v2'
            from ma2panel.mock import REAL_EXPORT
            mock.export_text = REAL_EXPORT.read_text(encoding='utf-8')
        return mock
    bridge.start_mock = start
    def create(*args, **kwargs):
        app = original_create(*args, **kwargs)
        async def control(request):
            if not bridge.is_loopback(request) or request.headers.get('x-ma2-test') != identity['token']:
                return JSONResponse({'ok': False}, status_code=403)
            mock = app.state.mock
            from ma2panel.mock_console import is_read_only
            if request.method == 'POST':
                data = await request.json()
                mode = data.get('mode')
                if mode == 'disconnect': mock.paused = True; mock.drop()
                elif mode == 'connect': mock.paused = False
                elif mode == 'external':
                    # A second actor on the simulated console, outside the panel's actions.
                    mock._reply('Fixture 1'); mock._reply('At 17')
                elif mode == 'clear-programmer':
                    mock._reply('ClearAll')
                elif mode in ('restart', 'reset'):
                    (root / '.quality-restart').write_text('reset' if mode == 'reset' else 'requested')
                    app.state.exit_code = 3; app.state.server.should_exit = True
                else: return JSONResponse({'ok': False}, status_code=400)
            return JSONResponse({'ok': True, 'instance': app.state.instance, 'received': mock.received, 'read_only': [c for c in mock.received if is_read_only(c)],
                                 'safety_mode': json.loads(settings_path.read_text(encoding='utf-8')).get('safety', {}).get('mode', 'test'),
                                 'output': mock.simulation_output(), 'selection': getattr(mock, 'sim_selection', []), 'profile': identity['profile'],
                                 'config': json.loads(config_path.read_text(encoding='utf-8'))})
        app.router.routes.insert(0, Route('/__quality/control', control, methods=['GET', 'POST']))
        return app
    bridge.create_app = create
    bridge.main()


if __name__ == '__main__': main()
