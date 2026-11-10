"""Stage 2: output evidence and transactional fixture/catalogue refresh."""
import asyncio
import copy
import pytest
from ma2panel.commands import ActionError, live_from_dmx, rel_lines, can_move
from ma2panel.fixtures import parse_export, parse_fixture_type
from test_status_evidence import context  # noqa: F401


def test_shutter_never_claims_open_without_byte():
    fixtures = [{'id': 1, 'type': 'D', 'address': '1.1'}]
    spec = {'D': {'dim': 1, 'shutter': 2, 'shutter_open': [[128, 255]], 'shutter_closed': [[0, 31]]}}
    assert 1 not in live_from_dmx(fixtures, {1: 255}, spec)
    assert live_from_dmx(fixtures, {1: 255, 2: 0}, spec)[1]['dim'] == 0
    assert live_from_dmx(fixtures, {1: 255, 2: 255}, spec)[1]['dim'] == 100
    assert 1 not in live_from_dmx(fixtures, {1: 255, 2: 80}, spec)


def test_unclassified_shutter_is_unknown():
    spec = parse_fixture_type('<MA><Module><ChannelType attribute="DIM" coarse="1"/>'
                              '<ChannelType attribute="SHUTTER1" coarse="2"/></Module></MA>')
    assert spec.get('shutter') == 2
    assert live_from_dmx([{'id': 1, 'type': 'D', 'address': '1.1'}], {1: 255, 2: 255}, {'D': spec}) == {}


@pytest.mark.parametrize('bad', ['<Fixture fixture_id="0" name="bad"/>', '<Fixture fixture_id="abc" name="bad"/>'])
def test_partial_fixture_export_is_not_a_complete_patch(bad):
    with pytest.raises(ValueError):
        parse_export('<MA><Fixture fixture_id="12"/>' + bad + '</MA>')


def test_import_renumber_updates_all_group_links(context):
    c = context
    c.cfg['fixtures'] = [{'id': 12, 'name': 'Head', 'type': 'H', 'label': 'Left', 'x': .2,
                          'flip_pan': True, 'address': '1.1', 'rdm': {'uid': 'abc'}}]
    c.cfg['groups'] = [{'id': 'local', 'fixtures': [12]}, {'id': 'desk', 'n': 4, 'fixtures': [12]}]
    c.cfg['ma2groups'] = [{'n': 4, 'name': 'Desk', 'label': 'Mine', 'ids': [12]}]
    async def go():
        return c.import_xml('<MA><Fixture fixture_id="31" name="Head" type="H"><Patch>513</Patch></Fixture></MA>', 'ma2')
    result = asyncio.run(go())
    assert result['ok']
    assert all(g['fixtures'] == [31] for g in c.cfg['groups'])
    assert c.cfg['ma2groups'][0]['ids'] == [31]
    assert c.cfg['ma2groups'][0]['label'] == 'Mine'
    f = c.cfg['fixtures'][0]
    assert f['label'] == 'Left' and f['x'] == .2 and f['flip_pan']
    assert f['rdm']['stale'] and 'address' not in f['rdm']


def test_partial_import_preserves_plan(context):
    c = context
    before = copy.deepcopy(c.cfg)
    with pytest.raises(ValueError):
        c.import_xml('<MA><Fixture fixture_id="31"/><Fixture fixture_id="broken"/></MA>', 'ma2')
    assert c.cfg == before


@pytest.mark.parametrize('reply,status', [('No objects found\n[Channel]>', 'empty'),
    ('Group 1 "Front"\nGroup 2 ???\n[Channel]>', 'partial'), ('???\n[Channel]>', 'error')])
def test_catalogue_completeness(context, reply, status):
    c = context
    async def send(line, **kw):
        return True, reply if 'Group' in line else 'No objects found\n[Channel]>'
    c.link.send = send
    result = asyncio.run(c.read_ma2())
    assert result['meta']['groups']['status'] == status
    assert result['ok'] == (status == 'empty')


def test_relative_different_heads_unknown_position():
    cfg = {'fixtures': [{'id': 1, 'flip_pan': False}, {'id': 2, 'flip_pan': True}], 'attrs': {'pan': {}, 'tilt': {}}}
    lines = rel_lines([1, 2], {'pan': 10, 'tilt': -2}, cfg)
    assert 'Attribute "Pan" At + 10' in lines and 'Attribute "Pan" At - 10' in lines
    assert 'Attribute "Tilt" At - 2' in lines
    assert not can_move({'params': ['PANROTATE']})
    assert can_move({'params': ['PAN']})


def test_disconnect_invalidates_actual_and_blocks_control(context):
    c = context
    c.state['live'] = {12: {'dim': 100, 'rgb': [100, 0, 0]}}
    c.state['dmx'] = {120: 255}
    async def go():
        c.link.state = 'disconnected'
        c.on_state('disconnected')
        await asyncio.sleep(0)
        assert c.state['live'] == {} and c.state['dmx'] == {}
        assert c.blocked('dim')
    asyncio.run(go())


def test_swapped_fixture_ids_require_explicit_identity():
    from ma2panel.fixtures import merge_fixtures
    old = [{'id': 1, 'name': 'Left', 'type': 'H', 'label': 'Mine L', 'x': .2},
           {'id': 2, 'name': 'Right', 'type': 'H', 'label': 'Mine R', 'x': .8}]
    found = [{'id': 2, 'name': 'Left', 'type': 'H', 'address': '1.1'},
             {'id': 1, 'name': 'Right', 'type': 'H', 'address': '2.1'}]
    preview = merge_fixtures(old, found)
    assert all(f.get('ambiguous_candidates') for f in preview)
    result = merge_fixtures(old, found, choices={'1': 2, '2': 1})
    assert {f['id']: f['label'] for f in result} == {1: 'Mine R', 2: 'Mine L'}
    assert {f['id']: f['x'] for f in result} == {1: .8, 2: .2}


def test_failed_import_save_keeps_confirmed_maps(context, monkeypatch):
    from ma2panel import bridge
    c = context
    before = copy.deepcopy(c.cfg)
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(bridge, 'save_config', fail)
    async def go():
        with pytest.raises(OSError):
            c.import_xml('<MA><Fixture fixture_id="31" name="New" type="H"/></MA>', 'ma2')
    asyncio.run(go())
    assert c.cfg == before


def test_deleted_and_added_fixtures_keep_manual_properties(context):
    c = context
    c.cfg['fixtures'] = [{'id': 12, 'name': 'Old', 'type': 'H', 'label': 'Keep', 'x': .3, 'icon': 'head'}]
    async def go():
        return c.import_xml('<MA><Fixture fixture_id="31" name="New" type="H"/></MA>', 'ma2')
    result = asyncio.run(go())
    assert result['added'] == result['missing'] == 1
    old = next(f for f in c.cfg['fixtures'] if f['id'] == 12)
    assert old['missing'] and old['label'] == 'Keep' and old['x'] == .3 and old['icon'] == 'head'


def test_import_keeps_previous_map_versions(context):
    c = context
    old = copy.deepcopy(c.cfg['dmx_map']['Par'])
    async def go():
        result = c.import_xml('<MA><Fixture fixture_id="12" type="New"/></MA>', 'ma2')
        return c.confirm_import({"request_token": result["request_token"], "choices": {"12": None}})
    asyncio.run(go())
    assert old in c.cfg['dmx_map_saved']['Par']
    assert c.cfg['dmx_map']['Par']['stale']


def test_relative_motion_preserves_offsets_external_changes_and_limits():
    from ma2panel.mock import MockMA2
    mock = MockMA2('panel', None)
    mock.positions = {1: {'pan': -20., 'tilt': 30.}, 2: {'pan': 80., 'tilt': -5.}}
    mock.position_ranges = {1: {'pan': (-270, 270)}, 2: {'pan': (-90, 90)}}
    cfg = {'fixtures': [{'id': 1}, {'id': 2}], 'attrs': {'pan': {}, 'tilt': {}}}
    def jog():
        for line in rel_lines([1, 2], {'pan': 5}, cfg):
            mock._reply(line)
    jog()
    assert [mock.positions[i]['pan'] for i in (1, 2)] == [-15, 85]
    mock.positions[1]['pan'] = 10  # desk operator changed position between ticks
    jog()
    assert [mock.positions[i]['pan'] for i in (1, 2)] == [15, 90]
    jog()
    assert [mock.positions[i]['pan'] for i in (1, 2)] == [20, 90]  # desk clamps each profile
    mock.positions.pop(2)
    jog()
    assert 2 not in mock.positions  # mock never invents unknown starting coordinates


def test_lua_error_in_one_block_does_not_block_another(context):
    import re
    c = context
    c.cfg['fixtures'] = [{'id': 1, 'type': 'D', 'address': '1.1', 'footprint': 1},
                         {'id': 2, 'type': 'D', 'address': '2.1', 'footprint': 1}]
    c.cfg['dmx_map'] = {'D': {'dim': 1, 'has': []}}
    c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
    nonce = ['']
    async def send(line, **kw):
        if 'local a,n,v=1,' in line or 'pcall(gma.show.getdmx,1)' in line:
            return False, 'Error #44'
        if 'local a,n,v=513,' in line:
            nonce[0] = re.search(r"'T([0-9a-f]+) '", line)[1]
        return True, f'$PANELDMX513 = "T{nonce[0]} 513 128"' if line == 'ListVar' else 'OK'
    async def go():
        c.link.send = send
        await c.read_dmx()
        await c.read_dmx()
        assert c.state['live'][2]['dim'] == 50.2
    asyncio.run(go())


@pytest.mark.parametrize('partial', [False, True])
def test_group_import_preserves_labels_and_rejects_partial_members(context, partial):
    import re
    from pathlib import Path
    c = context
    c.cfg['ma2groups'] = [{'n': 1, 'name': 'Old', 'label': 'My group', 'ids': [12]}]
    before = copy.deepcopy(c.cfg)
    async def send(line, **kw):
        if line == 'ListVar':
            return True, '$SHOWFILE = Mock show\n[Group]>'
        if line.startswith('List Group'):
            return True, 'Group 1 "New"\n[Group]>'
        if line.startswith('List Preset'):
            return True, 'No objects found\n[Group]>'
        if line.startswith('Export Group'):
            name = re.search(r'"([^"]+)"', line)[1]
            body = '<Group index="1" name="Other"/>' if partial else '<Group index="0" name="New"><Subfixture fix_id="12"/></Group>'
            Path(c.export_dir, name + '.xml').write_text('<MA>' + body + '</MA>')
        return True, 'OK'
    async def go():
        c.link.send = send
        return await c.ma2_action('ma2_import', {'groups': [1]}, {'selection': [], 'base': None})
    result = asyncio.run(go())
    if partial:
        assert not result['ok'] and c.cfg == before
        assert not c.state['read_freshness']['ma2']
        assert c.catalogue_meta()['groups']['status'] == 'partial'
    else:
        assert result['ok']
        assert c.cfg['ma2groups'] == [{'n': 1, 'name': 'New', 'label': 'My group', 'ids': [12]}]


def test_group_import_checks_actual_show_before_replacing_plan(context):
    c = context
    before = copy.deepcopy(c.cfg)
    calls = []
    async def send(line, **kw):
        calls.append(line)
        return True, '$SHOWFILE = Other\n[Group]>'
    async def go():
        c.link.send = send
        with pytest.raises(ActionError, match='другое шоу'):
            await c.ma2_action('ma2_import', {'groups': []}, {'selection': [], 'base': None})
    asyncio.run(go())
    assert calls == ['ListVar']
    # A changed show invalidates live maps, but never replaces the catalogue.
    assert c.cfg.get('ma2groups') == before.get('ma2groups')
