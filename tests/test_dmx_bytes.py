import pytest
from ma2panel.commands import parse_dmx, live_from_dmx


@pytest.mark.parametrize('value', ['-1', '256', '999', '1.5', '1..2', 'nan', 'inf', '255junk', '255,', '255;0'])
def test_invalid_dmx_is_unknown(value):
    assert parse_dmx(f'PANELDMX1 = "T 1 {value}"', span=(1, 1)) == {}


def test_valid_bytes_and_partial_chunk_policy():
    assert parse_dmx('PANELDMX1 = "T 1 0,255,256,-1,1.5"', span=(1, 5)) == {1: 0, 2: 255}
    assert parse_dmx('PANELDMX1 = "T 1 0,255"', span=(1, 3)) == {}
    dmx = parse_dmx('PANELDMX1 = "T 1 999,255,0,255"', span=(1, 4))
    assert live_from_dmx([{'id': 1, 'type': 'A', 'address': '1.001'}], dmx,
                         {'A': {'dim': 1, 'r': 2, 'g': 3, 'b': 4}}) == {}
