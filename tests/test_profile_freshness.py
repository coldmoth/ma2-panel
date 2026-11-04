"""DATA-005: failed refresh and offline import invalidate old profile evidence."""
import asyncio
import pytest
from fixtures import merge_fixtures, parse_fixture_type
from test_status_evidence import context  # noqa: F401


@pytest.mark.parametrize('kind', ['1 Old', '2 New'])
def test_import_drops_old_footprint_even_with_same_type(kind):
    old = [{'id': 10, 'type': '1 Old', 'footprint': 17, 'channels': 14, 'label': 'Keep'}]
    f = merge_fixtures(old, [{'id': 10, 'name': 'F', 'type': kind, 'address': '1.100', 'channels': 2}])[0]
    assert 'footprint' not in f
    assert f['label'] == 'Keep'


def test_failed_forced_refresh_retains_but_distrusts_maps(context):
    c = context
    c.cfg['fixtures'] = [{'id': 10, 'type': '1 Old', 'address': '1.100', 'footprint': 17}]
    c.cfg['dmx_map'] = {'1 Old': {'dim': 17, 'has': ['zoom']}}
    async def go():
        async def send(*args, **kw): return False, 'Error'
        c.link.send = send
        c.ma2['export_wait'] = 0
        await c.read_types(force=True)
        assert 'footprint' not in c.cfg['fixtures'][0]
        assert c.cfg['dmx_map']['1 Old']['dim'] == 17  # preserve operator data
        assert c.cfg['dmx_map']['1 Old']['stale'] is True
        assert c.config_msg()['config']['dmx_map'] == {}
    asyncio.run(go())


def test_complex_module_map_is_not_first_cell_guess():
    spec = parse_fixture_type('<FixtureType><Modules><Module><ChannelType attribute="DIM" coarse="1"/></Module><Module><ChannelType attribute="COLORRGB1" coarse="1"/></Module></Modules></FixtureType>')
    assert spec.get('unsupported') is True
    assert 'dim' not in spec


@pytest.mark.parametrize('event', ['disconnect', 'show', 'offline'])
def test_context_and_offline_import_invalidate_maps(context, event):
    c = context
    c.cfg['fixtures'] = [{'id': 10, 'type': '1 Old', 'address': '1.100', 'footprint': 17}]
    c.cfg['dmx_map'] = {'1 Old': {'dim': 17, 'has': ['zoom']}}
    c.state['dmx'] = {116: 255}
    c.state['live'] = {10: {'dim': 100}}
    async def go():
        if event == 'disconnect':
            c.on_state('down')
        elif event == 'show':
            c.update_show({'name': 'Other'})
        else:
            c.import_xml('<MA><Fixture id="10" type="1 Old"><Patch><Address>100</Address></Patch></Fixture></MA>', 'xml')
        assert 'footprint' not in c.cfg['fixtures'][0]
        assert c.state['live'] == {} and c.state['dmx'] == {}
        assert c.config_msg()['config']['dmx_map'] == {}
        assert c.cfg['dmx_map_saved']['1 Old'][0]['dim'] == 17
    asyncio.run(go())


def test_successful_force_replaces_sizes_with_current_list(context):
    c = context
    c.cfg['fixtures'] = [{'id': 10, 'type': '3 Current', 'address': '1.100', 'footprint': 17}]
    async def go():
        async def send(line, **kw):
            if line == 'List FixtureType':
                from pathlib import Path
                return True, Path('tests/list_fixturetype_3.9.60.txt').read_text()
            return False, 'Error'
        c.link.send = send
        await c.read_types(force=True)
        assert c.cfg['fixtures'][0]['footprint'] == 9
    asyncio.run(go())


def test_multi_instance_list_never_authorizes_single_range():
    from pathlib import Path
    from commands import parse_type_footprints
    text = Path('tests/list_fixturetype_3.9.60.txt').read_text()
    text = text.replace('17            1', '17            2')
    sizes = parse_type_footprints(text)
    assert '4' not in sizes and '5' not in sizes
    assert sizes['3'] == 9


def test_repeated_refresh_preserves_original_operator_map(context):
    c = context
    manual = {'dim': 17}
    automatic = {'dim': 2, 'has': []}
    c.cfg['dmx_map'] = {'1 Old': manual}
    c.invalidate_profiles()
    c.cfg['dmx_map'] = {'1 Old': automatic}
    c.invalidate_profiles()
    assert c.cfg['dmx_map_saved']['1 Old'] == [manual, automatic]
