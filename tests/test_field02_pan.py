"""FIELD-02: persisted Pan inversion controls relative commands, independently of beams."""
import json

import pytest

from test_bridge import ask, bridge_cfg, per_fixture


@pytest.mark.parametrize('action', [
    {'a': 'nudge', 'attr': 'pan', 'dir': 1, 'step': 1},
    {'a': 'jog', 'pan': 1, 'tilt': -2},
])
def test_pan_flag_saved_and_reversible_without_changing_tilt_or_neighbours(bridge_cfg, action):
    with bridge_cfg() as (ws, mock, path):
        for flipped in (False, True, False):
            assert ask(ws, {'a': 'select_group', 'id': 'front'})['ok']
            before = len(mock.received)
            assert ask(ws, {'a': 'fixture_flag', 'id': 12, 'flip_pan': flipped})['ok']
            assert mock.received[before:] == [], 'a flag change only saves the panel plan'
            fixtures = {f['id']: f for f in json.loads(path.read_text())['fixtures']}
            assert fixtures[12]['flip_pan'] is flipped
            assert not fixtures[14].get('flip_pan', False)
            assert not fixtures[12].get('flip_tilt', False)
            assert not fixtures[12].get('beam', {}).get('invert', False)
            before = len(mock.received)
            if action['a'] == 'jog':
                ws.send_json(action)
            else:
                result = ask(ws, action)
                assert result['ok'], result
            assert ask(ws, {'a': 'clear'})['ok']  # flush the throttled jog
            lines = mock.received[before:]
            assert per_fixture(lines, 'Pan') == {12: -1 if flipped else 1, 14: 1}
            assert per_fixture(lines, 'Tilt') == ({12: -2, 14: -2} if action['a'] == 'jog' else {})
