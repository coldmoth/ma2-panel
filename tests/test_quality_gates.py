import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from scripts import quality_gate as gate


def report(tmp_path):
    asset = tmp_path / 'candidate.zip'; asset.write_bytes(b'exact tested ZIP')
    sha = 'a' * 40
    data = {'schema': 1, 'source_sha': sha, 'checks': {k: 'success' for k in gate.REQUIRED},
            'assets': {asset.name: hashlib.sha256(asset.read_bytes()).hexdigest()}, 'blockers': [],
            'hardware': None, 'review': None}
    return data, sha, [asset]


def test_rc_is_separate_from_stable_acceptance(tmp_path):
    data, sha, assets = report(tmp_path)
    assert gate.evaluate(data, sha, assets) == []
    assert gate.evaluate(data, sha, assets, stable=True)
    for key in ('hardware', 'review'):
        data[key] = {'status': 'success', 'source_sha': sha, 'assets': data['assets'].copy()}
    assert gate.evaluate(data, sha, assets, stable=True)  # field v3 still missing
    data['field_v3'] = 'confirmed'
    assert gate.evaluate(data, sha, assets, stable=True) == []
    data['hardware']['source_sha'] = 'b' * 40
    assert gate.evaluate(data, sha, assets, stable=True)


@pytest.mark.parametrize('result', ['failure', 'skipped', 'cancelled', 'unknown', None])
def test_no_success_from_missing_or_skipped_mandatory_checks(tmp_path, result):
    data, sha, assets = report(tmp_path)
    data['checks']['webkit'] = result
    assert gate.evaluate(data, sha, assets)
    data['checks'].pop('webkit')
    assert gate.evaluate(data, sha, assets)


def test_changed_zip_sha_missing_assets_and_blockers_fail_closed(tmp_path):
    data, sha, assets = report(tmp_path)
    assert gate.evaluate(data, 'b' * 40, assets)
    assert gate.evaluate(data, sha, [])
    data['blockers'] = ['known fixture regression']
    assert gate.evaluate(data, sha, assets)
    data['blockers'] = []
    assets[0].write_bytes(b'different ZIP')
    assert gate.evaluate(data, sha, assets)


@pytest.mark.parametrize('data', [{}, None, {'schema': 1, 'checks': []}])
def test_malformed_report_is_failure(data):
    assert gate.evaluate(data, 'a' * 40, [])


def test_record_rejects_untracked_source_code(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / 'tracked.py').write_text('pass\n')
    subprocess.run(['git', '-C', str(tmp_path), 'add', 'tracked.py'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=QA', '-c', 'user.email=qa@example.invalid', 'commit', '-qm', 'fixture'], check=True)
    sha = subprocess.check_output(['git', '-C', str(tmp_path), 'rev-parse', 'HEAD'], text=True).strip()
    (tmp_path / 'candidate').mkdir(); asset = tmp_path / 'candidate/a.zip'; asset.write_bytes(b'ZIP')
    (tmp_path / 'untracked-source.py').write_text('changed source not in SHA\n')
    script = Path(__file__).resolve().parents[1] / 'scripts/quality_gate.py'
    run = subprocess.run([sys.executable, str(script), 'record', '--report', 'evidence/quality.json', '--sha', sha,
                          '--asset', str(asset), '--checks-json', json.dumps({k: 'success' for k in gate.REQUIRED})],
                         cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode != 0
    assert json.loads(run.stdout)['ready'] is False
