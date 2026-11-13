"""Fail-closed candidate checks. Does not publish, build or mutate an installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ma2panel.release_quality import REQUIRED
from ma2panel import release


def hashes(assets):
    result = {}
    for path in assets:
        path = Path(path)
        if not path.is_file() or path.is_symlink() or path.name in result:
            raise ValueError('Missing, duplicate or symlinked candidate asset')
        result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def evaluate(report, sha, assets, *, stable=False):
    if not isinstance(report, dict) or report.get('schema') != 1:
        return ['Missing or unsupported quality report']
    errors = []
    if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{40,64}', sha) or report.get('source_sha') != sha:
        errors.append('Source SHA mismatch')
    checks = report.get('checks')
    if not isinstance(checks, dict):
        errors.append('Missing mandatory checks')
    else:
        errors.extend('Required check: ' + name for name in REQUIRED if checks.get(name) != 'success')
    try:
        actual = hashes(assets)
    except (ValueError, OSError):
        actual = {}
    if not actual or actual != report.get('assets'):
        errors.append('Tested ZIP identity mismatch or missing asset')
    if not isinstance(report.get('blockers'), list) or report['blockers']:
        errors.append('Missing blocker assessment or known blocking regression')
    if stable:
        for name in ('hardware', 'review'):
            receipt = report.get(name)
            if not isinstance(receipt, dict) or receipt.get('status') != 'success' or receipt.get('source_sha') != sha or receipt.get('assets') != actual:
                errors.append('Missing current ' + name + ' acceptance')
        if report.get('field_v3') != 'confirmed':
            errors.append('Site FixtureType/membership evidence is incomplete (equivalent V2 accepted)')
    return errors


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=('record', 'verify'))
    p.add_argument('--report', required=True, type=Path)
    p.add_argument('--sha', required=True)
    p.add_argument('--asset', action='append', type=Path, default=[])
    p.add_argument('--checks-json', default='{}')
    p.add_argument('--stable', action='store_true')
    p.add_argument('--acceptance', type=Path)
    args = p.parse_args()
    try:
        if args.operation == 'record':
            current = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
            dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
            untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], text=True).splitlines()
            extra_source = [n for n in untracked if Path(n).parts[0] not in ('candidate', 'evidence', 'test-results')]
            if current != args.sha or dirty or extra_source:
                raise ValueError('Record only a clean checked-out source SHA')
            report = {'schema': 1, 'source_sha': current, 'checks': json.loads(args.checks_json),
                      'assets': hashes(args.asset), 'blockers': [], 'field_v3': 'missing', 'hardware': None, 'review': None}
            report['runtime'] = release.runtime(Path.cwd())
            if os.environ.get('GITHUB_RUN_ID') and os.environ.get('GITHUB_RUN_ATTEMPT'):
                report.update(candidate_run=int(os.environ['GITHUB_RUN_ID']), candidate_attempt=int(os.environ['GITHUB_RUN_ATTEMPT']))
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        else:
            report = json.loads(args.report.read_text(encoding='utf-8'))
        if args.acceptance:
            receipt = json.loads(args.acceptance.read_text(encoding='utf-8'))
            if receipt.get('source_sha') != args.sha or receipt.get('assets') != report.get('assets'):
                raise ValueError('Acceptance belongs to a different candidate')
            report = {**report, **{k: receipt.get(k) for k in ('hardware', 'review', 'field_v3')}}
        errors = evaluate(report, args.sha, args.asset, stable=args.stable)
        print(json.dumps({'ready': not errors, 'channel': 'stable' if args.stable else 'rc', 'errors': errors}))
        return bool(errors)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({'ready': False, 'error': str(error)}))
        return 1


if __name__ == '__main__': raise SystemExit(main())
