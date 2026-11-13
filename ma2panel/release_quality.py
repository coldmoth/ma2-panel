"""Stable evidence anchored in a successful GitHub promotion check, not a ZIP checksum.

Trust boundary: HTTPS, the repository's GitHub Actions app and reviewed workflows.
No local signing key or additional runtime dependencies.
"""
import hashlib
import json
import re
import zipfile

REQUIRED = ('python', 'node', 'chromium', 'webkit', 'e2e', 'windows', 'delivered',
            'first-run', 'update-rollback', 'migration', 'archives', 'docs', 'reproducible')
NAME = 'stable-quality.json'
CHECK = 'Stable quality evidence'


def fingerprint(report):
    return hashlib.sha256(json.dumps(report, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def validate(report, tag):
    if not isinstance(report, dict) or report.get('schema') != 1 or report.get('channel') != 'stable' or report.get('tag') != tag or not isinstance(tag, str) or not re.fullmatch(r'v?\d+\.\d+\.\d+', tag):
        raise ValueError('Нет свидетельства качества stable-релиза')
    sha = report.get('source_sha')
    if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('Некорректный SHA свидетельства')
    checks, assets = report.get('checks'), report.get('assets')
    if not isinstance(checks, dict) or any(checks.get(k) != 'success' for k in REQUIRED):
        raise ValueError('Обязательные проверки качества не пройдены')
    if not isinstance(assets, dict) or 'ma2-panel-update.zip' not in assets or any(not isinstance(h, str) or not re.fullmatch('[0-9a-f]{64}', h) for h in assets.values()):
        raise ValueError('Нет проверенного ZIP')
    if report.get('blockers') != [] or report.get('field_v3') != 'confirmed':
        raise ValueError('Приёмка площадки или оценка блокеров отсутствует')
    for name in ('review', 'hardware'):
        receipt = report.get(name)
        if not isinstance(receipt, dict) or receipt.get('status') != 'success' or receipt.get('source_sha') != sha or receipt.get('assets') != assets:
            raise ValueError('Нет приёмки ' + name)
    if any(type(report.get(k)) is not int or report[k] < 1 for k in ('promotion_run', 'promotion_attempt')):
        raise ValueError('Нет идентификатора promotion')
    return report


def authenticate(report, tag, repo, fetch):
    validate(report, tag)
    sha, ident, attempt = report['source_sha'], report['promotion_run'], report['promotion_attempt']
    api = f'https://api.github.com/repos/{repo}'
    run = fetch(f'{api}/actions/runs/{ident}/attempts/{attempt}')
    if not isinstance(run, dict) or (run.get('head_sha'), run.get('conclusion'), run.get('event'), run.get('path'), (run.get('repository') or {}).get('full_name')) != (sha, 'success', 'workflow_dispatch', '.github/workflows/promote.yml', repo):
        raise ValueError('Не подтверждён успешный promotion этого SHA')
    records = fetch(f'{api}/commits/{sha}/check-runs?check_name=Stable%20quality%20evidence&filter=all&per_page=100')
    if not isinstance(records, dict) or type(records.get('total_count')) is not int or records['total_count'] > 100 or not isinstance(records.get('check_runs'), list):
        raise ValueError('Неполные свидетельства GitHub checks')
    expected = fingerprint(report)
    for c in records['check_runs']:
        if (isinstance(c, dict) and c.get('name') == CHECK and c.get('head_sha') == sha and c.get('conclusion') == 'success'
                and isinstance(c.get('app'), dict) and c['app'].get('slug') == 'github-actions'
                and c.get('external_id') == f'quality:{ident}:{attempt}'
                and c.get('details_url') == f'https://github.com/{repo}/actions/runs/{ident}/attempts/{attempt}'
                and isinstance(c.get('output'), dict) and c['output'].get('summary') == expected):
            return report
    raise ValueError('Свидетельство подменено или не подтверждено GitHub Actions')


def verify_archive(archive, report, tag):
    validate(report, tag)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != report['assets']['ma2-panel-update.zip']:
        raise ValueError('ZIP не соответствует свидетельству качества')
    with zipfile.ZipFile(archive) as source:
        if source.read('source_identity.py').decode('ascii').removeprefix('# source-sha: ').strip() != report['source_sha']:
            raise ValueError('SHA программы не соответствует свидетельству качества')
