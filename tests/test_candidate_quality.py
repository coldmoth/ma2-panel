import hashlib

import pytest
from ma2panel import release, release_quality as quality


def evidence(tmp_path):
    sha = 'a' * 40
    archive = tmp_path / 'update.zip'
    release.write_zip({'source_identity.py': ('# source-sha: ' + sha).encode()}, archive)
    report = {'schema': 1, 'source_sha': sha, 'candidate_run': 42, 'candidate_attempt': 1,
              'checks': dict.fromkeys(quality.REQUIRED, 'success'), 'blockers': [],
              'assets': {'ma2-panel-update.zip': hashlib.sha256(archive.read_bytes()).hexdigest()},
              'runtime': {'python': '3.12', 'lock_sha256': 'a' * 64}}
    run = {'head_sha': sha, 'conclusion': 'success', 'event': 'workflow_dispatch',
           'path': '.github/workflows/ci.yml', 'repository': {'full_name': 'coldmoth/ma2-panel'}}
    check = {'name': 'Candidate quality evidence', 'head_sha': sha, 'conclusion': 'success',
             'app': {'slug': 'github-actions'}, 'external_id': 'candidate:42:1',
             'details_url': 'https://github.com/coldmoth/ma2-panel/actions/runs/42/attempts/1',
             'output': {'summary': quality.fingerprint(report)}}
    def fetch(url):
        return run if '/actions/' in url else {'total_count': 1, 'check_runs': [check]}
    return report, archive, fetch, run, check


def test_exact_ci_evidence_and_zip(tmp_path):
    report, archive, fetch, _, _ = evidence(tmp_path)
    assert quality.authenticate_candidate(report, 'v3.3.2-rc.1', 'coldmoth/ma2-panel', fetch) == report
    quality.verify_archive(archive, report, 'v3.3.2-rc.1', candidate=True)
    with pytest.raises(ValueError):
        quality.authenticate(report, 'v3.3.2', 'coldmoth/ma2-panel', fetch)


@pytest.mark.parametrize('failure', ['missing', 'checks', 'hash', 'sha', 'zip', 'run', 'app', 'workflow', 'attempt', 'runtime', 'blocker', 'stable-tag'])
def test_rejects_tampered_or_incomplete_candidate(tmp_path, failure):
    report, archive, fetch, run, check = evidence(tmp_path)
    tag = 'v3.3.2-rc.1'
    if failure == 'missing': report = None
    elif failure == 'checks': report['checks']['windows'] = 'skipped'
    elif failure == 'hash': check['output']['summary'] = '0' * 64
    elif failure == 'sha': report['source_sha'] = 'b' * 40
    elif failure == 'zip': archive.write_bytes(b'corrupt')
    elif failure == 'run': run['conclusion'] = 'failure'
    elif failure == 'app': check['app']['slug'] = 'untrusted'
    elif failure == 'workflow': run['path'] = '.github/workflows/other.yml'
    elif failure == 'attempt': check['external_id'] = 'candidate:42:2'
    elif failure == 'runtime': report.pop('runtime')
    elif failure == 'blocker': report['blockers'] = ['known blocker']
    elif failure == 'stable-tag': tag = 'v3.3.2'
    with pytest.raises(ValueError):
        quality.authenticate_candidate(report, tag, 'coldmoth/ma2-panel', fetch)
        quality.verify_archive(archive, report, tag, candidate=True)
