"""Produce the exact stable proof and GitHub check request after gate verification."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ma2panel import release_quality as quality
from scripts.quality_gate import evaluate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sha', required=True); p.add_argument('--tag', required=True)
    p.add_argument('--run', type=int, required=True); p.add_argument('--attempt', type=int, required=True)
    p.add_argument('--repo', required=True); p.add_argument('--asset', type=Path, action='append', required=True)
    p.add_argument('--report', type=Path, required=True); p.add_argument('--acceptance', type=Path, required=True)
    args = p.parse_args()
    report = json.loads(args.report.read_text()); receipt = json.loads(args.acceptance.read_text())
    if receipt.get('source_sha') != args.sha or receipt.get('assets') != report.get('assets'):
        raise ValueError('Acceptance belongs to another candidate')
    report.update({k: receipt.get(k) for k in ('hardware', 'review', 'field_v3')})
    errors = evaluate(report, args.sha, args.asset, stable=True)
    if errors: raise ValueError('; '.join(errors))
    report.update(channel='stable', tag=args.tag, promotion_run=args.run, promotion_attempt=args.attempt)
    quality.validate(report, args.tag)
    Path(quality.NAME).write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    request = {'name': quality.CHECK, 'head_sha': args.sha, 'status': 'completed', 'conclusion': 'success',
               'external_id': f'quality:{args.run}:{args.attempt}',
               'details_url': f'https://github.com/{args.repo}/actions/runs/{args.run}/attempts/{args.attempt}',
               'output': {'title': quality.CHECK, 'summary': quality.fingerprint(report)}}
    Path('stable-check.json').write_text(json.dumps(request) + '\n')


if __name__ == '__main__': main()
