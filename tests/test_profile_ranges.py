"""DATA-003: parameter count is never a confirmed physical DMX range."""
import pytest
from commands import ActionError, dmx_intervals, patch_plan, patch_rows


def test_real_minib_channel_count_does_not_authorize_patch():
    f = {'id': 10, 'address': '1.100', 'channels': 14}
    with pytest.raises(ActionError, match='не прочитано'):
        patch_plan([f], 10, 200, True, False)
    assert patch_rows([f])[0]['ma2'] is None
    assert dmx_intervals([f]) == []


def test_real_minib_reads_all_seventeen_slots_including_tail():
    f = {'id': 10, 'address': '1.100', 'channels': 14, 'footprint': 17}
    assert dmx_intervals([f]) == [(100, 17)]
    neighbor = {'id': 11, 'address': '1.216', 'footprint': 1}
    assert patch_plan([f, neighbor], 10, 200, True, False)['conflicts'] == [11]


def test_unknown_neighbor_cannot_hide_overlap_in_its_unread_tail():
    target = {'id': 10, 'address': '1.100', 'footprint': 17}
    unknown = {'id': 11, 'address': '1.190', 'channels': 14}
    with pytest.raises(ActionError, match='не прочитано'):
        patch_plan([target, unknown], 10, 200, True, False)
