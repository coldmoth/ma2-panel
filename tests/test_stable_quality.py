import hashlib
import json
from pathlib import Path

import pytest
from ma2panel import release
from ma2panel import release_quality as quality


def evidence(tmp_path):
    sha = 'a' * 40
    archive = tmp_path / 'update.zip'
    release.write_zip({'source_identity.py': ('# source-sha: ' + sha).encode()}, archive)
    data = {'schema': 1, 'channel': 'stable', 'tag': 'v3.3.1', 'source_sha': sha,
            'promotion_run': 42, 'promotion_attempt': 1, 'checks': dict.fromkeys(quality.REQUIRED, 'success'),
            'assets': {'ma2-panel-update.zip': hashlib.sha256(archive.read_bytes()).hexdigest()},
            'blockers': [], 'field_v3': 'confirmed'}
    for name in ('hardware', 'review'):
        data[name] = {'status': 'success', 'source_sha': sha, 'assets': data['assets'].copy()}
    run = {'head_sha': sha, 'conclusion': 'success', 'event': 'workflow_dispatch',
           'path': '.github/workflows/promote.yml', 'repository': {'full_name': 'coldmoth/ma2-panel'}}
    check = {'name': quality.CHECK, 'head_sha': sha, 'conclusion': 'success', 'app': {'slug': 'github-actions'},
             'external_id': 'quality:42:1', 'details_url': 'https://github.com/coldmoth/ma2-panel/actions/runs/42/attempts/1',
             'output': {'summary': quality.fingerprint(data)}}
    def fetch(url): return run if '/actions/' in url else {'total_count': 1, 'check_runs': [check]}
    return data, archive, fetch, run, check


def test_authentic_report_and_exact_zip(tmp_path):
    data, archive, fetch, _, _ = evidence(tmp_path)
    assert quality.authenticate(data, data['tag'], 'coldmoth/ma2-panel', fetch) == data
    quality.verify_archive(archive, data, data['tag'])


@pytest.mark.parametrize('failure', ['absent', 'malformed', 'tag', 'sha', 'zip', 'checks', 'check-hash', 'workflow', 'run', 'app', 'attempt', 'hardware'])
def test_fail_closed_on_missing_forged_mismatched_or_corrupt_evidence(tmp_path, failure):
    data, archive, fetch, run, check = evidence(tmp_path)
    if failure == 'absent': data = None
    elif failure == 'malformed': data = []
    elif failure == 'tag': data['tag'] = 'v9.0.0'
    elif failure == 'sha': data['source_sha'] = 'b' * 40
    elif failure == 'zip': archive.write_bytes(b'corrupt')
    elif failure == 'checks': data['checks']['windows'] = 'skipped'
    elif failure == 'check-hash': check['output']['summary'] = '0' * 64
    elif failure == 'workflow': run['path'] = '.github/workflows/other.yml'
    elif failure == 'run': run['conclusion'] = 'failure'
    elif failure == 'app': check['app']['slug'] = 'other-app'
    elif failure == 'attempt': check['external_id'] = 'quality:42:2'
    elif failure == 'hardware': data['hardware']['source_sha'] = 'b' * 40
    with pytest.raises(ValueError):
        quality.authenticate(data, 'v3.3.1', 'coldmoth/ma2-panel', fetch)
        quality.verify_archive(archive, data, 'v3.3.1')


def test_wrong_embedded_sha_even_with_matching_zip_hash(tmp_path):
    data, archive, _, _, _ = evidence(tmp_path)
    release.write_zip({'source_identity.py': b'# source-sha: ' + b'b' * 40}, archive)
    data['assets']['ma2-panel-update.zip'] = hashlib.sha256(archive.read_bytes()).hexdigest()
    for k in ('hardware', 'review'): data[k]['assets'] = data['assets'].copy()
    with pytest.raises(ValueError, match='SHA программы'):
        quality.verify_archive(archive, data, data['tag'])


def test_stable_without_quality_is_not_offered(monkeypatch):
    from ma2panel import browser_update as bu
    from ma2panel import update
    from test_online_update import metadata
    monkeypatch.setattr(bu, 'fetch_json', lambda _: metadata())
    with pytest.raises(update.UpdateError, match='качеств'):
        bu.latest()


def test_project_version_only_keeps_real_330_runtime_compatible(tmp_path):
    root = Path(__file__).resolve().parents[1]
    raw = (root/'uv.lock').read_text()
    (tmp_path/'uv.lock').write_text(raw)
    previous = {'python':'3.12','lock_sha256':'16fc35a00aaa556f2547fa51222cf8e84adf7638e8818169dad4434358f4a592'}
    assert release.runtime(tmp_path) == previous
    import re
    changed = re.sub(r'(name = "ma2-panel"\nversion = ")[^"]+(")', r'\g<1>3.3.9\2', raw)
    assert changed != raw
    (tmp_path/'uv.lock').write_text(changed)
    assert release.runtime(tmp_path) == previous
    (tmp_path/'uv.lock').write_text(raw.replace('version = "0.143.3"','version = "0.143.4"'))
    assert release.runtime(tmp_path) != previous


def test_updater_only_offers_github_authenticated_exact_tag(tmp_path,monkeypatch):
    from ma2panel import browser_update as bu
    data,archive,fetch,run,check=evidence(tmp_path)
    prefix=f'https://github.com/{bu.REPO}/releases/download/{data["tag"]}/'
    metadata={'tag_name':data['tag'],'draft':False,'prerelease':False,'body':'Notes',
              'assets':[{'name':n,'browser_download_url':prefix+n} for n in ('ma2-panel-update.zip','ma2-panel-update.zip.sha256',quality.NAME)]}
    def network(url):
        if url==bu.API:return metadata
        if url==prefix+quality.NAME:return data
        if url.endswith('/commits/'+data['tag']):return {'sha':data['source_sha']}
        return fetch(url)
    monkeypatch.setattr(bu,'fetch_json',network)
    assert bu.latest()['quality']==data
    check['output']['summary']='f'*64
    from ma2panel import update
    with pytest.raises(update.UpdateError,match='качеств'):bu.latest()


def test_verified_package_is_rechecked_before_install_after_tamper(tmp_path,monkeypatch):
    from ma2panel import browser_update as bu
    from ma2panel import update
    data,archive,fetch,_,_=evidence(tmp_path)
    root=tmp_path/'installed';root.mkdir();(root/'bridge.py').write_bytes(b'old code');(root/'VERSION').write_text('3.3.0')
    archive.write_bytes(b'changed after preparation')
    monkeypatch.setattr(bu.release_quality,'authenticate',lambda *a:data)
    monkeypatch.setattr(bu,'launch',lambda spec:None)
    monkeypatch.setattr(bu,'health',lambda *a:None)
    monkeypatch.setattr(update,'install',lambda *a,**kw:pytest.fail('invalid stable archive must never reach install'))
    bu.apply({'root':str(root),'id':'a'*32,'archive':str(archive),'version':'3.3.1','quality':data,'stable_tag':data['tag']})
    assert (root/'bridge.py').read_bytes()==b'old code'
    assert bu.status(root)['phase']!='completed'


@pytest.mark.parametrize('bad',[None,[],{'slug':'other-app'}])
def test_malformed_or_substituted_github_app_is_not_trusted(tmp_path,bad):
    data,_,fetch,_,check=evidence(tmp_path);check['app']=bad
    with pytest.raises(ValueError):quality.authenticate(data,data['tag'],'coldmoth/ma2-panel',fetch)


def test_github_canonical_stable_check_link_requires_matching_suite(tmp_path):
    data, archive, fetch, run, check = evidence(tmp_path)
    run['check_suite_id'] = 17
    check.update(id=29, check_suite={'id': 17}, details_url='https://github.com/coldmoth/ma2-panel/runs/29')
    assert quality.authenticate(data, data['tag'], 'coldmoth/ma2-panel', fetch) == data
    check['check_suite']['id'] = 18
    with pytest.raises(ValueError): quality.authenticate(data, data['tag'], 'coldmoth/ma2-panel', fetch)
