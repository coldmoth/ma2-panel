"""Temporary Windows CI isolation; no console I/O in the supervising process.

Also loaded as a pytest plugin to collect IDs and select long parameterized IDs
by hash (Windows command lines cannot hold some of the RDM parameters).
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
from scripts.ci_windows_tests import TESTS, run

MANIFEST = ROOT / 'scripts/ci_windows_groups.json'


def digest(nodes):
    return hashlib.sha256('\n'.join(sorted(nodes)).encode('utf-8')).hexdigest()


def group_for(node):
    file, _, test = node.partition('::')
    if file == 'tests/test_browser_update.py':
        return 'browser-worker' if test == 'test_real_worker_update_restart_and_both_ports' else 'browser-unit'
    return {'tests/test_release.py': 'release', 'tests/test_update.py': 'update',
            'tests/test_selfcheck.py': 'selfcheck', 'tests/test_rdm_search.py': 'rdm',
            'tests/test_ci_windows_tests.py': 'watchdog'}[file]


def validate_collection(nodes):
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    groups = {key: [] for key in manifest}
    if len(nodes) != len(set(nodes)):
        raise ValueError('Duplicate Windows node IDs')
    for node in nodes:
        try:
            groups[group_for(node)].append(node)
        except KeyError:
            raise ValueError(f'Unassigned Windows test: {node[:160]}') from None
    for key, values in groups.items():
        expected = manifest[key]
        if len(values) != expected['count'] or digest(values) != expected['sha256']:
            raise ValueError(f'Windows collection changed in {key}; review the diagnostic manifest')
    return groups


def pytest_addoption(parser):
    parser.addoption('--ci-collection', default=None)
    parser.addoption('--ci-node-hash', default=None)


def pytest_collection_modifyitems(config, items):
    output = config.getoption('--ci-collection')
    if output:
        Path(output).write_text(json.dumps([item.nodeid for item in items]), encoding='utf-8')
    selected_hash = config.getoption('--ci-node-hash')
    if selected_hash:
        selected = [item for item in items if digest([item.nodeid]) == selected_hash]
        if len(selected) != 1:
            import pytest
            raise pytest.UsageError('Expected exactly one Windows test matching the planned hash')
        config.hook.pytest_deselected(items=[item for item in items if item not in selected])
        items[:] = selected


def collect(output):
    output = Path(output).resolve()
    command = [sys.executable, '-u', '-m', 'pytest',
               *(f'tests/{name}' for name in TESTS), '-p', 'scripts.ci_windows_isolation',
               '--collect-only', '-q', '-o', 'addopts=--tb=short',
               '-o', 'faulthandler_timeout=15', f'--ci-collection={output / "nodes.json"}']
    result = run(command, output, timeout=45)
    if result:
        raise RuntimeError(f'Windows collection failed: {result}; see {output}')
    return validate_collection(json.loads((output / 'nodes.json').read_text(encoding='utf-8')))


def execute(group, nodes, output):
    limits = json.loads(MANIFEST.read_text(encoding='utf-8'))[group]
    deadline = time.monotonic() + limits['group_timeout_seconds']
    failed = False
    with (output / 'events.jsonl').open('a', encoding='utf-8', buffering=1) as events:
        for index, node in enumerate(nodes):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                events.write(json.dumps({'event': 'group_timeout', 'next_index': index}) + '\n')
                return 124
            key = digest([node])
            folder = output / key
            events.write(json.dumps({'event': 'start', 'index': index, 'node': node, 'directory': key}) + '\n')
            command = [sys.executable, '-u', '-m', 'pytest', node.split('::')[0],
                       '-p', 'scripts.ci_windows_isolation', f'--ci-node-hash={key}',
                       '-o', 'addopts=--tb=short', '-o',
                       f'faulthandler_timeout={max(1, limits["per_test_timeout_seconds"] - 5)}',
                       '-vv', '-s', f'--basetemp={folder / "tmp"}', f'--junitxml={folder / "pytest.xml"}']
            result = run(command, folder, timeout=min(remaining, limits['per_test_timeout_seconds']))
            events.write(json.dumps({'event': 'finish', 'index': index, 'returncode': result}) + '\n')
            failed = failed or result != 0
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', required=True, choices=list(json.loads(MANIFEST.read_text(encoding='utf-8'))))
    parser.add_argument('--collect-only', action='store_true')
    args = parser.parse_args()
    output = ROOT / 'test-results/windows' / args.group
    if args.collect_only:
        groups = collect(output / 'collection')
        (output / 'plan.json').write_text(json.dumps({'group': args.group, 'nodes': groups[args.group]}, indent=2), encoding='utf-8')
        return 0
    plan = json.loads((output / 'plan.json').read_text(encoding='utf-8'))
    expected = json.loads(MANIFEST.read_text(encoding='utf-8'))[args.group]
    if plan['group'] != args.group or len(plan['nodes']) != expected['count'] or digest(plan['nodes']) != expected['sha256']:
        raise ValueError('Invalid Windows test plan')
    return execute(args.group, plan['nodes'], output)


if __name__ == '__main__':
    sys.exit(main())
