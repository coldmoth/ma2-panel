"""Readback regressions. XML is synthetic; the FixtureType table is recorded MA2 3.9.60."""
import asyncio
import re
from pathlib import Path

import pytest

from ma2panel.commands import live_from_dmx
from ma2panel.fixtures import parse_fixture_type
from test_status_evidence import context  # noqa: F401


RGB = ('<ChannelType attribute="DIM" coarse="1"/>'
       '<ChannelType attribute="COLORRGB1" coarse="2"/>'
       '<ChannelType attribute="COLORRGB2" coarse="3"/>'
       '<ChannelType attribute="COLORRGB3" coarse="4"/>')


@pytest.fixture
def active_context(tmp_path, monkeypatch):
    from ma2panel import bridge
    create = bridge.create_app

    def configured(*args, **kwargs):
        kwargs['settings']['dmx_seconds'] = .1
        return create(*args, **kwargs)

    monkeypatch.setattr(bridge, 'create_app', configured)
    yield from context.__wrapped__(tmp_path, monkeypatch)


def profile(channels=RGB, instances='<Instance index="0" module_index="0" patch="1"/>'):
    return ('<FixtureType><Modules><Module index="0">' + channels + '</Module></Modules>'
            '<Instances>' + instances + '</Instances></FixtureType>')


def test_single_unshifted_instance_is_a_readable_profile():
    spec = parse_fixture_type(profile())
    assert live_from_dmx([{'id': 1, 'type': 'RGB', 'address': '2.001'}],
                         {513: 51, 514: 255, 515: 0, 516: 0}, {'RGB': spec}) == {
                             1: {'dim': 20.0, 'rgb': [100.0, 0.0, 0.0]}}


@pytest.mark.parametrize('instances', [
    '<Instance module_index="0" patch="2"/>',
    '<Instance module_index="1" patch="1"/>',
    '<Instance module_index="0" patch="1"/><Instance module_index="0" patch="5"/>',
])
def test_complex_instance_offsets_remain_unknown(instances):
    assert parse_fixture_type(profile(instances=instances))['unsupported'] is True


@pytest.mark.parametrize('attribute', ['COLOR1', 'COLORRGB4', 'COLORCMY1', 'COLORMIX1'])
def test_unmapped_colour_is_not_measured_white(attribute):
    spec = parse_fixture_type('<FixtureType><Module><ChannelType attribute="DIM" coarse="1"/>'
                              f'<ChannelType attribute="{attribute}" coarse="2"/></Module></FixtureType>')
    assert live_from_dmx([{'id': 1, 'type': 'Other', 'address': '1.001'}],
                         {1: 255, 2: 0}, {'Other': spec}) == {}


def test_partial_manual_rgb_map_does_not_invent_white():
    assert live_from_dmx([{'id': 1, 'type': 'Other', 'address': '1.001'}],
                         {1: 255, 2: 255}, {'Other': {'dim': 1, 'r': 2}}) == {}


def test_out_of_range_rgb_channels_do_not_become_white():
    spec = parse_fixture_type('<FixtureType><Module><ChannelType attribute="DIM" coarse="1"/>' +
                              ''.join(f'<ChannelType attribute="COLORRGB{i}" coarse="{64+i}"/>' for i in (1, 2, 3)) +
                              '</Module></FixtureType>')
    assert live_from_dmx([{'id': 1, 'type': 'Wide', 'address': '1.001'}], {1: 255}, {'Wide': spec}) == {}


def test_bare_recorded_type_name_recovers_after_reconnect(context):
    c = context
    c.cfg['fixtures'] = [{'id': 12, 'type': 'ARTIST_FL_1000', 'address': '2.001', 'footprint': 9}]
    original = {'dim': 1, 'r': 2, 'g': 3, 'b': 4, 'has': []}
    c.cfg['dmx_map'] = {'ARTIST_FL_1000': dict(original)}
    c.ma2['export_wait'] = 0
    lines, marker = [], ['']

    async def send(line, **kwargs):
        lines.append(line)
        if line == 'List FixtureType':
            return True, Path('ma2panel/resources/mock/list_fixturetype_3.9.60.txt').read_text()
        if line.startswith('Export FixtureType 3 '):
            name = re.search(r'"([^"]+)"', line)[1]
            (Path(c.config_path).parent / (name + '.xml')).write_text(profile())
        elif 'local a,n,v=' in line:
            marker[0] = re.search(r"'T([0-9a-f]+) '", line)[1]
        elif line == 'ListVar':
            return True, f'Global : $PANELDMX513 = "T{marker[0]} 513 51,255,0,0,0,0,0,0,0"'
        return True, ''

    async def go():
        c.link.send = send
        for _ in range(2):
            c.link._gen += 1
            c.invalidate_profiles()
            assert c.cfg['dmx_map']['ARTIST_FL_1000']['stale']
            assert not c.state['live']
            await c.read_dmx()
            assert c.cfg['dmx_map']['ARTIST_FL_1000'] == original
            assert c.cfg['fixtures'][0]['footprint'] == 9
            assert c.state['live'][12] == {'dim': 20.0, 'rgb': [100.0, 0.0, 0.0]}
        assert c.cfg['dmx_map_saved']['ARTIST_FL_1000'] == [original]
        assert all(line.startswith(('Lua ', 'Export FixtureType ', 'List')) for line in lines)
    asyncio.run(go())


def test_bad_universe_does_not_pause_healthy_universe_for_thirty_seconds(context):
    c = context
    c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
    c.cfg['fixtures'] = [{'id': 1, 'type': 'Par', 'address': '1.001', 'footprint': 4},
                         {'id': 2, 'type': 'Par', 'address': '2.001', 'footprint': 4}]
    current = [None]

    async def send(line, **kwargs):
        if 'local a,n,v=' in line:
            current[0] = (int(re.search(r'local a,n,v=(\d+)', line)[1]),
                          re.search(r"'T([0-9a-f]+) '", line)[1])
        if line == 'ListVar':
            a, tag = current[0]
            values = '-1,-1,-1,-1' if a == 1 else '51,0,0,255'
            return True, f'$PANELDMX{a} = "T{tag} {a} {values}"'
        return True, ''

    async def go():
        c.link.send = send
        pause = await c.read_dmx()
        assert pause < 6, 'one unreadable chunk must not starve all other chunks'
        await c.read_dmx()
        assert 1 not in c.state['live']
        assert c.state['live'][2] == {'dim': 20.0, 'rgb': [0.0, 0.0, 100.0]}
    asyncio.run(go())


def test_readback_diagnostics_explain_disabled_and_expired_output(context):
    c = context
    d = c.dmx_diagnostics()
    assert d['enabled'] is False  # mock polling defaults off; permission is separate
    assert d['connected'] is True
    assert d['stage'] == 'disabled'
    assert d['patched_fixtures'] == 1
    assert d['actual_fixtures'] == 0
    assert d['last_success'] is None


def test_fixture_type_long_names_must_be_unique():
    from ma2panel.commands import parse_type_names
    table = Path('ma2panel/resources/mock/list_fixturetype_3.9.60.txt').read_text()
    assert parse_type_names(table)['ARTIST_FL_1000'] == '3'
    duplicate = next(ln for ln in table.splitlines() if ln.startswith('FixtureType 3 '))
    assert 'ARTIST_FL_1000' not in parse_type_names(table + '\n' + duplicate.replace('FixtureType 3 ', 'FixtureType 9 ', 1))


def test_export_diagnostic_distinguishes_invalid_xml_from_missing_file(context):
    c = context
    c.cfg['fixtures'] = [{'id': 12, 'type': '3 Broken', 'address': '1.001'}]
    c.ma2['export_wait'] = 0

    async def send(line, **kwargs):
        if line.startswith('Export FixtureType'):
            name = re.search(r'"([^"]+)"', line)[1]
            (Path(c.config_path).parent / (name + '.xml')).write_text('<invalid')
        return True, ''

    async def go():
        c.link.send = send
        await c.read_types()
        trace = c.state['type_reads']['3']
        assert trace['error']
        assert trace['file'].endswith('.xml'), 'a found invalid file must not look like a missing export'
    asyncio.run(go())


def test_readable_lua_with_unavailable_bytes_is_not_a_format_error(context):
    c = context
    c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
    marker = ['']

    async def send(line, **kwargs):
        if 'local a,n,v=' in line:
            marker[0] = re.search(r"'T([0-9a-f]+) '", line)[1]
        if line == 'ListVar':
            return True, f'$PANELDMX120 = "T{marker[0]} 120 -1,-1,-1,-1"'
        return True, ''

    async def go():
        c.link.send = send
        await c.read_dmx()
        assert c.state['dmx_read']['stage'] == 'getdmx'
        assert not c.state['live']
    asyncio.run(go())


def test_reconnect_wakes_dmx_backoff_without_waiting_thirty_seconds(context):
    c = context
    c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
    marker, available = [''], [False]

    async def go():
        refused = asyncio.Event()
        measured = asyncio.Event()

        async def send(line, **kwargs):
            if line.startswith('Lua ') and not available[0]:
                refused.set()
                return False, 'Error #44'
            if 'local a,n,v=' in line:
                marker[0] = re.search(r"'T([0-9a-f]+) '", line)[1]
            if line == 'ListVar':
                measured.set()
                return True, f'$PANELDMX120 = "T{marker[0]} 120 51,255,0,0"'
            return True, ''

        c.link.send = send
        task = asyncio.create_task(c.poll_dmx())
        try:
            await asyncio.wait_for(refused.wait(), 1)
            await asyncio.sleep(.01)  # let poll_dmx enter its refusal backoff
            c.link._gen += 1
            c.invalidate_profiles()
            c.state['types_context'] = (c.state['plan_epoch'], c.link._gen)
            c.cfg['fixtures'][0]['footprint'] = 4
            c.cfg['dmx_map']['Par'] = {'dim': 1, 'r': 2, 'g': 3, 'b': 4}
            available[0] = True
            await asyncio.wait_for(measured.wait(), 1)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(go())


def test_diagnostics_never_count_expired_or_other_context_as_actual(active_context, monkeypatch):
    from ma2panel import bridge
    from types import SimpleNamespace
    c = active_context
    now = [100.0]
    monkeypatch.setattr(bridge, 'time', SimpleNamespace(monotonic=lambda: now[0], strftime=bridge.time.strftime))
    c.expire_dmx()
    c.state['dmx'] = {120: 51, 121: 255, 122: 0, 123: 0}
    c.dmx_cycle['seen'] = {a: 100.0 for a in c.state['dmx']}
    c.state['last_dmx_success'] = '2026-11-09 12:00:00'
    d = c.dmx_diagnostics()
    assert d['stage'] == 'output' and d['actual_fixtures'] == 1 and d['mapped_types'] == 1
    now[0] = 106.0
    d = c.dmx_diagnostics()
    assert d['stage'] == 'freshness' and d['actual_fixtures'] == 0
    assert c.state['dmx'], 'diagnostic request must not mutate the running reader'
    now[0] = 101.0
    c.link._gen += 1
    assert c.dmx_diagnostics()['actual_fixtures'] == 0


@pytest.mark.parametrize('case,stage', [('rights', 'disabled'), ('connection', 'connection'),
                                      ('addresses', 'addresses'), ('stale_map', 'dmx_map'),
                                      ('export', 'export'), ('xml', 'profile_parser')])
def test_diagnostics_explain_blocked_reading(active_context, case, stage):
    c = active_context
    if case == 'rights': c.safety['allow_fixture_read'] = False
    if case == 'connection': c.link.state = 'down'
    if case == 'addresses': c.cfg['fixtures'][0].pop('address')
    if case in ('stale_map', 'export', 'xml'): c.cfg['dmx_map']['Par']['stale'] = True
    if case in ('export', 'xml'):
        c.state['type_reads']['3'] = {'error': 'invalid', 'context': (c.state['plan_epoch'], c.link._gen),
                                      **({'file': 'test.xml'} if case == 'xml' else {})}
    d = c.dmx_diagnostics()
    assert d['stage'] == stage
    assert d['actual_fixtures'] == 0
    assert d['summary']
