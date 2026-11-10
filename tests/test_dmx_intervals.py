import re
import time
from test_bridge import bridge_cfg

def test_dmx_sparse_intervals_regression():
    from ma2panel.commands import dmx_intervals, dmx_span
    fixtures = [
        {"address": "2.001", "footprint": 2},
        {"address": "1.010", "footprint": 4},
        {"address": "1.013", "footprint": 4},
        {"address": "1.017", "footprint": 1},
        {"address": "1.018", "footprint": 495, "missing": True},
        {"footprint": 99},
    ]
    assert dmx_intervals(fixtures) == [(10, 8), (513, 2)]
    assert dmx_span(fixtures) == (10, 505)
    assert dmx_intervals([]) == []


def test_dmx_actual_round_robin_regression(bridge_cfg):
    def edit(cfg):
        cfg["fixtures"] = [
            {"id": 12, "label": "Wide", "address": "1.001", "footprint": 40, "type": "Par"},
            {"id": 14, "label": "Sparse", "address": "2.001", "footprint": 1, "type": "Par"},
        ]
        cfg["dmx_map"] = {"Par": {"dim": 1, "has": []}}

    with bridge_cfg(edit, confirmed_profiles=True, settings={
        "safety": {"mode": "full", "allow_fixture_read": True},
        "dmx_seconds": 0.1,
    }) as (ws, mock, _):
        deadline = time.monotonic() + 8
        chunks = []
        while time.monotonic() < deadline:
            chunks = [tuple(map(int, m.groups())) for line in list(mock.received)
                      if (m := re.search(r"local a,n,v=(\d+),(\d+),", line))]
            if len(chunks) >= 6:
                break
            time.sleep(0.02)
        assert chunks[:6] == [(1, 32), (33, 8), (513, 1)] * 2
        lines = list(mock.received)
        positions = [i for i, line in enumerate(lines) if "local a,n,v=" in line]
        # Each chunk finishes with its own ListVar before another chunk can hold the action lock.
        assert all("ListVar" in lines[a + 1:b] for a, b in zip(positions, positions[1:]))
        assert sum("local D='SetVar '" in line for line in lines) == 1


def test_manual_command_runs_during_dmx_lua_settle(bridge_cfg):
    from test_bridge import ask

    def edit(cfg):
        cfg['fixtures'] = [{'id': 12, 'label': 'Dimmer', 'address': '1.001', 'footprint': 1, 'type': 'Par'}]
        cfg['dmx_map'] = {'Par': {'dim': 1, 'has': []}}

    with bridge_cfg(edit, confirmed_profiles=True, settings={'safety': {'mode': 'full', 'allow_fixture_read': True}, 'dmx_seconds': .1}) as (ws, mock, _):
        deadline = time.monotonic() + 4
        while not any('local a,n,v=' in line for line in mock.received):
            assert time.monotonic() < deadline
            time.sleep(.005)
        first = next(i for i, line in enumerate(mock.received) if 'local a,n,v=' in line)
        assert ask(ws, {'a': 'scene_off', 'id': 'pianist'})['ok']
        lines = list(mock.received)
        manual = next(i for i, line in enumerate(lines[first + 1:], first + 1) if line.startswith('Off Executor '))
        assert lines[first + 1:manual] == ['ListVar', 'Masterfade 0 Executor 1.101']  # scene show preflight proceeds during DMX settle


def test_current_chunk_does_not_inherit_overlapping_listvar_rows():
    from ma2panel.commands import parse_dmx
    current = 'Global : $PANELDMX33 = "T 33 -1,128"'
    obsolete = 'Global : $PANELDMX1 = "T 1 ' + ','.join(['255'] * 64) + '"'
    for rows in ((current, obsolete), (obsolete, current)):
        assert parse_dmx('\n'.join(rows), span=(33, 2)) == {34: 128}
    assert parse_dmx('PANELDMX33=T 33 255', span=(33, 2)) == {}
    assert parse_dmx('PANELDMX34=T 33 255,128', span=(33, 2)) == {}


def test_empty_patch_invalidates_previous_dmx_even_when_poll_skips(bridge_cfg, monkeypatch):
    from ma2panel import bridge
    from test_bridge import until
    original = bridge.dmx_intervals
    empty = [False]
    monkeypatch.setattr(bridge, 'dmx_intervals', lambda fixtures: [] if empty[0] else original(fixtures))

    def edit(cfg):
        cfg['fixtures'] = [{'id': 12, 'label': 'Dimmer', 'address': '1.001', 'footprint': 1, 'type': 'Par'}]
        cfg['dmx_map'] = {'Par': {'dim': 1, 'has': []}}

    with bridge_cfg(edit, confirmed_profiles=True, settings={'safety': {'mode': 'full', 'allow_fixture_read': True}, 'dmx_seconds': .1}) as (ws, mock, _):
        mock.dmx = {1: 255}
        until(ws, lambda m: m.get('live', {}).get('12', {}).get('dim') == 100)
        empty[0] = True
        until(ws, lambda m: 'live' in m and m['live'] == {})
