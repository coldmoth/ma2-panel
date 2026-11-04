"""The diagnostic split must fail closed when collection changes."""
import pytest

from scripts import ci_windows_isolation as isolation


@pytest.fixture(scope="module")
def groups(tmp_path_factory):
    return isolation.collect(tmp_path_factory.mktemp("windows-collection"))


def test_all_regression_nodes_are_assigned_once(groups):
    assert {key: len(value) for key, value in groups.items()} == {
        'release': 18, 'update': 35, 'browser-unit': 12, 'browser-worker': 1,
        'selfcheck': 5, 'rdm': 50, 'watchdog': 4}
    nodes = [node for values in groups.values() for node in values]
    assert len(nodes) == len(set(nodes)) == 125


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'unexpected', 'renamed'])
def test_collection_drift_fails_closed(change, groups):
    nodes = [node for values in groups.values() for node in values]
    if change == 'missing':
        nodes.pop()
    elif change == 'duplicate':
        nodes.append(nodes[0])
    elif change == 'unexpected':
        nodes.append('tests/test_surprise.py::test_example')
    elif change == 'renamed':
        nodes[0] += '_renamed'
    with pytest.raises(ValueError):
        isolation.validate_collection(nodes)


def test_group_keeps_failure_and_timeout_and_runs_remaining_test(tmp_path, monkeypatch):
    import json
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PYTHONPATH', str(isolation.ROOT))
    (tmp_path / 'test_probe.py').write_text('''import time
from pathlib import Path

def test_failure():
    assert False, "diagnostic failure"

def test_hang():
    time.sleep(30)

def test_success():
    Path("completed").touch()
''')
    manifest = tmp_path / 'groups.json'
    manifest.write_text(json.dumps({'probe': {'per_test_timeout_seconds': 1, 'group_timeout_seconds': 10}}))
    monkeypatch.setattr(isolation, 'MANIFEST', manifest)
    nodes = [f'test_probe.py::test_{name}' for name in ('failure', 'hang', 'success')]
    assert isolation.execute('probe', nodes, tmp_path) == 1
    events = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text().splitlines()]
    assert [e['returncode'] for e in events if e['event'] == 'finish'] == [1, 124, 0]
    assert (tmp_path / 'completed').exists()
    assert 'diagnostic failure' in (tmp_path / isolation.digest([nodes[0]]) / 'pytest.log').read_text()
    assert json.loads((tmp_path / isolation.digest([nodes[1]]) / 'result.json').read_text())['reason'] == 'watchdog_timeout'


def test_exhausted_group_budget_is_failure(tmp_path, monkeypatch):
    import json
    manifest = tmp_path / 'groups.json'
    manifest.write_text(json.dumps({'probe': {'per_test_timeout_seconds': 1, 'group_timeout_seconds': 0}}))
    monkeypatch.setattr(isolation, 'MANIFEST', manifest)
    assert isolation.execute('probe', ['test_probe.py::test_not_started'], tmp_path) == 124
    event = json.loads((tmp_path / 'events.jsonl').read_text())
    assert event == {'event': 'group_timeout', 'next_index': 0}
