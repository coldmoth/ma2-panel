"""Local group editing must never send desk commands or lose configuration."""
import json

import pytest

from test_bridge import bridge_cfg, ask  # noqa: F401


def test_local_group_lifecycle(bridge_cfg):
    def seed(cfg):
        cfg['groups'] = [{'id': 'g1', 'label': 'Old', 'fixtures': [12],
                          'custom': {'keep': True}, 'color': '#9e8cef', 'icon': 'layers'},
                         {'id': 'g2', 'label': 'Other', 'fixtures': [12]}]
    with bridge_cfg(edit=seed) as (ws, mock, path):
        before = json.loads(path.read_text())
        sent = list(mock.received)
        assert ask(ws, {'a': 'group_save', 'id': 'g1', 'label': 'Left',
                        'ids': [12, 12], 'color': '#7ab7b0', 'icon': 'sun'})['ok']
        saved = json.loads(path.read_text())
        assert saved['groups'][0] == {**before['groups'][0], 'label': 'Left',
                                    'color': '#7ab7b0', 'icon': 'sun'}
        assert ask(ws, {'a': 'group_save', 'id': 'g1', 'label': 'Empty', 'ids': []})['ok']
        assert json.loads(path.read_text())['groups'][0]['fixtures'] == []
        assert ask(ws, {'a': 'group_save', 'label': 'New empty', 'ids': []})['ok']
        assert ask(ws, {'a': 'group_delete', 'id': 'g1'})['ok']
        final = json.loads(path.read_text())
        assert final['groups'][0] == before['groups'][1]
        assert final['groups'][1]['fixtures'] == []
        assert final['fixtures'] == before['fixtures']
        assert mock.received == sent


@pytest.mark.parametrize('change', [
    {'id': 'missing'}, {'id': 'desk'}, {'color': 'red'}, {'color': '#123456;bad'},
    {'icon': 'unknown'}, {'ids': [999999]}, {'ids': [True]}, {'ids': None},
])
def test_local_group_rejects_invalid_without_mutation(bridge_cfg, change):
    def seed(cfg):
        cfg['groups'] = [{'id': 'g1', 'label': 'Local', 'fixtures': [12]},
                         {'id': 'desk', 'label': 'MA2', 'fixtures': [12], 'n': 1}]
    with bridge_cfg(edit=seed) as (ws, mock, path):
        before, sent = path.read_bytes(), list(mock.received)
        assert not ask(ws, {'a': 'group_save', 'id': 'g1', 'label': 'Changed',
                            'ids': [12], **change})['ok']
        assert path.read_bytes() == before
        assert mock.received == sent


def test_local_group_disk_error_is_atomic(bridge_cfg, monkeypatch):
    from ma2panel import bridge as module
    with bridge_cfg() as (ws, mock, path):
        before, sent = path.read_bytes(), list(mock.received)
        def fail(*args, **kwargs):
            raise OSError('test disk full')
        with monkeypatch.context() as patch:
            patch.setattr(module, 'save_config', fail)
            assert not ask(ws, {'a': 'group_save', 'label': 'Not saved', 'ids': [12]})['ok']
        assert path.read_bytes() == before
        assert mock.received == sent
        # A later valid save must not contain the rejected group from memory.
        assert ask(ws, {'a': 'group_save', 'label': 'Saved', 'ids': []})['ok']
        assert not any(g['label'] == 'Not saved' for g in json.loads(path.read_text())['groups'])
